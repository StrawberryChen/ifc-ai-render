#!/usr/bin/env python3
"""Download a small, declared Poly Haven asset pack with checksums and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


USER_AGENT = "FormRenderAssetBuilder/0.1 (github.com/StrawberryChen/ifc-ai-render)"
API_ROOT = "https://api.polyhaven.com"


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def download(entry: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and hashlib.md5(target.read_bytes()).hexdigest() == entry["md5"]:
        return
    request = urllib.request.Request(entry["url"], headers={"User-Agent": USER_AGENT})
    temporary = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    digest = hashlib.md5(temporary.read_bytes()).hexdigest()
    if digest != entry["md5"]:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"MD5 mismatch for {target.name}: {digest}")
    temporary.replace(target)


def texture_files(files: dict[str, Any], resolution: str) -> dict[str, dict[str, Any]]:
    choices = {"base_color": "Diffuse", "normal": "nor_gl", "roughness": "Rough"}
    selected = {}
    for role, channel in choices.items():
        formats = files[channel][resolution]
        selected[role] = formats.get("jpg") or formats.get("png")
    displacement = files.get("Displacement", {}).get(resolution, {})
    if displacement:
        selected["displacement"] = displacement.get("jpg") or displacement.get("png")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("assets/sources/polyhaven_campus_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("assets/downloads/polyhaven"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    resolution = manifest["resolution"]
    completed = []
    for asset in manifest["assets"]:
        provider_id = asset["provider_id"]
        files = fetch_json(f"{API_ROOT}/files/{provider_id}")
        metadata = fetch_json(f"{API_ROOT}/info/{provider_id}")
        root = args.output_dir / provider_id
        if asset["type"] == "texture":
            selected = texture_files(files, resolution)
        else:
            selected = {"environment": files["hdri"][resolution]["hdr"]}
        local_files = {}
        for role, entry in selected.items():
            suffix = Path(urllib.parse.urlparse(entry["url"]).path).suffix
            target = root / f"{role}{suffix}"
            download(entry, target)
            local_files[role] = str(target.relative_to(args.output_dir.parents[1]))
        record = {
            **asset,
            "provider": manifest["provider"],
            "source_url": f"https://polyhaven.com/a/{provider_id}",
            "license_id": manifest["license_id"],
            "resolution": resolution,
            "files": local_files,
            "provider_metadata": {"name": metadata.get("name"), "authors": metadata.get("authors", {})},
        }
        (root / "metadata.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        completed.append(record)
        print(f"Downloaded {asset['asset_id']}: {len(selected)} files")
    index = {"schema_version": "1.0", "provider": manifest["provider"], "assets": completed}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Asset pack ready: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
