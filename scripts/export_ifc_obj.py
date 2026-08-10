#!/usr/bin/env python3
"""Export renderable IFC elements to a single OBJ plus component metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value.strip("_") or "unnamed"


def export_ifc_to_obj(ifc_path: Path, obj_path: Path, metadata_path: Path) -> dict[str, Any]:
    model = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    obj_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    vertex_offset = 1
    minimum = [float("inf")] * 3
    maximum = [float("-inf")] * 3
    components: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    with obj_path.open("w", encoding="utf-8") as obj:
        obj.write("# Exported from IFC with IfcOpenShell\n")
        for element in model.by_type("IfcElement"):
            if not getattr(element, "Representation", None):
                continue
            try:
                shape = ifcopenshell.geom.create_shape(settings, element)
                vertices = list(shape.geometry.verts)
                faces = list(shape.geometry.faces)
                if not vertices or not faces:
                    continue

                object_name = safe_name(f"{element.is_a()}_{element.id()}_{element.GlobalId}")
                obj.write(f"\no {object_name}\n")
                for index in range(0, len(vertices), 3):
                    xyz = [float(vertices[index + axis]) for axis in range(3)]
                    for axis, value in enumerate(xyz):
                        minimum[axis] = min(minimum[axis], value)
                        maximum[axis] = max(maximum[axis], value)
                    obj.write(f"v {xyz[0]:.9f} {xyz[1]:.9f} {xyz[2]:.9f}\n")

                for index in range(0, len(faces), 3):
                    triangle = [int(faces[index + axis]) + vertex_offset for axis in range(3)]
                    obj.write(f"f {triangle[0]} {triangle[1]} {triangle[2]}\n")

                container = ifcopenshell.util.element.get_container(element)
                components.append(
                    {
                        "object_name": object_name,
                        "ifc_id": element.id(),
                        "global_id": element.GlobalId,
                        "ifc_class": element.is_a(),
                        "name": element.Name,
                        "container": container.Name if container else None,
                        "vertex_count": len(vertices) // 3,
                        "triangle_count": len(faces) // 3,
                    }
                )
                vertex_offset += len(vertices) // 3
            except Exception as error:
                failures.append(
                    {
                        "ifc_id": element.id(),
                        "ifc_class": element.is_a(),
                        "name": element.Name,
                        "error": str(error),
                    }
                )

    if not components:
        raise RuntimeError("IFC中没有成功导出的可渲染构件")

    bounds = {
        "min": minimum,
        "max": maximum,
        "size": [maximum[i] - minimum[i] for i in range(3)],
        "center": [(maximum[i] + minimum[i]) / 2 for i in range(3)],
    }
    metadata = {
        "source_ifc": str(ifc_path.resolve()),
        "output_obj": str(obj_path.resolve()),
        "schema": model.schema,
        "component_count": len(components),
        "failed_count": len(failures),
        "bounds_metres": bounds,
        "components": components,
        "failures": failures,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将IFC可见构件导出为OBJ")
    parser.add_argument("ifc", type=Path)
    parser.add_argument("--obj", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata = export_ifc_to_obj(args.ifc, args.obj, args.metadata)
    print(f"已导出构件: {metadata['component_count']}")
    print(f"失败构件: {metadata['failed_count']}")
    size = metadata["bounds_metres"]["size"]
    print(f"尺寸(米): X={size[0]:.3f}, Y={size[1]:.3f}, Z={size[2]:.3f}")
    print(f"OBJ: {args.obj.resolve()}")
    print(f"元数据: {args.metadata.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
