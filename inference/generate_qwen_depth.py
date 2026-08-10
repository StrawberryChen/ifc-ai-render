#!/usr/bin/env python3
"""Generate an architectural concept image from an IFC-derived depth map."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


BASE_MODEL = "Qwen/Qwen-Image"
CONTROL_MODEL = "DiffSynth-Studio/Qwen-Image-Blockwise-ControlNet-Depth"


def valid_resolution(value: str) -> int:
    size = int(value)
    if size < 256 or size > 2048 or size % 16:
        raise argparse.ArgumentTypeError("分辨率必须在256–2048之间且为16的倍数")
    return size


def prepare_depth(path: Path, width: int, height: int) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(f"找不到深度图: {path}")
    with Image.open(path) as source:
        # Keep the 16-bit Blender depth ordering, then expose it as an RGB control image.
        if source.mode in {"I;16", "I", "F"}:
            extrema = source.getextrema()
            low, high = float(extrema[0]), float(extrema[1])
            if high <= low:
                raise ValueError("深度图没有有效的明暗变化")
            scale = 255.0 / (high - low)
            offset = -low * scale
            source = source.point(lambda p: p * scale + offset).convert("L")
        else:
            source = source.convert("L")
        return source.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")


def build_pipeline(low_vram: bool):
    import torch
    from diffsynth.pipelines.qwen_image import ModelConfig, QwenImagePipeline

    if not torch.cuda.is_available():
        raise RuntimeError("未检测到CUDA GPU；请在Colab中选择A100 GPU运行时")

    extra = {}
    pipeline_extra = {}
    if low_vram:
        extra = {
            "offload_dtype": "disk",
            "offload_device": "disk",
            "onload_dtype": torch.float8_e4m3fn,
            "onload_device": "cpu",
            "preparing_dtype": torch.float8_e4m3fn,
            "preparing_device": "cuda",
            "computation_dtype": torch.bfloat16,
            "computation_device": "cuda",
        }
        pipeline_extra["vram_limit"] = torch.cuda.mem_get_info("cuda")[1] / (1024**3) - 0.5

    configs = [
        ModelConfig(model_id=BASE_MODEL, origin_file_pattern="transformer/diffusion_pytorch_model*.safetensors", **extra),
        ModelConfig(model_id=BASE_MODEL, origin_file_pattern="text_encoder/model*.safetensors", **extra),
        ModelConfig(model_id=BASE_MODEL, origin_file_pattern="vae/diffusion_pytorch_model.safetensors", **extra),
        ModelConfig(model_id=CONTROL_MODEL, origin_file_pattern="model.safetensors", **extra),
    ]
    return QwenImagePipeline.from_pretrained(
        torch_dtype=torch.bfloat16,
        device="cuda",
        model_configs=configs,
        tokenizer_config=ModelConfig(model_id=BASE_MODEL, origin_file_pattern="tokenizer/"),
        **pipeline_extra,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IFC深度图 -> Qwen建筑效果图")
    parser.add_argument("--depth", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", type=Path, default=Path("outputs/generated/qwen-depth.png"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--width", type=valid_resolution, default=1328)
    parser.add_argument("--height", type=valid_resolution, default=1328)
    parser.add_argument("--no-low-vram", action="store_true", help="禁用官方磁盘/CPU分层卸载")
    parser.add_argument("--validate-only", action="store_true", help="只检查输入，不加载模型")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    depth = prepare_depth(args.depth, args.width, args.height)
    print(f"深度条件已就绪: {depth.size[0]}x{depth.size[1]}")
    if args.validate_only:
        return 0

    from diffsynth.pipelines.qwen_image import ControlNetInput

    pipe = build_pipeline(low_vram=not args.no_low_vram)
    result = pipe(
        args.prompt,
        seed=args.seed,
        blockwise_controlnet_inputs=[ControlNetInput(image=depth)],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output)
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_model": BASE_MODEL,
        "control_model": CONTROL_MODEL,
        "depth": str(args.depth),
        "prompt": args.prompt,
        "seed": args.seed,
        "width": args.width,
        "height": args.height,
        "low_vram": not args.no_low_vram,
    }
    args.output.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成完成: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
