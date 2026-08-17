#!/usr/bin/env python3
"""Local Streamlit chat interface for the DeepSeek architectural scene planner."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from scene_planner import (
    build_template_plan,
    call_chat_completion,
    call_openai_compatible,
    planner_prompt,
    validate_inventory,
    validate_plan,
)
from plan_editor import PlanEditor, RevisionStore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "data/examples/campus_scene_inventory.json"
DEFAULT_BRIEF = ROOT / "data/examples/campus_visual_brief.json"
DEFAULT_OUTPUT = ROOT / "outputs/planning/campus_scene_plan.deepseek.ui.json"
TOOL_SCHEMA_PATH = ROOT / "schemas/blender_tools_v1.json"
ASSET_REGISTRY_PATH = ROOT / "assets/registry/asset_registry.json"
PLAYBOOK_PATH = ROOT / "playbooks/architectural_visualization_v1.json"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com"


def load_capabilities() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in (TOOL_SCHEMA_PATH, ASSET_REGISTRY_PATH, PLAYBOOK_PATH)
    )


def current_parameter(plan: dict[str, Any], tool_id: str, name: str, default: Any) -> Any:
    sections = {
        "lighting.set_sun": plan.get("lighting_plan", {}).get("sun", {}),
        "lighting.set_world": plan.get("lighting_plan", {}).get("world", {}),
        "lighting.set_windows": plan.get("lighting_plan", {}).get("windows", {}),
        "lighting.set_streetlights": plan.get("lighting_plan", {}).get("street_lights", {}),
        "landscape.configure": plan.get("landscape_plan", {}),
    }
    if tool_id == "render.configure":
        preview = plan.get("render_plan", {}).get("preview_resolution", [1280, 720])
        final = plan.get("render_plan", {}).get("final_resolution", [4096, 3072])
        return dict(preview_width=preview[0], preview_height=preview[1], final_width=final[0], final_height=final[1]).get(name, default)
    if tool_id == "postprocess.configure":
        post = plan.get("postprocess_plan", {})
        values = {
            "global_strength": (post.get("diffusion_strength") or [default])[0],
            "upscale": post.get("upscale", {}).get("scale", default),
            "tiled_refinement": post.get("upscale", {}).get("tiled_refinement", default),
        }
        return values.get(name, default)
    return sections.get(tool_id, {}).get(name, default)


def parameter_widget(tool: dict[str, Any], name: str, definition: dict[str, Any], plan: dict[str, Any]) -> Any:
    ui = definition.get("ui", {})
    label = ui.get("label", name)
    default = current_parameter(plan, tool["tool_id"], name, definition.get("default"))
    key = f"editor_{tool['tool_id']}_{name}"
    if ui.get("options_source") == "camera_shot_ids":
        choices = [shot["id"] for shot in plan["camera_plan"]["shots"]]
        return st.selectbox(label, choices, key=key)
    if "enum" in definition:
        choices = definition["enum"]
        return st.selectbox(label, choices, index=choices.index(default) if default in choices else 0, key=key)
    if definition["type"] == "boolean":
        return st.checkbox(label, value=bool(default), key=key)
    if ui.get("widget") == "slider":
        if definition["type"] == "number":
            minimum = float(definition["minimum"])
            maximum = float(definition["maximum"])
            default = float(default)
            step = float(ui.get("step", 1))
        else:
            minimum = int(definition["minimum"])
            maximum = int(definition["maximum"])
            default = int(default)
            step = int(ui.get("step", 1))
        return st.slider(label, minimum, maximum, default, step, key=key)
    if definition["type"] in {"number", "integer"}:
        return st.number_input(label, min_value=definition.get("minimum"), max_value=definition.get("maximum"), value=default, step=ui.get("step", 1), key=key)
    return st.text_input(label, value=default or "", key=key)


def read_uploaded_json(upload: Any, fallback: Path) -> dict[str, Any]:
    if upload is None:
        return json.loads(fallback.read_text(encoding="utf-8"))
    return json.loads(upload.getvalue().decode("utf-8"))


def conversation_system_prompt(inventory: dict[str, Any], brief: dict[str, Any]) -> str:
    summary = [
        {"id": item["id"], "type": item["type"], "name": item.get("name", item["id"])}
        for item in inventory["objects"]
    ]
    return f"""你是建筑效果图项目的场景规划顾问。你的任务是通过中文对话收集用户对相机、时间天气、灯光、材质、绿化、人物车辆和交付规格的要求。

