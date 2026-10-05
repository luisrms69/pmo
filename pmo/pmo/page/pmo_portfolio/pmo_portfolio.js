// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — Portfolio (Page de gestión ejecutiva/PMO).
//
// TODOS los datos analíticos salen del Script Report `PMO Portfolio` vía
// `frappe.desk.query_report.run` -> execute() -> P4 server-side. El cliente NUNCA recalcula health,
// forecast, slips, overdue, planned/actual ni % consumed: solo agrupa/visualiza las filas ya
// devueltas (y ya filtradas/enmascaradas por P4). No se hacen queries adicionales desde JS.
//
// health_key (valor interno estable: on_track/at_risk/deviated) se usa para lógica/color; el texto
// visible viene en `health` (ya traducido por el server). El Script Report sigue disponible en Reports.
//
// IMPORTANTE (layout): `page.body === page.main === .layout-main-section`, y `.page-form` (donde
// `page.add_field` inyecta los filtros) es hijo de `page.body`. Por eso NUNCA se hace `page.body.html()`
// (borraría los filtros): el contenido se renderiza en un contenedor hijo propio (`this.$root`).

frappe.pages["pmo_portfolio"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("PMO Portfolio"),
		single_column: true,
	});
	new PMOPortfolio(page);
};

const REPORT = "PMO Portfolio";

// health_key estable -> color/orden de severidad. La etiqueta visible viene del server (`row.health`).
const HEALTH = {
	deviated: { color: "red", severity: 3 },
	at_risk: { color: "orange", severity: 2 },
	on_track: { color: "green", severity: 1 },
};

class PMOPortfolio {
	constructor(page) {
		this.page = page;
		this.rows = [];
		this.summary = [];

		this._inject_styles();
		this._build_filters(); // crea campos en .page-form (hijo de page.body)
		this._build_layout(); // agrega un contenedor hijo propio; NO borra page.body
		// delegación de clic para drill-down (por instancia; sobre elementos dinámicos)
		this.$root.on("click", ".proj[data-project]", (e) => {
			const p = $(e.currentTarget).attr("data-project");
			if (p) this._open_project(p);
		});
		this.refresh();
	}

