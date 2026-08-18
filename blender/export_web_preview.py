#!/usr/bin/env python3
"""Export the currently opened Blender scene as a browser-ready binary glTF."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(values)


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(args.output),
        export_format="GLB",
        use_selection=False,
        export_cameras=True,
        export_lights=True,
        export_apply=True,
        export_image_format="WEBP",
        export_image_quality=72,
    )
    print(f"Web preview exported: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
