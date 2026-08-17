#!/usr/bin/env python3
"""Local-only API used by the architectural visualization desktop client."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "sdcc_demo"
PLAN_PATH = ROOT / "outputs/planning/sdcc.landscape_demo.plan.json"
REVISION_ROOT = ROOT / "outputs/desktop_projects" / PROJECT_ID / "revisions"
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


def project_payload() -> dict[str, Any]:
    return {
        "id": PROJECT_ID,
        "name": "SDCC 建筑可视化演示",
        "status": "ready",
        "source_model_url": "/api/files/sdcc/building.obj",
        "source_texture_url": "/api/files/sdcc/baked_building.png",
        "staged_model_url": "/api/files/sdcc/building.obj",
        "render_preview_url": "/api/files/executor/sdcc.landscape_demo.preview.png",
        "plan_url": "/api/plan",
    }


def ensure_initial_revision() -> None:
    with REVISION_LOCK:
        REVISION_ROOT.mkdir(parents=True, exist_ok=True)
        if any(REVISION_ROOT.glob("rev_*.json")):
            return
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8")) if PLAN_PATH.exists() else {}
        save_revision("初始化项目", "导入模型并建立第一版场景计划", plan)


def save_revision(title: str, prompt: str, plan: dict[str, Any]) -> dict[str, Any]:
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
            "plan": plan,
        }
        path = REVISION_ROOT / f"rev_{number:04d}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(revision, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return revision


def read_revisions() -> list[dict[str, Any]]:
    with REVISION_LOCK:
        ensure_initial_revision()
        values = [json.loads(path.read_text(encoding="utf-8")) for path in REVISION_ROOT.glob("rev_*.json")]
    return sorted(values, key=lambda item: item["number"], reverse=True)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects/current")
def current_project() -> dict[str, Any]:
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
def create_prompt_preview(request: PromptRequest) -> dict[str, Any]:
    """Create an auditable draft revision; Blender execution is attached next."""
    current = read_revisions()[0]
    revision = save_revision("提示词修改（待执行）", request.prompt.strip(), current.get("plan", {}))
    return {
        "revision": revision,
        "status": "draft",
        "message": "修改已保存。下一阶段会在此处触发 Blender 预览任务。",
    }


@app.post("/api/revisions/{revision_id}/restore")
def restore_revision(revision_id: str) -> dict[str, Any]:
    selected = next((item for item in read_revisions() if item["id"] == revision_id), None)
    if selected is None:
        raise HTTPException(404, "找不到该版本")
    return save_revision(f"恢复 {revision_id}", f"恢复到 {revision_id} 的设置", selected.get("plan", {}))


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
