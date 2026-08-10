#!/usr/bin/env python3
"""Run the IFC-to-OBJ export and Blender white-model render as one command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from export_ifc_obj import export_ifc_to_obj


DEFAULT_BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将IFC转换并渲染为白模图")
    parser.add_argument("ifc", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/white_model"))
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--resolution", type=int, default=768)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.ifc.is_file():
        print(f"找不到IFC文件: {args.ifc}", file=sys.stderr)
        return 2
    if not args.blender.is_file():
        print(f"找不到Blender: {args.blender}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.ifc.stem
    obj_path = args.output_dir / f"{stem}.obj"
    metadata_path = args.output_dir / f"{stem}.components.json"
    image_path = args.output_dir / f"{stem}.white.png"
    depth_path = args.output_dir / f"{stem}.depth.png"
    camera_path = args.output_dir / f"{stem}.camera.json"
    blend_path = args.output_dir / f"{stem}.blend"

    metadata = export_ifc_to_obj(args.ifc, obj_path, metadata_path)
    print(f"IFC转换完成，共{metadata['component_count']}个构件")

    render_script = Path(__file__).with_name("render_white_model.py")
    command = [
        str(args.blender),
        "--background",
        "--python-exit-code",
        "1",
        "--python",
        str(render_script.resolve()),
        "--",
        "--obj",
        str(obj_path.resolve()),
        "--output",
        str(image_path.resolve()),
        "--depth-output",
        str(depth_path.resolve()),
        "--camera-output",
        str(camera_path.resolve()),
        "--blend",
        str(blend_path.resolve()),
        "--resolution",
        str(args.resolution),
    ]
    subprocess.run(command, check=True)
    if not image_path.is_file() or image_path.stat().st_size == 0:
        raise RuntimeError(f"Blender未生成有效图片: {image_path}")
    if not depth_path.is_file() or depth_path.stat().st_size == 0:
        raise RuntimeError(f"Blender未生成有效深度图: {depth_path}")
    print(f"完成: {image_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
