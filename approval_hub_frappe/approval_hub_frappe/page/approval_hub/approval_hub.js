/* global frappe */

frappe.pages["approval-hub"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Approval Hub"),
		single_column: true,
	});
	wrapper.approval_hub = new ApprovalHubPage(page, wrapper);
};

frappe.pages["approval-hub"].on_page_show = function (wrapper) {
	if (wrapper.approval_hub) {
		wrapper.approval_hub._collapse_sidebar_default();
		wrapper.approval_hub.refresh();
	}
};

class ApprovalHubPage {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.$root = $(wrapper).find(".layout-main-section");
		this.settings = {};
		this.configs = [];
		this.state = {
			filters: {
				search: "",
				doctype: "",
				branch: "",
				workflow_state: "",
				aging_status: "",
				date_from: "",
				date_to: "",
			},
			selected_kpi: "total_pending",
			start: 0,
			page_length: 20,
			loading: false,
			compact: false,
			pending_request_id: 0,
			total: 0,
			has_more: false,
			items: [],
			summary: {},
			last_refreshed: null,
		};

		this._render_shell();
		this._bind_events();
		this._setup_page_actions();
		this._collapse_sidebar_default();
		this._load_context();
	}

	_collapse_sidebar_default() {
		try {
			const sidebar = frappe.app && frappe.app.sidebar;
			if (!sidebar) return;

			// Persist collapsed preference and close if currently expanded
			localStorage.setItem("sidebar-expanded", JSON.stringify(false));
			if (sidebar.sidebar_expanded) {
				sidebar.close();
			}
		} catch (e) {
			// no-op
		}
	}

	_setup_page_actions() {
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	async _load_context() {
		this._set_loading(true);
		try {
			const { message } = await frappe.call({ method: "approval_hub_frappe.api.approval_hub.get_page_context" });
			const ctx = message || {};
			if (!ctx.enabled) {
				this._render_disabled(ctx.message || __("Approval Hub is currently disabled."));
				return;
			}
			this.settings = ctx.settings || {};
			this.configs = ctx.configs || [];
			this.state.page_length = this.settings.default_page_size || 20;
			this._render_filter_options(ctx);
			await this.refresh();
		} catch (e) {
			this._render_error(e.message || __("Failed to load page context."));
		} finally {
			this._set_loading(false);
		}
	}

	async refresh() {
		this.state.start = 0;
		await Promise.all([this._load_summary(), this._load_pending(false)]);
		this.state.last_refreshed = frappe.datetime.now_datetime();
		this._render_last_refreshed();
	}

	async _load_summary() {
		const filters = this._effective_filters();
		const { message } = await frappe.call({
			method: "approval_hub_frappe.api.approval_hub.get_approval_summary",
			args: { filters },
		});
		this.state.summary = message || {};
		this._render_kpis();
	}

	async _load_pending(append) {
		const requestId = ++this.state.pending_request_id;
		this._set_loading(true, "list");
		try {
			const filters = this._effective_filters();
			const { message } = await frappe.call({
				method: "approval_hub_frappe.api.approval_hub.get_pending_approvals",
				args: {
					filters,
					start: this.state.start,
					page_length: this.state.page_length,
				},
			});
			if (requestId !== this.state.pending_request_id) return;
			const data = message || {};
			this.state.total = data.total || 0;
			this.state.has_more = Boolean(data.has_more);
			const incoming = data.items || [];
			this.state.items = append ? this.state.items.concat(incoming) : incoming;
			this._render_list();
			this._render_list_meta();
		} catch (e) {
			this._render_error(e.message || __("Failed to load pending approvals."));
		} finally {
			this._set_loading(false, "list");
		}
	}

	_effective_filters() {
		const f = { ...this.state.filters };
		const kpi = this.state.selected_kpi;
		if (kpi === "critical" || kpi === "warning" || kpi === "normal") {
			f.aging_status = kpi;
		}
		return f;
	}

	_render_shell() {
		this.$root.html(`
			<div class="ah-page">
				<div class="ah-header">
					<div>
						<h2 class="ah-title">${__("Approval Hub")}</h2>
						<p class="ah-subtitle">${__("Documents waiting for your action")}</p>
					</div>
					<div class="ah-header-actions">
						<button class="btn btn-default btn-sm ah-refresh">${__("Refresh")}</button>
						<button class="btn btn-default btn-sm ah-compact-toggle">${__("Compact")}</button>
						<span class="ah-last-refreshed"></span>
					</div>
				</div>
				<div class="ah-kpi-grid"></div>
				<div class="ah-filter-card">
					<div class="ah-filter-title">${__("Filter Pending Approvals")}</div>
					<div class="ah-filter-bar">
						<div class="ah-field ah-field-search">
							<label>${__("Search")}</label>
							<div class="ah-search-control"></div>
						</div>
						<div class="ah-field">
							<label>${__("DocType")}</label>
							<div class="ah-doctype-control"></div>
						</div>
						<div class="ah-field">
							<label>${__("Branch")}</label>
							<div class="ah-branch-control"></div>
						</div>
						<div class="ah-field">
							<label>${__("Workflow State")}</label>
							<div class="ah-workflow-state-control"></div>
						</div>
						<div class="ah-field">
							<label>${__("Aging")}</label>
							<div class="ah-aging-control"></div>
						</div>
						<div class="ah-field">
							<label>${__("Date From")}</label>
							<div class="ah-date-from-control"></div>
						</div>
						<div class="ah-field">
							<label>${__("Date To")}</label>
							<div class="ah-date-to-control"></div>
						</div>
						<div class="ah-field ah-field-actions">
							<label>&nbsp;</label>
							<div class="ah-filter-actions-wrap">
								<button class="btn btn-primary ah-apply">${__("Apply Filters")}</button>
								<button class="btn btn-default ah-clear">${__("Clear")}</button>
							</div>
						</div>
					</div>
				</div>
				<div class="ah-list-meta"></div>
				<div class="ah-record-list"></div>
				<div class="ah-load-more-wrap"><button class="btn btn-default ah-load-more">${__("Load More")}</button></div>
			</div>
		`);

		this.$kpis = this.$root.find(".ah-kpi-grid");
		this.$list = this.$root.find(".ah-record-list");
		this.$meta = this.$root.find(".ah-list-meta");
		this.$lastRefreshed = this.$root.find(".ah-last-refreshed");
	}

	_render_filter_options(ctx) {
		this._init_filter_controls(ctx);
		this._init_date_controls();
	}

	_init_filter_controls(ctx) {
		if (this.search_control && this.doctype_control && this.branch_control && this.workflow_state_control && this.aging_control) {
			return;
		}

		this.search_control = frappe.ui.form.make_control({
			parent: this.$root.find(".ah-search-control"),
			df: {
				fieldtype: "Data",
				fieldname: "search",
				label: "",
				placeholder: __("Name, title, requester, branch, state"),
				onchange: () => {
					this.state.filters.search = this.search_control.get_value() || "";
				},
			},
			render_input: true,
		});

		this.doctype_control = frappe.ui.form.make_control({
			parent: this.$root.find(".ah-doctype-control"),
			df: {
				fieldtype: "Select",
				fieldname: "doctype",
				label: "",
				options: [__("All Doctypes"), ...this.configs.map((c) => c.value)].join("\n"),
				onchange: () => {
					const value = this.doctype_control.get_value();
					this.state.filters.doctype = value === __("All Doctypes") ? "" : (value || "");
				},
			},
			render_input: true,
		});

		this.branch_control = frappe.ui.form.make_control({
			parent: this.$root.find(".ah-branch-control"),
			df: {
				fieldtype: "Select",
				fieldname: "branch",
				label: "",
				options: [__("All Branches"), ...(ctx.branches || [])].join("\n"),
				onchange: () => {
					const value = this.branch_control.get_value();
					this.state.filters.branch = value === __("All Branches") ? "" : (value || "");
				},
			},
			render_input: true,
		});

		this.workflow_state_control = frappe.ui.form.make_control({
			parent: this.$root.find(".ah-workflow-state-control"),
			df: {
				fieldtype: "Select",
				fieldname: "workflow_state",
				label: "",
				options: [__("All States"), ...(ctx.workflow_states || [])].join("\n"),
				onchange: () => {
					const value = this.workflow_state_control.get_value();
					this.state.filters.workflow_state = value === __("All States") ? "" : (value || "");
				},
			},
			render_input: true,
		});

		this.aging_control = frappe.ui.form.make_control({
			parent: this.$root.find(".ah-aging-control"),
			df: {
				fieldtype: "Select",
				fieldname: "aging_status",
				label: "",
				options: [
					__("All Aging"),
					__("Critical"),
					__("Warning"),
					__("Normal"),
				].join("\n"),
				onchange: () => {
					const value = this.aging_control.get_value();
					const map = {
						[__("All Aging")]: "",
						[__("Critical")]: "critical",
						[__("Warning")]: "warning",
						[__("Normal")]: "normal",
					};
					this.state.filters.aging_status = map[value] || "";
				},
			},
			render_input: true,
		});

		this.doctype_control.set_value(__("All Doctypes"));
		this.branch_control.set_value(__("All Branches"));
		this.workflow_state_control.set_value(__("All States"));
		this.aging_control.set_value(__("All Aging"));
	}

	_init_date_controls() {
		if (this.date_from_control && this.date_to_control) return;

		this.date_from_control = frappe.ui.form.make_control({
			parent: this.$root.find(".ah-date-from-control"),
			df: {
				fieldtype: "Date",
				fieldname: "date_from",
				label: __("Date From"),
				onchange: () => {
					this.state.filters.date_from = this.date_from_control.get_value() || "";
				},
			},
			render_input: true,
		});

		this.date_to_control = frappe.ui.form.make_control({
			parent: this.$root.find(".ah-date-to-control"),
			df: {
				fieldtype: "Date",
				fieldname: "date_to",
				label: __("Date To"),
				onchange: () => {
					this.state.filters.date_to = this.date_to_control.get_value() || "";
				},
			},
			render_input: true,
		});

		if (!this.state.filters.date_from) {
			const fromDate = frappe.datetime.add_days(frappe.datetime.get_today(), -30);
			this.date_from_control.set_value(fromDate);
			this.state.filters.date_from = fromDate;
		}
		if (!this.state.filters.date_to) {
			const toDate = frappe.datetime.get_today();
			this.date_to_control.set_value(toDate);
			this.state.filters.date_to = toDate;
		}
	}

	_render_kpis() {
		const s = this.state.summary || {};
		const cards = [
			["total_pending", __("Total Pending"), s.total_pending || 0, "teal"],
			["critical", __("Critical"), s.critical || 0, "critical"],
			["warning", __("Warning"), s.warning || 0, "warning"],
			["normal", __("Normal"), s.normal || 0, "normal"],
			["my_available_actions", __("My Available Actions"), s.my_available_actions || 0, "neutral"],
			["oldest_pending", __("Oldest Pending"), s.oldest_pending || 0, "neutral"],
		];
		this.$kpis.html(
			cards
				.map(([key, label, value, tone]) => {
					const active = this.state.selected_kpi === key ? "is-active" : "";
					return `<button class="ah-kpi-card ${active} ah-kpi-${tone}" data-kpi="${key}"><span class="ah-kpi-label">${label}</span><span class="ah-kpi-value">${value}</span></button>`;
				})
				.join("")
		);
	}

	_render_list_meta() {
		this.$meta.text(
			__("Showing {0} of {1}", [this.state.items.length, this.state.total])
		);
		this.$root.find(".ah-load-more-wrap").toggle(this.state.has_more);
	}

	_render_list() {
		if (!this.state.items.length) {
			this.$list.html(`
				<div class="ah-empty-state">
					<div class="ah-empty-icon">✓</div>
					<h4>${__("No pending approvals")}</h4>
					<p>${__("You currently have no documents waiting for your action")}</p>
					<button class="btn btn-default ah-refresh">${__("Refresh")}</button>
				</div>
			`);
			return;
		}

		const rows = this.state.items.map((item) => this._row_html(item)).join("");
		this.$list.html(`<div class="ah-table-wrap"><table class="ah-table"><thead><tr><th>${__("Document")}</th><th>${__("State")}</th><th>${__("Branch")}</th><th>${__("Requester")}</th><th>${__("Amount")}</th><th>${__("Age")}</th><th>${__("Actions")}</th></tr></thead><tbody>${rows}</tbody></table></div>`);
	}

	_row_html(item) {
		const actions = (item.can_quick_action ? item.allowed_actions : []).map((a) => {
			const cls = a.toLowerCase().includes("reject") ? "reject" : a.toLowerCase().includes("approve") ? "approve" : "neutral";
			return `<button class="btn btn-xs ah-action-btn ah-action-${cls}" data-doctype="${frappe.utils.escape_html(item.doctype)}" data-docname="${frappe.utils.escape_html(item.name)}" data-action="${frappe.utils.escape_html(a)}">${frappe.utils.escape_html(a)}</button>`;
		}).join(" ");

		const amount = item.amount != null ? frappe.format(item.amount, { fieldtype: "Currency" }) : "-";
		const compactCls = this.state.compact ? "ah-row-compact" : "";
		return `
			<tr class="${compactCls}">
				<td>
					<div class="ah-doc-title">${frappe.utils.escape_html(item.title || item.name)}</div>
					<div class="ah-doc-meta"><span class="ah-badge ah-doctype">${frappe.utils.escape_html(item.config_label || item.doctype)}</span> <a href="${frappe.utils.escape_html(item.route)}">${frappe.utils.escape_html(item.name)}</a></div>
				</td>
				<td><span class="ah-badge ah-state">${frappe.utils.escape_html(item.workflow_state || "-")}</span></td>
				<td>${frappe.utils.escape_html(item.branch || "-")}</td>
				<td>${frappe.utils.escape_html(item.requester || "-")}</td>
				<td>${amount}</td>
				<td><span class="ah-badge ah-aging-${frappe.utils.escape_html(item.aging_status || "normal")}">${item.age_days != null ? `${item.age_days}d` : "-"}</span></td>
				<td>
					<div class="ah-row-actions">
						<button class="btn btn-default btn-xs ah-open ah-ghost-btn" data-route="${frappe.utils.escape_html(item.route)}">${__("Open")}</button>
						<button class="btn btn-default btn-xs ah-print ah-ghost-btn" data-doctype="${frappe.utils.escape_html(item.doctype)}" data-docname="${frappe.utils.escape_html(item.name)}">${__("Print")}</button>
						${actions}
					</div>
				</td>
			</tr>
		`;
	}

	_bind_events() {
		this.$root.on("click", ".ah-refresh", () => this.refresh());
		this.$root.on("click", ".ah-apply", () => this.refresh());
		this.$root.on("click", ".ah-clear", () => {
			const fromDate = frappe.datetime.add_days(frappe.datetime.get_today(), -30);
			const toDate = frappe.datetime.get_today();
			this.state.filters = { search: "", doctype: "", branch: "", workflow_state: "", aging_status: "", date_from: fromDate, date_to: toDate };
			if (this.search_control) this.search_control.set_value("");
			if (this.doctype_control) this.doctype_control.set_value("");
			if (this.branch_control) this.branch_control.set_value("");
			if (this.workflow_state_control) this.workflow_state_control.set_value("");
			if (this.aging_control) this.aging_control.set_value("");
			if (this.date_from_control) this.date_from_control.set_value("");
			if (this.date_to_control) this.date_to_control.set_value("");
			if (this.date_from_control) this.date_from_control.set_value(fromDate);
			if (this.date_to_control) this.date_to_control.set_value(toDate);
			this.state.selected_kpi = "total_pending";
			this.refresh();
		});
		this.$root.on("click", ".ah-kpi-card", (e) => {
			this.state.selected_kpi = $(e.currentTarget).data("kpi");
			this.state.start = 0;
			this._load_pending(false);
			this._render_kpis();
		});
		this.$root.on("keydown", ".ah-search-control input", (e) => {
			if (e.key === "Enter") this.refresh();
		});

		this.$root.on("click", ".ah-open", (e) => {
			const route = $(e.currentTarget).data("route");
			if (route) frappe.set_route(route);
		});
		this.$root.on("click", ".ah-print", (e) => {
			const doctype = $(e.currentTarget).data("doctype");
			const docname = $(e.currentTarget).data("docname");
			if (!doctype || !docname) return;
			this._open_print_preview(doctype, docname);
		});

		this.$root.on("click", ".ah-load-more", async () => {
			if (this.state.loading || !this.state.has_more) return;
			this.state.start += this.state.page_length;
			await this._load_pending(true);
		});

		this.$root.on("click", ".ah-action-btn", (e) => {
			const $btn = $(e.currentTarget);
			this._run_action($btn.data("doctype"), $btn.data("docname"), $btn.data("action"));
		});

		this.$root.on("click", ".ah-compact-toggle", () => {
			this.state.compact = !this.state.compact;
			this.$root.find(".ah-page").toggleClass("ah-compact", this.state.compact);
			this._render_list();
		});
	}

	_run_action(doctype, docname, action) {
		const needsRemarks = /reject|send back|return/i.test(action);
		if (!needsRemarks) {
			return this._confirm_and_submit_action(doctype, docname, action, null);
		}

		const d = new frappe.ui.Dialog({
			title: __(action),
			fields: [{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks"), reqd: 1 }],
			primary_action_label: __(action),
			primary_action: (values) => {
				d.hide();
				this._confirm_and_submit_action(doctype, docname, action, values.remarks);
			},
		});
		d.show();
	}

	_confirm_and_submit_action(doctype, docname, action, remarks) {
		frappe.confirm(
			__("Are you sure you want to apply <b>{0}</b> on <b>{1}</b>?", [action, docname]),
			() => this._submit_action(doctype, docname, action, remarks)
		);
	}

	async _submit_action(doctype, docname, action, remarks) {
		frappe.dom.freeze(__("Applying action..."));
		try {
			const { message } = await frappe.call({
				method: "approval_hub_frappe.api.approval_hub.apply_workflow_action_from_hub",
				args: { doctype, docname, action, remarks },
			});
			frappe.show_alert({ message: (message && message.message) || __("Action applied"), indicator: "green" });
			await this.refresh();
		} catch (e) {
			frappe.msgprint({ title: __("Action Failed"), message: e.message || __("Could not apply action."), indicator: "red" });
		} finally {
			frappe.dom.unfreeze();
		}
	}

	_render_disabled(message) {
		this.$root.html(`<div class="ah-error-state"><h4>${__("Approval Hub Disabled")}</h4><p>${frappe.utils.escape_html(message)}</p></div>`);
	}

	_render_error(message) {
		this.$list.html(`<div class="ah-error-state"><h4>${__("Something went wrong")}</h4><p>${frappe.utils.escape_html(message)}</p><button class="btn btn-default ah-refresh">${__("Retry")}</button></div>`);
	}

	_render_last_refreshed() {
		if (!this.state.last_refreshed) return;
		this.$lastRefreshed.text(__("Last refreshed: {0}", [frappe.datetime.str_to_user(this.state.last_refreshed)]));
	}

	_set_loading(value, scope) {
		this.state.loading = value;
		if (scope === "list" && value) {
			this.$list.html(`<div class="ah-loading">${__("Loading pending approvals...")}</div>`);
		}
	}

	_open_print_preview(doctype, docname) {
		const lang = (frappe.boot && frappe.boot.lang) || "en";
		const previewUrl = `/printview?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(docname)}&_lang=${encodeURIComponent(lang)}`;
		const safeTitle = frappe.utils.escape_html(`${doctype} ${docname}`);
		const labels = {
			zoomOut: frappe.utils.escape_html(__("Zoom Out")),
			zoomIn: frappe.utils.escape_html(__("Zoom In")),
			zoomReset: frappe.utils.escape_html(__("Reset Zoom")),
			print: frappe.utils.escape_html(__("Print")),
			preview: frappe.utils.escape_html(__("Print Preview")),
		};

		const previewWindow = window.open("", "_blank");
		if (!previewWindow) {
			frappe.msgprint({
				title: __("Popup Blocked"),
				message: __("Please allow popups to open the print preview."),
				indicator: "orange",
			});
			return;
		}

		const html = `<!doctype html>
<html>
<head>
	<meta charset="utf-8" />
	<meta name="viewport" content="width=device-width, initial-scale=1" />
	<title>${safeTitle}</title>
	<style>
		* { box-sizing: border-box; }
		body {
			margin: 0;
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
			height: 100vh;
			display: flex;
			flex-direction: column;
			background: #f5f7fa;
		}
		.preview-toolbar {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 10px 16px;
			background: #ffffff;
			border-bottom: 1px solid #dfe3e8;
			gap: 12px;
		}
		.preview-title {
			font-size: 16px;
			font-weight: 600;
			color: #1f2d3d;
		}
		.preview-actions {
			display: flex;
			align-items: center;
			gap: 8px;
		}
		.preview-actions button {
			border: 1px solid #dfe3e8;
			background: #ffffff;
			padding: 6px 10px;
			border-radius: 6px;
			font-size: 12px;
			cursor: pointer;
		}
		.preview-actions button.primary {
			background: #2490ef;
			color: #ffffff;
			border-color: #2490ef;
		}
		.preview-zoom {
			font-size: 12px;
			color: #52616b;
			min-width: 48px;
			text-align: center;
		}
		.preview-frame-wrap {
			flex: 1 1 auto;
			overflow: auto;
			background: #e9edf2;
			padding: 12px;
		}
		.preview-frame {
			border: 0;
			width: 100%;
			height: 100%;
			background: #ffffff;
			box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
		}
	</style>
</head>
<body>
	<div class="preview-toolbar">
		<div class="preview-title">${labels.preview}</div>
		<div class="preview-actions">
			<button id="zoom-out" title="${labels.zoomOut}">-</button>
			<span class="preview-zoom" id="zoom-label">100%</span>
			<button id="zoom-in" title="${labels.zoomIn}">+</button>
			<button id="zoom-reset" title="${labels.zoomReset}">${labels.zoomReset}</button>
			<button id="print-btn" class="primary">${labels.print}</button>
		</div>
	</div>
	<div class="preview-frame-wrap">
		<iframe class="preview-frame" id="print-preview-frame" src="${previewUrl}"></iframe>
	</div>
	<script>
		(() => {
			const iframe = document.getElementById("print-preview-frame");
			const zoomLabel = document.getElementById("zoom-label");
			const zoomIn = document.getElementById("zoom-in");
			const zoomOut = document.getElementById("zoom-out");
			const zoomReset = document.getElementById("zoom-reset");
			const printBtn = document.getElementById("print-btn");
			let zoom = 1;
			const clamp = (value) => Math.min(2, Math.max(0.5, value));
			const applyZoom = (value) => {
				zoom = clamp(value);
				iframe.style.transform = "scale(" + zoom + ")";
				iframe.style.transformOrigin = "0 0";
				iframe.style.width = (100 / zoom) + "%";
				iframe.style.height = (100 / zoom) + "%";
				zoomLabel.textContent = Math.round(zoom * 100) + "%";
			};
			zoomIn.addEventListener("click", () => applyZoom(zoom + 0.1));
			zoomOut.addEventListener("click", () => applyZoom(zoom - 0.1));
			zoomReset.addEventListener("click", () => applyZoom(1));
			printBtn.addEventListener("click", () => {
				if (!iframe.contentWindow) return;
				iframe.contentWindow.focus();
				iframe.contentWindow.print();
			});
			applyZoom(1);
		})();
	</script>
</body>
</html>`;

		previewWindow.document.open();
		previewWindow.document.write(html);
		previewWindow.document.close();
		previewWindow.focus();
	}
}
