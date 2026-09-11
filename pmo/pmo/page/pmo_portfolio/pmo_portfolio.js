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
					<div class="pmo-pf-h2">${__("Requires attention")}</div>
					<div data-region="attention"></div>
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
			this.$root
				.find('[data-region="attention"]')
				.html(
					`<div class="pmo-pf-empty">${__(
						"No visible projects for the current filters."
					)}</div>`
				);
			this.$root.find('[data-region="table"]').html("");
			return;
		}
		this._render_summary();
		this._render_health();
		this._render_attention();
		this._render_table();
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
			kpi(__("Deviated"), c.deviated, c.deviated ? "bad" : ""),
			kpi(__("At risk"), c.at_risk, c.at_risk ? "warn" : ""),
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

	// --- Capa 1b: Health compacto (On track / At risk / Deviated) — proporcional, ancho acotado ---
	_render_health() {
		const c = this._counts();
		const total = c.total || 1;
		const seg = (n, cls) =>
			n
				? `<span class="${cls}" style="width:${(n / total) * 100}%" title="${n}"></span>`
				: "";
		this.$root.find('[data-region="health"]').html(`
			<div class="pmo-pf-hl">
				<div class="pmo-pf-hl-title">${__("Health")}</div>
				<div class="bar">${seg(c.on_track, "ok")}${seg(c.at_risk, "warn")}${seg(c.deviated, "bad")}</div>
				<div class="legend">
					<span><i class="ok"></i>${__("On track")} ${c.on_track}</span>
					<span><i class="warn"></i>${__("At risk")} ${c.at_risk}</span>
					<span><i class="bad"></i>${__("Deviated")} ${c.deviated}</span>
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
						<th colspan="3"></th>
						<th colspan="3" class="grp-h">${__("Schedule")}</th>
						<th colspan="2" class="grp-h">${__("Exceptions")}</th>
						<th colspan="3" class="grp-h">${__("Effort")}</th>
					</tr>
					<tr>
						<th>${__("Project")}</th>
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
`;
		const style = document.createElement("style");
		style.id = "pmo-pf-styles";
		style.textContent = css;
		document.head.appendChild(style);
	}
}
