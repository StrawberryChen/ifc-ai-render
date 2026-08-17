#!/usr/bin/env python3
"""Translate a natural-language edit into validated Blender tool actions."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def implemented_tools(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [tool for tool in schema["tools"] if tool.get("executor_status") == "implemented"]


def call_deepseek(prompt: str, api_key: str, model: str) -> dict[str, Any]:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(content)


def rules_fallback(user_prompt: str, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Small local fallback for UI development; production uses DeepSeek."""
    actions: list[dict[str, Any]] = []
    text = user_prompt.lower()
    if any(word in text for word in ("黄昏", "蓝紫", "傍晚")):
        actions.extend([
            {"tool_id": "lighting.set_sun", "parameters": {"elevation_deg": 7, "azimuth_deg": 235, "strength": 1.6, "temperature_k": 4300}},
            {"tool_id": "lighting.set_world", "parameters": {"strength": 0.3, "sky_tint": "cool_blue"}},
        ])
    if any(word in text for word in ("白天", "晴天", "晴朗")):
        actions.extend([
            {"tool_id": "lighting.set_sun", "parameters": {"elevation_deg": 38, "azimuth_deg": 220, "strength": 3.0, "temperature_k": 5600}},
            {"tool_id": "lighting.set_world", "parameters": {"strength": 0.8, "sky_tint": "neutral"}},
        ])
    if "降低" in text and any(word in text for word in ("乔木", "树木", "绿化")):
        current = float(plan.get("landscape_plan", {}).get("tree_density", 0.32))
        actions.append({"tool_id": "landscape.configure", "parameters": {"tree_density": max(0.05, current - 0.12)}})
    if "增加" in text and any(word in text for word in ("乔木", "树木", "绿化")):
        current = float(plan.get("landscape_plan", {}).get("tree_density", 0.32))
        actions.append({"tool_id": "landscape.configure", "parameters": {"tree_density": min(0.8, current + 0.12)}})
    if "50mm" in text or "50 mm" in text:
        shot_id = plan["camera_plan"]["shots"][0]["id"]
        actions.append({"tool_id": "camera.update_shot", "parameters": {"shot_id": shot_id, "focal_length_mm": 50}})
    return actions


def plan_actions(
    user_prompt: str,
    plan: dict[str, Any],
    schema: dict[str, Any],
    api_key: str | None = None,
    model: str = "deepseek-v4-flash",
) -> tuple[list[dict[str, Any]], str]:
    tools = implemented_tools(schema)
    key = (os.environ.get("SCENE_PLANNER_API_KEY", "") if api_key is None else api_key).strip()
    if not key:
        actions = rules_fallback(user_prompt, plan)
        if not actions:
            raise ValueError("未配置 SCENE_PLANNER_API_KEY，且该描述超出本地演示规则")
        return actions, "local-rules-fallback"
    prompt = (
        "You convert one Chinese architectural visualization edit request into safe tool actions. "
        "Return JSON only: {\"summary\":string,\"actions\":[{\"tool_id\":string,\"parameters\":object}]}. "
        "Use only listed implemented tools. Include only parameters explicitly needed. Never redesign geometry.\n\n"
        f"USER_REQUEST:{json.dumps(user_prompt, ensure_ascii=False)}\n"
        f"CURRENT_PLAN:{json.dumps(plan, ensure_ascii=False)}\n"
        f"TOOLS:{json.dumps(tools, ensure_ascii=False)}"
    )
    result = call_deepseek(prompt, key, model)
    actions = result.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("DeepSeek 没有返回可执行动作")
    return actions, model
