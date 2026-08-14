#!/usr/bin/env python3
"""Map arbitrary scene objects onto the stable semantic vocabulary used by planning/execution."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STANDARD_TYPES = {
    "building", "sports_field", "court", "road", "pedestrian", "green_area",
    "boundary", "context_building", "water", "parking", "entrance", "unknown",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象: {path}")
    return value


def normalize(value: str) -> str:
    return re.sub(r"[\s_\-./]+", " ", value.lower()).strip()


def score_object(obj: dict[str, Any], rules: dict[str, Any]) -> tuple[str, float, list[str], list[dict[str, Any]]]:
    fields = {
        "name": normalize(obj.get("name", "")),
        "materials": normalize(" ".join(obj.get("materials", []))),
        "collections": normalize(" ".join(obj.get("collections", []))),
    }
    weights = {"name": 0.70, "materials": 0.55, "collections": 0.45}
    scores: dict[str, float] = {semantic_type: 0.0 for semantic_type in STANDARD_TYPES if semantic_type != "unknown"}
    reasons: dict[str, list[str]] = {key: [] for key in scores}
    for semantic_type, keywords in rules.get("keywords", {}).items():
        if semantic_type not in scores:
            continue
        for field, text in fields.items():
            for keyword in keywords:
                if normalize(keyword) in text:
                    scores[semantic_type] += weights[field]
                    reasons[semantic_type].append(f"{field}:{keyword}")

    dimensions = [abs(float(value)) for value in obj.get("dimensions", [0, 0, 0])]
    if len(dimensions) == 3:
        horizontal = sorted(dimensions[:2], reverse=True)
        height = dimensions[2]
        if height >= 3 and horizontal[0] >= 5 and horizontal[1] >= 3:
            scores["building"] += 0.28
            reasons["building"].append("geometry:large_vertical_volume")
        if height <= 1 and horizontal[0] >= 10 and horizontal[1] >= 5:
            for candidate in ("pedestrian", "green_area", "road", "sports_field"):
                scores[candidate] += 0.08
                reasons[candidate].append("geometry:large_horizontal_surface")
        if height <= 1 and horizontal[0] >= max(20, horizontal[1] * 3):
            scores["road"] += 0.12
            reasons["road"].append("geometry:elongated_horizontal_surface")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_type, raw_score = ranked[0]
    confidence = min(0.98, round(raw_score, 3))
    if confidence < float(rules.get("auto_accept_threshold", 0.6)):
        best_type = "unknown"
    candidates = [
        {"type": semantic_type, "score": round(score, 3)}
        for semantic_type, score in ranked[:3]
        if score > 0
    ]
    return best_type, confidence, reasons.get(ranked[0][0], []), candidates


def map_inventory(
    raw: dict[str, Any], rules: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    if raw.get("raw_schema_version") != "1.0":
        raise ValueError("raw_schema_version 必须是 1.0")
    exact = overrides.get("object_mapping", {})
    objects = []
    unresolved = []
    used_ids: set[str] = set()
    for index, source in enumerate(raw.get("objects", [])):
        source_id = source["source_id"]
        semantic_type, confidence, reasons, candidates = score_object(source, rules)
        status = "auto"
        if source_id in exact:
            semantic_type = exact[source_id]
            if semantic_type not in STANDARD_TYPES:
                raise ValueError(f"覆盖配置含未知语义类型: {semantic_type}")
            confidence = 1.0
            reasons = ["project_override"]
            candidates = [{"type": semantic_type, "score": 1.0}]
            status = "confirmed"
        elif semantic_type == "unknown":
            status = "needs_confirmation"
        base_id = source.get("suggested_id") or f"object_{index:04d}"
        object_id = base_id
        suffix = 2
        while object_id in used_ids:
            object_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(object_id)
        mapped = {
            "id": object_id,
            "type": semantic_type,
            "name": source.get("name", source_id),
            "source_object": source_id,
            "confidence": confidence,
            "mapping_status": status,
            "reasons": reasons,
            "candidates": candidates,
            "preserve_geometry": semantic_type not in {"unknown"},
            "source_features": {
                "materials": source.get("materials", []),
                "collections": source.get("collections", []),
                "dimensions": source.get("dimensions", []),
                "bbox_min": source.get("bbox_min"),
                "bbox_max": source.get("bbox_max"),
            },
        }
        objects.append(mapped)
        if status == "needs_confirmation":
            unresolved.append({
                "source_object": source_id,
                "suggested_id": object_id,
                "candidates": candidates,
                "question": f"对象“{source.get('name', source_id)}”应属于哪一类？",
            })
    return {
        "schema_version": "1.0",
        "source_mode": "semantic_mapper",
        "project": raw.get("project", {}),
        "source": raw.get("source", {}),
        "scene": raw.get("scene", {}),
        "objects": objects,
        "mapping_summary": {
            "total": len(objects),
            "confirmed": sum(item["mapping_status"] == "confirmed" for item in objects),
            "automatic": sum(item["mapping_status"] == "auto" for item in objects),
            "needs_confirmation": len(unresolved),
        },
        "unresolved": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="将原始场景对象映射到标准建筑语义")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--rules", type=Path, default=Path("configs/semantic_mapping_rules.json"))
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = load_json(args.input)
    rules = load_json(args.rules)
    overrides = load_json(args.overrides) if args.overrides else {}
    manifest = map_inventory(raw, rules, overrides)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = manifest["mapping_summary"]
    print(f"项目映射已生成: {args.output}")
    print(f"对象: {summary['total']}, 自动: {summary['automatic']}, 已确认: {summary['confirmed']}, 待确认: {summary['needs_confirmation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