规则：
1. 已有建筑、道路、运动场、围墙和场地几何属于权威设计，绝不能建议重新设计。
2. 每次最多追问一个最重要的问题，语言简洁，让非专业用户也能回答。
3. 用户不知道专业参数时，给出2到3个通俗选项并推荐一个。
4. 已经回答过的信息不要重复询问。
5. 信息足以生成第一版计划时，明确回复“信息已足够，可以点击生成场景计划”。
6. 不要输出JSON，当前阶段只进行需求访谈。

场景对象：{json.dumps(summary, ensure_ascii=False)}
初始需求：{json.dumps(brief, ensure_ascii=False)}"""


def plan_with_conversation(
    inventory: dict[str, Any],
    brief: dict[str, Any],
    messages: list[dict[str, str]],
    api_key: str,
    model: str,
    thinking: str,
) -> dict[str, Any]:
    enriched_brief = dict(brief)
    enriched_brief["user_conversation"] = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] in {"user", "assistant"}
    ]
    template = build_template_plan(inventory, enriched_brief)
    tool_schema, asset_registry, playbook = load_capabilities()
    plan = call_openai_compatible(
        DEEPSEEK_ENDPOINT,
        api_key,
        model,
        planner_prompt(inventory, enriched_brief, template, tool_schema, asset_registry, playbook),
        thinking=thinking,
    )
    validate_plan(plan, inventory)
    plan["generated_at"] = datetime.now(timezone.utc).isoformat()
    plan["planner"] = {"provider": "deepseek", "model": model, "interface": "streamlit-chat"}
    return plan


st.set_page_config(page_title="建筑效果图 Scene Planner", page_icon="🏫", layout="wide")
st.title("建筑效果图 Scene Planner")
st.caption("与 DeepSeek 对话确认表现需求，再生成可由 Blender Executor 执行的场景计划。")

with st.sidebar:
    st.header("连接与项目")
    environment_api_key = os.environ.get("SCENE_PLANNER_API_KEY", "").strip()
    if environment_api_key:
        api_key = environment_api_key
        st.success("已从环境变量读取 DeepSeek API Key")
        st.caption("界面不会显示、保存或返回该密钥。")
    else:
        api_key = st.text_input(
            "DeepSeek API Key",
            type="password",
            help="未检测到 SCENE_PLANNER_API_KEY；输入值仅保存在当前页面会话。",
        )
    model = st.selectbox("模型", ["deepseek-v4-flash", "deepseek-v4-pro"], index=0)
    thinking = st.selectbox("思考模式", ["disabled", "enabled"], index=0)
    inventory_upload = st.file_uploader("场景清单 JSON（可选）", type=["json"], key="inventory")
    brief_upload = st.file_uploader("初始需求 JSON（可选）", type=["json"], key="brief")
    output_path_text = st.text_input("输出文件", value=str(DEFAULT_OUTPUT))
    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.plan = None
        st.rerun()

try:
    inventory = read_uploaded_json(inventory_upload, DEFAULT_INVENTORY)
    brief = read_uploaded_json(brief_upload, DEFAULT_BRIEF)
    validate_inventory(inventory)
except Exception as error:
    st.error(f"项目JSON无效：{error}")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "plan" not in st.session_state:
    st.session_state.plan = None

left, right = st.columns([1.35, 1])
with left:
    st.subheader("需求问答")
    if not st.session_state.messages:
        st.info("请从最直观的要求开始，例如：我想要黄昏鸟瞰图，绿化丰富但不能遮挡教学楼。")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_text = st.chat_input("输入你的效果图需求或回答 DeepSeek 的问题")
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        if not api_key:
            st.error("请先在左侧输入 DeepSeek API Key。")
            st.stop()
        api_messages = [
            {"role": "system", "content": conversation_system_prompt(inventory, brief)},
            *st.session_state.messages,
        ]
        try:
            with st.spinner("DeepSeek 正在分析需求……"):
                answer = call_chat_completion(
                    DEEPSEEK_ENDPOINT,
                    api_key,
                    model,
                    api_messages,
                    thinking=thinking,
                )
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.rerun()
        except Exception as error:
            st.error(f"DeepSeek 调用失败：{error}")

with right:
    st.subheader("场景计划")
    st.write(f"场景对象：{len(inventory['objects'])} 个")
    st.write(f"已完成对话：{sum(1 for item in st.session_state.messages if item['role'] == 'user')} 轮")
    generate_disabled = not api_key or not any(item["role"] == "user" for item in st.session_state.messages)
    if st.button("生成场景计划", type="primary", disabled=generate_disabled, use_container_width=True):
        try:
            with st.spinner("DeepSeek 正在生成并校验场景计划……"):
                plan = plan_with_conversation(
                    inventory, brief, st.session_state.messages, api_key, model, thinking
                )
            output_path = Path(output_path_text).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            st.session_state.plan = plan
            revision_root = ROOT / "outputs/planning/ui_revisions" / plan["project"]["name"]
            RevisionStore(revision_root).initialize(plan)
            st.success(f"已保存：{output_path}")
        except Exception as error:
            st.error(f"计划生成或校验失败：{error}")

    if st.session_state.plan:
        st.divider()
        st.subheader("局部调整")
        tool_schema, _, _ = load_capabilities()
        tools = tool_schema["tools"]
        selected_label = st.selectbox(
            "调整项目",
            [tool["ui"]["label"] for tool in tools],
            key="selected_editor_tool",
        )
        selected_tool = next(tool for tool in tools if tool["ui"]["label"] == selected_label)
        status = selected_tool["executor_status"]
        st.caption("可立即生成 Blender 预览" if status == "implemented" else "计划字段已接入，Blender执行能力仍在开发")
        parameters = {
            name: parameter_widget(selected_tool, name, definition, st.session_state.plan)
            for name, definition in selected_tool["parameters"].items()
        }
        edit_col, undo_col = st.columns(2)
        output_path = Path(output_path_text).expanduser()
        revision_root = ROOT / "outputs/planning/ui_revisions" / st.session_state.plan["project"]["name"]
        store = RevisionStore(revision_root)
        with edit_col:
            if st.button("应用局部修改", type="primary", use_container_width=True):
                try:
                    updated = PlanEditor(tool_schema).apply(st.session_state.plan, selected_tool["tool_id"], parameters)
                    validate_plan(updated, inventory)
                    store.initialize(st.session_state.plan)
                    store.commit(updated, f"frontend:{selected_tool['tool_id']}")
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
                    st.session_state.plan = updated
                    st.success("局部修改已保存为新版本。")
                    st.rerun()
                except Exception as error:
                    st.error(f"修改失败：{error}")
        with undo_col:
            if st.button("撤销上一步", use_container_width=True):
                try:
                    previous = store.undo()
                    output_path.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
                    st.session_state.plan = previous
                    st.success("已恢复上一个版本。")
                    st.rerun()
                except Exception as error:
                    st.warning(str(error))

        plan_text = json.dumps(st.session_state.plan, ensure_ascii=False, indent=2)
        st.download_button(
            "下载 scene_plan.json",
            data=plan_text,
            file_name="scene_plan.json",
            mime="application/json",
            use_container_width=True,
        )
        st.json(st.session_state.plan, expanded=False)
    else:
        st.caption("完成几轮问答后点击生成。规划会经过对象ID和结构合法性校验。")
