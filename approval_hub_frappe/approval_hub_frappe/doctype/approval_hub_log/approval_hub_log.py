"""
approval_hub_frappe/doctype/approval_hub_log/approval_hub_log.py

Minimal controller for Approval Hub Log.
Log records are created programmatically only; no direct user edits.
"""

import frappe
from frappe.model.document import Document


class ApprovalHubLog(Document):

    def before_insert(self):
        """Enforce read-only creation via service only."""
        pass  # All logic is in log_service.py

    def before_save(self):
        """Prevent manual edits to log records after creation."""
        if not self.is_new():
            frappe.throw(
                frappe._("Approval Hub Log records cannot be edited after creation."),
                frappe.PermissionError,
            )