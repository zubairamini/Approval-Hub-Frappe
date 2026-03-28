# Approval Hub Frappe

Approval Hub Frappe is a dynamic, configuration-based approval center for Frappe / ERPNext. It is designed to collect pending approval documents from multiple workflow-enabled doctypes into one centralized page, so users can easily see what is waiting for their review, approval, rejection, or follow-up.

Instead of hardcoding logic for each doctype, this app uses configurable mappings through **Approval Hub Doctype Config**. This makes it possible to register any doctype, define the important fields, and let the system dynamically track pending approvals based on workflow, branch, permissions, and user roles.

---

## Features

- Centralized approval page for workflow-enabled doctypes
- Dynamic doctype registration using configuration
- Pending approvals filtered for the current logged-in user
- Workflow-aware approval tracking
- Branch-aware filtering support
- Permission-aware visibility
- Approval activity logging
- Dashboard-ready summary support
- Optional quick actions for supported doctypes
- Configurable aging / overdue tracking

---

## Core Doctypes

### 1. Approval Hub Settings
Global settings for the module, including:
- Enable / disable the module
- Respect user permissions
- Respect branch permissions
- Allow System Manager override
- Aging warning days
- Aging critical days
- Default page size

### 2. Approval Hub Doctype Config
The main configuration doctype used to register and control tracked doctypes.

It defines:
- Which doctype to track
- Whether it is active
- Whether workflow is required
- Whether pending documents should be tracked
- Whether history should be logged
- Whether it should appear in dashboard summaries
- Whether quick actions are allowed
- Which field represents branch, date, title, amount, requester, workflow state, etc.
- Permission mode
- Branch resolution mode

### 3. Approval Hub Log
Stores approval actions and history, including:
- Reference doctype
- Reference document
- From state
- To state
- Action
- Acted by
- Acted on
- Branch
- Requester
- Amount
- Remarks

---

## Core Page

### Approval Hub
A centralized page that shows:
- My Pending Approvals
- Overdue Approvals
- Approved Today
- Rejected Today

With filters such as:
- Doctype
- Branch
- Workflow State
- Date Range

Main list columns:
- Doctype
- Document
- Title
- Branch
- Requester
- Workflow State
- Date
- Aging
- Actions

---

## How It Works

1. The app reads **Approval Hub Settings**
2. It loads active records from **Approval Hub Doctype Config**
3. For each configured doctype:
   - workflow rules are checked
   - current user eligibility is evaluated
   - permissions are enforced
   - branch access is validated if enabled
4. Matching records are normalized into one unified approval list
5. Actions can be logged into **Approval Hub Log**

---

## Permission Mode

Approval Hub supports different permission strategies:

### Standard
Uses normal Frappe permission checks and workflow role checks.

### Strict
Uses normal permissions plus stricter branch and access validation.

### Custom
Reserved for future custom business rules and extensions.

---

## Branch Resolution Mode

Approval Hub supports different branch resolution methods:

### Direct Field
Reads branch directly from the configured branch field in the document.

### Linked Field
Reads branch from a linked document.

### Expression
Reserved for advanced branch resolution logic.

---

## Example Configuration

Example for **Sales Order**:

- Doctype Name: `Sales Order`
- Is Active: `1`
- Workflow Required: `1`
- Track Pending: `1`
- Track History: `1`
- Show In Dashboard: `1`
- Enable Overdue Tracking: `1`
- SLA Days: `5`
- Branch Field: `branch`
- Date Field: `transaction_date`
- Status Field: `docstatus`
- Workflow State Field: `workflow_state`
- Permission Mode: `Strict`
- Branch Resolution Mode: `Direct Field`

This means:
- Sales Orders are included in Approval Hub
- Only workflow-relevant pending approvals are shown
- Branch checks are enforced
- Aging is tracked
- Approval actions can be logged

---

## Installation

Get the app inside your Frappe bench:

```bash
cd ~/frappe-bench
bench get-app https://github.com/zubairamini/Approval-Hub-Frappe.git
bench --site your-site-name install-app approval_hub_frappe