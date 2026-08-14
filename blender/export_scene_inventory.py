#!/usr/bin/env python3
"""Run inside Blender to export a renderer-independent raw scene inventory."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


def script_args() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-name", default="")
    return parser.parse_args(args)


def vector(values: Vector) -> list[float]:
    return [round(float(value), 6) for value in values]


def safe_id(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name).strip("_").lower()
    return value or "object"


def world_bbox(obj: bpy.types.Object) -> tuple[list[float], list[float]] | tuple[None, None]:
    if not getattr(obj, "bound_box", None):
        return None, None
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        vector(Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))),
        vector(Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))),
    )


def export_object(obj: bpy.types.Object) -> dict:
    bbox_min, bbox_max = world_bbox(obj)
    materials = []
    if getattr(obj, "data", None) and hasattr(obj.data, "materials"):
        materials = [material.name for material in obj.data.materials if material]
    polygons = len(obj.data.polygons) if obj.type == "MESH" else 0
    vertices = len(obj.data.vertices) if obj.type == "MESH" else 0
    return {
        "source_id": obj.name,
        "suggested_id": safe_id(obj.name),
        "name": obj.name,
        "object_type": obj.type,
        "collections": sorted(collection.name for collection in obj.users_collection),
        "materials": materials,
        "location": vector(obj.matrix_world.translation),
        "dimensions": vector(obj.dimensions),
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
        "vertices": vertices,
        "polygons": polygons,
        "visible_render": not obj.hide_render,
        "custom_properties": {
            key: str(obj[key]) for key in obj.keys() if key != "_RNA_UI"
        },
    }


def main() -> None:
    args = script_args()
    scene = bpy.context.scene
    objects = [
        export_object(obj)
        for obj in scene.objects
        if obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "EMPTY"}
    ]
    cameras = [obj.name for obj in scene.objects if obj.type == "CAMERA"]
    payload = {
        "raw_schema_version": "1.0",
        "project": {"id": args.project_id, "name": args.project_name or args.project_id},
        "source": {
            "kind": "blender",
            "blend_file": bpy.data.filepath,
            "blender_version": bpy.app.version_string,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "scene": {
            "unit_system": scene.unit_settings.system,
            "scale_length": scene.unit_settings.scale_length,
            "active_camera": scene.camera.name if scene.camera else None,
            "cameras": cameras,
        },
        "objects": objects,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw scene inventory exported: {args.output} ({len(objects)} objects)")


if __name__ == "__main__":
    main()
