"""Stable Blender-side loader for assets registered in assets/registry/asset_registry.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bpy


class AssetLibrary:
    def __init__(self, registry_path: Path):
        self.registry_path = registry_path.resolve()
        self.asset_root = self.registry_path.parents[1]
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assets = {asset["asset_id"]: asset for asset in registry["assets"]}

    def record(self, asset_id: str) -> dict[str, Any]:
        if asset_id not in self.assets:
            raise KeyError(f"资产未注册: {asset_id}")
        return self.assets[asset_id]

    def source_path(self, asset_id: str) -> Path:
        path = self.asset_root / self.record(asset_id)["file"]
        if not path.is_file():
            raise FileNotFoundError(f"资产库文件不存在: {path}")
        return path

    def load_material(self, asset_id: str) -> bpy.types.Material:
        record = self.record(asset_id)
        if record["asset_type"] != "material":
            raise TypeError(f"资产不是材质: {asset_id}")
        name = record["datablock"]
        existing = bpy.data.materials.get(name)
        if existing:
            return existing
        with bpy.data.libraries.load(str(self.source_path(asset_id)), link=False) as (source, target):
            if name not in source.materials:
                raise KeyError(f"Blend文件中不存在材质数据块: {name}")
            target.materials = [name]
        return bpy.data.materials[name]

    def load_collection(self, asset_id: str) -> bpy.types.Collection:
        record = self.record(asset_id)
        if record["asset_type"] != "collection":
            raise TypeError(f"资产不是Collection: {asset_id}")
        name = record["datablock"]
        existing = bpy.data.collections.get(name)
        if existing:
            return existing
        with bpy.data.libraries.load(str(self.source_path(asset_id)), link=False) as (source, target):
            if name not in source.collections:
                raise KeyError(f"Blend文件中不存在Collection数据块: {name}")
            target.collections = [name]
        return bpy.data.collections[name]

    def instantiate_collection(
        self,
        asset_id: str,
        name: str,
        location: tuple[float, float, float] = (0, 0, 0),
        scale: float = 1.0,
    ) -> bpy.types.Object:
        collection = self.load_collection(asset_id)
        instance = bpy.data.objects.new(name, None)
        instance.instance_type = "COLLECTION"
        instance.instance_collection = collection
        instance.location = location
        instance.scale = (scale, scale, scale)
        bpy.context.scene.collection.objects.link(instance)
        instance["air_asset_id"] = asset_id
        return instance
