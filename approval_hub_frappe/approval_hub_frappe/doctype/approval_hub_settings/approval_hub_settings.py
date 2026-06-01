"""
approval_hub_frappe/doctype/approval_hub_settings/approval_hub_settings.py

Controller for the Approval Hub Settings singleton doctype.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ApprovalHubSettings(Document):

    def validate(self):
        self._validate_aging_days()
        self._validate_page_size()

    def on_update(self):
        """Clear cached settings on save so next request picks up fresh values."""
        _clear_settings_cache()

    def _validate_aging_days(self):
        warning = cint(self.aging_warning_days)
        critical = cint(self.aging_critical_days)

        if warning < 0:
            frappe.throw(_("Aging Warning Days cannot be negative."))

        if critical < 0:
            frappe.throw(_("Aging Critical Days cannot be negative."))

        if critical and warning and critical <= warning:
            frappe.throw(
                _("Aging Critical Days must be greater than Aging Warning Days.")
            )

    def _validate_page_size(self):
        ps = cint(self.default_page_size)
        if ps < 1:
            frappe.throw(_("Default Page Size must be at least 1."))
        if ps > 500:
            frappe.throw(_("Default Page Size cannot exceed 500."))


def _clear_settings_cache():
    """Clear per-request cached settings (no-op if not in request context)."""
    from approval_hub_frappe.utils.settings_utils import _SETTINGS_CACHE_KEY
    if hasattr(frappe.local, _SETTINGS_CACHE_KEY):
        delattr(frappe.local, _SETTINGS_CACHE_KEY)
