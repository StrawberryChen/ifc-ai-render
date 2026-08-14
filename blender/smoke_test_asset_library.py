#!/usr/bin/env python3
"""Run inside Blender to verify every registered asset can be appended."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_library import AssetLibrary


def main() -> None:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(values)
    library = AssetLibrary(args.registry)
    loaded = []
    for asset_id, record in library.assets.items():
        if record["asset_type"] == "material":
            datablock = library.load_material(asset_id)
        elif record["asset_type"] == "collection":
            datablock = library.load_collection(asset_id)
        else:
            raise TypeError(f"不支持的资产类型: {record['asset_type']}")
        loaded.append({"asset_id": asset_id, "datablock": datablock.name, "status": "loaded"})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"loaded": loaded}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Asset library smoke test passed: {len(loaded)} assets")


if __name__ == "__main__":
    main()
