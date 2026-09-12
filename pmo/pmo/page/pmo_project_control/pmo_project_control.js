// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — Project Control (experiencia de gestión de UN Project).
//
// Reúne 4 capacidades ya existentes, SIN motor nuevo ni recálculo en JS:
//   - Status / Schedule   -> Script Report `PMO Status Report`   (query_report.run) — P4 en el motor
//   - Planned vs Actual   -> Script Report `PMO Planned vs Actual`(query_report.run) — P4 en el motor
//   - Baseline Comparison -> Script Report `PMO Baseline Comparison`(query_report.run) — P4 en compare_baselines
//   - Change Control      -> `frappe.db.get_list("PMO Change Request", {project})` — P4 vía
//                            permission_query_conditions (ADR-0005 D13). NO query_report.run (es Report Builder).
//
// Las tablas se renderizan GENÉRICAMENTE desde `columns`+`result` de cada reporte (paridad garantizada:
// mismas columnas/labels/valores que el Script Report). El cliente no recalcula health/forecast/slips/etc.
//
// Contexto de Project: mecanismo nativo `frappe.get_route()[1]` (on_page_show) + selector Link (respeta P4).
// Preparado para abrirse desde un Project con `frappe.set_route("pmo_project_control", <project>)`.
//
// Layout: `page.body === .layout-main-section` y `.page-form` (filtros) es su hijo -> NUNCA `page.body.html()`;
// el contenido va en un contenedor hijo propio (this.$root).

frappe.pages["pmo_project_control"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("PMO Project Control"),
		single_column: true,
	});
	wrapper._pmo = new PMOProjectControl(page);
};

frappe.pages["pmo_project_control"].on_page_show = function (wrapper) {
	if (wrapper._pmo) wrapper._pmo.on_show();
};

const REP_STATUS = "PMO Status Report";
const REP_PVA = "PMO Planned vs Actual";
const REP_BC = "PMO Baseline Comparison";
const CR_DOCTYPE = "PMO Change Request";
const BASELINE_DT = "PMO Project Baseline";

const VIEWS = [
	{ key: "executive", label: __("Executive report") },
	{ key: "status", label: __("Status / Schedule") },
	{ key: "pva", label: __("Planned vs Actual") },
	{ key: "baseline", label: __("Baseline Comparison") },
	{ key: "change", label: __("Change Control") },
];

const WF_COLOR = {
	Draft: "gray",
	"In Review": "orange",
	Approved: "blue",
	Rejected: "red",
	Implemented: "green",
	Closed: "gray",
};

class PMOProjectControl {
	constructor(page) {
		this.page = page;
		this.state = { project: null, status_date: null, view: "executive", baselines: null };

		this._inject_styles();
		this._build_filters(); // Project + Status Date en .page-form (hijo de page.body)
		this._build_layout(); // contenedor hijo propio (no borra page.body -> filtros intactos)
		this.on_show();
	}

	// --- contexto: Project (Link, respeta P4) + Status Date ---
	_build_filters() {
		this.project_field = this.page.add_field({
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			change: () => this._on_project_change(),
		});
		this.status_date_field = this.page.add_field({
			fieldname: "status_date",
			label: __("Status Date"),
			fieldtype: "Date",
			change: () => {
				this.state.status_date = this.status_date_field.get_value() || null;
				if (["executive", "status", "pva"].includes(this.state.view)) this._render_view();
			},
		});
		this.page.set_primary_action(__("Refresh"), () => this._render_view(), "refresh");
	}

	// contenedor propio APPENDED a page.body (no reemplaza su contenido)
	_build_layout() {
		this.$root = $(`
			<div class="pmo-pc">
				<div class="pmo-pc-context" data-region="context"></div>
				<div class="pmo-pc-tabs" data-region="tabs"></div>
				<div class="pmo-pc-view" data-region="view"></div>
			</div>
		`).appendTo(this.page.body);
		this._render_tabs();
	}

	// Se dispara en cada show: toma el Project del route (…/pmo_project_control/<project>) si viene.
	on_show() {
		const route = frappe.get_route() || [];
		const routed = route.length > 1 ? decodeURIComponent(route[1]) : null;
		if (routed && routed !== this.state.project) {
			this.project_field.set_value(routed); // dispara _on_project_change
		} else if (!this.state.project) {
			this._render_view(); // muestra el estado "elige un Project"
		}
	}

