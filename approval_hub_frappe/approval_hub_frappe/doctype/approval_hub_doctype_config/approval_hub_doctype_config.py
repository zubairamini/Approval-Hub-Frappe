
import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ApprovalHubDoctypeConfig(Document):

    def validate(self):
        validate_doctype_config(self)

    def before_save(self):
        self._auto_set_workflow_state_field()
        self._normalise_sequence()


    
    # ---------------------------------------------------------------------------
    # Before-save hooks
    # ---------------------------------------------------------------------------

    def _auto_set_workflow_state_field(self):
        """Auto-populate workflow_state_field to 'workflow_state' if blank and field exists."""
        if self.workflow_state_field:
            return
        if not self.doctype_name:
            return

        doctype_fields = _get_doctype_field_names(self.doctype_name)
        if "workflow_state" in doctype_fields:
            self.workflow_state_field = "workflow_state"


    def _normalise_sequence(self):
        """Assign next available sequence number if left at 0 or None."""
        if cint(self.sequence):
            return

        max_seq = frappe.db.get_value(
            "Approval Hub Doctype Config",
            filters={"name": ["!=", self.name or ""]},
            fieldname="max(sequence)",
        )
        self.sequence = (cint(max_seq) or 0) + 10


# ---------------------------------------------------------------------------
# Exported validation function (also callable from API)
# ---------------------------------------------------------------------------

def validate_doctype_config(doc, method=None):
    """
    Full validation for Approval Hub Doctype Config.
    Can be called from the controller or from an API endpoint.
    """
    _validate_doctype_exists(doc)
    _validate_field_mappings(doc)
    _validate_sla_days(doc)
  
    _validate_no_duplicate_active(doc)
    _validate_workflow_state_field(doc)


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------

def _validate_doctype_exists(doc):
    """Ensure the referenced doctype actually exists in the system."""
    if not doc.doctype_name:
        frappe.throw(_("Doctype Name is required."), frappe.MandatoryError)

    if not frappe.db.exists("DocType", doc.doctype_name):
        frappe.throw(
            _(f"Doctype '{doc.doctype_name}' does not exist in this system."),
            frappe.ValidationError,
        )


def _validate_field_mappings(doc):
    """
    Verify that every mapped field name actually exists on the selected doctype.
    Skips empty/blank fields silently.
    """
    if not frappe.db.exists("DocType", doc.doctype_name):
        return  # already handled above

    doctype_fields = _get_doctype_field_names(doc.doctype_name)

    mapped_field_attrs = [
        "branch_field", "department_field", "company_field",
        "requester_field", "owner_field", "title_field", "amount_field",
        "date_field", "priority_field", "status_field", "workflow_state_field",
        "assigned_to_field", "employee_field",
    ]

    for attr in mapped_field_attrs:
        field_value = doc.get(attr)
        if not field_value:
            continue
        if field_value not in doctype_fields:
            frappe.throw(
                _(
                    f"Field '{field_value}' (mapped as {attr}) does not exist "
                    f"on Doctype '{doc.doctype_name}'."
                ),
                frappe.ValidationError,
            )


def _validate_sla_days(doc):
    """sla_days must be zero or positive if set."""
    if doc.sla_days is not None and cint(doc.sla_days) < 0:
        frappe.throw(_("SLA Days cannot be negative."), frappe.ValidationError)




def _validate_no_duplicate_active(doc):
    """
    Prevent two active configs for the same doctype.
    Allows inactive duplicates (for archival/testing purposes).
    """
    if not cint(doc.is_active):
        return

    existing = frappe.db.get_value(
        "Approval Hub Doctype Config",
        filters={
            "doctype_name": doc.doctype_name,
            "is_active": 1,
            "name": ["!=", doc.name or ""],
        },
        fieldname="name",
    )
    if existing:
        frappe.throw(
            _(
                f"An active Approval Hub Doctype Config already exists for "
                f"'{doc.doctype_name}' ({existing}). Please deactivate it first."
            ),
            frappe.DuplicateEntryError,
        )


def _validate_workflow_state_field(doc):
    """
    If workflow_required = 1 and workflow_state_field is blank,
    validate that 'workflow_state' exists on the doctype (Frappe default).
    """
    if not cint(doc.workflow_required):
        return

    if doc.workflow_state_field:
        return  # already set by user

    # Check Frappe default
    doctype_fields = _get_doctype_field_names(doc.doctype_name)
    if "workflow_state" not in doctype_fields:
        frappe.throw(
            _(
                f"workflow_required is enabled, but the doctype '{doc.doctype_name}' "
                f"does not have a 'workflow_state' field. Please map the Workflow State Field."
            ),
            frappe.ValidationError,
        )



# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _get_doctype_field_names(doctype_name: str) -> set[str]:
    """Return the set of field names defined on a doctype (DB columns + standard)."""
    meta = frappe.get_meta(doctype_name)
    field_names = {f.fieldname for f in meta.fields if f.fieldname}
    # Add standard Frappe fields
    field_names.update(
        {"name", "owner", "creation", "modified", "modified_by",
         "docstatus", "idx", "workflow_state"}
    )
    return field_names