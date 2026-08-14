#!/usr/bin/env python3
"""Two-stage architectural scene generation: masked environment inpaint, then Canny refinement."""

from __future__ import annotations

import argparse
import copy
import gc
import json
from pathlib import Path
from typing import Any

from generate_sdxl_img2img import load_config as load_refine_config
from generate_sdxl_img2img import prepare_image, resolve_path, run as run_refinement


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = ["input", "inpaint", "refinement", "runtime", "output"]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"配置缺少字段: {missing}")
    strength = float(config["inpaint"].get("strength", 0.99))
    if not 0 < strength < 1:
        raise ValueError("inpaint.strength 必须在 (0, 1) 范围内")
    if int(config["input"].get("mask_dilation", 0)) < 0:
        raise ValueError("input.mask_dilation 不得小于0")
    return config


def prepare_environment_mask(
    path: Path,
    width: int,
    height: int,
    resize_mode: str,
    white_is_protected: bool,
    dilation: int,
    blur: float,
) -> Any:
    """Return an inpaint mask where white pixels are editable environment."""
    from PIL import Image, ImageFilter, ImageOps

    mask = Image.open(path).convert("L")
    if mask.size != (width, height):
        rgb = prepare_image(path, width, height, resize_mode)
        mask = rgb.convert("L")
    mask = mask.point(lambda value: 255 if value >= 128 else 0)
    if white_is_protected:
        if dilation > 0:
            kernel = dilation * 2 + 1
            mask = mask.filter(ImageFilter.MaxFilter(kernel))
        mask = ImageOps.invert(mask)
    if blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur))
    return mask


def build_inpaint_pipeline(config: dict[str, Any], cache_dir: Path | None) -> Any:
    import torch
    from diffusers import AutoPipelineForInpainting, DPMSolverMultistepScheduler

    dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16}[
        config["inpaint"].get("dtype", "float16")
    ]
    kwargs: dict[str, Any] = {
        "torch_dtype": dtype,
        "use_safetensors": True,
    }
    if config["inpaint"].get("variant"):
        kwargs["variant"] = config["inpaint"]["variant"]
    if cache_dir:
        kwargs["cache_dir"] = str(cache_dir)
    pipeline = AutoPipelineForInpainting.from_pretrained(config["inpaint"]["model_id"], **kwargs)
    pipeline.scheduler = DPMSolverMultistepScheduler.from_config(
        pipeline.scheduler.config, algorithm_type="dpmsolver++", use_karras_sigmas=True
    )
    if config["runtime"].get("enable_vae_slicing", True):
        pipeline.enable_vae_slicing()
    return pipeline.to(config["runtime"].get("device", "cuda"))


def run(config: dict[str, Any], repo_root: Path, cache_dir: Path | None) -> list[Path]:
    import torch
    from PIL import Image

    width = int(config["input"]["width"])
    height = int(config["input"]["height"])
    resize_mode = config["input"].get("resize_mode", "cover")
    image_path = resolve_path(config["input"]["image"], repo_root)
    mask_path = resolve_path(config["input"]["building_mask"], repo_root)
    if not image_path.is_file() or not mask_path.is_file():
        raise FileNotFoundError(f"找不到输入图或建筑遮罩: {image_path}, {mask_path}")
    output_dir = resolve_path(config["output"]["directory"], repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    image = prepare_image(image_path, width, height, resize_mode)
    mask = prepare_environment_mask(
        mask_path, width, height, resize_mode,
        bool(config["input"].get("mask_white_is_protected", True)),
        int(config["input"].get("mask_dilation", 8)),
        float(config["input"].get("mask_blur", 4)),
    )
    mask.save(output_dir / "input.environment_mask.png")

    pipeline = build_inpaint_pipeline(config, cache_dir)
    device = config["runtime"].get("device", "cuda")
    seed = int(config["inpaint"]["seed"])
    scene = pipeline(
        prompt=config["inpaint"]["prompt"],
        negative_prompt=config["inpaint"].get("negative_prompt", ""),
        image=image,
        mask_image=mask,
        strength=float(config["inpaint"].get("strength", 0.99)),
        num_inference_steps=int(config["inpaint"].get("num_inference_steps", 30)),
        guidance_scale=float(config["inpaint"].get("guidance_scale", 7.0)),
        generator=torch.Generator(device=device).manual_seed(seed),
    ).images[0]
    stage1_path = output_dir / "stage1.environment.png"
    scene.save(stage1_path)

    del pipeline
    gc.collect()
    torch.cuda.empty_cache()

    refinement_path = resolve_path(config["refinement"]["config"], repo_root)
    refine_config = load_refine_config(refinement_path)
    refine_config = copy.deepcopy(refine_config)
    refine_config["input"]["image"] = str(stage1_path)
    refine_config["output"]["directory"] = str(output_dir / "stage2_refined")
    for key, value in config["refinement"].get("overrides", {}).items():
        if key in {"prompt", "negative_prompt"}:
            refine_config[key] = value
        elif key in refine_config["inference"]:
            refine_config["inference"][key] = value
        elif key in refine_config["controlnet"]:
            refine_config["controlnet"][key] = value
    outputs = run_refinement(refine_config, repo_root, cache_dir, stage1_path, output_dir / "stage2_refined")

    metadata = {
        "input": str(image_path),
        "building_mask": str(mask_path),
        "stage1": str(stage1_path),
        "stage2": [str(path) for path in outputs],
        "inpaint": config["inpaint"],
        "refinement": config["refinement"],
    }
    (output_dir / "two_stage_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return [stage1_path, *outputs]


def main() -> int:
    parser = argparse.ArgumentParser(description="SDXL建筑场景两阶段生成")
    parser.add_argument("--config", type=Path, default=Path("configs/sdxl_scene_two_stage.json"))
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(args.config.resolve())
    for field in ("image", "building_mask"):
        path = resolve_path(config["input"][field], repo_root)
        if not path.is_file():
            raise FileNotFoundError(f"找不到 {field}: {path}")
    refinement_path = resolve_path(config["refinement"]["config"], repo_root)
    load_refine_config(refinement_path)
    print(json.dumps({
        "input": config["input"],
        "inpaint_model": config["inpaint"]["model_id"],
        "refinement_config": str(refinement_path),
        "output": config["output"]["directory"],
    }, ensure_ascii=False, indent=2))
    if args.validate_only:
        return 0
    outputs = run(config, repo_root, args.cache_dir.resolve() if args.cache_dir else None)
    for output in outputs:
        print(f"生成完成: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