	_on_project_change() {
		const p = this.project_field.get_value() || null;
		this.state.project = p;
		this.state.baselines = null; // se recargan por Project
		if (!p) {
			this._render_view();
			return;
		}
		// Cutoff unificado (ADR-0006): la del Project o HOY por defecto (igual que el propio Status Report,
		// que exige fecha de corte y su JS defaultea a hoy). El usuario puede cambiarla.
		frappe.db.get_value("Project", p, "pmo_status_date").then((r) => {
			const sd =
				(r && r.message && r.message.pmo_status_date) || frappe.datetime.get_today();
			this.status_date_field.set_value(sd);
			this.state.status_date = sd;
			this._render_context();
			this._render_view();
		});
	}

	_render_tabs() {
		const $t = this.$root.find('[data-region="tabs"]');
		$t.html(
			VIEWS.map(
				(v) =>
					`<button class="pmo-pc-tab ${
						v.key === this.state.view ? "active" : ""
					}" data-view="${v.key}">${v.label}</button>`
			).join("")
		);
		$t.off("click").on("click", ".pmo-pc-tab", (e) => {
			this.state.view = $(e.currentTarget).attr("data-view");
			this._render_tabs();
			this._render_view();
		});
	}

	_render_context() {
		const $c = this.$root.find('[data-region="context"]');
		if (!this.state.project) {
			$c.html("");
			return;
		}
		const sd = this.state.status_date
			? `${__("Cutoff date")}: <b>${frappe.utils.escape_html(this.state.status_date)}</b>`
			: `${__("Cutoff date")}: <b>${__("today")}</b>`;
		$c.html(
			`<span class="pmo-pc-proj">${frappe.utils.escape_html(this.state.project)}</span>
			 <span class="pmo-pc-cut">${sd}</span>
			 <a class="pmo-pc-open" data-open-project="${frappe.utils.escape_html(this.state.project)}">${__(
				"Open Project"
			)}</a>`
		);
		$c.off("click").on("click", "[data-open-project]", (e) => {
			frappe.set_route("Form", "Project", $(e.currentTarget).attr("data-open-project"));
		});
	}

	_render_view() {
		this._render_context();
		const $v = this.$root.find('[data-region="view"]');
		if (!this.state.project) {
			$v.html(`<div class="pmo-pc-empty">${__("Select a Project to begin.")}</div>`);
			return;
		}
		$v.html(`<div class="pmo-pc-loading">${__("Loading...")}</div>`);
		if (this.state.view === "executive") return this._view_executive($v);
		if (this.state.view === "status")
			return this._view_report($v, REP_STATUS, this._status_filters(), true);
		if (this.state.view === "pva")
			return this._view_report($v, REP_PVA, this._status_filters(), false);
		if (this.state.view === "baseline") return this._view_baseline($v);
		if (this.state.view === "change") return this._view_change($v);
	}

	_status_filters() {
		// Cutoff siempre presente (el Status Report lo exige). Hoy por defecto si se vació.
		return {
			project: this.state.project,
			status_date: this.state.status_date || frappe.datetime.get_today(),
		};
	}

	// --- Vista Reporte Ejecutivo: HTML renderizado server-side (ADR-0011). La Page solo inyecta. ---
	// Contexto y KPIs los compone build_project_control() y los renderiza el template canónico
	// executive.html; el cliente NO recalcula nada. P4 la impone el builder (build_status_report).
	_view_executive($v) {
		frappe
			.xcall("pmo.project_control.get_executive_html", {
				project: this.state.project,
				cutoff: this.state.status_date || frappe.datetime.get_today(),
			})
			.then((html) => $v.html(html))
			.catch(() => {
				$v.html(`<div class="pmo-pc-empty">${__("Could not load the data.")}</div>`);
			});
	}

	// --- Vistas 1 y 2: Script Report vía query_report.run (P4 en el motor) ---
	_view_report($v, report_name, filters, schedule) {
		return frappe
			.call("frappe.desk.query_report.run", { report_name, filters })
			.then((r) => {
				const msg = (r && r.message) || {};
				const rows = msg.result || [];
				const table = rows.length
					? this._table_html(msg.columns || [], rows, schedule)
					: `<div class="pmo-pc-empty note">${
							schedule
								? __(
										"No schedule rows at this cutoff date: this Project has no effective baseline. The summary above still applies."
								  )
								: __("This Project has no tasks with effort to show.")
					  }</div>`;
				$v.html(this._summary_html(msg.report_summary) + table);
			})
			.catch(() => {
				$v.html(`<div class="pmo-pc-empty">${__("Could not load the data.")}</div>`);
			});
	}

