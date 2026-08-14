#!/usr/bin/env python3
"""Provider-independent scene planning agent for Blender architectural rendering."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLAN_VERSION = "1.0"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象: {path}")
    return value


def validate_inventory(inventory: dict[str, Any]) -> None:
    if inventory.get("schema_version") != "1.0":
        raise ValueError("inventory.schema_version 必须是 1.0")
    objects = inventory.get("objects")
    if not isinstance(objects, list) or not objects:
        raise ValueError("inventory.objects 必须是非空数组")
    valid_types = {
        "building", "sports_field", "court", "road", "pedestrian", "green_area",
        "boundary", "context_building", "water", "unknown",
    }
    ids: set[str] = set()
    for item in objects:
        if not item.get("id") or item["id"] in ids:
            raise ValueError("每个场景对象必须有唯一id")
        ids.add(item["id"])
        if item.get("type") not in valid_types:
            raise ValueError(f"不支持的对象类型: {item.get('type')}")


def validate_plan(plan: dict[str, Any], inventory: dict[str, Any]) -> None:
    required = [
        "schema_version", "project", "assumptions", "questions", "camera_plan",
        "lighting_plan", "material_plan", "landscape_plan", "entourage_plan",
        "render_plan", "postprocess_plan",
    ]
    missing = [key for key in required if key not in plan]
    if missing:
        raise ValueError(f"场景计划缺少字段: {missing}")
    known_ids = {item["id"] for item in inventory["objects"]}
    for assignment in plan.get("material_plan", {}).get("assignments", []):
        unknown = set(assignment.get("target_ids", [])) - known_ids
        if unknown:
            raise ValueError(f"材质计划引用未知对象: {sorted(unknown)}")
    if not plan["camera_plan"].get("shots"):
        raise ValueError("camera_plan.shots 不得为空")


def object_ids(inventory: dict[str, Any], *types: str) -> list[str]:
    return [item["id"] for item in inventory["objects"] if item["type"] in types]


def build_template_plan(inventory: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Produce a safe executable baseline before an LLM provider is connected."""
    buildings = object_ids(inventory, "building")
    sports = object_ids(inventory, "sports_field", "court")
    roads = object_ids(inventory, "road", "pedestrian")
    greens = object_ids(inventory, "green_area")
    context = object_ids(inventory, "context_building")
    style = brief.get("visual_target", {})
    return {
        "schema_version": PLAN_VERSION,
        "project": {
            "name": inventory.get("project", {}).get("name", "unnamed_project"),
            "goal": brief.get("goal", "client-facing architectural visualization"),
            "source_mode": inventory.get("source_mode", "parsed_model"),
        },
        "assumptions": [
            "All supplied design geometry is authoritative and must not be redesigned.",
            "Vegetation, entourage and lighting are visualization layers, not construction documentation.",
            "North direction and exact geographic sun position require confirmation when absent.",
        ],
        "questions": [
            {"id": "north_direction", "blocking": False, "question": "项目正北方向和期望日照方向是什么？"},
            {"id": "hero_shots", "blocking": False, "question": "是否保留SketchUp现有场景相机作为主视角？"},
            {"id": "landscape_density", "blocking": False, "question": "绿化需要克制展示建筑，还是形成高密度校园环境？"},
        ],
        "camera_plan": {
            "strategy": "preserve_source_cameras_then_add_ranked_candidates",
            "shots": [
                {"id": "hero_aerial", "type": "aerial_oblique", "focal_length_mm": 45, "target_coverage": 0.72, "priority": 1},
                {"id": "entrance_eye_level", "type": "eye_level", "focal_length_mm": 35, "priority": 2},
                {"id": "sports_overview", "type": "aerial_oblique", "focal_length_mm": 50, "priority": 3},
            ],
        },
        "lighting_plan": {
            "preset": style.get("time_of_day", "blue_hour"),
            "sun": {"elevation_deg": 8, "azimuth_deg": 235, "strength": 1.8, "temperature_k": 4300},
            "world": {"strength": 0.35, "sky_tint": "cool_blue"},
            "windows": {"enabled": True, "lit_ratio": 0.38, "temperature_k": 3200},
            "street_lights": {"enabled": True, "temperature_k": 3000, "spacing_m": 22},
            "constraint": "all visible shadows must follow one sun vector",
        },
        "material_plan": {
            "assignments": [
                {"target_ids": buildings, "preset": "preserve_source_architecture_pbr"},
                {"target_ids": sports, "preset": "school_sports_surfaces_pbr"},
                {"target_ids": roads, "preset": "urban_paving_and_asphalt_pbr"},
                {"target_ids": greens, "preset": "maintained_campus_groundcover"},
                {"target_ids": context, "preset": "neutral_context_massing"},
            ],
        },
        "landscape_plan": {
            "target_ids": greens,
            "preset": brief.get("landscape", {}).get("preset", "northeast_china_campus"),
            "tree_density": brief.get("landscape", {}).get("tree_density", 0.32),
            "tree_height_m": [5.0, 11.0],
            "minimum_spacing_m": 6.0,
            "building_clearance_m": 5.0,
            "road_clearance_m": 1.5,
            "rules": ["keep_primary_facades_visible", "protect_entrances", "avoid_sports_surfaces"],
        },
        "entourage_plan": {
            "people": {"density": "low", "areas": roads + sports, "scale_m": [1.55, 1.9]},
            "vehicles": {"density": "low", "areas": object_ids(inventory, "road")},
            "exclude": buildings + greens,
        },
        "render_plan": {
            "engine": "BLENDER_EEVEE_NEXT_PREVIEW_CYCLES_FINAL",
            "preview_resolution": [1280, 720],
            "final_resolution": [2048, 1536],
            "color_management": {"view_transform": "AgX", "look": "Medium High Contrast"},
            "passes": ["beauty", "depth", "normal", "object_id", "material_id", "shadow", "edge"],
        },
        "postprocess_plan": {
            "structure_controls": ["depth", "edge"],
            "style_reference": brief.get("reference", {}),
            "diffusion_strength": [0.22, 0.35],
            "upscale": {"scale": 2, "tiled_refinement": True},
            "quality_checks": [
                "geometry_preserved", "single_shadow_direction", "facades_not_occluded",
                "sports_markings_preserved", "no_generated_text", "multi_view_style_consistency",
            ],
        },
    }


