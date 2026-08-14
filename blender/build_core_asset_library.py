#!/usr/bin/env python3
"""Build the self-owned procedural core asset library. Run with Blender in background mode."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy


def args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(values)


def clear() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)


def principled_material(
    name: str,
    base_color: tuple[float, float, float, float],
    roughness: float,
    metallic: float = 0.0,
    transmission: float = 0.0,
    emission_color: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    node = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    node.inputs["Base Color"].default_value = base_color
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Metallic"].default_value = metallic
    transmission_input = node.inputs.get("Transmission Weight") or node.inputs.get("Transmission")
    if transmission_input:
        transmission_input.default_value = transmission
    if emission_color:
        emission_input = node.inputs.get("Emission Color") or node.inputs.get("Emission")
        strength_input = node.inputs.get("Emission Strength")
        if emission_input:
            emission_input.default_value = emission_color
        if strength_input:
            strength_input.default_value = emission_strength
    material.asset_mark()
    material.asset_data.description = "IFC AI Render self-owned procedural PBR preset"
    material["air_license_id"] = "SELF_OWNED_CC0_COMPATIBLE"
    return material


def build_materials(output: Path) -> None:
    clear()
    principled_material("AIR_MAT_Concrete_Light", (0.52, 0.50, 0.46, 1), 0.78)
    principled_material("AIR_MAT_Asphalt_Dark", (0.035, 0.042, 0.05, 1), 0.86)
    principled_material("AIR_MAT_Grass_Campus", (0.055, 0.19, 0.045, 1), 0.92)
    principled_material("AIR_MAT_Track_Red", (0.32, 0.045, 0.025, 1), 0.72)
    principled_material("AIR_MAT_Steel_Dark", (0.035, 0.045, 0.055, 1), 0.28, metallic=0.82)
    glass = principled_material("AIR_MAT_Glass_Architectural", (0.075, 0.16, 0.20, 1), 0.12, transmission=0.85)
    glass.diffuse_color = (0.075, 0.16, 0.20, 0.28)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))


def object_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def add_cylinder(name: str, radius: float, depth: float, z: float, material: bpy.types.Material, collection: bpy.types.Collection) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=depth, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    object_to_collection(obj, collection)
    return obj


def add_crown(name: str, radius: float, location: tuple[float, float, float], scale: tuple[float, float, float], material: bpy.types.Material, collection: bpy.types.Collection) -> None:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    object_to_collection(obj, collection)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True


def build_tree(name: str, height: float, crown_radius: float, crown_count: int, bark: bpy.types.Material, leaves: bpy.types.Material) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    trunk_height = height * 0.48
    add_cylinder(f"{name}_Trunk", crown_radius * 0.12, trunk_height, trunk_height * 0.5, bark, collection)
    crown_z = trunk_height + (height - trunk_height) * 0.45
    offsets = [(0, 0), (-0.38, 0.08), (0.34, 0.12), (0.05, -0.32), (-0.12, 0.35)]
    for index in range(crown_count):
        ox, oy = offsets[index]
        add_crown(
            f"{name}_Crown_{index + 1:02d}", crown_radius,
            (ox * crown_radius, oy * crown_radius, crown_z + (index % 2) * crown_radius * 0.18),
            (1.0, 0.92, 0.78), leaves, collection,
        )
    collection.asset_mark()
    collection.asset_data.description = f"Procedural deciduous campus tree, nominal height {height}m"
    collection["air_nominal_height_m"] = height
    collection["air_license_id"] = "SELF_OWNED_CC0_COMPATIBLE"
    return collection


def build_streetlight(metal: bpy.types.Material, glow: bpy.types.Material) -> bpy.types.Collection:
    collection = bpy.data.collections.new("AIR_OBJ_Streetlight_Campus_01")
    bpy.context.scene.collection.children.link(collection)
    add_cylinder("Streetlight_Pole", 0.075, 5.5, 2.75, metal, collection)
    bpy.ops.mesh.primitive_cube_add(location=(0.45, 0, 5.45), scale=(0.5, 0.08, 0.055))
    arm = bpy.context.object
    arm.name = "Streetlight_Arm"
    arm.data.materials.append(metal)
    object_to_collection(arm, collection)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.15, location=(0.9, 0, 5.32), scale=(1.4, 0.75, 0.35))
    lamp = bpy.context.object
    lamp.name = "Streetlight_Luminaire"
    lamp.data.materials.append(glow)
    object_to_collection(lamp, collection)
    collection.asset_mark()
    collection.asset_data.description = "Procedural 5.5m campus street light"
    collection["air_nominal_height_m"] = 5.5
    collection["air_license_id"] = "SELF_OWNED_CC0_COMPATIBLE"
    return collection


def build_objects(output: Path) -> None:
    clear()
    bark = principled_material("AIR_INTERNAL_Bark", (0.085, 0.035, 0.015, 1), 0.9)
    leaves_a = principled_material("AIR_INTERNAL_Leaves_Green", (0.025, 0.16, 0.035, 1), 0.82)
    leaves_b = principled_material("AIR_INTERNAL_Leaves_Deep", (0.018, 0.10, 0.028, 1), 0.86)
    metal = principled_material("AIR_INTERNAL_Light_Metal", (0.025, 0.03, 0.038, 1), 0.28, metallic=0.8)
    glow = principled_material(
        "AIR_INTERNAL_Light_Glow", (0.9, 0.45, 0.12, 1), 0.3,
        emission_color=(1.0, 0.32, 0.06, 1), emission_strength=8.0,
    )
    build_tree("AIR_OBJ_Tree_Deciduous_01", 8.0, 2.15, 3, bark, leaves_a)
    build_tree("AIR_OBJ_Tree_Deciduous_02", 10.5, 2.65, 5, bark, leaves_b)
    build_tree("AIR_OBJ_Tree_Deciduous_03", 6.5, 1.85, 4, bark, leaves_a)
    build_streetlight(metal, glow)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))


def main() -> None:
    parsed = args()
    output_dir = parsed.output_dir.resolve()
    build_materials(output_dir / "core_materials.blend")
    build_objects(output_dir / "core_objects.blend")
    print(f"Core asset library built: {output_dir}")


if __name__ == "__main__":
    main()
