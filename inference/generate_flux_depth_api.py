#!/usr/bin/env python3
"""Generate an image with fal.ai FLUX Depth from a Blender depth pass."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


ENDPOINT = "fal-ai/flux-control-lora-depth"


def prepare_fal_depth(source_path: Path, output_path: Path, invert: bool = True) -> Image.Image:
    """Normalize non-zero camera distance to an 8-bit FLUX control image."""
    if not source_path.is_file():
        raise FileNotFoundError(f"找不到深度图: {source_path}")
    with Image.open(source_path) as source:
        values = list(source.convert("I").get_flattened_data())
        foreground = [value for value in values if value > 0]
        if len(set(foreground)) < 2:
            raise ValueError("深度图没有足够的有效距离层次")
        low, high = min(foreground), max(foreground)
        scale = 255.0 / (high - low)
        normalized = []
        for value in values:
            if value <= 0:
                normalized.append(0)
                continue
            mapped = round((value - low) * scale)
            normalized.append(255 - mapped if invert else mapped)
        depth = Image.new("L", source.size)
        depth.putdata(normalized)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    depth.save(output_path)
    return depth


def build_arguments(args: argparse.Namespace, image_url: str) -> dict:
    return {
        "prompt": args.prompt,
        "control_lora_image_url": image_url,
        "preprocess_depth": False,
        "control_lora_strength": args.control_strength,
        "image_size": {"width": args.width, "height": args.height},
        "num_inference_steps": args.steps,
        "guidance_scale": args.guidance,
        "seed": args.seed,
        "num_images": 1,
        "enable_safety_checker": True,
        "output_format": "png",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="调用fal.ai FLUX Depth API生成建筑效果图")
    parser.add_argument("--depth", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", type=Path, default=Path("outputs/fal_flux_depth/result.png"))
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=28)
    parser.add_argument("--guidance", type=float, default=3.5)
    parser.add_argument("--control-strength", type=float, default=1.0)
    parser.add_argument("--no-invert-depth", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    for name in ("width", "height"):
        value = getattr(args, name)
        if value < 512 or value > 1536 or value % 16:
            raise ValueError(f"{name}必须在512–1536之间且为16的倍数")
    if not 1 <= args.steps <= 50:
        raise ValueError("steps必须在1–50之间")
    if not 0 <= args.control_strength <= 2:
        raise ValueError("control-strength必须在0–2之间")


def main() -> int:
    args = parse_args()
    validate_args(args)
    control_path = args.output.with_name(f"{args.output.stem}.control-depth.png")
    depth = prepare_fal_depth(args.depth, control_path, invert=not args.no_invert_depth)
    print(f"控制图已就绪: {control_path.resolve()} ({depth.size[0]}x{depth.size[1]})")
    if args.validate_only:
        return 0
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError("未设置FAL_KEY环境变量")

    import fal_client

    print("正在上传深度控制图…")
    image_url = fal_client.upload_file(control_path)
    request_args = build_arguments(args, image_url)

    def on_update(status) -> None:
        for log in getattr(status, "logs", None) or []:
            message = log.get("message") if isinstance(log, dict) else getattr(log, "message", None)
            if message:
                print(message)

    print(f"正在调用 {ENDPOINT}…")
    result = fal_client.subscribe(
        ENDPOINT,
        arguments=request_args,
        with_logs=True,
        on_queue_update=on_update,
        client_timeout=600,
    )
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError(f"API未返回有效图片: {result}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(images[0]["url"], args.output)
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": "fal.ai",
        "endpoint": ENDPOINT,
        "source_depth": str(args.depth),
        "control_depth": str(control_path),
        "depth_inverted": not args.no_invert_depth,
        "request": {**request_args, "control_lora_image_url": "<uploaded>"},
        "response": result,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"生成完成: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