def planner_prompt(inventory: dict[str, Any], brief: dict[str, Any], template: dict[str, Any]) -> str:
    return (
        "You are an architectural visualization scene planner. Return JSON only. "
        "Never redesign authoritative geometry. Vegetation, materials, cameras, lighting and entourage "
        "must be executable by Blender. Keep every top-level key and data type from the template. "
        "Only reference object ids present in inventory. Put uncertainty into assumptions/questions.\n\n"
        f"INVENTORY:\n{json.dumps(inventory, ensure_ascii=False)}\n\n"
        f"BRIEF:\n{json.dumps(brief, ensure_ascii=False)}\n\n"
        f"OUTPUT_TEMPLATE:\n{json.dumps(template, ensure_ascii=False)}"
    )


def call_openai_compatible(
    endpoint: str, api_key: str, model: str, prompt: str, timeout: int = 120
) -> dict[str, Any]:
    url = endpoint.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成Blender建筑可视化场景计划")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=["template", "openai-compatible"], default="template")
    parser.add_argument("--endpoint", default=os.environ.get("SCENE_PLANNER_ENDPOINT", ""))
    parser.add_argument("--model", default=os.environ.get("SCENE_PLANNER_MODEL", "qwen-plus"))
    parser.add_argument("--api-key-env", default="SCENE_PLANNER_API_KEY")
    args = parser.parse_args()

    inventory = load_json(args.inventory)
    brief = load_json(args.brief)
    validate_inventory(inventory)
    template = build_template_plan(inventory, brief)
    if args.provider == "template":
        plan = template
    else:
        api_key = os.environ.get(args.api_key_env, "")
        if not args.endpoint or not api_key:
            raise ValueError(f"需要 --endpoint 和环境变量 {args.api_key_env}")
        plan = call_openai_compatible(args.endpoint, api_key, args.model, planner_prompt(inventory, brief, template))
    validate_plan(plan, inventory)
    plan["generated_at"] = datetime.now(timezone.utc).isoformat()
    plan["planner"] = {"provider": args.provider, "model": args.model if args.provider != "template" else "rules-v1"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"场景计划已生成: {args.output}")
    print(f"相机数量: {len(plan['camera_plan']['shots'])}")
    print(f"待确认问题: {len(plan['questions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
