from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import PurePosixPath
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, WebSocket
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.analysis import ANALYSIS_TYPES, run_analysis
from src.api.auth import (
    COOKIE_NAME,
    create_web_session,
    delete_web_session,
    find_or_create_sso_user,
    login_audit,
    require_admin,
    require_api_user,
    websocket_user,
)
from src.api.serialization import analysis_output_public, dataset_public
from src.auth.service import authenticate, list_users, set_user_active
from src.config import get_settings
from src.services.arc_stream import (
    ArcChannelRef,
    ensure_arc_stream_task,
    get_arc_stream_output,
    get_arc_stream_snapshot,
)
from src.services.datasets import (
    get_dataset,
    hydrate_dataset_metadata,
    list_datasets,
    load_channel,
    scan_datasets,
)
from src.services.jobs import (
    create_job,
    get_artifacts,
    list_jobs,
    mark_running,
    read_artifact,
    render_figure_bytes,
    save_job_result,
)

router = APIRouter()
API_USER = Depends(require_api_user)


class LoginRequest(BaseModel):
    username: str
    password: str


class PreviewRequest(BaseModel):
    dataset_id: int
    channel: str
    analysis_type: str
    start: int = 0
    end: int | None = None
    sample_rate: float | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ArcChannelRequest(BaseModel):
    dataset_id: int
    channel: str
    label: str


class ArcTaskRequest(BaseModel):
    channels: list[ArcChannelRequest]
    sample_rate: float | None = None
    probability_threshold: float = Field(default=0.5, ge=0, le=1)
    required_arc_halfwaves: int = Field(default=3, ge=1)


class SaveArcRequest(BaseModel):
    task_id: str


class UserStatusRequest(BaseModel):
    active: bool


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "analysis-api"}


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    user = authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(401, "用户名或密码错误。")
    create_web_session(user["id"], response)
    login_audit(user, "local")
    return {"user": user}


