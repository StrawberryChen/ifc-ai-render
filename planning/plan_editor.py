#!/usr/bin/env python3
"""Validated action-based plan editing and revision storage for frontend clients."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def validate_parameters(tool: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    definitions = tool["parameters"]
    unknown = set(parameters) - set(definitions)
    if unknown:
        raise ValueError(f"未知参数: {sorted(unknown)}")
    normalized = {}
    for name, definition in definitions.items():
        if definition.get("required") and name not in parameters:
            raise ValueError(f"缺少必填参数: {name}")
        if name not in parameters:
            continue
        value = parameters[name]
        expected = definition["type"]
        if expected == "boolean" and not isinstance(value, bool):
            raise TypeError(f"{name}必须是boolean")
        if expected in {"number", "integer"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name}必须是数值")
            if expected == "integer" and int(value) != value:
                raise TypeError(f"{name}必须是整数")
            if "minimum" in definition and value < definition["minimum"]:
                raise ValueError(f"{name}低于最小值{definition['minimum']}")
            if "maximum" in definition and value > definition["maximum"]:
                raise ValueError(f"{name}高于最大值{definition['maximum']}")
            value = int(value) if expected == "integer" else float(value)
        if expected == "string" and not isinstance(value, str):
            raise TypeError(f"{name}必须是字符串")
        if "enum" in definition and value not in definition["enum"]:
            raise ValueError(f"{name}不在允许值中: {definition['enum']}")
        normalized[name] = value
    return normalized


class PlanEditor:
    def __init__(self, tool_schema: dict[str, Any]):
        self.schema = tool_schema
        self.tools = {tool["tool_id"]: tool for tool in tool_schema["tools"]}

    def apply(self, plan: dict[str, Any], tool_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if tool_id not in self.tools:
            raise KeyError(f"未知工具: {tool_id}")
        values = validate_parameters(self.tools[tool_id], parameters)
        result = copy.deepcopy(plan)
        if tool_id == "camera.update_shot":
            shot_id = values.pop("shot_id")
            shot = next((item for item in result["camera_plan"]["shots"] if item["id"] == shot_id), None)
            if not shot:
                raise KeyError(f"未知视角: {shot_id}")
            shot.update(values)
        elif tool_id == "lighting.set_sun":
            result["lighting_plan"].setdefault("sun", {}).update(values)
        elif tool_id == "lighting.set_world":
            result["lighting_plan"].setdefault("world", {}).update(values)
        elif tool_id == "lighting.set_windows":
            result["lighting_plan"].setdefault("windows", {}).update(values)
        elif tool_id == "lighting.set_streetlights":
            result["lighting_plan"].setdefault("street_lights", {}).update(values)
        elif tool_id == "landscape.configure":
            result.setdefault("landscape_plan", {}).update(values)
        elif tool_id == "render.configure":
            render = result.setdefault("render_plan", {})
            preview = render.setdefault("preview_resolution", [1280, 720])
            final = render.setdefault("final_resolution", [4096, 3072])
            preview[0] = values.get("preview_width", preview[0])
            preview[1] = values.get("preview_height", preview[1])
            final[0] = values.get("final_width", final[0])
            final[1] = values.get("final_height", final[1])
        elif tool_id == "postprocess.configure":
            post = result.setdefault("postprocess_plan", {})
            if "global_strength" in values:
                post["diffusion_strength"] = [values["global_strength"]]
            if "upscale" in values:
                post.setdefault("upscale", {})["scale"] = values["upscale"]
            if "tiled_refinement" in values:
                post.setdefault("upscale", {})["tiled_refinement"] = values["tiled_refinement"]
        else:
            raise NotImplementedError(tool_id)
        result.setdefault("edit_history", []).append({
            "tool_id": tool_id,
            "parameters": parameters,
            "edited_at": datetime.now(timezone.utc).isoformat(),
        })
        return result


class RevisionStore:
    def __init__(self, root: Path):
        self.root = root
        self.revisions = root / "revisions"
        self.current = root / "current_plan.json"

    def initialize(self, plan: dict[str, Any]) -> Path:
        self.revisions.mkdir(parents=True, exist_ok=True)
        if self.current.exists():
            return self.current
        return self.commit(plan, "initial_plan")

    def commit(self, plan: dict[str, Any], message: str) -> Path:
        self.revisions.mkdir(parents=True, exist_ok=True)
        number = len(list(self.revisions.glob("rev_*.json"))) + 1
        envelope = {
            "revision": number,
            "message": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "plan": plan,
        }
        revision_path = self.revisions / f"rev_{number:04d}.json"
        revision_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        self.current.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return revision_path

    def undo(self) -> dict[str, Any]:
        paths = sorted(self.revisions.glob("rev_*.json"))
        if len(paths) < 2:
            raise ValueError("没有可撤销的历史版本")
        paths[-1].unlink()
        previous = json.loads(paths[-2].read_text(encoding="utf-8"))["plan"]
        self.current.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
        return previous
