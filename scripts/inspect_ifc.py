#!/usr/bin/env python3
"""Inspect an IFC model and export a compact, machine-readable summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.unit


def entity_label(entity: Any) -> dict[str, Any]:
    return {
        "ifc_id": entity.id(),
        "global_id": getattr(entity, "GlobalId", None),
        "ifc_class": entity.is_a(),
        "name": getattr(entity, "Name", None),
    }


def spatial_summary(model: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    spatial_classes = ("IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace")
    for ifc_class in spatial_classes:
        for entity in model.by_type(ifc_class):
            row = entity_label(entity)
            if entity.is_a("IfcBuildingStorey"):
                row["elevation"] = getattr(entity, "Elevation", None)
            rows.append(row)
    return rows


def element_summary(model: Any) -> tuple[dict[str, int], list[dict[str, Any]]]:
    elements = model.by_type("IfcElement")
    counts = Counter(element.is_a() for element in elements)
    rows: list[dict[str, Any]] = []

    for element in elements:
        row = entity_label(element)
        container = ifcopenshell.util.element.get_container(element)
        row["container"] = entity_label(container) if container else None
        rows.append(row)

    return dict(sorted(counts.items())), rows


def geometry_bounds(model: Any) -> dict[str, Any]:
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    minimum = [float("inf")] * 3
    maximum = [float("-inf")] * 3
    processed = 0
    failed = 0

    for element in model.by_type("IfcElement"):
        if not getattr(element, "Representation", None):
            continue
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            vertices = shape.geometry.verts
            if not vertices:
                continue
            for index in range(0, len(vertices), 3):
                for axis in range(3):
                    value = float(vertices[index + axis])
                    minimum[axis] = min(minimum[axis], value)
                    maximum[axis] = max(maximum[axis], value)
            processed += 1
        except RuntimeError:
            failed += 1

    if processed == 0:
        return {"processed_elements": 0, "failed_elements": failed, "bounds": None}

    size = [maximum[i] - minimum[i] for i in range(3)]
    return {
        "processed_elements": processed,
        "failed_elements": failed,
        "bounds": {"min": minimum, "max": maximum, "size": size},
    }


def inspect_model(ifc_path: Path, include_geometry: bool) -> dict[str, Any]:
    model = ifcopenshell.open(str(ifc_path))
    projects = [entity_label(item) for item in model.by_type("IfcProject")]
    counts, elements = element_summary(model)

    result: dict[str, Any] = {
        "source": str(ifc_path.resolve()),
        "file_size_bytes": ifc_path.stat().st_size,
        "schema": model.schema,
        "length_unit_scale_to_metre": ifcopenshell.util.unit.calculate_unit_scale(model),
        "projects": projects,
        "spatial_structure": spatial_summary(model),
        "element_count": len(elements),
        "element_counts_by_class": counts,
        "elements": elements,
    }
    if include_geometry:
        result["geometry"] = geometry_bounds(model)
    return result


def print_human_summary(summary: dict[str, Any]) -> None:
    print(f"文件: {summary['source']}")
    print(f"IFC版本: {summary['schema']}")
    print(f"长度单位换算到米: {summary['length_unit_scale_to_metre']}")
    print(f"空间节点数: {len(summary['spatial_structure'])}")
    print(f"构件总数: {summary['element_count']}")
    print("构件类别:")
    for ifc_class, count in summary["element_counts_by_class"].items():
        print(f"  {ifc_class}: {count}")

    geometry = summary.get("geometry")
    if geometry:
        print(f"成功解析几何的构件: {geometry['processed_elements']}")
        print(f"几何解析失败的构件: {geometry['failed_elements']}")
        if geometry["bounds"]:
            size = geometry["bounds"]["size"]
            print(f"模型包围盒尺寸: X={size[0]:.3f}, Y={size[1]:.3f}, Z={size[2]:.3f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="读取IFC并输出构件与空间结构摘要")
    parser.add_argument("ifc", type=Path, help="输入的.ifc文件")
    parser.add_argument("--output", "-o", type=Path, help="JSON输出路径")
    parser.add_argument(
        "--geometry",
        action="store_true",
        help="解析全部构件几何并计算模型包围盒；大型模型会较慢",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.ifc.is_file():
        print(f"找不到IFC文件: {args.ifc}", file=sys.stderr)
        return 2
    if args.ifc.suffix.lower() != ".ifc":
        print(f"输入文件不是.ifc: {args.ifc}", file=sys.stderr)
        return 2

    try:
        summary = inspect_model(args.ifc, args.geometry)
    except Exception as error:
        print(f"IFC解析失败: {error}", file=sys.stderr)
        return 1

    print_human_summary(summary)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON已写入: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
