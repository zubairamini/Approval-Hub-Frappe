"""
approval_hub_frappe/services/pending_engine.py

The core engine that iterates all active Approval Hub Doctype Configs,
fetches pending-approval documents for the current user, filters and
normalises the result into a unified response structure.
"""

import frappe
from frappe import _
from frappe.utils import (
    date_diff,
    nowdate,
    now_datetime,
    cint,
    flt,
)
from approval_hub_frappe.utils.config_utils import get_active_doctype_configs
from approval_hub_frappe.utils.permission_utils import (
    get_current_user_roles,
    get_user_allowed_branches,
    has_branch_access,
    resolve_branch_value,
    has_document_access,
    is_system_manager,
)
from approval_hub_frappe.services.workflow_service import (
    get_workflow_doc,
    get_workflow_for_doctype,
    get_workflow_state,
    get_allowed_transitions,
    get_allowed_actions_for_user,
)


class PendingApprovalEngine:
    """
    Loads and normalises pending-approval documents across all configured
    doctypes for a given user.
    """

    def __init__(self, user: str, settings: dict, filters: dict = None):
        self.user = user
        self.settings = settings
        self.filters = filters or {}
        self.user_roles = get_current_user_roles(user)
        self.is_sysmanager = is_system_manager(user)
        self.user_branches = get_user_allowed_branches(user)

        # Pre-compute aging thresholds
        self.warning_days = settings.get("aging_warning_days", 3)
        self.critical_days = settings.get("aging_critical_days", 7)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_pending(self, page: int = 1, page_size: int = 20) -> dict:
        """Return paginated pending-approval list."""
        all_items = self._collect_all_pending()

        total = len(all_items)
        start = (page - 1) * page_size
        items = all_items[start: start + page_size]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),  # ceil division
        }

    def get_summary(self) -> dict:
        """Return summary counts for dashboard cards."""
        all_items = self._collect_all_pending()

        today_str = nowdate()
        now_str = now_datetime()

        overdue = sum(1 for i in all_items if i.get("aging_status") == "critical")

        # Approved / Rejected today – query log table
        approved_today = frappe.db.count(
            "Approval Hub Log",
            filters={
                "acted_by": self.user,
                "action": ["in", ["Approve", "Approved"]],
                "acted_on": [">=", today_str],
            },
        )
        rejected_today = frappe.db.count(
            "Approval Hub Log",
            filters={
                "acted_by": self.user,
                "action": ["in", ["Reject", "Rejected"]],
                "acted_on": [">=", today_str],
            },
        )

        return {
            "my_pending": len(all_items),
            "overdue": overdue,
            "approved_today": approved_today,
            "rejected_today": rejected_today,
        }

    # ------------------------------------------------------------------
    # Internal collection
    # ------------------------------------------------------------------

    def _collect_all_pending(self) -> list[dict]:
        """Collect and normalise pending items across all active configs."""
        configs = get_active_doctype_configs(for_pending=True)

        # Optional doctype filter from page UI
        ui_doctype = self.filters.get("doctype")

        all_items = []
        for config in configs:
            doctype = config["doctype_name"]

            # UI-level doctype filter
            if ui_doctype and doctype != ui_doctype:
                continue

            # Skip if workflow required but none attached
            if config["workflow_required"] and not get_workflow_for_doctype(doctype):
                continue

            items = self._fetch_for_config(config)
            all_items.extend(items)

        # Sort by date ascending (oldest first – most urgent)
        all_items.sort(key=lambda x: x.get("date") or "")

        return all_items

    def _fetch_for_config(self, config: dict) -> list[dict]:
        """Fetch and normalise pending docs for one doctype config."""
        doctype = config["doctype_name"]
        wf_doc = get_workflow_doc(doctype)

        if not wf_doc:
            # No workflow – no approval state to check
            return []

        wf_state_field = wf_doc.workflow_state_field or "workflow_state"

        # Build list of "pending" states – states where a transition is
        # possible for this user given their roles
        pending_states = self._get_pending_states_for_user(wf_doc)
        if not pending_states:
            return []

        # Build ORM filters
        orm_filters = self._build_orm_filters(config, wf_state_field, pending_states)

        # Determine fields to fetch
        fields_to_fetch = self._fields_to_fetch(config, wf_state_field)

        try:
            rows = frappe.get_list(
                doctype,
                filters=orm_filters,
                fields=fields_to_fetch,
                ignore_permissions=not self.settings.get("respect_user_permissions"),
                limit=500,  # safety cap per doctype; pagination applied after merge
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Approval Hub - fetch error for {doctype}",
            )
            return []

        normalised = []
        for row in rows:
            item = self._normalise(row, config, wf_state_field)
            if item:
                normalised.append(item)

        return normalised

    def _get_pending_states_for_user(self, wf_doc) -> list[str]:
        """
        Return workflow states from which the current user can transition.
        i.e. states where at least one transition is allowed for user's roles.
        """
        pending_states = set()
        for transition in wf_doc.transitions:
            allowed_roles = [r.strip() for r in (transition.allowed or "").split(",") if r.strip()]
            # Sysmanager override or role match
            if not allowed_roles:
                pending_states.add(transition.state)
            elif self.is_sysmanager and self.settings.get("allow_system_manager_override"):
                pending_states.add(transition.state)
            elif any(role in self.user_roles for role in allowed_roles):
                pending_states.add(transition.state)
        return list(pending_states)

    def _build_orm_filters(
        self,
        config: dict,
        wf_state_field: str,
        pending_states: list[str],
    ) -> list:
        """Build the filter list for frappe.get_list."""
        orm_filters = []

        # Workflow state must be one of the pending states
        if len(pending_states) == 1:
            orm_filters.append([wf_state_field, "=", pending_states[0]])
        else:
            orm_filters.append([wf_state_field, "in", pending_states])

        # Base filters from config JSON
        for key, val in (config.get("base_filters") or {}).items():
            if isinstance(val, list):
                orm_filters.append([key, val[0], val[1]])
            else:
                orm_filters.append([key, "=", val])

        # UI filters
        ui_branch = self.filters.get("branch")
        if ui_branch and config.get("branch_field"):
            orm_filters.append([config["branch_field"], "=", ui_branch])

        ui_state = self.filters.get("workflow_state")
        if ui_state:
            # Override the "in pending_states" filter with the specific state
            orm_filters = [f for f in orm_filters if f[0] != wf_state_field]
            orm_filters.append([wf_state_field, "=", ui_state])

        ui_date_from = self.filters.get("date_from")
        ui_date_to = self.filters.get("date_to")
        if ui_date_from and config.get("date_field"):
            orm_filters.append([config["date_field"], ">=", ui_date_from])
        if ui_date_to and config.get("date_field"):
            orm_filters.append([config["date_field"], "<=", ui_date_to])

        # Branch restriction filter
        if (
            self.settings.get("respect_branch_permissions")
            and self.user_branches  # non-empty = restricted
            and config.get("branch_field")
            and not (self.is_sysmanager and self.settings.get("allow_system_manager_override"))
        ):
            orm_filters.append([config["branch_field"], "in", self.user_branches])

        return orm_filters

    def _fields_to_fetch(self, config: dict, wf_state_field: str) -> list[str]:
        """Build the list of fields to select from the doctype."""
        fields = {"name", "owner", "creation", "modified"}

        # Always include workflow state field
        fields.add(wf_state_field)

        # Add all mapped fields that are non-empty
        mapped = [
            "branch_field", "department_field", "company_field",
            "requester_field", "owner_field", "title_field", "amount_field",
            "date_field", "priority_field", "status_field",
            "workflow_state_field", "assigned_to_field", "employee_field",
        ]
        for key in mapped:
            field_name = config.get(key)
            if field_name:
                fields.add(field_name)

        return list(fields)

    def _normalise(self, row: dict, config: dict, wf_state_field: str) -> dict | None:
        """
        Normalise a raw DB row into the unified Approval Hub item structure.
        Returns None if the item should be excluded (permission / branch check).
        """
        doctype = config["doctype_name"]
        docname = row.get("name")

        # Respect user permissions (doc-level)
        if self.settings.get("respect_user_permissions"):
            if not has_document_access(self.user, doctype, docname):
                return None

        # Resolve and check branch access
        branch = resolve_branch_value(row, config)
        if self.settings.get("respect_branch_permissions"):
            if not has_branch_access(self.user, branch, self.settings):
                return None

        # Compute allowed actions for this specific document
        allowed_actions = get_allowed_actions_for_user(
            doctype,
            docname,
            self.user,
            wf_state_field,
            override=(
                self.is_sysmanager
                and self.settings.get("allow_system_manager_override")
            ),
        )
        if not allowed_actions:
            return None  # User can't act → exclude

        # Resolve display values from mapped fields
        workflow_state = row.get(config.get("workflow_state_field") or wf_state_field)
        title = (
            row.get(config.get("title_field"))
            or row.get("title")
            or docname
        )
        date_value = row.get(config.get("date_field")) or row.get("creation")
        amount = flt(row.get(config.get("amount_field"))) if config.get("amount_field") else None

        # Aging
        aging_days, aging_status = self._compute_aging(date_value)

        # Overdue check
        sla_days = cint(config.get("sla_days"))
        if config.get("enable_overdue_tracking") and sla_days and aging_days is not None:
            is_overdue = aging_days > sla_days
        else:
            is_overdue = aging_status == "critical"

        return {
            "doctype": doctype,
            "document_name": docname,
            "label": config.get("label") or doctype,
            "title": title,
            "branch": branch,
            "department": row.get(config.get("department_field")),
            "company": row.get(config.get("company_field")),
            "requester": row.get(config.get("requester_field")) or row.get("owner"),
            "owner": row.get("owner"),
            "amount": amount,
            "date": str(date_value) if date_value else None,
            "priority": row.get(config.get("priority_field")),
            "status": row.get(config.get("status_field")),
            "workflow_state": workflow_state,
            "aging_days": aging_days,
            "aging_status": aging_status,
            "is_overdue": is_overdue,
            "allowed_actions": allowed_actions,
            "can_quick_action": config.get("allow_quick_action", False),
            "url_to_open_doc": f"/app/{frappe.scrub(doctype)}/{docname}",
        }

    def _compute_aging(self, date_value) -> tuple[int | None, str]:
        """
        Return (aging_days, aging_status) based on the document date.
        aging_status: 'normal' | 'warning' | 'critical'
        """
        if not date_value:
            return None, "normal"

        try:
            date_str = str(date_value)[:10]  # strip time if datetime
            days = date_diff(nowdate(), date_str)
        except Exception:
            return None, "normal"

        if days >= self.critical_days:
            status = "critical"
        elif days >= self.warning_days:
            status = "warning"
        else:
            status = "normal"

        return days, status