	// --- Vista 3: Baseline Comparison (dos baselines del Project; compare_baselines valida P4) ---
	_view_baseline($v) {
		const render = () => {
			const opts = (this.state.baselines || [])
				.map(
					(b) =>
						`<option value="${frappe.utils.escape_html(
							b.name
						)}">${frappe.utils.escape_html(
							b.revision || b.name
						)} · ${frappe.utils.escape_html(b.effective_date || "")}</option>`
				)
				.join("");
			if ((this.state.baselines || []).length < 2) {
				$v.html(
					`<div class="pmo-pc-empty note">${__(
						"Baseline Comparison needs two submitted baselines of this Project. This Project does not have enough yet."
					)}</div>`
				);
				return;
			}
			$v.html(`
				<div class="pmo-pc-bcbar">
					<label>${__("Before baseline")}</label>
					<select data-role="before">${opts}</select>
					<label>${__("After baseline")}</label>
					<select data-role="after">${opts}</select>
					<button class="btn btn-xs btn-primary" data-role="compare">${__("Compare")}</button>
				</div>
				<div data-region="bcresult"></div>`);
			// preselección razonable: before = penúltima, after = última (orden por effective_date asc)
			const n = this.state.baselines.length;
			if (n >= 2) {
				$v.find('[data-role="before"]').val(this.state.baselines[n - 2].name);
				$v.find('[data-role="after"]').val(this.state.baselines[n - 1].name);
			}
			$v.off("click.bc").on("click.bc", '[data-role="compare"]', () => {
				const before = $v.find('[data-role="before"]').val();
				const after = $v.find('[data-role="after"]').val();
				const $out = $v.find('[data-region="bcresult"]');
				if (!before || !after || before === after) {
					$out.html(
						`<div class="pmo-pc-empty">${__("Select two different baselines.")}</div>`
					);
					return;
				}
				$out.html(`<div class="pmo-pc-loading">${__("Loading...")}</div>`);
				frappe
					.call("frappe.desk.query_report.run", {
						report_name: REP_BC,
						filters: {
							project: this.state.project,
							baseline_before: before,
							baseline_after: after,
						},
					})
					.then((r) => {
						const msg = (r && r.message) || {};
						$out.html(
							this._summary_html(msg.report_summary) +
								this._table_html(msg.columns || [], msg.result || [], false)
						);
					})
					.catch(() => {
						$out.html(
							`<div class="pmo-pc-empty">${__("Could not load the data.")}</div>`
						);
					});
			});
		};

		if (this.state.baselines) return render();
		// baselines del Project (docstatus=1). get_list respeta permission_query_conditions del baseline.
		frappe.db
			.get_list(BASELINE_DT, {
				filters: { project: this.state.project, docstatus: 1 },
				fields: ["name", "revision", "effective_date"],
				order_by: "effective_date asc",
				limit: 0,
			})
			.then((rows) => {
				this.state.baselines = rows || [];
				render();
			});
	}

	// --- Vista 4: Change Control (lista de CR del Project; P4 vía pqc, sin Report Builder) ---
	_view_change($v) {
		frappe.db
			.get_list(CR_DOCTYPE, {
				filters: { project: this.state.project },
				fields: [
					"name",
					"title",
					"workflow_state",
					"request_date",
					"priority",
					"impact_summary",
					"baseline_before",
					"baseline_after",
				],
				order_by: "request_date desc",
				limit: 0,
			})
			.then((rows) => {
				if (!rows || !rows.length) {
					$v.html(
						`<div class="pmo-pc-empty note">${__(
							"This Project has no Change Requests."
						)}</div>`
					);
					return;
				}
				const h = (x) => frappe.utils.escape_html(x == null ? "" : String(x));
				const badge = (s) =>
					`<span class="pmo-pc-badge ${WF_COLOR[s] || "gray"}">${h(__(s))}</span>`;
				const body = rows
					.map(
						(cr) => `
					<tr>
						<td><a class="crlink" data-cr="${h(cr.name)}">${h(cr.title || cr.name)}</a>
							<div class="muted">${h(cr.name)}</div></td>
						<td>${cr.workflow_state ? badge(cr.workflow_state) : "—"}</td>
						<td>${h(cr.request_date) || "—"}</td>
						<td>${cr.priority ? h(__(cr.priority)) : "—"}</td>
						<td class="sec">${h(cr.impact_summary) || "—"}</td>
						<td class="sec">${h(cr.baseline_before) || "—"} → ${h(cr.baseline_after) || "—"}</td>
					</tr>`
					)
					.join("");
				$v.html(`
					<div class="pmo-pc-tablewrap"><table class="pmo-pc-table">
						<thead><tr>
							<th>${__("Change Request")}</th>
							<th>${__("State")}</th>
							<th>${__("Request date")}</th>
							<th>${__("Priority")}</th>
							<th>${__("Impact summary")}</th>
							<th>${__("Baselines")}</th>
						</tr></thead>
						<tbody>${body}</tbody>
					</table></div>`);
				$v.off("click.cr").on("click.cr", ".crlink", (e) => {
					frappe.set_route("Form", CR_DOCTYPE, $(e.currentTarget).attr("data-cr"));
				});
			});
	}

