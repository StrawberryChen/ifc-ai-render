#!/usr/bin/env python3
"""Run several depth-controlled prompts while loading Qwen-Image only once."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from generate_qwen_depth import BASE_MODEL, CONTROL_MODEL, build_pipeline, prepare_depth


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量运行Qwen建筑深度控制基线实验")
    parser.add_argument("--depth", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/depth_baseline"))
    parser.add_argument("--width", type=int, default=1328)
    parser.add_argument("--height", type=int, default=1328)
    parser.add_argument("--no-low-vram", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("实验配置必须是非空JSON数组")
    names: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not all(key in case for key in ("name", "seed", "prompt")):
            raise ValueError("每个实验项必须包含name、seed和prompt")
        if not str(case["name"]).replace("_", "").isalnum():
            raise ValueError(f"非法实验名称: {case['name']}")
        if case["name"] in names:
            raise ValueError(f"重复实验名称: {case['name']}")
        names.add(case["name"])
    return cases


def main() -> int:
    args = parse_args()
    cases = load_cases(args.config)
    depth = prepare_depth(args.depth, args.width, args.height)
    print(f"已验证深度图 {depth.size}，共 {len(cases)} 个实验方案")
    if args.validate_only:
        return 0

    from diffsynth.pipelines.qwen_image import ControlNetInput

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pipe = build_pipeline(low_vram=not args.no_low_vram)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_model": BASE_MODEL,
        "control_model": CONTROL_MODEL,
        "depth": str(args.depth),
        "resolution": [args.width, args.height],
        "cases": [],
    }
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] 生成 {case['name']} (seed={case['seed']})")
        image = pipe(
            case["prompt"],
            seed=int(case["seed"]),
            blockwise_controlnet_inputs=[ControlNetInput(image=depth)],
        )
        output = args.output_dir / f"{index:02d}_{case['name']}.png"
        image.save(output)
        manifest["cases"].append({**case, "output": str(output)})
        print(f"已保存: {output}")
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
