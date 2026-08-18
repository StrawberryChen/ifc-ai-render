#!/usr/bin/env python3
"""Compile downloaded PBR maps into a stable Blender material asset library."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


MATERIAL_NAMES = {
    "ph_asphalt_02": "AIR_PH_Asphalt_02",
    "ph_concrete_pavers_02": "AIR_PH_Concrete_Pavers_02",
    "ph_concrete_floor_02": "AIR_PH_Concrete_Floor_02",
    "ph_leafy_grass": "AIR_PH_Leafy_Grass",
}


def arguments() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(values)


def image_node(nodes, path: Path, label: str, non_color: bool = False):
    node = nodes.new("ShaderNodeTexImage")
    node.label = label
    node.image = bpy.data.images.load(str(path.resolve()), check_existing=True)
    if non_color:
        node.image.colorspace_settings.name = "Non-Color"
    return node


def build_material(record: dict, assets_root: Path) -> None:
    material = bpy.data.materials.new(MATERIAL_NAMES[record["asset_id"]])
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = next(node for node in nodes if node.bl_idname == "ShaderNodeBsdfPrincipled")
    principled.inputs["Roughness"].default_value = 0.72

    files = record["files"]
    color = image_node(nodes, assets_root / files["base_color"], "Base Color")
    roughness = image_node(nodes, assets_root / files["roughness"], "Roughness", True)
    normal_texture = image_node(nodes, assets_root / files["normal"], "Normal", True)
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.65
    links.new(color.outputs["Color"], principled.inputs["Base Color"])
    links.new(roughness.outputs["Color"], principled.inputs["Roughness"])
    links.new(normal_texture.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], principled.inputs["Normal"])

    if files.get("displacement"):
        height = image_node(nodes, assets_root / files["displacement"], "Height", True)
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.18
        bump.inputs["Distance"].default_value = 0.08
        links.new(height.outputs["Color"], bump.inputs["Height"])
        links.new(normal.outputs["Normal"], bump.inputs["Normal"])
        links.new(bump.outputs["Normal"], principled.inputs["Normal"])

    material.asset_mark()
    material.asset_data.description = f"{record['name_zh']} | Poly Haven CC0 | {record['source_url']}"
    material["air_asset_id"] = record["asset_id"]
    material["air_license_id"] = record["license_id"]
    material["air_source_url"] = record["source_url"]


def main() -> None:
    args = arguments()
    index_path = args.index.resolve()
    assets_root = index_path.parents[2]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    for record in index["assets"]:
        if record["asset_id"] in MATERIAL_NAMES:
            build_material(record, assets_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    print(f"External material library built: {args.output.resolve()}")


if __name__ == "__main__":
    main()
