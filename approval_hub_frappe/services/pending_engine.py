import frappe
from frappe.utils import date_diff, nowdate, cint, flt
from approval_hub_frappe.utils.config_utils import get_active_doctype_configs
from approval_hub_frappe.utils.permission_utils import (
    get_current_user_roles,
    get_user_allowed_branches,
    has_branch_access,
    resolve_branch_value,
    has_document_access,
    is_system_manager,
)
from approval_hub_frappe.services.workflow_service import get_workflow_doc, get_workflow_for_doctype, get_allowed_actions_for_user


class PendingApprovalEngine:
    def __init__(self, user: str, settings: dict, filters: dict = None):
        self.user = user
        self.settings = settings
        self.filters = filters or {}
        self.user_roles = get_current_user_roles(user)
        self.is_sysmanager = is_system_manager(user)
        self.user_branches = get_user_allowed_branches(user)
        self.warning_days = settings.get("aging_warning_days", 3)
        self.critical_days = settings.get("aging_critical_days", 7)

    def get_pending(self, page: int = 1, page_size: int = 20) -> dict:
        all_items = self._collect_all_pending()
        total = len(all_items)
        start = (page - 1) * page_size
        items = all_items[start:start + page_size]
        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": max(1, -(-total // page_size))}

    def get_summary(self) -> dict:
        all_items = self._collect_all_pending()
        by_doctype = {}
        for item in all_items:
            by_doctype[item["doctype"]] = by_doctype.get(item["doctype"], 0) + 1
        return {
            "total_pending": len(all_items),
            "critical": sum(1 for i in all_items if i.get("aging_status") == "critical"),
            "warning": sum(1 for i in all_items if i.get("aging_status") == "warning"),
            "normal": sum(1 for i in all_items if i.get("aging_status") == "normal"),
            "by_doctype": by_doctype,
        }

    def _collect_all_pending(self) -> list[dict]:
        configs = get_active_doctype_configs(for_pending=True)
        ui_doctype = self.filters.get("doctype")
        all_items = []
        for config in configs:
            doctype = config.get("doctype_name")
            if not doctype or not frappe.db.exists("DocType", doctype):
                continue
            if ui_doctype and doctype != ui_doctype:
                continue
            if config.get("workflow_required") and not get_workflow_for_doctype(doctype):
                continue
            all_items.extend(self._fetch_for_config(config))
        all_items.sort(key=lambda x: x.get("date") or "")
        return all_items

    def _fetch_for_config(self, config: dict) -> list[dict]:
        doctype = config["doctype_name"]
        wf_doc = get_workflow_doc(doctype)
        if not wf_doc:
            return []
        wf_state_field = wf_doc.workflow_state_field or "workflow_state"
        pending_states = self._get_pending_states_for_user(wf_doc)
        if not pending_states:
            return []

        orm_filters = self._build_orm_filters(config, wf_state_field, pending_states)
        if frappe.db.has_column(doctype, "docstatus"):
            orm_filters.append(["docstatus", "!=", 2])

        rows = frappe.get_list(
            doctype,
            filters=orm_filters,
            fields=self._fields_to_fetch(config, wf_state_field),
            ignore_permissions=not self.settings.get("respect_user_permissions"),
            limit=500,
        )
        out = []
        for row in rows:
            item = self._normalise(row, config, wf_state_field)
            if item:
                out.append(item)
        return out

    def _get_pending_states_for_user(self, wf_doc) -> list[str]:
        pending_states = set()
        for transition in wf_doc.transitions:
            allowed_roles = [r.strip() for r in (transition.allowed or "").split(",") if r.strip()]
            if not allowed_roles:
                pending_states.add(transition.state)
            elif self.is_sysmanager and self.settings.get("allow_system_manager_override"):
                pending_states.add(transition.state)
            elif any(role in self.user_roles for role in allowed_roles):
                pending_states.add(transition.state)

        final_keywords = ("approved", "rejected", "cancel", "completed", "closed", "final", "submitted", "kept")
        return [s for s in pending_states if not any(k in (s or "").lower() for k in final_keywords)]

    def _build_orm_filters(self, config, wf_state_field, pending_states):
        filters = [[wf_state_field, "in", pending_states]]
        for key, val in (config.get("base_filters") or {}).items():
            if isinstance(val, list) and len(val) >= 2:
                filters.append([key, val[0], val[1]])
            else:
                filters.append([key, "=", val])
        if self.filters.get("branch") and config.get("branch_field"):
            filters.append([config["branch_field"], "=", self.filters["branch"]])
        if self.filters.get("workflow_state"):
            filters = [f for f in filters if f[0] != wf_state_field]
            filters.append([wf_state_field, "=", self.filters["workflow_state"]])
        if self.filters.get("date_from") and config.get("date_field"):
            filters.append([config["date_field"], ">=", self.filters["date_from"]])
        if self.filters.get("date_to") and config.get("date_field"):
            filters.append([config["date_field"], "<=", self.filters["date_to"]])
        return filters

    def _fields_to_fetch(self, config, wf_state_field):
        fields = {"name", "owner", "creation", wf_state_field}
        mapped = ["branch_field", "department_field", "company_field", "requester_field", "title_field", "amount_field", "date_field", "priority_field", "status_field"]
        for key in mapped:
            if config.get(key):
                fields.add(config[key])
        if frappe.db.has_column(config["doctype_name"], "docstatus"):
            fields.add("docstatus")
        return list(fields)

    def _normalise(self, row, config, wf_state_field):
        doctype = config["doctype_name"]
        docname = row.get("name")
        if self.settings.get("respect_user_permissions") and not has_document_access(self.user, doctype, docname):
            return None
        branch = resolve_branch_value(row, config)
        if self.settings.get("respect_branch_permissions") and not has_branch_access(self.user, branch, self.settings):
            return None
        allowed_actions = get_allowed_actions_for_user(doctype, docname, self.user, wf_state_field, override=(self.is_sysmanager and self.settings.get("allow_system_manager_override")))
        if not allowed_actions:
            return None
        date_value = row.get(config.get("date_field")) or row.get("creation")
        age_days, aging_status = self._compute_aging(date_value)
        return {
            "doctype": doctype,
            "name": docname,
            "title": row.get(config.get("title_field")) or docname,
            "workflow_state": row.get(config.get("workflow_state_field") or wf_state_field),
            "status": row.get(config.get("status_field")) or row.get(config.get("workflow_state_field") or wf_state_field),
            "branch": branch,
            "department": row.get(config.get("department_field")),
            "requester": row.get(config.get("requester_field")) or row.get("owner"),
            "amount": flt(row.get(config.get("amount_field"))) if config.get("amount_field") else None,
            "date": str(date_value) if date_value else None,
            "age_days": age_days,
            "aging_status": aging_status,
            "allowed_actions": allowed_actions,
            "can_quick_action": config.get("allow_quick_action", False),
            "config_label": config.get("label") or doctype,
            "route": f"/app/{frappe.scrub(doctype)}/{docname}",
        }

    def _compute_aging(self, date_value):
        if not date_value:
            return None, "normal"
        try:
            days = date_diff(nowdate(), str(date_value)[:10])
        except Exception:
            return None, "normal"
        if days >= self.critical_days:
            return days, "critical"
        if days >= self.warning_days:
            return days, "warning"
        return days, "normal"
