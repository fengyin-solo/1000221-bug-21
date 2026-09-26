"""角色选角业务规则：状态流转、字段校验与筛选口径都收在这里。

列表查询与导出共用 :meth:`apply_filters`，保证页面看到的结果和导出清单
始终是同一套条件；动作执行采用“先校验、后写入”，失败时不会改动原记录，
重试时会保留已有字段（例如角色说明）。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.store import store

MODULE = "casting"
REQUIRED_FIELDS = ["角色编号", "角色名称", "角色类型"]
LIST_FIELDS = [
    "角色编号",
    "角色名称",
    "角色类型",
    "候选演员",
    "试镜日期",
    "片酬区间",
    "签约状态",
    "角色说明",
]
# 允许随动作提交、并在重试时回填的可编辑字段
EDITABLE_FIELDS = [
    "候选演员",
    "试镜日期",
    "片酬区间",
    "签约状态",
    "角色说明",
    "选中演员",
]
STATUS_ORDER = ["待试镜", "试镜中", "已定角", "已换角"]
# 已定角、已换角都视为已了结，不再计入待处理
TERMINAL_STATUSES = ["已定角", "已换角"]
ACTION_RULES = {"安排试镜": "试镜中", "确认定角": "已定角", "更换演员": "已换角"}
NEGATIVE_ACTIONS = []


def _has_value(value: Any) -> bool:
    """空字符串、纯空白都视为没填，不能用来覆盖已有内容。"""
    return value is not None and str(value).strip() != ""


class CastingService:
    def list_entries(
        self,
        *,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self.apply_filters(filters)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [dict(row) for row in rows[start:start + size]], total

    def apply_filters(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        """查询、列表视图、导出共用同一套过滤口径。

        支持按角色编号关键字（``keyword``）、流程状态（``status``）以及任意
        中文字段做包含匹配；空条件直接忽略。
        """
        filters = {key: value for key, value in (filters or {}).items() if _has_value(value)}
        rows = [dict(row) for row in store.rows(MODULE)]
        for key, raw in filters.items():
            value = str(raw).strip()
            if not value:
                continue
            if key == "keyword":
                rows = [row for row in rows if value in str(row.get("角色编号", ""))]
            elif key == "status":
                rows = [row for row in rows if row.get("status") == value]
            elif key in LIST_FIELDS:
                rows = [row for row in rows if value in str(row.get(key, ""))]
        return rows

    def stats(self) -> dict[str, int]:
        """页面卡片用的汇总数字，始终按全量数据计算，不受筛选影响。"""
        rows = store.rows(MODULE)
        return {
            "待定角色": sum(1 for row in rows if row.get("status") in ("待试镜", "试镜中")),
            "已定角角色": sum(1 for row in rows if row.get("status") == "已定角"),
            "试镜中角色": sum(1 for row in rows if row.get("status") == "试镜中"),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 选填字段一并落库，避免“角色说明”等内容登记后被静默丢弃
        for field in EDITABLE_FIELDS:
            if _has_value(values.get(field)):
                entry[field] = values[field]
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"角色 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于角色选角可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        values = values or {}
        # 先在副本上完成所有校验与字段合并，确认无误再写回，保证失败不污染原记录
        updated = deepcopy(entry)
        for field in EDITABLE_FIELDS:
            if _has_value(values.get(field)):
                updated[field] = values[field]

        candidates = [item.strip() for item in str(updated.get("候选演员") or "").split(",") if item.strip()]
        selected = str(updated.get("选中演员") or "").strip()
        if action == "确认定角":
            if not candidates and not selected:
                return None, "该角色还没有候选演员，无法确认定角，请先补充候选演员"
            if selected and candidates and selected not in candidates:
                return None, f"选中演员「{selected}」不在候选演员名单内，请核对后重试"
            if not selected:
                # 未显式指定时取第一位候选，作为定角结果
                updated["选中演员"] = candidates[0]
        elif action == "更换演员" and selected:
            if candidates and selected not in candidates:
                return None, f"更换演员「{selected}」不在候选演员名单内，请核对后重试"

        updated["status"] = target
        updated["pending"] = target not in TERMINAL_STATUSES
        updated["abnormal"] = action in NEGATIVE_ACTIONS
        entry.clear()
        entry.update(updated)
        return entry, f"角色已{action}"

    def export_entries(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        """导出与列表同条件；已定角/已换角的角色只保留实际选中的演员。"""
        rows = self.apply_filters(filters)
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            selected = str(item.get("选中演员") or "").strip()
            if item.get("status") in TERMINAL_STATUSES:
                item["候选演员"] = selected or str(item.get("候选演员") or "")
            items.append(item)
        return items, len(items)
