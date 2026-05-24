/**
 * approval_hub_frappe/page/approval_hub/approval_hub.js
 *
 * Frappe Desk page JS for the Approval Hub.
 * Renders summary cards, filters, and a paginated approval list.
 * All data is fetched from backend Python methods.
 */

/* global frappe */

frappe.pages["approval-hub"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Approval Hub"),
		single_column: true,
	});

	// Attach the ApprovalHub controller to the page
	wrapper.approval_hub = new ApprovalHub(page, wrapper);
};

frappe.pages["approval-hub"].on_page_show = function (wrapper) {
	if (wrapper.approval_hub) {
		wrapper.approval_hub.refresh();
	}
};

// ============================================================
// Main Controller
// ============================================================

class ApprovalHub {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.$main = $(wrapper).find(".layout-main-section");

		// State
		this.settings = {};
		this.configs = [];
		this.branches = [];
		this.current_page = 1;
		this.page_size = 20;
		this.total = 0;
		this.total_pages = 1;
		this.filters = {};
		this.loading = false;

		this._build_skeleton();
		this._add_page_actions();
		this.init();
	}

	// ----------------------------------------------------------
	// Initialisation
	// ----------------------------------------------------------

	async init() {
		this._set_loading(true);
		try {
			await this._load_page_context();
		} catch (e) {
			this._show_error(__("Failed to load Approval Hub. Please refresh."));
		} finally {
			this._set_loading(false);
		}
	}

	async refresh() {
		this.current_page = 1;
		this._set_loading(true);
		try {
			await Promise.all([
				this._load_summary(),
				this._load_pending(),
			]);
		} finally {
			this._set_loading(false);
		}
	}

	// ----------------------------------------------------------
	// Page context (first load)
	// ----------------------------------------------------------

	async _load_page_context() {
		const r = await frappe.call({
			method: "approval_hub_frappe.api.approval_hub.get_page_context",
		});

		const ctx = r.message || {};

		if (!ctx.enabled) {
			this._show_disabled(ctx.message || __("Approval Hub is disabled."));
			return;
		}

		this.settings = ctx.settings || {};
		this.page_size = this.settings.default_page_size || 20;
		this.configs = ctx.configs || [];
		this.branches = ctx.branches || [];

		this._build_filters();
		this._render_summary(ctx.summary || {});
		await this._load_pending();
	}

	// ----------------------------------------------------------
	// Summary cards
	// ----------------------------------------------------------

	async _load_summary() {
		const r = await frappe.call({
			method: "approval_hub_frappe.api.approval_hub.get_approval_summary",
			args: { filters: this.filters },
		});
		this._render_summary(r.message || {});
	}

	_render_summary(data) {
		const cards = [
			{
				key: "total_pending",
				label: __("My Pending"),
				value: data.total_pending || 0,
				color: "var(--blue-500)",
				icon: "⏳",
			},
			{
				key: "critical",
				label: __("Critical"),
				value: data.critical || 0,
				color: "var(--red-500)",
				icon: "🔴",
			},
			{
				key: "warning",
				label: __("Warning"),
				value: data.warning || 0,
				color: "var(--green-500)",
				icon: "🟠",
			},
			{
				key: "normal",
				label: __("Normal"),
				value: data.normal || 0,
				color: "var(--green-500)",
				icon: "🟢",
			},
		];

		const html = cards
			.map(
				(c) => `
			<div class="ah-summary-card" style="border-top: 3px solid ${c.color};">
				<div class="ah-summary-icon">${c.icon}</div>
				<div class="ah-summary-value" id="ah-stat-${c.key}">${c.value}</div>
				<div class="ah-summary-label">${c.label}</div>
			</div>`
			)
			.join("");

		this.$summary.html(html);
	}

	// ----------------------------------------------------------
	// Filters
	// ----------------------------------------------------------

	_build_filters() {
		// Doctype selector
		const dtOptions = [{ value: "", label: __("All Doctypes") }].concat(this.configs);
		let dtHtml = dtOptions.map((o) => `<option value="${o.value}">${o.label}</option>`).join("");

		// Branch selector
		const branchOptions = [{ value: "", label: __("All Branches") }].concat(
			this.branches.map((b) => ({ value: b, label: b }))
		);
		let brHtml = branchOptions.map((o) => `<option value="${o.value}">${o.label}</option>`).join("");

		this.$filters.html(`
			<div class="ah-filters">
				<div class="ah-filter-group">
					<label>${__("Doctype")}</label>
					<select class="form-control ah-filter" data-key="doctype">
						${dtHtml}
					</select>
				</div>
				<div class="ah-filter-group">
					<label>${__("Branch")}</label>
					<select class="form-control ah-filter" data-key="branch">
						${brHtml}
					</select>
				</div>
				<div class="ah-filter-group">
					<label>${__("Workflow State")}</label>
					<input type="text" class="form-control ah-filter"
						   data-key="workflow_state" placeholder="${__("e.g. Pending")}">
				</div>
				<div class="ah-filter-group">
					<label>${__("Date From")}</label>
					<input type="date" class="form-control ah-filter" data-key="date_from">
				</div>
				<div class="ah-filter-group">
					<label>${__("Date To")}</label>
					<input type="date" class="form-control ah-filter" data-key="date_to">
				</div>
				<div class="ah-filter-group ah-filter-actions">
					<button class="btn btn-primary btn-sm ah-apply-filters">
						${__("Apply")}
					</button>
					<button class="btn btn-default btn-sm ah-clear-filters">
						${__("Clear")}
					</button>
				</div>
			</div>
		`);

		this.$filters.on("click", ".ah-apply-filters", () => this._apply_filters());
		this.$filters.on("click", ".ah-clear-filters", () => this._clear_filters());
		// Allow Enter key in text inputs to trigger apply
		this.$filters.on("keyup", "input.ah-filter", (e) => {
			if (e.key === "Enter") this._apply_filters();
		});
	}

	_apply_filters() {
		const filters = {};
		this.$filters.find(".ah-filter").each(function () {
			const key = $(this).data("key");
			const val = $(this).val().trim();
			if (val) filters[key] = val;
		});
		this.filters = filters;
		this.current_page = 1;
		this.refresh();
	}

	_clear_filters() {
		this.$filters.find(".ah-filter").val("");
		this.filters = {};
		this.current_page = 1;
		this.refresh();
	}

	// ----------------------------------------------------------
	// Pending list
	// ----------------------------------------------------------

	async _load_pending() {
		const r = await frappe.call({
			method: "approval_hub_frappe.api.approval_hub.get_pending_approvals",
			args: {
				filters: this.filters,
				page: this.current_page,
				page_size: this.page_size,
			},
		});

		const data = r.message || {};
		this.total = data.total || 0;
		this.total_pages = data.total_pages || 1;
		this._render_list(data.items || []);
		this._render_pagination();
	}

	_render_list(items) {
		if (!items.length) {
			this.$list.html(`
				<div class="ah-empty-state">
					<div class="ah-empty-icon">🎉</div>
					<h3>${__("All caught up!")}</h3>
					<p>${__("No documents are pending your approval right now.")}</p>
				</div>
			`);
			return;
		}

		const rows = items.map((item) => this._render_row(item)).join("");

		this.$list.html(`
			<div class="ah-table-wrapper">
				<table class="ah-table">
					<thead>
						<tr>
							<th>${__("Doctype")}</th>
							<th>${__("Document")}</th>
							<th>${__("Title")}</th>
							<th>${__("Branch")}</th>
							<th>${__("Requester")}</th>
							<th>${__("Workflow State")}</th>
							<th>${__("Date")}</th>
							<th>${__("Aging")}</th>
							<th>${__("Actions")}</th>
						</tr>
					</thead>
					<tbody>
						${rows}
					</tbody>
				</table>
			</div>
		`);

		// Bind action buttons
		this.$list.on("click", ".ah-open-doc", (e) => {
			const url = $(e.currentTarget).data("url");
			if (url) frappe.set_route(url);
		});

		this.$list.on("click", ".ah-quick-action", (e) => {
			const btn = $(e.currentTarget);
			this._handle_quick_action(
				btn.data("doctype"),
				btn.data("docname"),
				btn.data("action")
			);
		});
	}

	_render_row(item) {
		const agingBadge = this._aging_badge(item.age_days, item.aging_status);
		const stateBadge = `<span class="ah-state-badge">${item.workflow_state || ""}</span>`;

		let actionHtml = `
			<button class="btn btn-xs btn-default ah-open-doc"
					data-url="${item.route}" title="${__("Open Document")}">
				${__("Open")}
			</button>
		`;

		if (item.can_quick_action && item.allowed_actions && item.allowed_actions.length) {
			const actionBtns = item.allowed_actions
				.map(
					(action) => `
				<button class="btn btn-xs ah-quick-action ah-action-${frappe.scrub(action)}"
						data-doctype="${item.doctype}"
						data-docname="${item.name}"
						data-action="${action}">
					${__(action)}
				</button>`
				)
				.join("");
			actionHtml += `<div class="ah-quick-actions">${actionBtns}</div>`;
		}

		const amount = item.amount != null
			? frappe.format(item.amount, { fieldtype: "Currency" })
			: "—";

		return `
		<tr class="ah-row ${item.aging_status === "critical" ? "ah-row-critical" : ""}">
			<td><span class="ah-doctype-badge">${item.config_label || item.doctype}</span></td>
			<td>
				<a href="${item.route}" target="_blank" class="ah-doc-link">
					${item.name}
				</a>
			</td>
			<td class="ah-col-title" title="${item.title || ""}">${item.title || "—"}</td>
			<td>${item.branch || "—"}</td>
			<td>${item.requester || "—"}</td>
			<td>${stateBadge}</td>
			<td>${item.date ? frappe.datetime.str_to_user(item.date) : "—"}</td>
			<td>${agingBadge}</td>
			<td class="ah-actions-cell">${actionHtml}</td>
		</tr>`;
	}

	_aging_badge(days, status) {
		if (days == null) return `<span class="ah-aging ah-aging-normal">—</span>`;
		const label = `${days}d`;
		return `<span class="ah-aging ah-aging-${status}" title="${__(status)}">${label}</span>`;
	}

	// ----------------------------------------------------------
	// Pagination
	// ----------------------------------------------------------

	_render_pagination() {
		if (this.total_pages <= 1) {
			this.$pagination.html("");
			return;
		}

		const prevDisabled = this.current_page <= 1 ? "disabled" : "";
		const nextDisabled = this.current_page >= this.total_pages ? "disabled" : "";

		this.$pagination.html(`
			<div class="ah-pagination">
				<span class="ah-pagination-info">
					${__("Showing page {0} of {1} ({2} total)", [
						this.current_page,
						this.total_pages,
						this.total,
					])}
				</span>
				<div class="ah-pagination-controls">
					<button class="btn btn-default btn-xs ah-prev-page" ${prevDisabled}>
						&larr; ${__("Prev")}
					</button>
					<button class="btn btn-default btn-xs ah-next-page" ${nextDisabled}>
						${__("Next")} &rarr;
					</button>
				</div>
			</div>
		`);

		this.$pagination.on("click", ".ah-prev-page", () => {
			if (this.current_page > 1) {
				this.current_page--;
				this._load_pending();
			}
		});

		this.$pagination.on("click", ".ah-next-page", () => {
			if (this.current_page < this.total_pages) {
				this.current_page++;
				this._load_pending();
			}
		});
	}

	// ----------------------------------------------------------
	// Quick Actions
	// ----------------------------------------------------------

	_handle_quick_action(doctype, docname, action) {
		const dialog = new frappe.ui.Dialog({
			title: __(action),
			fields: [
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Remarks (optional)"),
				},
			],
			primary_action_label: __(action),
			primary_action: (values) => {
				dialog.hide();
				this._apply_action(doctype, docname, action, values.remarks);
			},
		});
		dialog.show();
	}

	async _apply_action(doctype, docname, action, remarks) {
		frappe.dom.freeze(__("Applying action…"));
		try {
			const r = await frappe.call({
				method: "approval_hub_frappe.api.approval_hub.apply_workflow_action_from_hub",
				args: { doctype, docname, action, remarks },
			});

			if (r.message && r.message.success) {
				frappe.show_alert({
					message: r.message.message || __("Action applied."),
					indicator: "green",
				});
				this.refresh();
			}
		} catch (err) {
			frappe.msgprint({
				title: __("Error"),
				message: err.message || __("An error occurred. Please try again."),
				indicator: "red",
			});
		} finally {
			frappe.dom.unfreeze();
		}
	}

	// ----------------------------------------------------------
	// Page structure
	// ----------------------------------------------------------

	_build_skeleton() {
		const css = this._styles();

		this.$main.html(`
			<style>${css}</style>
			<div class="ah-wrapper">
				<div class="ah-summary-row" id="ah-summary"></div>
				<div class="ah-filters-wrapper" id="ah-filters"></div>
				<div class="ah-list-wrapper" id="ah-list">
					<div class="ah-loading">${__("Loading…")}</div>
				</div>
				<div class="ah-pagination-wrapper" id="ah-pagination"></div>
			</div>
		`);

		this.$summary = this.$main.find("#ah-summary");
		this.$filters = this.$main.find("#ah-filters");
		this.$list = this.$main.find("#ah-list");
		this.$pagination = this.$main.find("#ah-pagination");
	}

	_add_page_actions() {
		this.page.add_action_item(__("Refresh"), () => this.refresh());
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	_set_loading(state) {
		this.loading = state;
		if (state) {
			this.$list.html(`<div class="ah-loading"><div class="ah-spinner"></div>${__("Loading…")}</div>`);
		}
	}

	_show_disabled(message) {
		this.$main.html(`
			<div class="ah-disabled-state">
				<div class="ah-disabled-icon">🔒</div>
				<h3>${__("Approval Hub Disabled")}</h3>
				<p>${message}</p>
			</div>
		`);
	}

	_show_error(message) {
		this.$list.html(`
			<div class="ah-error-state">
				<p>⚠️ ${message}</p>
			</div>
		`);
	}

	// ----------------------------------------------------------
	// Styles (scoped to page)
	// ----------------------------------------------------------

	_styles() {
		return `
/* ---- Approval Hub scoped styles ---- */
.ah-wrapper { padding: 16px 0; }

/* Summary cards */
.ah-summary-row {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
	gap: 16px;
	margin-bottom: 24px;
}
.ah-summary-card {
	background: var(--card-bg);
	border-radius: var(--border-radius-lg);
	padding: 20px 16px;
	text-align: center;
	box-shadow: var(--shadow-sm);
}
.ah-summary-icon { font-size: 24px; margin-bottom: 8px; }
.ah-summary-value {
	font-size: 2rem;
	font-weight: 700;
	color: var(--text-color);
}
.ah-summary-label {
	font-size: var(--text-sm);
	color: var(--text-muted);
	margin-top: 4px;
}

/* Filters */
.ah-filters {
	display: flex;
	flex-wrap: wrap;
	gap: 12px;
	align-items: flex-end;
	background: var(--card-bg);
	padding: 16px;
	border-radius: var(--border-radius-lg);
	box-shadow: var(--shadow-sm);
	margin-bottom: 20px;
}
.ah-filter-group {
	display: flex;
	flex-direction: column;
	gap: 4px;
	min-width: 160px;
}
.ah-filter-group label {
	font-size: var(--text-sm);
	font-weight: 500;
	color: var(--text-muted);
}
.ah-filter-actions {
	flex-direction: row;
	gap: 8px;
	align-items: flex-end;
	min-width: auto;
}

/* Table */
.ah-table-wrapper { overflow-x: auto; }
.ah-table {
	width: 100%;
	border-collapse: collapse;
	font-size: var(--text-sm);
}
.ah-table thead th {
	background: var(--subtle-bg);
	padding: 10px 12px;
	text-align: left;
	font-weight: 600;
	color: var(--text-muted);
	border-bottom: 1px solid var(--border-color);
	white-space: nowrap;
}
.ah-table tbody tr {
	border-bottom: 1px solid var(--border-color);
	transition: background 0.1s;
}
.ah-table tbody tr:hover { background: var(--hover-bg); }
.ah-table tbody td {
	padding: 10px 12px;
	vertical-align: middle;
}
.ah-row-critical { background: rgba(255, 59, 48, 0.05); }

/* Doc link */
.ah-doc-link {
	color: var(--primary);
	text-decoration: none;
	font-weight: 500;
}
.ah-doc-link:hover { text-decoration: underline; }

/* Column constraints */
.ah-col-title {
	max-width: 200px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

/* Badges */
.ah-doctype-badge {
	background: var(--blue-100);
	color: var(--blue-700);
	padding: 2px 8px;
	border-radius: 12px;
	font-size: 11px;
	font-weight: 600;
	white-space: nowrap;
}
.ah-state-badge {
	background: var(--subtle-bg);
	border: 1px solid var(--border-color);
	padding: 2px 8px;
	border-radius: 12px;
	font-size: 11px;
	white-space: nowrap;
}

/* Aging */
.ah-aging {
	padding: 3px 10px;
	border-radius: 12px;
	font-size: 11px;
	font-weight: 600;
	white-space: nowrap;
}
.ah-aging-normal {
	background: var(--green-100, #d1fae5);
	color: var(--green-700, #047857);
}
.ah-aging-warning {
	background: var(--orange-100, #ffedd5);
	color: var(--orange-700, #c2410c);
}
.ah-aging-critical {
	background: var(--red-100, #fee2e2);
	color: var(--red-700, #b91c1c);
}

/* Actions */
.ah-actions-cell { white-space: nowrap; }
.ah-quick-actions { display: inline-flex; gap: 4px; margin-left: 4px; }
.ah-action-approve { background: var(--green-500) !important; color: #fff !important; border-color: var(--green-500) !important; }
.ah-action-reject  { background: var(--red-500)   !important; color: #fff !important; border-color: var(--red-500) !important; }
.ah-action-send-back { background: var(--orange-400) !important; color: #fff !important; border-color: var(--orange-400) !important; }

/* Pagination */
.ah-pagination {
	display: flex;
	justify-content: space-between;
	align-items: center;
	padding: 12px 0;
	font-size: var(--text-sm);
	color: var(--text-muted);
}
.ah-pagination-controls { display: flex; gap: 8px; }

/* States */
.ah-empty-state, .ah-disabled-state, .ah-error-state {
	text-align: center;
	padding: 64px 24px;
	color: var(--text-muted);
}
.ah-empty-icon, .ah-disabled-icon { font-size: 48px; margin-bottom: 16px; }
.ah-empty-state h3, .ah-disabled-state h3 { color: var(--text-color); }
.ah-loading {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 48px;
	justify-content: center;
	color: var(--text-muted);
}
.ah-spinner {
	width: 20px; height: 20px;
	border: 3px solid var(--border-color);
	border-top-color: var(--primary);
	border-radius: 50%;
	animation: ah-spin 0.7s linear infinite;
}
@keyframes ah-spin { to { transform: rotate(360deg); } }
`;
	}
}