@router.post("/auth/logout")
def logout(
    response: Response,
    analysis_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> dict[str, bool]:
    # Query support is kept for API clients; browsers use the HttpOnly cookie below.
    delete_web_session(analysis_session, response)
    return {"ok": True}


@router.get("/auth/me")
def me(user: dict[str, Any] = API_USER) -> dict[str, Any]:
    settings = get_settings()
    return {
        "user": user,
        "managerUrl": settings.manager_url,
        "ssoEnabled": bool(settings.manager_sso_verify_url),
    }


@router.get("/auth/sso/callback")
async def sso_callback(ticket: str) -> RedirectResponse:
    settings = get_settings()
    if not settings.manager_sso_verify_url:
        raise HTTPException(503, "尚未配置 test-manager SSO 验证接口。")
    headers = {"Accept": "application/json"}
    if settings.manager_sso_shared_secret:
        headers["X-SSO-Secret"] = settings.manager_sso_shared_secret
    async with httpx.AsyncClient(timeout=10) as client:
        verification = await client.post(
            settings.manager_sso_verify_url,
            json={"ticket": ticket, "target": "analysis"},
            headers=headers,
        )
    if verification.status_code != 200:
        raise HTTPException(401, "test-manager 登录凭证无效或已经过期。")
    profile = verification.json()
    if isinstance(profile.get("data"), dict):
        profile = profile["data"]
    user = find_or_create_sso_user(profile)
    response = RedirectResponse("/analysis/#/dashboard", status_code=303)
    create_web_session(user["id"], response)
    login_audit(user, "test-manager-sso")
    return response


@router.get("/datasets")
def datasets(
    search: str = "",
    status: Literal["ready", "pending", "error", "missing"] | None = "ready",
    user: dict[str, Any] = API_USER,
) -> dict[str, Any]:
    del user
    items = list_datasets(search=search, status=status)
    return {"items": [dataset_public(item) for item in items], "total": len(items)}


@router.get("/datasets/tree")
def dataset_tree(user: dict[str, Any] = API_USER) -> dict[str, Any]:
    del user
    root: dict[str, Any] = {"children": {}}
    for item in list_datasets(status="ready"):
        parts = PurePosixPath(str(item["relative_path"]).replace("\\", "/")).parts
        cursor = root
        for part in parts[:-1]:
            cursor = cursor["children"].setdefault(part, {"children": {}, "files": []})
        cursor.setdefault("files", []).append(dataset_public(item))

    def serialize(name: str, node: dict[str, Any], prefix: str) -> dict[str, Any]:
        path = f"{prefix}/{name}" if prefix else name
        children = [
            serialize(child_name, child, path)
            for child_name, child in sorted(node.get("children", {}).items())
        ]
        children.extend(
            {
                "key": f"file:{item['id']}",
                "title": item["name"],
                "isLeaf": True,
                "dataset": item,
            }
            for item in node.get("files", [])
        )
        return {"key": f"folder:{path}", "title": name, "children": children}

    nodes = [
        serialize(name, node, "") for name, node in sorted(root["children"].items())
    ]
    return {"nodes": nodes}


@router.get("/datasets/{dataset_id}")
def dataset_detail(
    dataset_id: int, user: dict[str, Any] = API_USER
) -> dict[str, Any]:
    del user
    item = get_dataset(dataset_id)
    if item is None:
        raise HTTPException(404, "数据文件不存在。")
    if item["metadata"].get("metadata_pending"):
        item = hydrate_dataset_metadata(dataset_id)
    return {"dataset": dataset_public(item)}


@router.post("/datasets/scan")
async def scan(user: dict[str, Any] = API_USER) -> dict[str, int]:
    require_admin(user)
    return await run_in_threadpool(scan_datasets, user["id"])


def _preview(payload: PreviewRequest):
    if payload.analysis_type not in ANALYSIS_TYPES or payload.analysis_type == "arc_features":
        raise ValueError("该分析方法不支持普通预览接口。")
    dataset = get_dataset(payload.dataset_id)
    if dataset is None or dataset["status"] != "ready":
        raise ValueError("数据文件不存在或尚未就绪。")
    metadata = dataset["metadata"]
    shape = metadata.get("shapes", {}).get(payload.channel)
    total = int(math.prod(shape) if shape else metadata.get("total_samples", 0))
    end = min(total, payload.end or total)
    if end <= payload.start:
        raise ValueError("分析结束位置必须大于开始位置。")
    values, detected_rate = load_channel(payload.dataset_id, payload.channel, payload.start, end)
    sample_rate = float(payload.sample_rate or detected_rate or metadata.get("sample_rate") or 1e6)
    parameters = dict(payload.parameters)
    if payload.analysis_type == "waveform":
        parameters.update(
            {"max_output_points": 20_000, "time_offset": payload.start / sample_rate}
        )
    return run_analysis(payload.analysis_type, values, sample_rate, parameters)


@router.post("/analysis/preview")
async def analysis_preview(
    payload: PreviewRequest, user: dict[str, Any] = API_USER
) -> dict[str, Any]:
    del user
    try:
        output = await run_in_threadpool(_preview, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return analysis_output_public(output)


@router.get("/analysis/types")
def analysis_types(user: dict[str, Any] = API_USER) -> dict[str, Any]:
    del user
    return {
        "items": [
            {"key": key, "label": value["label"], "description": value["description"]}
            for key, value in ANALYSIS_TYPES.items()
            if key != "arc_features"
        ]
    }


@router.post("/arc/tasks")
def start_arc_task(
    payload: ArcTaskRequest, user: dict[str, Any] = API_USER
) -> dict[str, Any]:
    del user
    if not payload.channels:
        raise HTTPException(400, "至少选择一个通道。")
    refs: list[ArcChannelRef] = []
    detected_rates: list[float] = []
    for selection in payload.channels:
        dataset = get_dataset(selection.dataset_id)
        if dataset is None or dataset["status"] != "ready":
            raise HTTPException(400, f"数据文件 {selection.dataset_id} 尚未就绪。")
        metadata = dataset["metadata"]
        if selection.channel not in metadata.get("channels", []):
            raise HTTPException(400, f"{selection.channel} 不是有效通道。")
        shape = metadata.get("shapes", {}).get(selection.channel)
        total_samples = int(math.prod(shape) if shape else metadata.get("total_samples", 0))
        refs.append(
            (
                selection.dataset_id,
                str(dataset["modified_at"]),
                selection.channel,
                selection.label,
                total_samples,
            )
        )
        if metadata.get("sample_rate"):
            detected_rates.append(float(metadata["sample_rate"]))
    sample_rate = float(payload.sample_rate or (detected_rates[0] if detected_rates else 2e6))
    parameters = {
        "probability_threshold": payload.probability_threshold,
        "required_arc_halfwaves": payload.required_arc_halfwaves,
    }
    source = json.dumps(
        {"refs": refs, "sample_rate": sample_rate, "parameters": parameters},
        ensure_ascii=False,
        sort_keys=True,
    )
    task_id = hashlib.sha256(source.encode("utf-8")).hexdigest()
    ensure_arc_stream_task(task_id, tuple(refs), sample_rate, parameters)
    return {"taskId": task_id, "snapshot": get_arc_stream_snapshot(task_id)}


@router.get("/arc/tasks/{task_id}")
def arc_task(
    task_id: str, user: dict[str, Any] = API_USER
) -> dict[str, Any]:
    del user
    snapshot = get_arc_stream_snapshot(task_id)
    if snapshot["status"] == "missing":
        raise HTTPException(404, "检测任务不存在或已经过期。")
    return {"snapshot": snapshot}


@router.websocket("/arc/tasks/{task_id}/stream")
async def arc_task_stream(websocket: WebSocket, task_id: str) -> None:
    user = await websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    last_signature: tuple[Any, ...] | None = None
    try:
        while True:
            snapshot = get_arc_stream_snapshot(task_id)
            signature = (snapshot["status"], snapshot["processed"], snapshot.get("error"))
            if signature != last_signature:
                await websocket.send_json({"snapshot": snapshot})
                last_signature = signature
            if snapshot["status"] in {"completed", "error", "cancelled", "missing"}:
                break
            await asyncio.sleep(0.2)
    finally:
        await websocket.close()


@router.get("/arc/tasks/{task_id}/result")
def arc_result(
    task_id: str,
    include_table: bool = False,
    user: dict[str, Any] = API_USER,
) -> dict[str, Any]:
    del user
    output = get_arc_stream_output(task_id)
    if output is None:
        raise HTTPException(409, "检测尚未完成。")
    return {"result": analysis_output_public(output, include_table=include_table)}


@router.post("/arc/tasks/{task_id}/save")
async def save_arc_task(
    task_id: str, user: dict[str, Any] = API_USER
) -> dict[str, Any]:
    output = get_arc_stream_output(task_id)
    snapshot = get_arc_stream_snapshot(task_id)
    if output is None or snapshot.get("source_dataset_id") is None:
        raise HTTPException(409, "检测尚未完成。")
    job_id = create_job(
        user["id"],
        int(snapshot["source_dataset_id"]),
        "arc_features",
        {"source": "vue", "task_id": task_id},
    )
    mark_running(job_id)
    artifacts = await run_in_threadpool(save_job_result, job_id, user["id"], output)
    return {"jobId": job_id, "artifacts": artifacts}


@router.get("/arc/tasks/{task_id}/export/{file_format}")
def export_arc_task(
    task_id: str,
    file_format: Literal["csv", "png"],
    user: dict[str, Any] = API_USER,
) -> Response:
    del user
    output = get_arc_stream_output(task_id)
    if output is None:
        raise HTTPException(409, "检测尚未完成。")
    if file_format == "csv":
        content = output.table.to_csv(index=False).encode("utf-8-sig")
        media_type = "text/csv"
    else:
        content = render_figure_bytes(output, "png")
        media_type = "image/png"
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="arc-result.{file_format}"'},
    )


@router.get("/jobs")
def jobs(user: dict[str, Any] = API_USER) -> dict[str, Any]:
    items = list_jobs(user["id"], is_admin=user["role"] == "admin", limit=200)
    return {"items": items, "total": len(items)}


@router.get("/jobs/{job_id}/artifacts/{artifact_id}")
def artifact_download(
    job_id: str,
    artifact_id: int,
    user: dict[str, Any] = API_USER,
) -> Response:
    artifacts = get_artifacts(job_id, user["id"], is_admin=user["role"] == "admin")
    artifact = next((item for item in artifacts if int(item["id"]) == artifact_id), None)
    if artifact is None:
        raise HTTPException(404, "结果文件不存在。")
    return Response(
        read_artifact(artifact),
        media_type=artifact["media_type"],
        headers={"Content-Disposition": f'attachment; filename="{artifact["name"]}"'},
    )


@router.get("/system/users")
def users(user: dict[str, Any] = API_USER) -> dict[str, Any]:
    require_admin(user)
    items = list_users()
    return {"items": items, "total": len(items)}


@router.put("/system/users/{user_id}/status")
def update_user_status(
    user_id: int,
    payload: UserStatusRequest,
    user: dict[str, Any] = API_USER,
) -> dict[str, bool]:
    require_admin(user)
    set_user_active(user_id, payload.active, user["id"])
    return {"ok": True}
