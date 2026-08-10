#!/usr/bin/env python3
"""Blender-side script: import an OBJ and render an automatically framed white model."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def scene_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
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


def make_white_material() -> bpy.types.Material:
    material = bpy.data.materials.new("White_Model_Material")
    material.diffuse_color = (0.72, 0.72, 0.72, 1.0)
    nodes = material.node_tree.nodes
    nodes.clear()
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = (0.72, 0.72, 0.72, 1.0)
    shader.inputs["Roughness"].default_value = 0.72
    return material


def assign_material(objects: list[bpy.types.Object], material: bpy.types.Material) -> None:
    for obj in objects:
        if obj.type != "MESH":
            continue
        obj.data.materials.clear()
        obj.data.materials.append(material)


def is_site_context(obj: bpy.types.Object) -> bool:
    excluded_prefixes = (
        "IfcEarthworksFill_",
        "IfcGeographicElement_",
        "IfcCivilElement_",
        "IfcBuildingElementProxy_",
    )
    return obj.name.startswith(excluded_prefixes)


def framing_objects(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    """Prefer building fabric when site/earthwork objects would dominate framing."""
    preferred = [obj for obj in objects if not is_site_context(obj)]
    return preferred or objects


def add_camera(minimum: Vector, maximum: Vector) -> bpy.types.Object:
    center = (minimum + maximum) / 2
    size = maximum - minimum
    horizontal = max(size.x, size.y, 1.0)
    target = Vector((center.x, center.y, minimum.z + size.z * 0.42))
    direction = Vector((1.35, -1.35, 0.85)).normalized()
    distance = max(horizontal * 1.75, size.z * 3.5, 8.0)

    camera_data = bpy.data.cameras.new("Camera")
    camera_data.lens = 50
    camera_data.clip_start = 0.05
    camera_data.clip_end = distance * 4.0
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = target + direction * distance
    look_at(camera, target)
    bpy.context.scene.camera = camera
    return camera


def write_camera_metadata(
    output: Path,
    camera: bpy.types.Object,
    minimum: Vector,
    maximum: Vector,
    resolution: int,
) -> None:
    data = {
        "camera": {
            "location": list(camera.location),
            "rotation_euler_radians": list(camera.rotation_euler),
            "lens_mm": camera.data.lens,
            "sensor_width_mm": camera.data.sensor_width,
            "clip_start": camera.data.clip_start,
            "clip_end": camera.data.clip_end,
        },
        "resolution": {"width": resolution, "height": resolution},
        "framing_bounds": {
            "min": list(minimum),
            "max": list(maximum),
            "center": list((minimum + maximum) / 2),
            "size": list(maximum - minimum),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_lighting(minimum: Vector, maximum: Vector) -> None:
    center = (minimum + maximum) / 2
    size = maximum - minimum

    sun_data = bpy.data.lights.new("Sun", type="SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-20), math.radians(-35))

    area_data = bpy.data.lights.new("Fill", type="AREA")
    area_data.energy = max(size.x, size.y, 1.0) * 75
    area_data.shape = "DISK"
    area_data.size = max(size.x, size.y, 1.0) * 1.5
    area = bpy.data.objects.new("Fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = center + Vector((-size.x, size.y, max(size.z * 2.5, 10)))
    look_at(area, center)


def add_ground(minimum: Vector, maximum: Vector) -> None:
    size = maximum - minimum
    radius = max(size.x, size.y, 1.0) * 1.8
    bpy.ops.mesh.primitive_plane_add(size=radius * 2, location=((minimum.x + maximum.x) / 2, (minimum.y + maximum.y) / 2, minimum.z - 0.02))
    ground = bpy.context.object
    ground.name = "Ground"
    material = bpy.data.materials.new("Ground_Material")
    material.diffuse_color = (0.14, 0.14, 0.14, 1.0)
    nodes = material.node_tree.nodes
    nodes.clear()
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = (0.14, 0.14, 0.14, 1.0)
    shader.inputs["Roughness"].default_value = 0.9
    ground.data.materials.append(material)


def configure_render(output: Path, resolution: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output.resolve())
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.color = (0.055, 0.055, 0.055)


def render_depth(output: Path, minimum: Vector, maximum: Vector) -> None:
    """Render normalized camera-space depth: near geometry white, background black."""
    scene = bpy.context.scene
    view_layer = scene.view_layers[0]

    camera = scene.camera
    corners = [
        Vector((x, y, z))
        for x in (minimum.x, maximum.x)
        for y in (minimum.y, maximum.y)
        for z in (minimum.z, maximum.z)
    ]
    distances = [(corner - camera.location).length for corner in corners]
    near_distance = max(min(distances) * 0.8, camera.data.clip_start)
    far_distance = max(distances) * 1.15
    depth_material = bpy.data.materials.new("Camera_Depth_Material")
    nodes = depth_material.node_tree.nodes
    nodes.clear()
    camera_data = nodes.new("ShaderNodeCameraData")
    map_range = nodes.new("ShaderNodeMapRange")
    emission = nodes.new("ShaderNodeEmission")
    material_output = nodes.new("ShaderNodeOutputMaterial")
    map_range.inputs["From Min"].default_value = near_distance
    map_range.inputs["From Max"].default_value = far_distance
    map_range.inputs["To Min"].default_value = 1.0
    map_range.inputs["To Max"].default_value = 0.0
    map_range.clamp = True
    depth_material.node_tree.links.new(camera_data.outputs["View Z Depth"], map_range.inputs["Value"])
    depth_material.node_tree.links.new(map_range.outputs["Result"], emission.inputs["Color"])
    depth_material.node_tree.links.new(emission.outputs["Emission"], material_output.inputs["Surface"])

    world_nodes = scene.world.node_tree.nodes
    world_nodes.clear()
    background = world_nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    background.inputs["Strength"].default_value = 0.0
    world_output = world_nodes.new("ShaderNodeOutputWorld")
    scene.world.node_tree.links.new(background.outputs["Background"], world_output.inputs["Surface"])
    view_layer.material_override = depth_material

    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "BW"
    scene.render.image_settings.color_depth = "16"
    scene.render.filepath = str(output.resolve())
    bpy.ops.render.render(write_still=True)
    view_layer.material_override = None


def parse_args() -> argparse.Namespace:
    argv = []
    if "--" in __import__("sys").argv:
        argv = __import__("sys").argv[__import__("sys").argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--obj", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--depth-output", type=Path, required=True)
    parser.add_argument("--camera-output", type=Path, required=True)
    parser.add_argument("--blend", type=Path)
    parser.add_argument("--resolution", type=int, default=768)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    clear_scene()
    bpy.ops.wm.obj_import(filepath=str(args.obj.resolve()), forward_axis="NEGATIVE_Z", up_axis="Y")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("OBJ导入后没有发现网格对象")

    subjects = framing_objects(meshes)
    for obj in meshes:
        if obj not in subjects:
            obj.hide_render = True
    minimum, maximum = scene_bounds(subjects)
    assign_material(meshes, make_white_material())
    add_ground(minimum, maximum)
    camera = add_camera(minimum, maximum)
    add_lighting(minimum, maximum)
    configure_render(args.output, args.resolution)
    write_camera_metadata(args.camera_output, camera, minimum, maximum, args.resolution)
    bpy.ops.render.render(write_still=True)
    render_depth(args.depth_output, minimum, maximum)
    if args.blend:
        args.blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(args.blend.resolve()))
    print(f"白模图已输出: {args.output.resolve()}")
    print(f"深度图已输出: {args.depth_output.resolve()}")
    print(f"相机参数已输出: {args.camera_output.resolve()}")


if __name__ == "__main__":
    main()
