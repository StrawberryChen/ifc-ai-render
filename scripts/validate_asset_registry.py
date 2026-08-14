#!/usr/bin/env python3
"""Validate asset IDs, files, presets and license traceability without loading Blender."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(registry_path: Path, preset_paths: list[Path]) -> dict[str, int]:
    asset_root = registry_path.parents[1]
    registry = load(registry_path)
    assets = registry.get("assets", [])
    ids = [asset["asset_id"] for asset in assets]
    if len(ids) != len(set(ids)):
        raise ValueError("asset_id存在重复")
    licenses = {}
    license_dir = asset_root / "licenses"
    for path in license_dir.glob("*.json"):
        record = load(path)
        licenses[record["license_id"]] = record
    for asset in assets:
        source = asset_root / asset["file"]
        if not source.is_file():
            raise FileNotFoundError(f"资产文件不存在: {source}")
        if asset["license_id"] not in licenses:
            raise ValueError(f"资产缺少许可证记录: {asset['asset_id']}")
    checked_presets = 0
    known_ids = set(ids)
    for path in preset_paths:
        preset = load(path)
        references = list(preset.get("materials", {}).values())
        references += preset.get("vegetation", {}).get("asset_pool", [])
        streetlight = preset.get("street_lighting", {}).get("asset_id")
        if streetlight:
            references.append(streetlight)
        unknown = set(references) - known_ids
        if unknown:
            raise ValueError(f"预设{path}引用未知资产: {sorted(unknown)}")
        checked_presets += 1
    return {"assets": len(assets), "licenses": len(licenses), "presets": checked_presets}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("assets/registry/asset_registry.json"))
    parser.add_argument("--presets", type=Path, nargs="*", default=[Path("assets/presets/campus_northeast_china.json")])
    args = parser.parse_args()
    summary = validate(args.registry, args.presets)
    print(f"资产注册表有效: {summary['assets']} assets, {summary['licenses']} licenses, {summary['presets']} presets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
