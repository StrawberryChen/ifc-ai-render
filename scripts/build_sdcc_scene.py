#!/usr/bin/env python3
"""Run the SDCC Blender renderer from a normal Python shell."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


DEFAULT_BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成SDCC材质图和对齐的控制图")
    parser.add_argument("--source-dir", type=Path, default=Path("data/sdcc"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/sdcc"))
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=768)
    args = parser.parse_args()
    script = Path(__file__).with_name("render_sdcc_scene.py")
    command = [
        str(args.blender), "--background", "--python-exit-code", "1",
        "--python", str(script.resolve()), "--",
        "--source-dir", str(args.source_dir.resolve()),
        "--output-dir", str(args.output_dir.resolve()),
        "--width", str(args.width), "--height", str(args.height),
    ]
    subprocess.run(command, check=True)
    expected = [
        args.output_dir / "sdcc.material.png",
        args.output_dir / "sdcc.depth.png",
        args.output_dir / "sdcc.edge.png",
        args.output_dir / "sdcc.building_mask.png",
        args.output_dir / "sdcc.scene.blend",
    ]
    missing = [str(path) for path in expected if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Blender没有生成完整输出: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
