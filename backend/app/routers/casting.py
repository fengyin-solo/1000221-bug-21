"""角色选角接口：维护角色，覆盖安排试镜、确认定角、更换演员等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.casting import FILTER_FIELDS, CastingService

router = APIRouter(prefix="/api/casting", tags=["角色选角"])

service = CastingService()

LIST_FIELDS = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]
STATUSES = ["待试镜", "试镜中", "已定角", "已换角"]


def _read_filters(request: Request) -> tuple[str | None, str | None, dict[str, str]]:
    """从查询串里解析同一套筛选条件，列表与导出共用，保证口径一致。"""
    keyword = request.query_params.get("keyword")
    status = request.query_params.get("status")
    filters = {
        field: value
        for field in FILTER_FIELDS
        if (value := request.query_params.get(field)) is not None
    }
    return keyword, status, filters


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按角色编号、候选演员、试镜日期等条件过滤角色选角列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    keyword, status, filters = _read_filters(request)
    items, total = service.list_entries(
        keyword=keyword, status=status, filters=filters, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export 必须在 /{entry_id} 之前注册，否则会被动态路径当作 entry_id="export"。
@router.get("/export")
def export_entries(request: Request) -> dict[str, Any]:
    """导出角色选角清单：与列表页使用完全相同的过滤条件，只导出当前筛选下的角色。"""
    keyword, status, filters = _read_filters(request)
    items, total = service.list_entries(
        keyword=keyword, status=status, filters=filters, page=1, size=10000
    )
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


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """在原角色上非破坏性地补录/重试：留空字段沿用原值，校验不过时原记录保持不动。"""
    if service.get_entry(entry_id) is None:
        return ActionResult(ok=False, message=f"角色 {entry_id} 不存在或已归档")
    entry, missing = service.update_entry(entry_id, payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}", entry=entry)
    return ActionResult(ok=True, message="角色信息已更新", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条角色执行安排试镜、确认定角、更换演员；不允许的动作会被拦下并说明原因。

    动作同时可以携带试镜日期、候选演员、角色说明等字段，先做非破坏性合并再流转状态，
    因此重试时已填写的角色说明不会丢失，校验失败也不会改动原记录。
    """
    values = dict(payload.values)
    action = str(values.pop("action", "") or "").strip()
    entry, message = service.run_action(entry_id, action, values=values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
