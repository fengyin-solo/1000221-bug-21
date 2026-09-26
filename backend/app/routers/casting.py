"""角色选角接口：维护角色，覆盖安排试镜、确认定角、更换演员等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.casting import LIST_FIELDS, CastingService

router = APIRouter(prefix="/api/casting", tags=["角色选角"])

service = CastingService()

STATUSES = ["待试镜", "试镜中", "已定角", "已换角"]


def _collect_filters(request: Request, keyword: str | None, status: str | None) -> dict[str, Any]:
    """列表与导出共用：把角色编号关键字、流程状态和中文字段筛选统一收口。"""
    filters: dict[str, Any] = {}
    if keyword:
        filters["keyword"] = keyword
    if status:
        filters["status"] = status
    for field in LIST_FIELDS:
        value = request.query_params.get(field)
        if value and value.strip():
            filters[field] = value.strip()
    return filters


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    keyword: str | None = Query(default=None, description="按角色编号检索"),
    status: str | None = Query(default=None, description="待试镜、试镜中、已定角、已换角"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按角色编号、状态、试镜日期、候选演员等条件过滤角色选角列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    filters = _collect_filters(request, keyword, status)
    items, total = service.list_entries(filters=filters, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size, stats=service.stats())


# 注意：/export 必须在 /{entry_id} 之前注册，否则会被明细路由当作 entry_id 匹配
@router.get("/export")
def export_entries(request: Request) -> dict[str, Any]:
    """导出角色选角清单：与列表页使用完全相同的过滤条件，只导出当前筛选结果。"""
    filters = _collect_filters(
        request,
        request.query_params.get("keyword"),
        request.query_params.get("status"),
    )
    items, total = service.export_entries(filters=filters)
    return {"module": "casting", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条角色明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"角色 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条角色，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="角色已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条角色执行安排试镜、确认定角、更换演员；不允许的动作会被拦下并说明原因。

    提交的试镜日期、候选演员、角色说明等字段会与原记录合并（空值不覆盖），
    校验失败时直接返回，不会改动已有记录。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