	// ---------- render genérico (paridad con el Script Report) ----------
	_summary_html(summary) {
		if (!summary || !summary.length) return "";
		const color = {
			Red: "bad",
			Green: "ok",
			Orange: "warn",
			Blue: "info",
			Gray: "muted",
			Grey: "muted",
		};
		const cards = summary
			.map((s) => {
				const cls = color[s.indicator] || "";
				// Contadores secundarios en 0 (sin indicador de alerta) se atenúan: menos peso visual,
				// sin quitar la métrica. Los que tienen indicador (Red/Orange/…) conservan su énfasis.
				const isCount = ["Int", "Float", "Percent"].includes(s.datatype);
				const zero = isCount && !cls && (s.value === 0 || s.value === 0.0);
				const val = this._fmt_value(s.value, s.datatype);
				return `<div class="pmo-pc-kpi ${cls} ${
					zero ? "zero" : ""
				}"><div class="v">${val}</div><div class="l">${frappe.utils.escape_html(
					s.label || ""
				)}</div></div>`;
			})
			.join("");
		return `<div class="pmo-pc-kpis">${cards}</div>`;
	}

	_table_html(columns, rows, schedule) {
		if (!columns.length) return `<div class="pmo-pc-empty">${__("No data.")}</div>`;
		const head = columns
			.map(
				(c) =>
					`<th class="${this._is_num(c) ? "num" : ""}">${frappe.utils.escape_html(
						c.label || ""
					)}</th>`
			)
			.join("");
		const body = rows
			.map((row) => {
				const tds = columns
					.map((c) => {
						const raw = row[c.fieldname];
						const num = this._is_num(c);
						let cell = this._fmt_cell(raw, c);
						// realces mínimos (no recalculan nada): slip/variance positivos en rojo; % consumido con barra
						let cls = num ? "num" : "";
						if (
							/slip|variance/i.test(c.fieldname) &&
							typeof raw === "number" &&
							raw > 0
						)
							cls += " bad";
						if (c.fieldtype === "Percent" || /consumed/i.test(c.fieldname))
							cell = this._pct(raw);
						return `<td class="${cls}">${cell}</td>`;
					})
					.join("");
				return `<tr>${tds}</tr>`;
			})
			.join("");
		return `<div class="pmo-pc-tablewrap ${
			schedule ? "schedule" : ""
		}"><table class="pmo-pc-table">
			<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
	}

	_is_num(c) {
		return ["Int", "Float", "Currency", "Percent"].includes(c.fieldtype);
	}

	_fmt_cell(v, c) {
		if (v == null || v === "") return '<span class="dash">—</span>';
		if (c.fieldtype === "Link" && (c.options === "Task" || c.options === "Project")) {
			return `<a class="proj" data-doctype="${frappe.utils.escape_html(
				c.options
			)}" data-name="${frappe.utils.escape_html(v)}">${frappe.utils.escape_html(v)}</a>`;
		}
		if (this._is_num(c)) return frappe.format(v, { fieldtype: c.fieldtype });
		return frappe.utils.escape_html(String(v));
	}

	_fmt_value(v, datatype) {
		if (v == null || v === "") return "—";
		if (["Int", "Float", "Currency", "Percent"].includes(datatype))
			return frappe.format(v, { fieldtype: datatype });
		return frappe.utils.escape_html(String(v));
	}

	_pct(v) {
		if (v == null) return '<span class="dash">—</span>';
		const w = Math.min(100, Math.max(0, v));
		const cls = v > 100 ? "bad" : v >= 80 ? "warn" : "ok";
		return `<span class="pmo-pc-pct"><span class="${cls}" style="width:${w}%"></span></span><span class="pct-t">${v}%</span>`;
	}

	_inject_styles() {
		if (document.getElementById("pmo-pc-styles")) return;
		const css = `
.pmo-pc{padding:6px 2px}
.pmo-pc-context{display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap}
.pmo-pc-proj{font-weight:700;font-size:15px}
.pmo-pc-cut{color:var(--text-muted);font-size:12px}
.pmo-pc-open{font-size:12px;cursor:pointer}
.pmo-pc-tabs{display:flex;gap:4px;border-bottom:1px solid var(--border-color);margin-bottom:14px;flex-wrap:wrap}
.pmo-pc-tab{border:none;background:transparent;padding:8px 14px;font-size:13px;color:var(--text-muted);border-bottom:2px solid transparent;cursor:pointer}
.pmo-pc-tab.active{color:var(--text-color);border-bottom-color:var(--primary);font-weight:600}
.pmo-pc-kpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.pmo-pc-kpi{flex:1 1 120px;min-width:104px;border:1px solid var(--border-color);border-radius:8px;padding:6px 10px;background:var(--card-bg)}
.pmo-pc-kpi .v{font-size:16px;font-weight:700;line-height:1.1}
.pmo-pc-kpi .l{font-size:10px;color:var(--text-muted);margin-top:3px;text-transform:uppercase;letter-spacing:.02em}
.pmo-pc-kpi.bad .v{color:var(--red-600)}.pmo-pc-kpi.warn .v{color:var(--orange-600)}.pmo-pc-kpi.ok .v{color:var(--green-600)}.pmo-pc-kpi.info .v{color:var(--blue-600)}
.pmo-pc-kpi.zero{opacity:.5}.pmo-pc-kpi.zero .v{font-weight:600}
.pmo-pc-bcbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.pmo-pc-bcbar label{font-size:11px;color:var(--text-muted);margin:0}
.pmo-pc-bcbar select{max-width:280px}
.pmo-pc-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;color:#fff}
.pmo-pc-badge.green{background:var(--green-500)}.pmo-pc-badge.orange{background:var(--orange-500)}.pmo-pc-badge.red{background:var(--red-500)}.pmo-pc-badge.blue{background:var(--blue-500)}.pmo-pc-badge.gray{background:var(--gray-500)}
.pmo-pc-empty,.pmo-pc-loading{padding:12px 2px;color:var(--text-muted)}
.pmo-pc-empty.note{border:1px dashed var(--border-color);border-radius:8px;padding:14px 16px;background:var(--subtle-fg,var(--gray-50));font-size:13px}
.pmo-pc-tablewrap{overflow-x:auto;border:1px solid var(--border-color);border-radius:8px}
.pmo-pc-table{width:100%;border-collapse:collapse;font-size:12px}
.pmo-pc-table th,.pmo-pc-table td{padding:8px 10px;border-bottom:1px solid var(--border-color);text-align:left;white-space:nowrap}
.pmo-pc-table thead th{background:var(--subtle-fg,var(--gray-100));color:var(--text-muted);font-weight:600}
.pmo-pc-table td.num,.pmo-pc-table th.num{text-align:right}
.pmo-pc-table td.sec{color:var(--text-muted)}
.pmo-pc-table td.bad{color:var(--red-600);font-weight:600}
.pmo-pc-table .dash{color:var(--gray-400)}
.pmo-pc-table .proj,.pmo-pc-table .crlink{cursor:pointer;font-weight:600}
.pmo-pc-table .muted{font-size:10px;color:var(--text-muted)}
.pmo-pc-pct{display:inline-block;width:64px;height:8px;border-radius:4px;background:var(--gray-200);overflow:hidden;vertical-align:middle;margin-right:6px}
.pmo-pc-pct span{display:block;height:100%}
.pmo-pc-pct span.ok{background:var(--green-500)}.pmo-pc-pct span.warn{background:var(--orange-500)}.pmo-pc-pct span.bad{background:var(--red-500)}
.pmo-pc-table .pct-t{font-size:11px;color:var(--text-muted)}
`;
		const style = document.createElement("style");
		style.id = "pmo-pc-styles";
		style.textContent = css;
		document.head.appendChild(style);
		// drill-down de celdas Link (Task/Project) — delegación por instancia
		this._bind_cell_drill = true;
	}
}

// drill-down de celdas Link Task/Project (delegación global una sola vez)
$(document)
	.off("click.pmopc")
	.on("click.pmopc", ".pmo-pc .proj[data-doctype]", function () {
		const dt = $(this).attr("data-doctype");
		const name = $(this).attr("data-name");
		if (dt && name) frappe.set_route("Form", dt, name);
	});
