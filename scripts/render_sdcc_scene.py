#!/usr/bin/env python3
"""Import the public-domain SDCC OBJ assets and render aligned AI inputs."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
import OpenImageIO as oiio
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=768)
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def import_obj(path: Path, name: str) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    # The source OBJ uses Y-up. This conversion makes Blender Z-up.
    bpy.ops.wm.obj_import(
        filepath=str(path.resolve()),
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )
    imported = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
    if len(imported) != 1:
        raise RuntimeError(f"Expected one mesh from {path}, got {len(imported)}")
    imported[0].name = name
    return imported[0]


def textured_material(name: str, image_path: Path, roughness: float) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(image_path.resolve()), check_existing=True)
    texture.interpolation = "Linear"
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Specular IOR Level"].default_value = 0.35
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def emission_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = 1.0
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            minimum.x = min(minimum.x, point.x)
            minimum.y = min(minimum.y, point.y)
            minimum.z = min(minimum.z, point.z)
            maximum.x = max(maximum.x, point.x)
            maximum.y = max(maximum.y, point.y)
            maximum.z = max(maximum.z, point.z)
    return minimum, maximum


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_camera(minimum: Vector, maximum: Vector, aspect: float) -> bpy.types.Object:
    center = (minimum + maximum) / 2
    size = maximum - minimum
    target = Vector((center.x, center.y, minimum.z + size.z * 0.38))
    direction = Vector((1.15, -1.45, 0.72)).normalized()
    horizontal = max(size.x, size.y / max(aspect, 0.1), 0.5)
    distance = max(horizontal * 2.35, size.z * 3.8, 4.0)
    data = bpy.data.cameras.new("Camera")
    data.lens = 52
    data.clip_start = 0.01
    data.clip_end = distance * 8
    camera = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(camera)
    camera.location = target + direction * distance
    look_at(camera, target)
    bpy.context.scene.camera = camera
    return camera


def add_lighting(minimum: Vector, maximum: Vector) -> None:
    center = (minimum + maximum) / 2
    size = maximum - minimum
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(5)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(30), math.radians(-25), math.radians(-40))

    area_data = bpy.data.lights.new("Sky_Fill", "AREA")
    area_data.energy = 180.0
    area_data.shape = "DISK"
    area_data.size = max(size.x, size.y) * 1.5
    area = bpy.data.objects.new("Sky_Fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = center + Vector((-size.x, -size.y * 0.3, size.z * 3.0))
    look_at(area, center)


def configure_scene(width: int, height: int) -> None:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.055, 0.075, 0.11, 1.0)
    background.inputs["Strength"].default_value = 0.45


def render(path: Path) -> None:
    scene = bpy.context.scene
    scene.render.filepath = str(path.resolve())
    bpy.ops.render.render(write_still=True)


def render_depth(path: Path, camera: bpy.types.Object, objects: list[bpy.types.Object]) -> tuple[float, float]:
    """Ray-cast one metric camera distance per pixel and save a 16-bit depth PNG."""
    scene = bpy.context.scene
    width = scene.render.resolution_x
    height = scene.render.resolution_y
    frame = camera.data.view_frame(scene=scene)
    top_right, bottom_right, bottom_left, top_left = frame
    origin = camera.location.copy()
    depths = np.zeros((height, width), dtype=np.float32)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for row in range(height):
        v = (row + 0.5) / height
        left = top_left * (1.0 - v) + bottom_left * v
        right = top_right * (1.0 - v) + bottom_right * v
        for column in range(width):
            u = (column + 0.5) / width
            camera_point = left * (1.0 - u) + right * u
            direction = (camera.matrix_world.to_quaternion() @ camera_point).normalized()
            hit, location, _normal, _face, hit_object, _matrix = scene.ray_cast(
                depsgraph, origin, direction, distance=camera.data.clip_end
            )
            if hit and hit_object is not None:
                depths[row, column] = (location - origin).length
    valid = depths > camera.data.clip_start
    if not np.any(valid):
        raise RuntimeError("Ray-cast depth contains no foreground pixels")
    near = float(np.min(depths[valid]))
    far = float(np.max(depths[valid]))
    normalized = np.zeros_like(depths, dtype=np.float32)
    normalized[valid] = 1.0 - np.clip((depths[valid] - near) / max(far - near, 1e-6), 0.0, 1.0)
    depth_u16 = np.ascontiguousarray(np.round(normalized * 65535.0).astype(np.uint16)[..., np.newaxis])
    output = oiio.ImageOutput.create(str(path))
    output.open(str(path), oiio.ImageSpec(width, height, 1, oiio.UINT16))
    output.write_image(depth_u16)
    output.close()
    return near, far


def render_mask(path: Path, building: bpy.types.Object, ground: bpy.types.Object) -> None:
    original_building = list(building.data.materials)
    original_ground = list(ground.data.materials)
    assign_material(building, emission_material("Mask_White", (1, 1, 1, 1)))
    assign_material(ground, emission_material("Mask_Black", (0, 0, 0, 1)))
    scene = bpy.context.scene
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    scene.render.image_settings.color_mode = "BW"
    render(path)
    building.data.materials.clear()
    ground.data.materials.clear()
    for material in original_building:
        building.data.materials.append(material)
    for material in original_ground:
        ground.data.materials.append(material)
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"


def render_edges(path: Path, building: bpy.types.Object, ground: bpy.types.Object) -> None:
    """Render visible mesh edges as a ControlNet-friendly line image."""
    original_building = list(building.data.materials)
    original_ground = list(ground.data.materials)
    assign_material(building, emission_material("Edge_White", (1, 1, 1, 1)))
    assign_material(ground, emission_material("Edge_White", (1, 1, 1, 1)))
    scene = bpy.context.scene
    scene.render.use_freestyle = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    linestyle = bpy.data.linestyles[0]
    linestyle.color = (0, 0, 0)
    linestyle.thickness = 1.25
    scene.render.image_settings.color_mode = "BW"
    render(path)
    scene.render.use_freestyle = False
    building.data.materials.clear()
    ground.data.materials.clear()
    for material in original_building:
        building.data.materials.append(material)
    for material in original_ground:
        ground.data.materials.append(material)
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"


def main() -> None:
    args = parse_args()
    source = args.source_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    required = [
        source / "building.obj",
        source / "ground.obj",
        source / "baked_building.png",
        source / "baked_ground.png",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing SDCC assets: {missing}")

    clear_scene()
    building = import_obj(source / "building.obj", "SDCC_Building")
    ground = import_obj(source / "ground.obj", "SDCC_Ground")
    building_material = textured_material("SDCC_Baked_Building", source / "baked_building.png", 0.58)
    ground_material = textured_material("SDCC_Baked_Ground", source / "baked_ground.png", 0.82)
    assign_material(building, building_material)
    assign_material(ground, ground_material)

    scene_minimum, scene_maximum = bounds([building, ground])
    minimum, maximum = bounds([building])
    configure_scene(args.width, args.height)
    camera = add_camera(minimum, maximum, args.width / args.height)
    add_lighting(minimum, maximum)

    rgb_path = output / "sdcc.material.png"
    depth_path = output / "sdcc.depth.png"
    edge_path = output / "sdcc.edge.png"
    mask_path = output / "sdcc.building_mask.png"
    blend_path = output / "sdcc.scene.blend"
    metadata_path = output / "sdcc.camera.json"

    render(rgb_path)
    near, far = render_depth(depth_path, camera, [building])
    render_mask(mask_path, building, ground)
    render_edges(edge_path, building, ground)

    metadata = {
        "resolution": {"width": args.width, "height": args.height},
        "camera": {
            "location": list(camera.location),
            "rotation_euler_radians": list(camera.rotation_euler),
            "lens_mm": camera.data.lens,
            "clip_start": camera.data.clip_start,
            "clip_end": camera.data.clip_end,
        },
        "depth_normalization": {"near": near, "far": far, "near_is_white": True},
        "building_bounds": {"min": list(minimum), "max": list(maximum)},
        "scene_bounds": {"min": list(scene_minimum), "max": list(scene_maximum)},
        "source_license": "Public domain; see data/sdcc/README.txt",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"SDCC RGB: {rgb_path}")
    print(f"SDCC depth: {depth_path}")
    print(f"SDCC edge: {edge_path}")
    print(f"SDCC mask: {mask_path}")
    print(f"SDCC scene: {blend_path}")


if __name__ == "__main__":
    main()
