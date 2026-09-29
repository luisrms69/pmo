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
		title: __("PMO Panel"),
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
const PANEL = "pmo.project_control"; // backend natural del Panel PMO (contrato contextual project_governance_state)
const BL_MOD = "pmo.pmo.doctype.pmo_project_baseline.pmo_project_baseline";

// Gobernanza es la primera pestaña (consola operativa del Project). El resto son las capacidades de control
// existentes. Color por etapa (solo presentación; la clasificación la produce el motor vía el contrato).
const GOV_PAL = {
	acta: "#2f6fed",
	baseline: "#6a2be0",
	risk: "#e8590c",
	change: "#0f766e",
	closure: "#c31336",
	review: "#6d28d9",
};

const VIEWS = [
	{ key: "executive", label: __("Summary") },
	{ key: "status", label: __("Status / Schedule") },
	{ key: "baseline", label: __("Baseline Comparison") },
	{ key: "change", label: __("Change Control") },
	{ key: "financial", label: __("Financial") },
	{ key: "governance", label: __("Governance") }, // al FINAL, después de Financiero
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
				if (["executive", "status"].includes(this.state.view)) this._render_view();
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
		// Pestaña inicial opcional por ruta (…/pmo_project_control/<project>/<view>). Sin ella, landing = Resumen.
		const wantedView = route.length > 2 ? route[2] : null;
		if (wantedView && VIEWS.some((v) => v.key === wantedView)) {
			this.state.view = wantedView;
			this._render_tabs();
		}
		if (routed && routed !== this.state.project) {
			this.project_field.set_value(routed); // dispara _on_project_change → _render_view (usa state.view)
		} else if (!this.state.project || wantedView) {
			this._render_view();
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
		if (this.state.view === "governance") return this._view_governance($v);
		if (this.state.view === "executive") return this._view_executive($v);
		if (this.state.view === "financial") return this._view_financial($v);
		if (this.state.view === "status") return this._view_schedule($v);
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

	// --- Vista Resumen: HTML renderizado server-side (get_summary_html → resumen.html). La Page solo
	// inyecta; todo lo compone build_project_control (+ build_expediente/governance_flags/risk_signals).
	// El cliente NO recalcula nada. P4 la impone el builder. executive.html/get_executive_html quedan
	// intactos para el Print Format. ---
	_view_executive($v) {
		frappe
			.xcall("pmo.project_control.get_summary_html", {
				project: this.state.project,
				cutoff: this.state.status_date || frappe.datetime.get_today(),
			})
			.then((html) => {
				$v.html(html);
				this._wire_risk_actions($v); // acciones contextuales de la sección Riesgos
				this._wire_summary_actions($v); // drill-down: gobernanza (Form) + saltos a otras pestañas
			})
			.catch(() => {
				$v.html(`<div class="pmo-pc-empty">${__("Could not load the data.")}</div>`);
			});
	}

	// Drill-down del Resumen hacia rutas/artefactos EXISTENTES: documentos de gobernanza (Form) y saltos
	// a otras pestañas ya presentes (Estado/Cronograma, Control de cambios). No crea rutas nuevas.
	_wire_summary_actions($v) {
		$v.off("click.pmosum")
			.on("click.pmosum", ".pmo-sum-doc", (e) => {
				const dt = $(e.currentTarget).attr("data-doctype");
				const name = $(e.currentTarget).attr("data-name");
				if (dt && name) frappe.set_route("Form", dt, name);
			})
			.on("click.pmosum", ".pmo-sum-goto", (e) => {
				const view = $(e.currentTarget).attr("data-view");
				if (view) {
					this.state.view = view;
					this._render_tabs();
					this._render_view();
				}
			});
	}

	// ADR-0016: cablea las acciones de la sección Riesgos (route-agnóstico, sin hardcodear /desk|/app).
	// "Realizar/Ver evaluación" = open-or-create del Assessment; "Gestionar riesgos" = lista PMO Project Risk
	// FILTRADA por este Project (no global).
	_wire_risk_actions($v) {
		const project = this.state.project;
		$v.off("click.pmorisk")
			.on("click.pmorisk", ".pmo-risk-assess", (e) => {
				const a = $(e.currentTarget).attr("data-assessment");
				if (a) frappe.set_route("Form", "PMO Project Risk Assessment", a);
				else frappe.new_doc("PMO Project Risk Assessment", { project });
			})
			.on("click.pmorisk", ".pmo-risk-manage", () => {
				frappe.set_route("List", "PMO Project Risk", { project });
			});
	}

	// --- Vista Financiera: HTML server-side (build_project_control + pc.costs + gate económico). ---
	// La Page solo inyecta; el permiso económico se decide server-side (no en JS). Excluida del PDF.
	_view_financial($v) {
		frappe
			.xcall("pmo.project_control.get_financial_html", {
				project: this.state.project,
				cutoff: this.state.status_date || frappe.datetime.get_today(),
			})
			.then((html) => $v.html(html))
			.catch(() => {
				$v.html(`<div class="pmo-pc-empty">${__("Could not load the data.")}</div>`);
			});
	}

	// --- Vista Estado / Cronograma: HTML server-side (get_schedule_html → estado.html). Gantt comparativo
	// (línea base vs plan vigente) + estado de ejecución + excepciones. La Page solo inyecta; el cliente NO
	// recalcula fechas/slips (los compone build_status_report + snapshots + compare_snapshots). P4 en el motor. ---
	_view_schedule($v) {
		frappe
			.xcall("pmo.project_control.get_schedule_html", {
				project: this.state.project,
				cutoff: this.state.status_date || frappe.datetime.get_today(),
			})
			.then((html) => {
				$v.html(html);
				this._wire_task_drill($v); // clic en Task/hito → Task nativo
			})
			.catch(() => {
				$v.html(`<div class="pmo-pc-empty">${__("Could not load the data.")}</div>`);
			});
	}

	// Drill-down de cronograma: clic en cualquier elemento con data-task → Form Task nativo (ruta existente).
	_wire_task_drill($v) {
		$v.off("click.pmotask").on("click.pmotask", "[data-task]", (e) => {
			const t = $(e.currentTarget).attr("data-task");
			if (t) frappe.set_route("Form", "Task", t);
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
				// Tarjeta con navegación (p. ej. Línea base vigente): muestra el valor humano (revision) como
				// enlace al documento, sin cambiar la identidad interna.
				const val = s._open
					? `<a href="/app/${frappe.router.slug(s._open.doctype)}/${encodeURIComponent(
							s._open.name
					  )}">${frappe.utils.escape_html(String(s.value))}</a>`
					: this._fmt_value(s.value, s.datatype);
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

	// --- Vista Gobernanza: consola operativa del ciclo del Project. Los DATOS y la clasificación vienen del
	// contrato `project_governance_state` (que reutiliza el motor _evaluate); aquí SOLO se presenta y se
	// dispara la acción contextual. La creación siempre nace vinculada al Project actual. -----------------
	_view_governance($v) {
		frappe
			.xcall(`${PANEL}.project_governance_state`, { project: this.state.project })
			.then((d) => this._render_governance($v, d))
			.catch(() => {
				$v.html(`<div class="pmo-pc-empty">${__("Could not load the PMO panel.")}</div>`);
			});
	}

	_render_governance($v, d) {
		const esc = frappe.utils.escape_html;
		if (d.exempt) {
			$v.html(
				`<div class="gv-exempt"><b>${__(
					"Excluded from PMO governance"
				)}</b><div class="gv-r">${esc(d.exempt_reason || "—")}</div></div>`
			);
			return;
		}
		const next = (d.controls || []).find((c) => c.state === "pendiente");
		const head =
			`<div class="gv-head"><div><div class="gv-title">${__("Project governance")}</div>` +
			`<div class="gv-sub">${__(
				"Where this project stands, what is missing, and who must act."
			)}</div></div>` +
			`<div class="gv-badge ${d.pending_count ? "warn" : "ok"}">${
				d.pending_count ? `${d.pending_count} ${__("pending")}` : __("Up to date")
			}</div></div>` +
			(next
				? `<div class="gv-next">${__("Next step")}: <b>${esc(next.label)}</b>${
						next.action_owner ? ` · ${esc(next.action_owner)}` : ""
				  }</div>`
				: "");
		const cards = (d.controls || [])
			.map((c, i) => this._gov_card(c, i + 1, d))
			.join('<span class="gv-arrow">›</span>');
		$v.html(`<div class="gv">${head}<div class="gv-cycle">${cards}</div></div>`);
		this._gov_wire($v, d);
	}

	_gov_state_chip(c) {
		if (c.state === "completo") return `<span class="gv-st ok">✓ ${__("Complete")}</span>`;
		if (c.state === "pendiente") return `<span class="gv-st pend">! ${__("Pending")}</span>`;
		return `<span class="gv-st na">${__("Not applicable yet")}</span>`;
	}

	_gov_line(c) {
		const esc = frappe.utils.escape_html;
		if (c.state === "no_aplica")
			return `<div class="gv-line muted">${esc(c.na_reason || "")}</div>`;
		if (c.control === "risk" && c.counts) {
			if (!c.counts.assessment_exists)
				return `<div class="gv-line">${__("Risk assessment pending")}</div>`;
			return `<div class="gv-line">${c.counts.open} ${__("active")} · ${
				c.counts.needs_attention
			} ${__("need attention")}</div>`;
		}
		if (c.control === "change" && c.counts) {
			if (!c.counts.open)
				return `<div class="gv-line muted">${__("No change requests")}</div>`;
			return `<div class="gv-line">${c.counts.open} ${__("open")}${
				c.counts.in_review ? ` · ${c.counts.in_review} ${__("awaiting PMO")}` : ""
			}</div>`;
		}
		if (c.situation) return `<div class="gv-line">${esc(c.situation)}</div>`;
		return "";
	}

	_gov_btn(label, gact, control, opts = {}) {
		const dis = opts.disabled ? "disabled" : "";
		const title = opts.title ? `title="${frappe.utils.escape_html(opts.title)}"` : "";
		const cls = opts.primary ? "btn-primary" : "btn-default";
		return `<button class="btn btn-xs ${cls}" data-gact="${gact}" data-control="${control}" ${dis} ${title}>${frappe.utils.escape_html(
			label
		)}</button>`;
	}

	_gov_actions(c, d) {
		const k = c.control;
		const needPerm = __("Requires the appropriate role/permission");
		const btns = [];
		if (c.existing && c.state !== "pendiente") {
			// documento existente → abrir (lectura siempre disponible)
			if (k !== "change") btns.push(this._gov_btn(__("Open"), "open", k, {}));
		}
		if (k === "baseline") {
			if (d.baseline.has_baseline) {
				if (d.baseline.eligible_crs?.length || d.baseline.can_replan)
					btns.push(this._gov_btn(__("New baseline"), "newbaseline", k, {}));
				if (d.baseline.baseline_count > 0)
					btns.push(this._gov_btn(__("History"), "history", k, {}));
			} else if (c.state === "pendiente") {
				btns.push(
					this._gov_btn(__("Set baseline"), "establish", k, {
						primary: true,
						disabled: !c.can_create,
						title: c.can_create ? "" : needPerm,
					})
				);
			}
		} else if (k === "risk") {
			if (c.counts && !c.counts.assessment_exists)
				btns.push(
					this._gov_btn(__("Assess risks"), "new", k, {
						primary: c.state === "pendiente",
						disabled: !c.can_create,
						title: c.can_create ? "" : needPerm,
					})
				);
			else btns.push(this._gov_btn(__("Manage risks"), "risklist", k, {}));
		} else if (k === "change") {
			btns.push(this._gov_btn(__("View changes"), "crlist", k, {}));
			btns.push(
				this._gov_btn(__("New request"), "new", k, {
					disabled: !c.can_create,
					title: c.can_create ? "" : needPerm,
				})
			);
		} else if (c.state === "pendiente") {
			// acta / cierre / revisión pendientes → crear (según permisos)
			const label =
				k === "acta"
					? __("Create record")
					: k === "closure"
					? __("Create closure")
					: __("Create review");
			btns.push(
				this._gov_btn(label, "new", k, {
					primary: true,
					disabled: !c.can_create,
					title: c.can_create ? "" : needPerm,
				})
			);
		}
		return btns.join(" ");
	}

	_gov_card(c, n, d) {
		const esc = frappe.utils.escape_html;
		const col = GOV_PAL[c.control] || "var(--text-muted)";
		const owner =
			c.state === "pendiente" && c.action_owner
				? `<span class="gv-own ${c.action_owner === "PMO" ? "pmo" : "pm"}">${esc(
						c.action_owner
				  )}</span>`
				: "";
		return (
			`<div class="gv-card" style="border-top:3px solid ${col}">` +
			`<div class="gv-cn"><span class="gv-num" style="background:${col}">${n}</span>` +
			`<span class="gv-nm">${esc(c.label)}</span>${owner}</div>` +
			`<div class="gv-desc">${esc(c.description)}</div>` +
			`<div class="gv-status">${this._gov_state_chip(c)}</div>` +
			this._gov_line(c) +
			`<div class="gv-acts">${this._gov_actions(c, d)}</div>` +
			`</div>`
		);
	}

	_gov_wire($v, d) {
		const self = this;
		const cmap = {};
		(d.controls || []).forEach((c) => (cmap[c.control] = c));
		const NEW_DT = {
			acta: "PMO Project Handoff",
			risk: "PMO Project Risk Assessment",
			change: "PMO Change Request",
			closure: "PMO Project Closure",
			review: "PMO Post-Project Review",
		};
		$v.off("click.gov").on("click.gov", "[data-gact]", function () {
			const gact = $(this).attr("data-gact");
			const k = $(this).attr("data-control");
			const c = cmap[k];
			if (gact === "open" && c.existing)
				frappe.set_route("Form", c.existing.doctype, c.existing.name);
			else if (gact === "new") frappe.new_doc(NEW_DT[k], { project: self.state.project });
			else if (gact === "establish") self._establish_baseline();
			else if (gact === "newbaseline") self._new_baseline(d.baseline);
			else if (gact === "history")
				frappe.set_route("List", BASELINE_DT, { project: self.state.project });
			else if (gact === "risklist")
				frappe.set_route("List", "PMO Project Risk", { project: self.state.project });
			else if (gact === "crlist")
				frappe.set_route("List", CR_DOCTYPE, { project: self.state.project });
		});
	}

	_establish_baseline() {
		const self = this;
		frappe.prompt(
			[
				{
					fieldtype: "Small Text",
					fieldname: "reason",
					label: __("Reason (justification)"),
					reqd: 1,
				},
			],
			(v) => {
				frappe
					.xcall(`${BL_MOD}.establish_baseline`, {
						project: self.state.project,
						reason: v.reason,
					})
					.then((r) => {
						frappe.show_alert({
							message: __("Baseline set: {0}", [r.revision]),
							indicator: "green",
						});
						self._render_view();
					});
			},
			__("Set baseline"),
			__("Confirm")
		);
	}

	_new_baseline(bl) {
		const self = this;
		const has_cr = (bl.eligible_crs || []).length > 0;
		if (!has_cr && !bl.can_replan) {
			frappe.msgprint({
				title: __("New baseline"),
				indicator: "orange",
				message: __(
					"A formal substitution needs an approved, implemented Change Request. A PMO replan (without a Change Request) requires an authorized PMO role."
				),
			});
			return;
		}
		const fields = [];
		if (has_cr)
			fields.push({
				fieldtype: "Select",
				fieldname: "change_request",
				label: bl.can_replan
					? __("Backing Change Request (optional)")
					: __("Backing Change Request"),
				options: (bl.can_replan ? [""] : [])
					.concat((bl.eligible_crs || []).map((c) => c.name))
					.join("\n"),
				reqd: bl.can_replan ? 0 : 1,
			});
		fields.push({
			fieldtype: "Small Text",
			fieldname: "reason",
			label: __("Reason (justification)"),
			reqd: 1,
		});
		frappe.prompt(
			fields,
			(v) => {
				frappe
					.xcall(`${BL_MOD}.new_baseline`, {
						project: self.state.project,
						reason: v.reason,
						change_request: v.change_request || null,
					})
					.then((r) => {
						frappe.show_alert({
							message: __("New baseline created: {0}", [r.revision]),
							indicator: "green",
						});
						self._render_view();
					});
			},
			__("New baseline"),
			__("Confirm")
		);
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
/* Gobernanza (consola del ciclo) */
.gv-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:2px 0 6px;flex-wrap:wrap}
.gv-title{font-size:15px;font-weight:600}
.gv-sub{font-size:12px;color:var(--text-muted)}
.gv-badge{padding:4px 12px;border-radius:12px;font-size:12px;font-weight:700}
.gv-badge.warn{background:var(--orange-100,#fdecd2);color:var(--orange-700,#a5680d)}
.gv-badge.ok{background:var(--green-100,#d7f0e0);color:var(--green-700,#1a7a4d)}
.gv-next{font-size:12px;color:var(--text-color);margin:2px 0 12px}
.gv-cycle{display:flex;flex-wrap:nowrap;align-items:stretch;gap:0}
.gv-card{flex:1 1 0;min-width:0;border:1px solid var(--border-color);border-radius:10px;padding:11px 11px 10px;display:flex;flex-direction:column;gap:6px;background:var(--card-bg)}
.gv-cn{display:flex;align-items:center;gap:8px}
.gv-num{width:20px;height:20px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto}
.gv-nm{font-weight:600;font-size:12.5px;line-height:1.15}
.gv-own{margin-left:auto;padding:0 7px;border-radius:9px;font-size:10px;font-weight:700}
.gv-own.pmo{background:var(--red-100,#fde4e4);color:var(--red-700,#a82121)}
.gv-own.pm{background:var(--blue-100,#d3e6fb);color:var(--blue-700,#12659e)}
.gv-desc{font-size:11px;color:var(--text-muted);line-height:1.3;min-height:42px}
.gv-st{font-size:11px;font-weight:600}
.gv-st.ok{color:var(--green-600,#28a745)}.gv-st.pend{color:var(--orange-600,#e8951b)}.gv-st.na{color:var(--text-muted)}
.gv-line{font-size:11px;color:var(--text-color)}.gv-line.muted{color:var(--text-muted)}
.gv-acts{margin-top:auto;display:flex;flex-wrap:wrap;gap:5px;padding-top:4px}
.gv-acts .btn-xs{font-size:11px;padding:2px 8px}
.gv-arrow{align-self:center;color:var(--text-muted);font-size:16px;flex:0 0 auto;padding:0 2px}
.gv-exempt{padding:14px;border:1px dashed var(--border-color);border-radius:10px}
.gv-exempt .gv-r{color:var(--text-muted);font-size:12px;margin-top:4px}
@media(max-width:1000px){.gv-cycle{flex-wrap:wrap}.gv-card{flex:1 1 150px;min-width:150px}.gv-arrow{display:none}}
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