	// --- filtros: actúan sobre el motor server-side (mismos que el Script Report) ---
	_build_filters() {
		this.company_field = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			change: () => this.refresh(),
		});
		this.completed_field = this.page.add_field({
			fieldname: "include_completed",
			label: __("Include completed"),
			fieldtype: "Check",
			default: 0,
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	_filters() {
		return {
			company: this.company_field.get_value() || undefined,
			include_completed: this.completed_field.get_value() ? 1 : 0,
		};
	}

	// Contenedor propio APPENDED a page.body (no reemplaza su contenido -> .page-form/filtros intactos).
	_build_layout() {
		this.$root = $(`
			<div class="pmo-pf">
				<div class="pmo-pf-band">
					<div class="pmo-pf-summary" data-region="summary"></div>
					<div class="pmo-pf-healthbox" data-region="health"></div>
				</div>
				<div class="pmo-pf-section">
					<div class="pmo-pf-h2">${__("Project health (PHI)")}</div>
					<div data-region="phi"></div>
				</div>
				<div class="pmo-pf-section pmo-pf-bycust">
					<div class="pmo-pf-h2">${__("Projects by customer")}</div>
					<div data-region="bycustomer"></div>
				</div>
				<div class="pmo-pf-section">
					<div class="pmo-pf-h2">${__("Requires attention")}</div>
					<div data-region="attention"></div>
				</div>
				<div class="pmo-pf-section">
					<div class="pmo-pf-h2">${__("Schedule")}</div>
					<div data-region="cronograma"></div>
				</div>
				<div class="pmo-pf-section">
					<div class="pmo-pf-h2">${__("Portfolio")}</div>
					<div data-region="table"></div>
				</div>
			</div>
		`).appendTo(this.page.body);
	}

	refresh() {
		return frappe
			.call("frappe.desk.query_report.run", {
				report_name: REPORT,
				filters: this._filters(),
			})
			.then((r) => {
				const msg = (r && r.message) || {};
				this.rows = (msg.result || []).filter((row) => row && row.project);
				this.summary = msg.report_summary || [];
				this._render();
			});
	}

	// ------- helpers de derivación (solo cuentan señales existentes; sin nuevo scoring) -------
	_counts() {
		const c = {
			total: this.rows.length,
			on_track: 0,
			at_risk: 0,
			deviated: 0,
			overdue: 0, // proyectos con >=1 tarea vencida
			forecast_exceeds: 0, // proyectos con forecast > compromiso
			no_baseline: 0,
		};
		this.rows.forEach((row) => {
			if (row.health_key in HEALTH) c[row.health_key] += 1;
			if ((row.overdue || 0) > 0) c.overdue += 1;
			if ((row.forecast_exceeds || 0) > 0) c.forecast_exceeds += 1;
			if (!row.has_baseline) c.no_baseline += 1;
		});
		return c;
	}

	// Requiere atención = SOLO señales existentes: deviated / at_risk / overdue>0 / forecast>committed.
	// Orden por severidad (peor primero); NO altera el orden de la tabla completa.
	_attention_rows() {
		return this.rows
			.filter(
				(row) =>
					row.health_key === "deviated" ||
					row.health_key === "at_risk" ||
					(row.overdue || 0) > 0 ||
					(row.forecast_exceeds || 0) > 0
			)
			.sort((a, b) => {
				const sev =
					(HEALTH[b.health_key]?.severity || 0) - (HEALTH[a.health_key]?.severity || 0);
				if (sev) return sev;
				return (b.slip_committed || 0) - (a.slip_committed || 0);
			});
	}

	_render() {
		if (!this.rows.length) {
			this.$root.find('[data-region="summary"]').html("");
			this.$root.find('[data-region="health"]').html("");
			this.$root.find('[data-region="bycustomer"]').html("");
			this.$root
				.find('[data-region="attention"]')
				.html(
					`<div class="pmo-pf-empty">${__(
						"No visible projects for the current filters."
					)}</div>`
				);
			this.$root.find('[data-region="table"]').html("");
			this.$root.find('[data-region="cronograma"]').html("");
			this.$root.find('[data-region="phi"]').html("");
			return;
		}
		this._render_summary();
		this._render_health();
		this._render_phi();
		this._render_customers();
		this._render_attention();
		this._render_cronograma();
		this._render_table();
	}

	// --- PHI: salud integral por proyecto (ADR-0013). Filas ya vienen ordenadas por criticidad
	// desde el server; aquí solo se presentan. Los exentos se muestran como "Basic tracking" (no PHI). ---
	_render_phi() {
		const h = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const sc = (v) => (v == null ? '<span class="dash">—</span>' : v);
		const PHI_CLS = { deviated: "bad", at_risk: "warn", on_track: "ok" };
		const rows = this.rows
			.map((row) => {
				const st = row.phi_state;
				if (st === "scored") {
					const cls = PHI_CLS[row.phi_band] || "";
					return `
					<tr class="phi-row ${cls}">
						<td class="cell-project"><a class="proj" data-project="${h(row.project)}">${h(
						row.project_name || row.project
					)}</a></td>
						<td class="phi-num ${cls}">${row.phi}</td>
						<td><span class="phi-badge ${cls}">${h(row.phi_health)}</span></td>
						<td>${sc(row.phi_execution)}</td>
						<td>${sc(row.phi_schedule)}</td>
						<td>${sc(row.phi_governance)}</td>
						<td class="phi-cov">${h(row.phi_coverage)}${
						row.phi_conditions && row.phi_conditions.length
							? ` · <span class="phi-cond">${h(
									row.phi_conditions.join(", ")
							  )}</span>`
							: ""
					}</td>
					<td>${row.fin_health ? h(row.fin_health) : "—"}</td>
					</tr>`;
				}
				const label = st === "exempt" ? __("Basic tracking") : __("PHI unavailable");
				return `
				<tr class="phi-row muted">
					<td class="cell-project"><a class="proj" data-project="${h(row.project)}">${h(
					row.project_name || row.project
				)}</a></td>
					<td class="phi-num muted">—</td>
					<td><span class="phi-badge muted">${label}</span></td>
					<td>—</td><td>—</td><td>—</td>
					<td class="phi-cov muted">${
						st === "exempt"
							? __("Not subject to PMO monitoring")
							: __("Insufficient execution data")
					}</td>
					<td>${row.fin_health ? h(row.fin_health) : "—"}</td>
				</tr>`;
			})
			.join("");
		this.$root.find('[data-region="phi"]').html(`
			<table class="pmo-pf-table pmo-pf-phi">
				<thead><tr>
					<th>${__("Project")}</th><th>${__("PHI")}</th><th>${__("Health")}</th>
					<th>${__("Execution")}</th><th>${__("Commitment")}</th><th>${__("Governance")}</th>
					<th>${__("Coverage")}</th><th>${__("Financial health")}</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>`);
	}

	// --- Resumen compacto "Proyectos por cliente" — agrupa las MISMAS filas del inventario (ya
	// filtradas/enmascaradas por P4). Solo cuenta proyectos por cliente; sin economía ni nuevas métricas. ---
	_render_customers() {
		const total = this.rows.length || 1; // proporción sobre el total del portafolio (mismas filas)
		const map = new Map();
		this.rows.forEach((row) => {
			const key = row.customer || "";
			map.set(key, (map.get(key) || 0) + 1);
		});
		const bars = [...map.entries()]
			.sort((a, b) => b[1] - a[1])
			.map(([cust, n]) => {
				const label = cust ? frappe.utils.escape_html(cust) : __("No customer");
				const pct = Math.round((n / total) * 100);
				return `
				<div class="pmo-pf-cbar">
					<div class="pmo-pf-cbar-l" title="${label}">${label}</div>
					<div class="pmo-pf-cbar-track"><div class="pmo-pf-cbar-fill" style="width:${pct}%"></div></div>
					<div class="pmo-pf-cbar-v"><b>${n}</b> · ${pct}%</div>
				</div>`;
			})
			.join("");
		this.$root
			.find('[data-region="bycustomer"]')
			.html(`<div class="pmo-pf-cbars">${bars}</div>`);
	}

	// --- Capa 1a: Resumen ejecutivo (KPIs primarios + señales operativas secundarias) ---
	_render_summary() {
		const c = this._counts();
		const kpi = (label, value, cls) =>
			`<div class="pmo-pf-kpi ${
				cls || ""
			}"><div class="v">${value}</div><div class="l">${label}</div></div>`;
		const sec = (label, value, bad) =>
			`<span class="pmo-pf-sec ${
				bad && value ? "bad" : ""
			}"><b>${value}</b> ${label}</span>`;

		const primary = [
			kpi(__("Projects"), c.total),
			kpi(__("Off track"), c.deviated, c.deviated ? "bad" : ""),
			kpi(__("Behind"), c.at_risk, c.at_risk ? "warn" : ""),
			kpi(__("Without baseline"), c.no_baseline, c.no_baseline ? "warn" : ""),
		].join("");

		const secondary = [
			sec(__("With overdue tasks"), c.overdue, true),
			sec(__("Forecast exceeds commitment"), c.forecast_exceeds, true),
		].join("");

		this.$root
			.find('[data-region="summary"]')
			.html(
				`<div class="pmo-pf-kpis">${primary}</div><div class="pmo-pf-secline">${secondary}</div>`
			);
	}

	// --- Capa 1b: Estado de cronograma compacto (En plazo / Con atraso / Desviado) — NO es "salud"
	// (eso es PHI). Proporcional, ancho acotado. ---
	_render_health() {
		const c = this._counts();
		const total = c.total || 1;
		const seg = (n, cls) =>
			n
				? `<span class="${cls}" style="width:${(n / total) * 100}%" title="${n}"></span>`
				: "";
		this.$root.find('[data-region="health"]').html(`
			<div class="pmo-pf-hl">
				<div class="pmo-pf-hl-title">${__("Schedule status")}</div>
				<div class="bar">${seg(c.on_track, "ok")}${seg(c.at_risk, "warn")}${seg(c.deviated, "bad")}</div>
				<div class="legend">
					<span><i class="ok"></i>${__("On schedule")} ${c.on_track}</span>
					<span><i class="warn"></i>${__("Behind")} ${c.at_risk}</span>
					<span><i class="bad"></i>${__("Off track")} ${c.deviated}</span>
				</div>
			</div>`);
	}

	// --- Capa 2: Requiere atención (excepciones; orden por severidad; estado vacío discreto) ---
	_render_attention() {
		const rows = this._attention_rows();
		const $r = this.$root.find('[data-region="attention"]');
		if (!rows.length) {
			$r.html(
				`<div class="pmo-pf-empty muted">${__("No projects require attention.")}</div>`
			);
			return;
		}
		const chip = (txt, cls) => `<span class="pmo-pf-chip ${cls}">${txt}</span>`;
		const items = rows
			.map((row) => {
				const reasons = [];
				if ((row.slip_committed || 0) > 0)
					reasons.push(
						chip(`${__("Slip vs commitment")}: ${row.slip_committed}d`, "bad")
					);
				if ((row.overdue || 0) > 0)
					reasons.push(chip(`${__("Overdue")}: ${row.overdue}`, "bad"));
				if ((row.forecast_exceeds || 0) > 0)
					reasons.push(
						chip(`${__("Forecast > commitment")}: ${row.forecast_exceeds}`, "bad")
					);
				if ((row.slip_baseline || 0) > 0)
					reasons.push(chip(`${__("Slip vs Baseline")}: ${row.slip_baseline}d`, "warn"));
				return `
					<div class="pmo-pf-att">
						<div class="head">
							${this._health_badge(row)}
							<a class="proj" data-project="${frappe.utils.escape_html(row.project)}">${frappe.utils.escape_html(
					row.project_name || row.project
				)}</a>
						</div>
						<div class="reasons">${reasons.join("") || "—"}</div>
					</div>`;
			})
			.join("");
		$r.html(`<div class="pmo-pf-attlist">${items}</div>`);
	}

	// --- Cronograma: tabla específica de Schedule Intelligence (ADR-0017). El JS SOLO presenta; todos los
	// valores, severidades y labels vienen ya resueltos del dominio (scheduling.portfolio_schedule_signals /
	// build_status_report). No hay umbrales, scoring ni reglas de negocio aquí. Orden del motor sin cambios.
	_render_cronograma() {
		const h = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const dash = '<span class="dash">—</span>';
		// Mapa token→clase CSS (presentación pura; el token lo decide el dominio).
		const sevCls = (t) =>
			t === "bad" || t === "critical" || t === "breach"
				? "bad"
				: t === "warn"
				? "warn"
				: t === "ok"
				? "ok"
				: "";
		// Número con severidad del dominio (sin comparar en JS). null → "—".
		const numSev = (v, sev) =>
			v == null ? dash : `<span class="${sevCls(sev)}">${h(v)}</span>`;
		// Slip (SSOT status report, sin token de severidad): formato de signo cosmético, SIN color.
		const slip = (v) => (v == null ? dash : `${v > 0 ? "+" : ""}${v} d`);
		const dt = (v) => (v ? h(v) : dash);
		// Margen vs compromiso: label y severidad ya resueltos en el dominio.
		const margin = (row) =>
			row.committed_margin_label == null
				? dash
				: `<span class="${sevCls(row.committed_margin_sev)}">${h(
						row.committed_margin_label
				  )}</span>`;
		// Calendario: dot de severidad (dominio) + texto corto (nombre/estado), compacto con ellipsis.
		const cal = (row) =>
			row.calendar_short == null
				? dash
				: `<span class="cal-dot ${sevCls(
						row.calendar_sev
				  )}"></span><span class="cal-t" title="${h(row.calendar_short)}">${h(
						row.calendar_short
				  )}</span>`;

		const body = this.rows
			.map(
				(row) => `
			<tr>
				<td class="cell-project"><a class="proj" data-project="${h(row.project)}">${h(
					row.project_name || row.project
				)}</a></td>
				<td class="sec">${dt(row.forecast_end)}</td>
				<td class="num sec">${slip(row.slip_baseline)}</td>
				<td class="num sec">${slip(row.slip_committed)}</td>
				<td class="num">${margin(row)}</td>
				<td class="num">${numSev(row.critical_count, row.critical_sev)}</td>
				<td class="num">${numSev(row.deadline_breach_count, row.deadline_breach_sev)}</td>
				<td class="num">${numSev(row.planning_problems, row.planning_problems_sev)}</td>
				<td class="cal-cell">${cal(row)}</td>
			</tr>`
			)
			.join("");
		this.$root.find('[data-region="cronograma"]').html(`
			<div class="pmo-pf-tablewrap">
			<table class="pmo-pf-table pmo-pf-cron">
				<thead><tr>
					<th>${__("Project")}</th>
					<th>${__("Forecast end")}</th>
					<th class="num">${__("Slip vs Baseline (d)")}</th>
					<th class="num">${__("Slip vs commitment (d)")}</th>
					<th class="num">${__("Margin vs commitment")}</th>
					<th class="num">${__("Critical tasks")}</th>
					<th class="num">${__("Deadlines missed")}</th>
					<th class="num">${__("Planning issues")}</th>
					<th>${__("Calendar")}</th>
				</tr></thead>
				<tbody>${body}</tbody>
			</table>
			</div>`);
	}

	// --- Capa 3: Portafolio completo (TODAS las columnas; orden del motor sin cambios) ---
	_render_table() {
		const h = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const num = (v, d = 1) =>
			v == null
				? '<span class="dash">—</span>'
				: frappe.format(v, { fieldtype: "Float", precision: d });
		const intv = (v, bad) =>
			v == null
				? '<span class="dash">—</span>'
				: `<span class="${bad && v > 0 ? "bad" : ""}">${v}</span>`;
		const dt = (v) => (v ? h(v) : '<span class="dash">—</span>');
		const pct = (v) => {
			if (v == null) return '<span class="dash">—</span>';
			const w = Math.min(100, Math.max(0, v));
			const cls = v > 100 ? "bad" : v >= 80 ? "warn" : "ok";
			return `<span class="pmo-pf-pct"><span class="${cls}" style="width:${w}%"></span></span><span class="pct-t">${v}%</span>`;
		};
		// Orden EXACTO del motor: se itera this.rows tal como llega de query_report.run (sin sort).
		const body = this.rows
			.map(
				(row) => `
			<tr>
				<td class="cell-project"><a class="proj" data-project="${h(row.project)}">${h(
					row.project_name || row.project
				)}</a><div class="muted">${h(row.project)}</div></td>
				<td class="sec">${row.customer ? h(row.customer) : '<span class="dash">—</span>'}</td>
					<td class="sec">${h(row.status)}</td>
				<td>${this._health_badge(row)}</td>
				<td class="sec">${dt(row.forecast_end)}</td>
				<td class="num sec">${intv(row.slip_baseline, true)}</td>
				<td class="num sec">${intv(row.slip_committed, true)}</td>
				<td class="num sec">${intv(row.overdue, true)}</td>
				<td class="num sec">${intv(row.forecast_exceeds, true)}</td>
				<td class="num sec">${num(row.planned_hours)}</td>
				<td class="num sec">${num(row.actual_hours)}</td>
				<td class="pctcell">${pct(row.pct_consumed)}</td>
			</tr>`
			)
			.join("");
		this.$root.find('[data-region="table"]').html(`
			<div class="pmo-pf-tablewrap">
			<table class="pmo-pf-table">
				<thead>
					<tr class="grp">
						<th colspan="4"></th>
						<th colspan="3" class="grp-h">${__("Schedule")}</th>
						<th colspan="2" class="grp-h">${__("Exceptions")}</th>
						<th colspan="3" class="grp-h">${__("Effort")}</th>
					</tr>
					<tr>
						<th>${__("Project")}</th>
						<th>${__("Customer")}</th>
						<th>${__("Status")}</th>
						<th>${__("Health")}</th>
						<th>${__("Forecast end")}</th>
						<th class="num">${__("Slip vs Baseline (d)")}</th>
						<th class="num">${__("Slip vs commitment (d)")}</th>
						<th class="num">${__("Overdue")}</th>
						<th class="num">${__("Forecast > commitment")}</th>
						<th class="num">${__("Planned (h)")}</th>
						<th class="num">${__("Actual (h)")}</th>
						<th>${__("% Consumed")}</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
			</div>`);
	}

	_health_badge(row) {
		const color = (HEALTH[row.health_key] || {}).color || "gray";
		return `<span class="pmo-pf-badge ${color}">${frappe.utils.escape_html(
			row.health || row.health_key || ""
		)}</span>`;
	}

	// --- drill-down: Portfolio -> Project Control (que a su vez ofrece "Abrir Project" al DocType nativo) ---
	_open_project(project) {
		// Punto único de navegación. Project Control lee el Project de frappe.get_route()[1] (mecanismo nativo).
		frappe.set_route("pmo_project_control", project);
	}

	_inject_styles() {
		if (document.getElementById("pmo-pf-styles")) return;
		const css = `
.pmo-pf{padding:6px 2px}
.pmo-pf-band{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
.pmo-pf-summary{flex:1 1 520px;min-width:320px}
.pmo-pf-healthbox{flex:0 0 260px}
.pmo-pf-kpis{display:flex;gap:10px;flex-wrap:wrap}
.pmo-pf-kpi{flex:1 1 110px;min-width:100px;border:1px solid var(--border-color);border-radius:8px;padding:8px 12px;background:var(--card-bg)}
.pmo-pf-kpi .v{font-size:22px;font-weight:700;line-height:1}
.pmo-pf-kpi .l{font-size:11px;color:var(--text-muted);margin-top:4px;text-transform:uppercase;letter-spacing:.02em}
.pmo-pf-kpi.warn .v{color:var(--orange-600)}.pmo-pf-kpi.bad .v{color:var(--red-600)}
.pmo-pf-secline{margin-top:8px;display:flex;gap:18px;flex-wrap:wrap}
.pmo-pf-sec{font-size:12px;color:var(--text-muted)}
.pmo-pf-sec b{color:var(--text-color)}
.pmo-pf-sec.bad b{color:var(--red-600)}
.pmo-pf-hl{border:1px solid var(--border-color);border-radius:8px;padding:8px 12px;background:var(--card-bg)}
.pmo-pf-hl-title{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.02em;margin-bottom:6px}
.pmo-pf-hl .bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--gray-200)}
.pmo-pf-hl .bar span{display:block;height:100%}
.pmo-pf-hl .bar .ok{background:var(--green-500)}.pmo-pf-hl .bar .warn{background:var(--orange-500)}.pmo-pf-hl .bar .bad{background:var(--red-500)}
.pmo-pf-hl .legend{display:flex;flex-direction:column;gap:2px;margin-top:6px;font-size:11px;color:var(--text-muted)}
.pmo-pf-hl .legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:middle}
.pmo-pf-hl .legend i.ok{background:var(--green-500)}.pmo-pf-hl .legend i.warn{background:var(--orange-500)}.pmo-pf-hl .legend i.bad{background:var(--red-500)}
.pmo-pf-section{margin-top:16px}
.pmo-pf-h2{font-size:12px;margin:0 0 8px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.03em;font-weight:600}
.pmo-pf-cbars{display:flex;flex-direction:column;gap:6px}
.pmo-pf-cbar{display:grid;grid-template-columns:minmax(120px,220px) 1fr auto;align-items:center;gap:10px}
.pmo-pf-cbar-l{font-size:12px;color:var(--text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pmo-pf-cbar-track{height:12px;border-radius:6px;background:var(--gray-200);overflow:hidden}
.pmo-pf-cbar-fill{height:100%;background:var(--blue-500,#2490ef);border-radius:6px}
.pmo-pf-cbar-v{font-size:12px;color:var(--text-muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.pmo-pf-cbar-v b{color:var(--text-color)}
.pmo-pf-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;color:#fff}
.pmo-pf-badge.green{background:var(--green-500)}.pmo-pf-badge.orange{background:var(--orange-500)}.pmo-pf-badge.red{background:var(--red-500)}.pmo-pf-badge.gray{background:var(--gray-500)}
.pmo-pf-attlist{display:flex;flex-direction:column;gap:8px}
.pmo-pf-att{border:1px solid var(--border-color);border-left:3px solid var(--red-500);border-radius:6px;padding:8px 12px;background:var(--card-bg)}
.pmo-pf-att .head{display:flex;align-items:center;gap:10px}
.pmo-pf-att .proj{font-weight:600;cursor:pointer}
.pmo-pf-att .reasons{margin-top:6px;display:flex;flex-wrap:wrap;gap:6px}
.pmo-pf-chip{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--gray-200)}
.pmo-pf-chip.bad{background:var(--red-100);color:var(--red-700)}.pmo-pf-chip.warn{background:var(--orange-100);color:var(--orange-700)}
.pmo-pf-empty{padding:8px 2px;color:var(--text-muted)}
.pmo-pf-empty.muted{font-size:12px}
.pmo-pf-tablewrap{overflow-x:auto;border:1px solid var(--border-color);border-radius:8px}
.pmo-pf-table{width:100%;border-collapse:collapse;font-size:12px}
.pmo-pf-table th,.pmo-pf-table td{padding:8px 10px;border-bottom:1px solid var(--border-color);text-align:left;white-space:nowrap}
.pmo-pf-table thead th{background:var(--subtle-fg,var(--gray-100));color:var(--text-muted);font-weight:600}
.pmo-pf-table tr.grp th{background:transparent;border-bottom:none;padding-bottom:2px;font-size:10px;letter-spacing:.04em}
.pmo-pf-table tr.grp th.grp-h{border-left:1px solid var(--border-color);color:var(--text-light,var(--text-muted))}
.pmo-pf-table td.num,.pmo-pf-table th.num{text-align:right}
.pmo-pf-table td.sec{color:var(--text-muted)}
.pmo-pf-table td .bad{color:var(--red-600);font-weight:600}
.pmo-pf-table .dash{color:var(--gray-400)}
.pmo-pf-table td.cell-project .proj{font-weight:600;cursor:pointer;color:var(--text-color)}
.pmo-pf-table .muted{font-size:10px;color:var(--text-muted)}
.pmo-pf-pct{display:inline-block;width:64px;height:8px;border-radius:4px;background:var(--gray-200);overflow:hidden;vertical-align:middle;margin-right:6px}
.pmo-pf-pct span{display:block;height:100%}
.pmo-pf-pct span.ok{background:var(--green-500)}.pmo-pf-pct span.warn{background:var(--orange-500)}.pmo-pf-pct span.bad{background:var(--red-500)}
.pmo-pf-table .pctcell{white-space:nowrap}.pmo-pf-table .pct-t{font-size:11px;color:var(--text-muted)}
/* PHI (ADR-0013) */
.pmo-pf-phi td.phi-num{font-weight:800;font-size:15px;font-variant-numeric:tabular-nums}
.pmo-pf-phi td.phi-num.ok{color:var(--green-600)}.pmo-pf-phi td.phi-num.warn{color:var(--orange-600)}.pmo-pf-phi td.phi-num.bad{color:var(--red-600)}.pmo-pf-phi td.phi-num.muted{color:var(--gray-400)}
.pmo-pf-phi .phi-badge{display:inline-block;padding:2px 9px;border-radius:10px;font-size:11px;font-weight:700;color:#fff}
.pmo-pf-phi .phi-badge.ok{background:var(--green-500)}.pmo-pf-phi .phi-badge.warn{background:var(--orange-500)}.pmo-pf-phi .phi-badge.bad{background:var(--red-500)}.pmo-pf-phi .phi-badge.muted{background:var(--gray-400)}
.pmo-pf-phi tr.phi-row.bad{background:var(--red-50,rgba(226,76,76,.06))}
.pmo-pf-phi tr.phi-row.warn{background:var(--orange-50,rgba(248,129,79,.06))}
.pmo-pf-phi tr.phi-row td{border-left:3px solid transparent}
.pmo-pf-phi tr.phi-row.bad td:first-child{border-left-color:var(--red-500)}
.pmo-pf-phi tr.phi-row.warn td:first-child{border-left-color:var(--orange-500)}
.pmo-pf-phi tr.phi-row.ok td:first-child{border-left-color:var(--green-500)}
.pmo-pf-phi .phi-cov{color:var(--text-muted);font-size:11px}.pmo-pf-phi .phi-cond{color:var(--red-600);font-weight:600}
/* Cronograma (ADR-0017): severidad por token del dominio; sin lógica en JS. */
.pmo-pf-cron td .ok{color:var(--green-600)}.pmo-pf-cron td .warn{color:var(--orange-600);font-weight:600}.pmo-pf-cron td .bad{color:var(--red-600);font-weight:700}
.pmo-pf-cron .cal-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;background:var(--gray-400)}
.pmo-pf-cron .cal-dot.ok{background:var(--green-500)}.pmo-pf-cron .cal-dot.warn{background:var(--orange-500)}.pmo-pf-cron .cal-dot.bad{background:var(--red-500)}
.pmo-pf-cron .cal-cell{max-width:220px}
.pmo-pf-cron .cal-t{display:inline-block;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle;font-size:11px;color:var(--text-muted)}
`;
		const style = document.createElement("style");
		style.id = "pmo-pf-styles";
		style.textContent = css;
		document.head.appendChild(style);
	}
}
