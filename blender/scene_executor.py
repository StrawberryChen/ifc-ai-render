#!/usr/bin/env python3
"""Execute a validated scene plan inside Blender without modifying authoritative geometry."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-blend", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    return parser.parse_args(values)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scene_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise ValueError("没有可用于相机定位的设计对象")
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return minimum, maximum


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def ensure_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if collection.name not in bpy.context.scene.collection.children:
        try:
            bpy.context.scene.collection.children.link(collection)
        except RuntimeError:
            pass
    return collection


def link_only(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def configure_world(plan: dict[str, Any]) -> dict[str, Any]:
    lighting = plan["lighting_plan"]
    world_config = lighting.get("world", {})
    world = bpy.context.scene.world or bpy.data.worlds.new("AIR_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    tint = world_config.get("sky_tint", "neutral")
    colors = {
        "cool_blue": (0.055, 0.085, 0.16, 1.0),
        "warm": (0.22, 0.13, 0.07, 1.0),
        "neutral": (0.12, 0.12, 0.12, 1.0),
    }
    background.inputs["Color"].default_value = colors.get(tint, colors["neutral"])
    background.inputs["Strength"].default_value = float(world_config.get("strength", 0.35))
    return {"action": "configure_world", "status": "executed", "tint": tint}


def configure_sun(plan: dict[str, Any], collection: bpy.types.Collection) -> dict[str, Any]:
    sun_config = plan["lighting_plan"].get("sun", {})
    light_data = bpy.data.lights.get("AIR_Sun") or bpy.data.lights.new("AIR_Sun", "SUN")
    sun = bpy.data.objects.get("AIR_Sun") or bpy.data.objects.new("AIR_Sun", light_data)
    if not sun.users_collection:
        collection.objects.link(sun)
    elif collection not in sun.users_collection:
        link_only(sun, collection)
    elevation = math.radians(float(sun_config.get("elevation_deg", 25)))
    azimuth = math.radians(float(sun_config.get("azimuth_deg", 225)))
    position_direction = Vector((
        math.cos(elevation) * math.cos(azimuth),
        math.cos(elevation) * math.sin(azimuth),
        math.sin(elevation),
    ))
    ray_direction = -position_direction
    sun.rotation_euler = ray_direction.to_track_quat("-Z", "Y").to_euler()
    light_data.energy = float(sun_config.get("strength", 2.0))
    light_data.angle = math.radians(4.0)
    return {
        "action": "configure_sun", "status": "executed",
        "elevation_deg": math.degrees(elevation), "azimuth_deg": math.degrees(azimuth),
    }


def configure_render(plan: dict[str, Any], preview: Path | None) -> dict[str, Any]:
    scene = bpy.context.scene
    render_plan = plan["render_plan"]
    resolution = render_plan.get("preview_resolution" if preview else "final_resolution", [1280, 720])
    scene.render.resolution_x = int(resolution[0])
    scene.render.resolution_y = int(resolution[1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    color = render_plan.get("color_management", {})
    if color.get("view_transform"):
        try:
            scene.view_settings.view_transform = color["view_transform"]
        except TypeError:
            pass
    if preview:
        scene.render.filepath = str(preview)
    return {"action": "configure_render", "status": "executed", "resolution": resolution}


def configure_cameras(
    plan: dict[str, Any], design_objects: list[bpy.types.Object], collection: bpy.types.Collection
) -> list[dict[str, Any]]:
    minimum, maximum = scene_bounds(design_objects)
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    radius = max(size.x, size.y, size.z * 2, 10.0)
    reports = []
    directions = [225, 135, 315, 45]
    for index, shot in enumerate(plan["camera_plan"].get("shots", [])):
        name = f"AIR_Camera_{shot['id']}"
        camera_data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
        camera = bpy.data.objects.get(name) or bpy.data.objects.new(name, camera_data)
        if not camera.users_collection:
            collection.objects.link(camera)
        camera_data.lens = float(shot.get("focal_length_mm", 45))
        shot_type = shot.get("type", "aerial_oblique")
        azimuth = math.radians(directions[index % len(directions)])
        if shot_type == "eye_level":
            distance, height = radius * 1.25, max(1.7, minimum.z + size.z * 0.18)
            target = Vector((center.x, center.y, minimum.z + size.z * 0.35))
        else:
            distance, height = radius * 1.45, maximum.z + radius * 0.85
            target = center
        camera.location = Vector((
            center.x + math.cos(azimuth) * distance,
            center.y + math.sin(azimuth) * distance,
            height,
        ))
        look_at(camera, target)
        reports.append({
            "action": "create_camera", "status": "executed", "shot_id": shot["id"],
            "object": camera.name, "location": list(camera.location),
        })
    if reports:
        bpy.context.scene.camera = bpy.data.objects[reports[0]["object"]]
    return reports


def execute(args: argparse.Namespace) -> dict[str, Any]:
    source_blend = bpy.data.filepath
    manifest = read_json(args.manifest)
    plan = read_json(args.plan)
    unresolved = manifest.get("unresolved", [])
    if unresolved:
        raise ValueError(f"manifest仍有{len(unresolved)}个未确认对象，拒绝执行")
    object_map = {}
    missing = []
    for item in manifest["objects"]:
        source = bpy.data.objects.get(item["source_object"])
        if source:
            object_map[item["id"]] = source
            source["air_semantic_id"] = item["id"]
            source["air_semantic_type"] = item["type"]
            source["air_preserve_geometry"] = bool(item.get("preserve_geometry", True))
        else:
            missing.append(item["source_object"])
    if missing:
        raise ValueError(f"Blender中找不到manifest对象: {missing}")

    controls = ensure_collection("AIR_CONTROLS")
    actions = [configure_world(plan), configure_sun(plan, controls), configure_render(plan, args.preview)]
    actions.extend(configure_cameras(plan, list(object_map.values()), controls))
    actions.extend([
        {"action": "material_assignments", "status": "planned_not_implemented", "reason": "asset preset library not connected"},
        {"action": "landscape_scatter", "status": "planned_not_implemented", "reason": "vegetation asset library not connected"},
        {"action": "entourage_scatter", "status": "planned_not_implemented", "reason": "people/vehicle asset library not connected"},
        {"action": "window_lighting", "status": "planned_not_implemented", "reason": "window material semantic mask unavailable"},
    ])
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.render.render(write_still=True)
    report = {
        "schema_version": "1.0",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "source_blend": source_blend,
        "manifest": str(args.manifest),
        "plan": str(args.plan),
        "output_blend": str(args.output_blend),
        "bound_objects": {key: value.name for key, value in object_map.items()},
        "actions": actions,
        "summary": {
            "executed": sum(item["status"] == "executed" for item in actions),
            "not_implemented": sum(item["status"] == "planned_not_implemented" for item in actions),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    report = execute(args)
    print(f"Scene plan executed: {report['summary']['executed']} actions")
    print(f"Pending executor modules: {report['summary']['not_implemented']}")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
