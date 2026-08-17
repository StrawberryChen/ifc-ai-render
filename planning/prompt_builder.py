#!/usr/bin/env python3
"""Build versioned planner prompts from live project capabilities instead of a static mega-prompt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_assets(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "asset_id": asset["asset_id"],
            "asset_type": asset["asset_type"],
            "semantic_tags": asset.get("semantic_tags", []),
            "nominal_height_m": asset.get("nominal_height_m"),
        }
        for asset in registry.get("assets", [])
    ]


def compact_tools(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "tool_id": tool["tool_id"],
            "executor_status": tool["executor_status"],
            "parameters": {
                name: {
                    key: value
                    for key, value in definition.items()
                    if key in {"type", "minimum", "maximum", "enum", "required", "default"}
                }
                for name, definition in tool["parameters"].items()
            },
        }
        for tool in schema.get("tools", [])
    ]


def build_planner_prompt(
    inventory: dict[str, Any],
    brief: dict[str, Any],
    template: dict[str, Any],
    tool_schema: dict[str, Any],
    asset_registry: dict[str, Any],
    playbook: dict[str, Any],
) -> str:
    context = {
        "contract": {
            "task": "Produce an executable architectural visualization scene plan.",
            "output": "Return one JSON object only, with exactly the top-level structure of OUTPUT_TEMPLATE.",
            "uncertainty": "Put uncertain facts in assumptions/questions; never fabricate project geometry or IDs.",
            "capabilities": "Only request listed tools and registered assets. Respect executor_status.",
        },
        "project_manifest": inventory,
        "user_brief": brief,
        "available_tools": compact_tools(tool_schema),
        "available_assets": compact_assets(asset_registry),
        "professional_playbook": playbook,
        "output_template": template,
    }
    return (
        "You are the planning component of a controlled architectural visualization system. "
        "You create plans; you never emit Python or directly operate Blender.\n\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )
