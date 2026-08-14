#!/usr/bin/env python3
"""Configuration-driven SDXL Img2Img baseline for architectural render enhancement."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = ["model", "input", "prompt", "inference", "runtime", "output"]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"配置缺少字段: {missing}")
    strengths = config["inference"].get("strengths", [])
    if not strengths or any(not 0 < float(value) <= 1 for value in strengths):
        raise ValueError("inference.strengths 必须是 (0, 1] 范围内的非空数组")
    for dimension in ("width", "height"):
        value = int(config["input"][dimension])
        if value < 512 or value % 8:
            raise ValueError(f"input.{dimension} 必须不小于512且为8的倍数")
    if int(config["inference"]["num_inference_steps"]) < 1:
        raise ValueError("num_inference_steps 必须大于0")
    controlnet = config.get("controlnet")
    if controlnet and controlnet.get("enabled", True):
        if not controlnet.get("model_id") or not controlnet.get("image"):
            raise ValueError("启用 ControlNet 时必须提供 controlnet.model_id 和 controlnet.image")
        scale = float(controlnet.get("conditioning_scale", 1.0))
        start = float(controlnet.get("guidance_start", 0.0))
        end = float(controlnet.get("guidance_end", 1.0))
        if scale < 0 or not 0 <= start < end <= 1:
            raise ValueError("ControlNet 参数必须满足 scale>=0 且 0<=guidance_start<guidance_end<=1")
    return config


def resolve_path(value: str, repo_root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else repo_root / path


def resize_cover(image: Any, width: int, height: int) -> Any:
    from PIL import Image

    scale = max(width / image.width, height / image.height)
    resized = image.resize((math.ceil(image.width * scale), math.ceil(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def prepare_image(path: Path, width: int, height: int, resize_mode: str) -> Any:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    if image.size == (width, height):
        return image
    if resize_mode == "stretch":
        return image.resize((width, height), Image.Resampling.LANCZOS)
    if resize_mode == "cover":
        return resize_cover(image, width, height)
    raise ValueError(f"不支持的 resize_mode: {resize_mode}")


def prepare_control_image(
    path: Path,
    width: int,
    height: int,
    resize_mode: str,
    invert: bool = False,
) -> Any:
    """Load a precomputed RGB control map and keep it pixel-aligned with the init image."""
    from PIL import ImageOps

    image = prepare_image(path, width, height, resize_mode)
    return ImageOps.invert(image) if invert else image


def build_pipeline(config: dict[str, Any], cache_dir: Path | None) -> Any:
    import torch
    from diffusers import (
        ControlNetModel,
        DPMSolverMultistepScheduler,
        StableDiffusionXLControlNetImg2ImgPipeline,
        StableDiffusionXLImg2ImgPipeline,
    )

    dtype_name = config["model"].get("dtype", "float16")
    dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16}[dtype_name]
    kwargs: dict[str, Any] = {
        "torch_dtype": dtype,
        "use_safetensors": bool(config["model"].get("use_safetensors", True)),
    }
    if config["model"].get("variant"):
        kwargs["variant"] = config["model"]["variant"]
    if cache_dir:
        kwargs["cache_dir"] = str(cache_dir)
    controlnet_config = config.get("controlnet")
    if controlnet_config and controlnet_config.get("enabled", True):
        controlnet_kwargs: dict[str, Any] = {"torch_dtype": dtype, "use_safetensors": True}
        if cache_dir:
            controlnet_kwargs["cache_dir"] = str(cache_dir)
        controlnet = ControlNetModel.from_pretrained(controlnet_config["model_id"], **controlnet_kwargs)
        pipeline = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
            config["model"]["id"], controlnet=controlnet, **kwargs
        )
    else:
        pipeline = StableDiffusionXLImg2ImgPipeline.from_pretrained(config["model"]["id"], **kwargs)
    if config["inference"].get("scheduler") == "dpmpp_2m_karras":
        pipeline.scheduler = DPMSolverMultistepScheduler.from_config(
            pipeline.scheduler.config,
            algorithm_type="dpmsolver++",
            use_karras_sigmas=True,
        )
    if config["runtime"].get("enable_vae_slicing", True):
        pipeline.enable_vae_slicing()
    if config["runtime"].get("enable_model_cpu_offload", False):
        pipeline.enable_model_cpu_offload()
    else:
        pipeline = pipeline.to(config["runtime"].get("device", "cuda"))
    return pipeline


def run(config: dict[str, Any], repo_root: Path, cache_dir: Path | None, input_override: Path | None, output_override: Path | None) -> list[Path]:
    import torch

    input_path = input_override or resolve_path(config["input"]["image"], repo_root)
    output_dir = output_override or resolve_path(config["output"]["directory"], repo_root)
    if not input_path.is_file():
        raise FileNotFoundError(f"找不到输入图: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    image = prepare_image(
        input_path,
        int(config["input"]["width"]),
        int(config["input"]["height"]),
        config["input"].get("resize_mode", "cover"),
    )
    controlnet_config = config.get("controlnet")
    control_image = None
    control_path = None
    if controlnet_config and controlnet_config.get("enabled", True):
        control_path = resolve_path(controlnet_config["image"], repo_root)
        if not control_path.is_file():
            raise FileNotFoundError(f"找不到 ControlNet 条件图: {control_path}")
        control_image = prepare_control_image(
            control_path,
            int(config["input"]["width"]),
            int(config["input"]["height"]),
            config["input"].get("resize_mode", "cover"),
            bool(controlnet_config.get("invert_image", False)),
        )
    pipeline = build_pipeline(config, cache_dir)
    seed = int(config["inference"]["seed"])
    steps = int(config["inference"]["num_inference_steps"])
    generated: list[Path] = []
    records = []
    for strength_value in config["inference"]["strengths"]:
        strength = float(strength_value)
        generator = torch.Generator(device=config["runtime"].get("device", "cuda")).manual_seed(seed)
        pipeline_args: dict[str, Any] = {
            "prompt": config["prompt"],
            "negative_prompt": config.get("negative_prompt", ""),
            "image": image,
            "strength": strength,
            "num_inference_steps": steps,
            "guidance_scale": float(config["inference"]["guidance_scale"]),
            "generator": generator,
        }
        if control_image is not None:
            pipeline_args.update({
                "control_image": control_image,
                "controlnet_conditioning_scale": float(controlnet_config.get("conditioning_scale", 1.0)),
                "control_guidance_start": float(controlnet_config.get("guidance_start", 0.0)),
                "control_guidance_end": float(controlnet_config.get("guidance_end", 1.0)),
            })
        result = pipeline(
            **pipeline_args
        ).images[0]
        result_path = output_dir / f"sdcc.strength_{strength:.2f}.seed_{seed}.png"
        result.save(result_path)
        generated.append(result_path)
        records.append({
            "strength": strength,
            "nominal_steps": steps,
            "approximate_denoising_steps": max(1, round(steps * strength)),
            "seed": seed,
            "file": result_path.name,
        })
    if config["output"].get("save_input_copy", True):
        image.save(output_dir / "input.material.png")
        if control_image is not None:
            control_image.save(output_dir / "input.canny.png")
    if config["output"].get("save_metadata", True):
        metadata = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model": config["model"],
            "input": str(input_path),
            "controlnet": config.get("controlnet"),
            "control_image": str(control_path) if control_path else None,
            "prompt": config["prompt"],
            "negative_prompt": config.get("negative_prompt", ""),
            "inference": config["inference"],
            "results": records,
        }
        (output_dir / "run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行SDXL建筑材质增强基线")
    parser.add_argument("--config", type=Path, default=Path("configs/sdxl_img2img_baseline.json"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(args.config.resolve())
    input_path = args.input.resolve() if args.input else resolve_path(config["input"]["image"], repo_root)
    print(json.dumps({
        "model": config["model"]["id"],
        "input": str(input_path),
        "controlnet": config.get("controlnet"),
        "resolution": [config["input"]["width"], config["input"]["height"]],
        "strengths": config["inference"]["strengths"],
        "steps": config["inference"]["num_inference_steps"],
        "seed": config["inference"]["seed"],
    }, ensure_ascii=False, indent=2))
    if args.validate_only:
        if not input_path.is_file():
            raise FileNotFoundError(f"找不到输入图: {input_path}")
        controlnet_config = config.get("controlnet")
        if controlnet_config and controlnet_config.get("enabled", True):
            control_path = resolve_path(controlnet_config["image"], repo_root)
            if not control_path.is_file():
                raise FileNotFoundError(f"找不到 ControlNet 条件图: {control_path}")
        return 0
    input_override = args.input.resolve() if args.input else None
    output_override = args.output_dir.resolve() if args.output_dir else None
    cache_dir = args.cache_dir.resolve() if args.cache_dir else None
    outputs = run(config, repo_root, cache_dir, input_override, output_override)
    for path in outputs:
        print(f"生成完成: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
