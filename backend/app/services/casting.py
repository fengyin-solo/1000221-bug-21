"""角色选角业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "casting"
# 列表/导出/编辑共用同一份字段口径，避免某个出口漏字段。
LIST_FIELDS = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]
REQUIRED_FIELDS = ["角色编号", "角色名称", "角色类型"]
# 可在查询与导出里作为过滤条件的字段（状态单独走 status 参数）。
FILTER_FIELDS = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期"]
STATUS_ORDER = ["待试镜", "试镜中", "已定角", "已换角"]
# 仍需继续跟进试镜/定角的状态；已定角、已换角都不再算作待处理。
PENDING_STATUSES = {"待试镜", "试镜中"}
ACTION_RULES = {"安排试镜": "试镜中", "确认定角": "已定角", "更换演员": "已换角"}
NEGATIVE_ACTIONS = []


def _is_pending(status: str) -> bool:
    return status in PENDING_STATUSES


class CastingService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """列表页、概览核对与导出共用的同一套筛选口径。"""
        rows = store.rows(MODULE)
        # 角色编号既兼容老的 keyword 参数，也兼容筛选条上的同名字段。
        terms: dict[str, str] = {}
        if keyword:
            terms["角色编号"] = keyword.strip()
        for field in FILTER_FIELDS:
            value = (filters or {}).get(field)
            if value and value.strip():
                # 同字段多个条件取最严（交集），不允许后写的空值把前面的冲掉。
                terms[field] = value.strip()
        for field, term in terms.items():
            rows = [row for row in rows if term in str(row.get(field) or "")]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(keyword=keyword, status=status, filters=filters)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        # 把提交的全部业务字段都落库，重试时补充的角色说明等不会再被静默丢掉。
        for field in LIST_FIELDS:
            entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """重试/补录：在原记录上做非破坏性合并。

        - 必填字段若仍为空就整体拦下，一条字段都不改，保证失败不丢原记录；
        - 只写入本次提交了非空值的字段，留空的字段沿用原值，因此角色说明等
          已填内容在重试时会原样保留。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, []
        merged = dict(entry)
        for field in LIST_FIELDS:
            value = values.get(field)
            # 仅接受去除空白后仍有内容的值；纯空白不能覆盖原值，否则必填校验会被绕过。
            if field in values and str(value or "").strip():
                merged[field] = value
        missing = [field for field in REQUIRED_FIELDS if not str(merged.get(field) or "").strip()]
        if missing:
            return entry, missing
        for field in LIST_FIELDS:
            entry[field] = merged[field]
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
        # 先校验、后改记录：动作不合法或必填缺失时，原记录保持不动。
        if values:
            updated, missing = self.update_entry(entry_id, values)
            if missing:
                return None, f"缺少必填字段：{'、'.join(missing)}"
            entry = updated
        entry["status"] = target
        entry["pending"] = _is_pending(target)
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"角色已{action}"
