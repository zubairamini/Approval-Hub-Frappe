"""Pending approval aggregation engine."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import date_diff, flt, getdate, nowdate

from approval_hub_frappe.services.workflow_service import get_allowed_actions_for_user, get_workflow_doc
from approval_hub_frappe.utils.config_utils import get_active_doctype_configs, validate_config_field_mapping
from approval_hub_frappe.utils.permission_utils import (
    get_current_user_roles,
    has_branch_access,
    has_document_access,
    is_system_manager,
    resolve_branch_value,
    state_looks_final,
    system_manager_override_applies,
)


FINAL_TERMS = ("approved", "rejected", "cancel", "completed", "closed", "final", "submitted", "kept")


class PendingApprovalEngine:
    def __init__(self, user: str, settings: dict, filters: dict | None = None):
        self.user = user
        self.settings = settings or {}
        self.filters = filters or {}
        self.roles = get_current_user_roles(user)
        self.is_system_manager = is_system_manager(user)
        self.warning_days = int(self.settings.get("aging_warning_days") or 3)
        self.critical_days = int(self.settings.get("aging_critical_days") or 7)
        self.override = system_manager_override_applies(user, self.settings)

    def get_pending(self, start: int = 0, page_length: int = 20) -> dict:
        items = self._collect_all_pending()
        total = len(items)
        safe_start = max(0, int(start or 0))
        safe_page_length = min(500, max(1, int(page_length or 20)))
        paged = items[safe_start : safe_start + safe_page_length]

        return {
            "items": paged,
            "total": total,
            "start": safe_start,
            "page_length": safe_page_length,
            "has_more": safe_start + safe_page_length < total,
            "total_pages": max(1, (total + safe_page_length - 1) // safe_page_length),
            "page": (safe_start // safe_page_length) + 1,
        }

    def get_summary(self) -> dict:
        items = self._collect_all_pending()
        by_doctype = defaultdict(int)
        by_branch = defaultdict(int)
        by_state = defaultdict(int)
        total_actions = 0
        oldest = 0

        for item in items:
            by_doctype[item["doctype"]] += 1
            by_branch[item.get("branch") or "Unspecified"] += 1
            by_state[item.get("workflow_state") or "Unspecified"] += 1
            total_actions += len(item.get("allowed_actions") or [])
            oldest = max(oldest, item.get("age_days") or 0)

        return {
            "total_pending": len(items),
            "critical": sum(1 for i in items if i.get("aging_status") == "critical"),
            "warning": sum(1 for i in items if i.get("aging_status") == "warning"),
            "normal": sum(1 for i in items if i.get("aging_status") == "normal"),
            "my_available_actions": total_actions,
            "oldest_pending": oldest,
            "by_doctype": dict(sorted(by_doctype.items())),
            "by_branch": dict(sorted(by_branch.items())),
            "by_state": dict(sorted(by_state.items())),
        }

    def _collect_all_pending(self) -> list[dict]:
        all_items = []
        configs = get_active_doctype_configs(for_pending=True)

        doctype_filter = self.filters.get("doctype")
        for raw_config in configs:
            doctype = raw_config.get("doctype_name")
            if doctype_filter and doctype_filter != doctype:
                continue
            if not doctype or not frappe.db.exists("DocType", doctype):
                continue

            source_meta = frappe.get_meta(doctype)
            config = validate_config_field_mapping(raw_config, source_meta)

            wf_doc = get_workflow_doc(doctype)
            if not wf_doc:
                continue

            wf_state_field = config.get("workflow_state_field") or wf_doc.workflow_state_field or "workflow_state"
            if wf_state_field not in set(source_meta.get_valid_columns()):
                continue

            pending_states = self._get_pending_states_for_user(wf_doc)
            if not pending_states:
                continue

            all_items.extend(self._fetch_for_config(config, source_meta, wf_state_field, pending_states))

        all_items.sort(key=lambda x: (x.get("age_days") or 0), reverse=True)
        all_items.sort(key=lambda x: x.get("date") or "", reverse=False)
        return all_items

    def _fetch_for_config(self, config: dict, source_meta, wf_state_field: str, pending_states: list[str]) -> list[dict]:
        doctype = config["doctype_name"]
        filters = self._build_orm_filters(config, source_meta, wf_state_field, pending_states)
        fields = self._fields_to_fetch(config, source_meta, wf_state_field)

        results = []
        for row in self._iter_rows(doctype, filters, fields):
            item = self._normalise(row, config, wf_state_field)
            if item and self._match_search(item):
                results.append(item)
        return results

    def _iter_rows(self, doctype: str, filters: list, fields: list[str]):
        start = 0
        batch = 500
        while True:
            rows = frappe.get_list(
                doctype,
                filters=filters,
                fields=fields,
                ignore_permissions=not self.settings.get("respect_user_permissions"),
                limit_start=start,
                limit_page_length=batch,
                order_by="creation asc",
            )
            if not rows:
                break
            for row in rows:
                yield row
            if len(rows) < batch:
                break
            start += batch

    def _get_pending_states_for_user(self, wf_doc) -> list[str]:
        pending_states = set()
        for transition in wf_doc.transitions:
            if not transition.state:
                continue
            if state_looks_final(transition.state):
                continue
            if any(term in transition.state.lower() for term in FINAL_TERMS):
                continue

            allowed_roles = [r.strip() for r in (transition.allowed or "").split(",") if r.strip()]
            if self.override:
                pending_states.add(transition.state)
            elif not allowed_roles:
                pending_states.add(transition.state)
            elif any(role in self.roles for role in allowed_roles):
                pending_states.add(transition.state)
        return sorted(pending_states)

    def _build_orm_filters(self, config: dict, source_meta, wf_state_field: str, pending_states: list[str]) -> list:
        valid_columns = set(source_meta.get_valid_columns())

        filters = [[wf_state_field, "in", pending_states]]

        base_filters = config.get("base_filters") or {}
        for key, val in base_filters.items():
            if key not in valid_columns:
                continue
            if isinstance(val, list) and len(val) >= 2:
                filters.append([key, val[0], val[1]])
            else:
                filters.append([key, "=", val])

        if "docstatus" in valid_columns:
            filters.append(["docstatus", "!=", 2])

        branch_field = config.get("branch_field")
        if self.filters.get("branch") and branch_field and branch_field in valid_columns:
            filters.append([branch_field, "=", self.filters["branch"]])

        if self.filters.get("workflow_state"):
            filters = [f for f in filters if f[0] != wf_state_field]
            filters.append([wf_state_field, "=", self.filters["workflow_state"]])

        if self.filters.get("date_from") and config.get("date_field") in valid_columns:
            filters.append([config["date_field"], ">=", self.filters["date_from"]])

        if self.filters.get("date_to") and config.get("date_field") in valid_columns:
            filters.append([config["date_field"], "<=", self.filters["date_to"]])

        return filters

    def _fields_to_fetch(self, config: dict, source_meta, wf_state_field: str) -> list[str]:
        valid_columns = set(source_meta.get_valid_columns())
        fields = {"name", "owner", "creation", wf_state_field}

        for key in [
            "branch_field",
            "department_field",
            "company_field",
            "requester_field",
            "owner_field",
            "title_field",
            "amount_field",
            "date_field",
            "status_field",
            "workflow_state_field",
            "employee_field",
        ]:
            val = config.get(key)
            if val and val in valid_columns:
                fields.add(val)

        if "docstatus" in valid_columns:
            fields.add("docstatus")

        return sorted(fields)

    def _normalise(self, row: dict, config: dict, wf_state_field: str) -> dict | None:
        doctype = config["doctype_name"]
        docname = row.get("name")
        workflow_state = row.get(config.get("workflow_state_field") or wf_state_field)

        if not docname or not workflow_state:
            return None

        if state_looks_final(workflow_state):
            return None

        if self.settings.get("respect_user_permissions") and not has_document_access(self.user, doctype, docname):
            return None

        branch = resolve_branch_value(row, config)
        if self.settings.get("respect_branch_permissions") and not has_branch_access(self.user, branch, self.settings):
            return None

        actions = get_allowed_actions_for_user(
            doctype=doctype,
            docname=docname,
            user=self.user,
            workflow_state_field=wf_state_field,
            override=self.override,
        )
        if not actions:
            return None

        actions = sorted({a for a in actions if a})
        if not actions:
            return None

        date_value = row.get(config.get("date_field")) or row.get("creation")
        age_days, aging_status = self._compute_aging(date_value)
        doctype_route = frappe.scrub(doctype).replace("_", "-")

        return {
            "doctype": doctype,
            "name": docname,
            "title": row.get(config.get("title_field")) or docname,
            "workflow_state": workflow_state,
            "status": row.get(config.get("status_field")) or workflow_state,
            "branch": branch,
            "department": row.get(config.get("department_field")),
            "requester": row.get(config.get("requester_field")) or row.get("owner"),
            "amount": flt(row.get(config.get("amount_field"))) if config.get("amount_field") else None,
            "date": str(date_value)[:10] if date_value else None,
            "age_days": age_days,
            "aging_status": aging_status,
            "allowed_actions": actions,
            "can_quick_action": bool(config.get("allow_quick_action")),
            "config_label": config.get("label") or doctype,
            "route": f"/app/{doctype_route}/{docname}",
        }

    def _compute_aging(self, date_value):
        if not date_value:
            return None, "normal"
        try:
            parsed = getdate(date_value)
        except (TypeError, ValueError):
            return None, "normal"
        if not parsed:
            return None, "normal"

        days = date_diff(nowdate(), parsed)

        if days >= self.critical_days:
            return days, "critical"
        if days >= self.warning_days:
            return days, "warning"
        return days, "normal"

    def _match_search(self, item: dict) -> bool:
        aging_filter = self.filters.get("aging_status")
        if aging_filter and item.get("aging_status") != aging_filter:
            return False

        query = (self.filters.get("search") or "").strip().lower()
        if not query:
            return True

        haystack = " ".join(
            [
                str(item.get("name") or ""),
                str(item.get("title") or ""),
                str(item.get("requester") or ""),
                str(item.get("branch") or ""),
                str(item.get("workflow_state") or ""),
            ]
        ).lower()
        if query not in haystack:
            return False

        return True
