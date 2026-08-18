#!/usr/bin/env python3
"""Execute a validated scene plan inside Blender without modifying authoritative geometry."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_library import AssetLibrary


ROOT = Path(__file__).resolve().parents[1]
LIGHTING_PRESETS_PATH = ROOT / "assets/presets/lighting_environments.json"


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-blend", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--asset-registry", type=Path, default=Path("assets/registry/asset_registry.json"))
    parser.add_argument("--asset-preset", type=Path, default=Path("assets/presets/campus_northeast_china.json"))
    parser.add_argument("--meters-per-unit", type=float)
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
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    preset_id = lighting.get("preset", "neutral")
    environment_presets = read_json(LIGHTING_PRESETS_PATH).get("presets", {}) if LIGHTING_PRESETS_PATH.is_file() else {}
    environment = environment_presets.get(preset_id)
    if environment:
        image_path = ROOT / "assets" / environment["file"]
        if image_path.is_file():
            texture = nodes.new("ShaderNodeTexEnvironment")
            texture.image = bpy.data.images.load(str(image_path), check_existing=True)
            coordinates = nodes.new("ShaderNodeTexCoord")
            mapping = nodes.new("ShaderNodeMapping")
            rotation_deg = float(world_config.get("rotation_deg", environment.get("rotation_deg", 0)))
            mapping.inputs["Rotation"].default_value[2] = math.radians(rotation_deg)
            links.new(coordinates.outputs["Generated"], mapping.inputs["Vector"])
            links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
            links.new(texture.outputs["Color"], background.inputs["Color"])
            links.new(background.outputs["Background"], output.inputs["Surface"])
            background.inputs["Strength"].default_value = max(0.01, float(world_config.get("strength", environment.get("strength", 0.32))))
            return {
                "action": "configure_world", "status": "executed", "sky": "hdri",
                "asset_id": environment["asset_id"], "rotation_deg": rotation_deg,
                "path": str(image_path),
            }
    sky = nodes.new("ShaderNodeTexSky")
    tint_mix = nodes.new("ShaderNodeMixRGB")
    try:
        sky.sky_type = "NISHITA"
    except TypeError:
        sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = True
    sun_config = lighting.get("sun", {})
    sky.sun_elevation = math.radians(float(sun_config.get("elevation_deg", 8)))
    sky.sun_rotation = math.radians(float(sun_config.get("azimuth_deg", 235)))
    sky.altitude = 0.2
    sky.air_density = 1.15
    links.new(sky.outputs["Color"], tint_mix.inputs[1])
    links.new(tint_mix.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    tint = world_config.get("sky_tint", "neutral")
    colors = {
        "cool_blue": (0.055, 0.085, 0.16, 1.0),
        "warm": (0.22, 0.13, 0.07, 1.0),
        "neutral": (0.12, 0.12, 0.12, 1.0),
    }
    tint_mix.blend_type = "MULTIPLY"
    tint_mix.inputs[0].default_value = 0.42 if tint == "cool_blue" else 0.25
    tint_mix.inputs[2].default_value = colors.get(tint, colors["neutral"])
    background.inputs["Strength"].default_value = max(0.45, float(world_config.get("strength", 0.35)))
    return {"action": "configure_world", "status": "executed", "tint": tint, "sky": "nishita", "fallback": True}


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
    radius = max(size.x, size.y, size.z * 2, 0.1)
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
        azimuth = math.radians(float(shot.get("azimuth_deg", directions[index % len(directions)])))
        if shot_type == "eye_level":
            distance, height = radius * 1.25, max(1.7, minimum.z + size.z * 0.18)
            target = Vector((center.x, center.y, minimum.z + size.z * 0.35))
        else:
            coverage = min(0.9, max(0.35, float(shot.get("target_coverage", 0.72))))
            framing_scale = 0.72 / coverage
            distance_multiplier = min(12.0, max(0.25, float(shot.get("distance_multiplier", 1.35))))
            elevation = math.radians(min(80.0, max(8.0, float(shot.get("elevation_deg", 34.0)))))
            slant_distance = radius * distance_multiplier * framing_scale
            distance = slant_distance * math.cos(elevation)
            height = center.z + slant_distance * math.sin(elevation)
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


def configure_context_ground(
    design_objects: list[bpy.types.Object],
    collection: bpy.types.Collection,
    plan: dict[str, Any],
    has_supplied_context: bool,
) -> dict[str, Any]:
    """Add non-authoritative surroundings when the supplied model has no context geometry."""
    minimum, maximum = scene_bounds(design_objects)
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    radius = max(size.x, size.y, 1.0)
    mesh = bpy.data.meshes.get("AIR_ContextGround_Mesh")
    context = bpy.data.objects.get("AIR_ContextGround")
    if context is None:
        bpy.ops.mesh.primitive_plane_add(
            size=radius * 12,
            location=(center.x, center.y, minimum.z - max(radius * 0.004, 0.002)),
        )
        context = bpy.context.object
        context.name = "AIR_ContextGround"
        mesh = context.data
        mesh.name = "AIR_ContextGround_Mesh"
        link_only(context, collection)
    material = bpy.data.materials.get("AIR_ContextGround_Material") or bpy.data.materials.new("AIR_ContextGround_Material")
    material.use_nodes = True
    material_nodes = material.node_tree.nodes
    principled = next((node for node in material_nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"), None) or material_nodes.new("ShaderNodeBsdfPrincipled")
    material_output = next((node for node in material_nodes if node.bl_idname == "ShaderNodeOutputMaterial"), None) or material_nodes.new("ShaderNodeOutputMaterial")
    if not principled.outputs["BSDF"].is_linked:
        material.node_tree.links.new(principled.outputs["BSDF"], material_output.inputs["Surface"])
    preset = plan.get("lighting_plan", {}).get("preset", "neutral")
    color = (0.075, 0.105, 0.13, 1.0) if preset == "blue_hour" else (0.19, 0.22, 0.18, 1.0)
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = 0.92
    context.data.materials.clear()
    context.data.materials.append(material)
    context["air_visualization_context"] = True

    context_blocks = []
    if not has_supplied_context:
        block_material = bpy.data.materials.get("AIR_ContextBlock_Material") or bpy.data.materials.new("AIR_ContextBlock_Material")
        block_color = (0.075, 0.12, 0.18, 1.0) if preset == "blue_hour" else (0.24, 0.30, 0.32, 1.0)
        block_material.diffuse_color = block_color
        block_material.use_nodes = True
        block_nodes = block_material.node_tree.nodes
        block_principled = next((node for node in block_nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"), None) or block_nodes.new("ShaderNodeBsdfPrincipled")
        block_output = next((node for node in block_nodes if node.bl_idname == "ShaderNodeOutputMaterial"), None) or block_nodes.new("ShaderNodeOutputMaterial")
        if not block_principled.outputs["BSDF"].is_linked:
            block_material.node_tree.links.new(block_principled.outputs["BSDF"], block_output.inputs["Surface"])
        block_principled.inputs["Base Color"].default_value = block_color
        block_principled.inputs["Roughness"].default_value = 0.88
        half_x, half_y = max(size.x * 0.5, radius * 0.18), max(size.y * 0.5, radius * 0.18)
        margin = radius * 0.42
        placements = [
            (-half_x * 0.72, half_y + margin, 0.24, 0.22, 0.36),
            (half_x * 0.02, half_y + margin, 0.30, 0.22, 0.50),
            (half_x * 0.76, half_y + margin, 0.25, 0.22, 0.40),
            (half_x + margin, -half_y * 0.15, 0.22, 0.28, 0.38),
            (half_x + margin, half_y * 0.62, 0.24, 0.26, 0.46),
        ]
        for index, (offset_x, offset_y, sx, sy, height) in enumerate(placements, 1):
            name = f"AIR_ContextBlock_{index:02d}"
            block = bpy.data.objects.get(name)
            if block is None:
                bpy.ops.mesh.primitive_cube_add(
                    size=1,
                )
                block = bpy.context.object
                block.name = name
                link_only(block, collection)
            block.location = (center.x + offset_x, center.y + offset_y, minimum.z + height * radius * 0.5)
            block.dimensions = (sx * radius, sy * radius, height * radius)
            block.data.materials.clear()
            block.data.materials.append(block_material)
            block["air_visualization_context"] = True
            context_blocks.append(block.name)
    return {
        "action": "context_environment",
        "status": "executed",
        "ground_size": radius * 12,
        "placeholder_context": not has_supplied_context,
        "context_blocks": context_blocks,
    }


def bbox(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))),
        Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))),
    )


def infer_meters_per_unit(manifest: dict[str, Any], object_map: dict[str, bpy.types.Object], override: float | None) -> tuple[float, str]:
    if override:
        if override <= 0:
            raise ValueError("--meters-per-unit 必须大于0")
        return override, "cli_override"
    heights = []
    for item in manifest["objects"]:
        if item["type"] == "building" and item["id"] in object_map:
            minimum, maximum = bbox(object_map[item["id"]])
            if maximum.z - minimum.z > 0:
                heights.append(maximum.z - minimum.z)
    scene_info = manifest.get("scene", {})
    scene_scale = float(scene_info.get("scale_length", 0))
    if scene_info.get("unit_system") == "METRIC" and scene_scale > 0:
        metric_heights = [height * scene_scale for height in heights]
        if not metric_heights or all(3.0 <= height <= 200.0 for height in metric_heights):
            return scene_scale, "blender_metric_scene"
    if heights:
        heights.sort()
        median_height = heights[len(heights) // 2]
        return 18.0 / median_height, "inferred_assuming_18m_building"
    return 1.0, "fallback_one_meter_per_unit"


def apply_semantic_materials(
    manifest: dict[str, Any],
    object_map: dict[str, bpy.types.Object],
    preset: dict[str, Any],
    library: AssetLibrary,
) -> dict[str, Any]:
    applied = []
    skipped = []
    mappings = preset.get("materials", {})
    for item in manifest["objects"]:
        asset_id = mappings.get(item["type"])
        obj = object_map.get(item["id"])
        if not asset_id or not obj or obj.type != "MESH":
            skipped.append(item["id"])
            continue
        material = library.load_material(asset_id)
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj["air_material_asset_id"] = asset_id
        applied.append({"semantic_id": item["id"], "object": obj.name, "asset_id": asset_id})
    return {"action": "material_assignments", "status": "executed", "applied": applied, "skipped": skipped}


def inside_expanded_bbox(point: Vector, obj: bpy.types.Object, clearance_units: float) -> bool:
    minimum, maximum = bbox(obj)
    return (
        minimum.x - clearance_units <= point.x <= maximum.x + clearance_units
        and minimum.y - clearance_units <= point.y <= maximum.y + clearance_units
    )


def upward_triangles(obj: bpy.types.Object) -> list[tuple[Vector, Vector, Vector, float]]:
    mesh = obj.data
    matrix = obj.matrix_world
    result = []
    for polygon in mesh.polygons:
        vertices = [matrix @ mesh.vertices[index].co for index in polygon.vertices]
        if len(vertices) < 3:
            continue
        for index in range(1, len(vertices) - 1):
            a, b, c = vertices[0], vertices[index], vertices[index + 1]
            normal = (b - a).cross(c - a)
            area = normal.length * 0.5
            if area > 1e-8 and abs(normal.normalized().z) >= 0.7:
                result.append((a, b, c, area))
    return result


def scatter_landscape(
    manifest: dict[str, Any],
    object_map: dict[str, bpy.types.Object],
    plan: dict[str, Any],
    preset: dict[str, Any],
    library: AssetLibrary,
    collection: bpy.types.Collection,
    meters_per_unit: float,
) -> dict[str, Any]:
    config = preset.get("vegetation", {})
    asset_pool = config.get("asset_pool", [])
    green_objects = [object_map[item["id"]] for item in manifest["objects"] if item["type"] == "green_area" and item["id"] in object_map]
    buildings = [object_map[item["id"]] for item in manifest["objects"] if item["type"] == "building" and item["id"] in object_map]
    if not green_objects or not asset_pool:
        return {"action": "landscape_scatter", "status": "skipped_no_semantic_targets", "instances": 0}
    seed = int(plan.get("landscape_plan", {}).get("seed", 4201))
    rng = random.Random(seed)
    density = float(plan.get("landscape_plan", {}).get("tree_density", config.get("default_density", 0.32)))
    spacing_m = float(plan.get("landscape_plan", {}).get("minimum_spacing_m", config.get("minimum_spacing_m", 6.0)))
    clearance_m = float(plan.get("landscape_plan", {}).get("building_clearance_m", config.get("building_clearance_m", 5.0)))
    spacing_units = spacing_m / meters_per_unit
    clearance_units = clearance_m / meters_per_unit
    placed: list[Vector] = []
    instances = []
    for green in green_objects:
        triangles = upward_triangles(green)
        total_area_units = sum(item[3] for item in triangles)
        total_area_m = total_area_units * meters_per_unit * meters_per_unit
        target_count = min(500, max(1, round(total_area_m / max(spacing_m * spacing_m, 1) * density)))
        cumulative = []
        running = 0.0
        for triangle in triangles:
            running += triangle[3]
            cumulative.append(running)
        attempts = 0
        while len(instances) < target_count and attempts < target_count * 40 and cumulative:
            attempts += 1
            value = rng.random() * cumulative[-1]
            triangle_index = next(i for i, end in enumerate(cumulative) if value <= end)
            a, b, c, _ = triangles[triangle_index]
            r1, r2 = math.sqrt(rng.random()), rng.random()
            point = a * (1 - r1) + b * (r1 * (1 - r2)) + c * (r1 * r2)
            if any((point.xy - existing.xy).length < spacing_units for existing in placed):
                continue
            if any(inside_expanded_bbox(point, building, clearance_units) for building in buildings):
                continue
            asset_id = rng.choice(asset_pool)
            record = library.record(asset_id)
            scale_min, scale_max = record.get("scale_range", [1.0, 1.0])
            scale = rng.uniform(scale_min, scale_max) / meters_per_unit
            instance = library.instantiate_collection(asset_id, f"AIR_Tree_{len(instances) + 1:04d}", tuple(point), scale)
            instance.rotation_euler.z = rng.random() * math.tau
            link_only(instance, collection)
            placed.append(point)
            instances.append({"object": instance.name, "asset_id": asset_id})
    return {"action": "landscape_scatter", "status": "executed", "seed": seed, "instances": len(instances), "assets": instances}


def perimeter_points(minimum: Vector, maximum: Vector, spacing: float) -> list[tuple[Vector, float]]:
    points: list[tuple[Vector, float]] = []
    edges = [
        (Vector((minimum.x, minimum.y, maximum.z)), Vector((maximum.x, minimum.y, maximum.z)), 0.0),
        (Vector((maximum.x, minimum.y, maximum.z)), Vector((maximum.x, maximum.y, maximum.z)), math.pi / 2),
        (Vector((maximum.x, maximum.y, maximum.z)), Vector((minimum.x, maximum.y, maximum.z)), math.pi),
        (Vector((minimum.x, maximum.y, maximum.z)), Vector((minimum.x, minimum.y, maximum.z)), -math.pi / 2),
    ]
    for start, end, rotation in edges:
        length = (end - start).length
        count = max(1, round(length / max(spacing, 1e-6)))
        for index in range(count):
            t = (index + 0.5) / count
            points.append((start.lerp(end, t), rotation))
    return points


def place_streetlights(
    manifest: dict[str, Any],
    object_map: dict[str, bpy.types.Object],
    plan: dict[str, Any],
    preset: dict[str, Any],
    library: AssetLibrary,
    collection: bpy.types.Collection,
    meters_per_unit: float,
) -> dict[str, Any]:
    light_plan = plan.get("lighting_plan", {}).get("street_lights", {})
    if not light_plan.get("enabled", False):
        return {"action": "streetlight_placement", "status": "skipped_disabled", "instances": 0}
    config = preset.get("street_lighting", {})
    asset_id = config.get("asset_id")
    targets = [object_map[item["id"]] for item in manifest["objects"] if item["type"] in {"road", "pedestrian"} and item["id"] in object_map]
    if not asset_id or not targets:
        return {"action": "streetlight_placement", "status": "skipped_no_semantic_targets", "instances": 0}
    spacing_m = float(light_plan.get("spacing_m", config.get("default_spacing_m", 22.0)))
    spacing_units = spacing_m / meters_per_unit
    scale = 1.0 / meters_per_unit
    instances = []
    for target in targets:
        minimum, maximum = bbox(target)
        for point, rotation in perimeter_points(minimum, maximum, spacing_units):
            instance = library.instantiate_collection(asset_id, f"AIR_Streetlight_{len(instances) + 1:04d}", tuple(point), scale)
            instance.rotation_euler.z = rotation
            link_only(instance, collection)
            instances.append(instance.name)
    return {"action": "streetlight_placement", "status": "executed", "asset_id": asset_id, "instances": len(instances)}


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
    asset_instances = ensure_collection("AIR_ASSET_INSTANCES")
    library = AssetLibrary(args.asset_registry)
    preset = read_json(args.asset_preset)
    meters_per_unit, scale_source = infer_meters_per_unit(manifest, object_map, args.meters_per_unit)
    actions = [configure_world(plan), configure_sun(plan, controls), configure_render(plan, args.preview)]
    design_objects = list(object_map.values())
    actions.extend(configure_cameras(plan, design_objects, controls))
    has_supplied_context = any(item["type"] == "context_building" for item in manifest["objects"])
    actions.append(configure_context_ground(design_objects, controls, plan, has_supplied_context))
    actions.extend([
        apply_semantic_materials(manifest, object_map, preset, library),
        scatter_landscape(manifest, object_map, plan, preset, library, asset_instances, meters_per_unit),
        place_streetlights(manifest, object_map, plan, preset, library, asset_instances, meters_per_unit),
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
        "unit_scale": {"meters_per_unit": meters_per_unit, "source": scale_source},
        "asset_registry": str(args.asset_registry),
        "asset_preset": str(args.asset_preset),
        "actions": actions,
        "summary": {
            "executed": sum(item["status"] == "executed" for item in actions),
            "not_implemented": sum(item["status"] == "planned_not_implemented" for item in actions),
            "skipped": sum(item["status"].startswith("skipped") for item in actions),
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
