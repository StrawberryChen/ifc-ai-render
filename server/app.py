#!/usr/bin/env python3
"""Local-only API used by the architectural visualization desktop client."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from planning.action_planner import plan_actions
from planning.plan_editor import PlanEditor
from planning.scene_planner import validate_plan


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "sdcc_demo"
PLAN_PATH = ROOT / "outputs/planning/sdcc.landscape_demo.plan.json"
MANIFEST_PATH = ROOT / "outputs/manifests/sdcc.landscape_demo.manifest.json"
SOURCE_BLEND = ROOT / "outputs/sdcc/sdcc.scene.blend"
REVISION_ROOT = ROOT / "outputs/desktop_projects" / PROJECT_ID / "revisions"
PROJECT_ROOT = ROOT / "outputs/desktop_projects" / PROJECT_ID
TOOL_SCHEMA_PATH = ROOT / "schemas/blender_tools_v1.json"
DEFAULT_STAGED_BLEND = ROOT / "outputs/executor/sdcc.landscape_demo.blend"
REVISION_LOCK = threading.RLock()

app = FastAPI(title="IFC AI Render Desktop API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=2000)


class CameraViewRequest(BaseModel):
    azimuth_deg: float = Field(ge=0, le=360)
    elevation_deg: float = Field(ge=8, le=80)
    distance_multiplier: float = Field(ge=0.25, le=12)
    focal_length_mm: float = Field(default=45, ge=18, le=120)


def project_payload() -> dict[str, Any]:
    return {
        "id": PROJECT_ID,
        "name": "SDCC 建筑可视化演示",
        "status": "ready",
        "source_model_url": "/api/project-files/models/source.glb",
        "staged_model_url": "/api/project-files/models/staged.glb",
        "render_preview_url": "/api/files/executor/sdcc.landscape_demo.preview.png",
        "environment_url": "/api/asset-files/downloads/polyhaven/belfast_sunset_puresky/environment.hdr",
        "plan_url": "/api/plan",
        "planner_mode": "deepseek" if os.environ.get("SCENE_PLANNER_API_KEY", "").strip() else "local-rules",
    }


def ensure_web_models() -> None:
    blender = Path(os.environ.get("BLENDER_EXECUTABLE", "/Applications/Blender.app/Contents/MacOS/Blender"))
    models = [(SOURCE_BLEND, PROJECT_ROOT / "models/source.glb"), (DEFAULT_STAGED_BLEND, PROJECT_ROOT / "models/staged.glb")]
    for blend, target in models:
        if target.exists() or not blend.exists() or not blender.exists():
            continue
        subprocess.run([
            str(blender), "-b", str(blend), "--python", str(ROOT / "blender/export_web_preview.py"), "--",
            "--output", str(target),
        ], cwd=ROOT, check=True, timeout=180, capture_output=True, text=True)


def ensure_initial_revision() -> None:
    with REVISION_LOCK:
        REVISION_ROOT.mkdir(parents=True, exist_ok=True)
        if any(REVISION_ROOT.glob("rev_*.json")):
            return
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8")) if PLAN_PATH.exists() else {}
        save_revision("初始化项目", "导入模型并建立第一版场景计划", plan)


def save_revision(
    title: str,
    prompt: str,
    plan: dict[str, Any],
    *,
    status: str = "ready",
    actions: list[dict[str, Any]] | None = None,
    planner: str = "initial",
) -> dict[str, Any]:
    with REVISION_LOCK:
        REVISION_ROOT.mkdir(parents=True, exist_ok=True)
        number = len(list(REVISION_ROOT.glob("rev_*.json"))) + 1
        revision = {
            "id": f"V{number}",
            "number": number,
            "title": title,
            "prompt": prompt,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "preview_url": "/api/files/executor/sdcc.landscape_demo.preview.png",
            "status": status,
            "actions": actions or [],
            "planner": planner,
            "plan": plan,
        }
        path = REVISION_ROOT / f"rev_{number:04d}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(revision, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return revision


def update_revision(revision: dict[str, Any]) -> None:
    with REVISION_LOCK:
        path = REVISION_ROOT / f"rev_{revision['number']:04d}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(revision, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def run_blender_preview(revision: dict[str, Any]) -> None:
    number = revision["number"]
    run_root = PROJECT_ROOT / "runs" / f"rev_{number:04d}"
    run_root.mkdir(parents=True, exist_ok=True)
    plan_path = run_root / "scene_plan.json"
    blend_path = run_root / "scene.blend"
    report_path = run_root / "execution_report.json"
    preview_path = run_root / "preview.png"
    staged_path = PROJECT_ROOT / "models/staged.glb"
    plan_path.write_text(json.dumps(revision["plan"], ensure_ascii=False, indent=2), encoding="utf-8")
    blender = Path(os.environ.get("BLENDER_EXECUTABLE", "/Applications/Blender.app/Contents/MacOS/Blender"))
    try:
        subprocess.run([
            str(blender), "-b", str(SOURCE_BLEND), "--python", str(ROOT / "blender/scene_executor.py"), "--",
            "--manifest", str(MANIFEST_PATH), "--plan", str(plan_path), "--output-blend", str(blend_path),
            "--report", str(report_path), "--preview", str(preview_path),
        ], cwd=ROOT, check=True, timeout=300, capture_output=True, text=True)
        subprocess.run([
            str(blender), "-b", str(blend_path), "--python", str(ROOT / "blender/export_web_preview.py"), "--",
            "--output", str(staged_path),
        ], cwd=ROOT, check=True, timeout=180, capture_output=True, text=True)
        revision["status"] = "ready"
        revision["preview_url"] = f"/api/project-files/runs/rev_{number:04d}/preview.png"
        revision["staged_model_url"] = "/api/project-files/models/staged.glb"
    except Exception as error:
        revision["status"] = "failed"
        revision["error"] = str(error)
    update_revision(revision)


def read_revisions() -> list[dict[str, Any]]:
    with REVISION_LOCK:
        ensure_initial_revision()
        values = [json.loads(path.read_text(encoding="utf-8")) for path in REVISION_ROOT.glob("rev_*.json")]
        for value in values:
            value.setdefault("status", "ready")
            value.setdefault("actions", [])
            value.setdefault("planner", "legacy")
    return sorted(values, key=lambda item: item["number"], reverse=True)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects/current")
def current_project() -> dict[str, Any]:
    ensure_web_models()
    ensure_initial_revision()
    return project_payload()


@app.get("/api/plan")
def current_plan() -> dict[str, Any]:
    if not PLAN_PATH.exists():
        raise HTTPException(404, "当前项目还没有 Scene Plan")
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


@app.get("/api/revisions")
def revisions(limit: int = 5) -> list[dict[str, Any]]:
    return read_revisions()[: max(1, min(limit, 5))]


@app.post("/api/prompts/preview")
def create_prompt_preview(request: PromptRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Translate a prompt, patch the plan, and enqueue a Blender preview."""
    current = read_revisions()[0]
    schema = json.loads(TOOL_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        actions, planner = plan_actions(request.prompt.strip(), current.get("plan", {}), schema)
        editor = PlanEditor(schema)
        updated_plan = current.get("plan", {})
        for action in actions:
            updated_plan = editor.apply(updated_plan, action["tool_id"], action.get("parameters", {}))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        validate_plan(updated_plan, manifest)
    except Exception as error:
        raise HTTPException(422, str(error)) from error
    revision = save_revision(
        "AI 场景调整",
        request.prompt.strip(),
        updated_plan,
        status="rendering",
        actions=actions,
        planner=planner,
    )
    background_tasks.add_task(run_blender_preview, revision)
    return {
        "revision": revision,
        "status": "rendering",
        "message": f"已生成 {len(actions)} 个受控动作，Blender 正在生成快速预览。",
    }


@app.post("/api/camera/render")
def render_camera_view(request: CameraViewRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    current = read_revisions()[0]
    plan = current.get("plan", {})
    shot_id = plan["camera_plan"]["shots"][0]["id"]
    action = {
        "tool_id": "camera.update_shot",
        "parameters": {
            "shot_id": shot_id,
            "azimuth_deg": request.azimuth_deg,
            "elevation_deg": request.elevation_deg,
            "distance_multiplier": request.distance_multiplier,
            "focal_length_mm": request.focal_length_mm,
        },
    }
    schema = json.loads(TOOL_SCHEMA_PATH.read_text(encoding="utf-8"))
    updated_plan = PlanEditor(schema).apply(plan, action["tool_id"], action["parameters"])
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    validate_plan(updated_plan, manifest)
    revision = save_revision(
        "三维视角渲染",
        f"使用布景模型视角：方位 {request.azimuth_deg:.0f}°，俯角 {request.elevation_deg:.0f}°",
        updated_plan,
        status="rendering",
        actions=[action],
        planner="frontend-3d-camera",
    )
    background_tasks.add_task(run_blender_preview, revision)
    return {"revision": revision, "status": "rendering", "message": "视角已写入场景计划，Blender 正在渲染。"}


@app.post("/api/revisions/{revision_id}/restore")
def restore_revision(revision_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    selected = next((item for item in read_revisions() if item["id"] == revision_id), None)
    if selected is None:
        raise HTTPException(404, "找不到该版本")
    revision = save_revision(
        f"恢复 {revision_id}",
        f"恢复到 {revision_id} 的设置",
        selected.get("plan", {}),
        status="rendering",
        planner="version-restore",
    )
    background_tasks.add_task(run_blender_preview, revision)
    return revision


@app.get("/api/files/{folder}/{filename}")
def project_file(folder: str, filename: str) -> FileResponse:
    allowed = {
        "sdcc": ROOT / "data/sdcc",
        "executor": ROOT / "outputs/executor",
    }
    if folder not in allowed:
        raise HTTPException(404, "未知文件区域")
    base = allowed[folder].resolve()
    path = (base / filename).resolve()
    if path.parent != base or not path.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path)


@app.get("/api/project-files/{path:path}")
def desktop_project_file(path: str) -> FileResponse:
    base = PROJECT_ROOT.resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404, "项目文件不存在")
    return FileResponse(target, headers={"Cache-Control": "no-cache"})


@app.get("/api/asset-files/{path:path}")
def asset_file(path: str) -> FileResponse:
    base = (ROOT / "assets").resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404, "资产文件不存在")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=86400"})
