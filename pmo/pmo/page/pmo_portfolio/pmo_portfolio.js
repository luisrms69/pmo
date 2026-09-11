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
		this.$body = $(page.body);
		this.rows = [];
		this.summary = [];

		this._inject_styles();
		this._build_filters();
		this._build_layout();
		// delegación de clic para drill-down (por instancia; sobre elementos dinámicos)
		this.$body.on("click", ".proj[data-project]", (e) => {
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

	_build_layout() {
		this.$body.html(`
			<div class="pmo-pf">
				<div class="pmo-pf-kpis" data-region="kpis"></div>
				<h2 class="pmo-pf-h2">${__("Requires attention")}</h2>
				<div data-region="attention"></div>
				<h2 class="pmo-pf-h2">${__("Portfolio")}</h2>
				<div data-region="table"></div>
			</div>
		`);
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
			this.$body.find('[data-region="kpis"]').html("");
			this.$body
				.find('[data-region="attention"]')
				.html(
					`<div class="pmo-pf-empty">${__(
						"No visible projects for the current filters."
					)}</div>`
				);
			this.$body.find('[data-region="table"]').html("");
			return;
		}
		this._render_kpis();
		this._render_attention();
		this._render_table();
	}

	// --- Capa 1: Resumen (KPIs + distribución de health) ---
	_render_kpis() {
		const c = this._counts();
		const card = (label, value, cls) =>
			`<div class="pmo-pf-kpi ${
				cls || ""
			}"><div class="v">${value}</div><div class="l">${label}</div></div>`;

		const kpis = [
			card(__("Projects"), c.total),
			card(__("On track"), c.on_track, "ok"),
			card(__("At risk"), c.at_risk, "warn"),
			card(__("Deviated"), c.deviated, "bad"),
			card(__("With overdue tasks"), c.overdue, c.overdue ? "bad" : ""),
			card(
				__("Forecast exceeds commitment"),
				c.forecast_exceeds,
				c.forecast_exceeds ? "bad" : ""
			),
			card(__("Without baseline"), c.no_baseline, c.no_baseline ? "warn" : ""),
		].join("");

		// distribución de health (barra apilada) — derivada de los conteos existentes
		const total = c.total || 1;
		const seg = (n, cls) =>
			n
				? `<span class="${cls}" style="width:${(n / total) * 100}%" title="${n}"></span>`
				: "";
		const dist = `
			<div class="pmo-pf-dist">
				<div class="bar">
					${seg(c.on_track, "ok")}${seg(c.at_risk, "warn")}${seg(c.deviated, "bad")}
				</div>
				<div class="legend">
					<span><i class="ok"></i>${__("On track")} ${c.on_track}</span>
					<span><i class="warn"></i>${__("At risk")} ${c.at_risk}</span>
					<span><i class="bad"></i>${__("Deviated")} ${c.deviated}</span>
				</div>
			</div>`;

		this.$body.find('[data-region="kpis"]').html(`<div class="cards">${kpis}</div>${dist}`);
	}

	// --- Capa 2: Requiere atención (excepciones, señales existentes) ---
	_render_attention() {
		const rows = this._attention_rows();
		const $r = this.$body.find('[data-region="attention"]');
		if (!rows.length) {
			$r.html(`<div class="pmo-pf-ok">${__("No projects require attention.")}</div>`);
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
					<div class="pmo-pf-att" data-project="${frappe.utils.escape_html(row.project)}">
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

	// --- Capa 3: Portafolio completo (tabla enriquecida; conserva TODO el detalle del Script Report) ---
	_render_table() {
		const h = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const num = (v, d = 1) =>
			v == null ? "—" : frappe.format(v, { fieldtype: "Float", precision: d });
		const intv = (v) => (v == null ? "—" : v);
		const pct = (v) => {
			if (v == null) return "—";
			const w = Math.min(100, Math.max(0, v));
			const cls = v > 100 ? "bad" : v >= 80 ? "warn" : "ok";
			return `<div class="pmo-pf-pct"><span class="${cls}" style="width:${w}%"></span></div><span class="pct-t">${v}%</span>`;
		};
		const body = this.rows
			.map(
				(row) => `
			<tr>
				<td><a class="proj" data-project="${h(row.project)}">${h(row.project_name || row.project)}</a>
					<div class="muted">${h(row.project)}</div></td>
				<td>${h(row.status)}</td>
				<td>${this._health_badge(row)}</td>
				<td>${h(row.forecast_end) || "—"}</td>
				<td class="num ${(row.slip_baseline || 0) > 0 ? "bad" : ""}">${intv(row.slip_baseline)}</td>
				<td class="num ${(row.slip_committed || 0) > 0 ? "bad" : ""}">${intv(row.slip_committed)}</td>
				<td class="num ${(row.overdue || 0) > 0 ? "bad" : ""}">${intv(row.overdue)}</td>
				<td class="num ${(row.forecast_exceeds || 0) > 0 ? "bad" : ""}">${intv(row.forecast_exceeds)}</td>
				<td class="num">${num(row.planned_hours)}</td>
				<td class="num">${num(row.actual_hours)}</td>
				<td class="pctcell">${pct(row.pct_consumed)}</td>
			</tr>`
			)
			.join("");
		this.$body.find('[data-region="table"]').html(`
			<div class="pmo-pf-tablewrap">
			<table class="pmo-pf-table">
				<thead><tr>
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
				</tr></thead>
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

	// --- drill-down: hoy abre el Project nativo; preparado para sustituir por Project Control ---
	_open_project(project) {
		// Punto único de navegación: cuando exista Project Control, se cambia SOLO aquí.
		frappe.set_route("Form", "Project", project);
	}

	_inject_styles() {
		if (document.getElementById("pmo-pf-styles")) return;
		const css = `
.pmo-pf{padding:4px 2px}
.pmo-pf-h2{font-size:14px;margin:18px 0 8px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.03em}
.pmo-pf .cards{display:flex;flex-wrap:wrap;gap:10px}
.pmo-pf-kpi{flex:1;min-width:120px;border:1px solid var(--border-color);border-radius:8px;padding:10px 12px;background:var(--card-bg)}
.pmo-pf-kpi .v{font-size:22px;font-weight:700;line-height:1}
.pmo-pf-kpi .l{font-size:11px;color:var(--text-muted);margin-top:4px;text-transform:uppercase;letter-spacing:.02em}
.pmo-pf-kpi.ok .v{color:var(--green-600)}.pmo-pf-kpi.warn .v{color:var(--orange-600)}.pmo-pf-kpi.bad .v{color:var(--red-600)}
.pmo-pf-dist{margin-top:12px}
.pmo-pf-dist .bar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--gray-200)}
.pmo-pf-dist .bar span{display:block;height:100%}
.pmo-pf-dist .bar .ok{background:var(--green-500)}.pmo-pf-dist .bar .warn{background:var(--orange-500)}.pmo-pf-dist .bar .bad{background:var(--red-500)}
.pmo-pf-dist .legend{display:flex;gap:16px;margin-top:6px;font-size:12px;color:var(--text-muted)}
.pmo-pf-dist .legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle}
.pmo-pf-dist .legend i.ok{background:var(--green-500)}.pmo-pf-dist .legend i.warn{background:var(--orange-500)}.pmo-pf-dist .legend i.bad{background:var(--red-500)}
.pmo-pf-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;color:#fff}
.pmo-pf-badge.green{background:var(--green-500)}.pmo-pf-badge.orange{background:var(--orange-500)}.pmo-pf-badge.red{background:var(--red-500)}.pmo-pf-badge.gray{background:var(--gray-500)}
.pmo-pf-attlist{display:flex;flex-direction:column;gap:8px}
.pmo-pf-att{border:1px solid var(--border-color);border-left:3px solid var(--red-500);border-radius:6px;padding:8px 12px;background:var(--card-bg)}
.pmo-pf-att .head{display:flex;align-items:center;gap:10px}
.pmo-pf-att .proj{font-weight:600;cursor:pointer}
.pmo-pf-att .reasons{margin-top:6px;display:flex;flex-wrap:wrap;gap:6px}
.pmo-pf-chip{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--gray-200)}
.pmo-pf-chip.bad{background:var(--red-100);color:var(--red-700)}.pmo-pf-chip.warn{background:var(--orange-100);color:var(--orange-700)}
.pmo-pf-ok,.pmo-pf-empty{padding:10px 12px;color:var(--text-muted)}
.pmo-pf-tablewrap{overflow-x:auto;border:1px solid var(--border-color);border-radius:8px}
.pmo-pf-table{width:100%;border-collapse:collapse;font-size:12px}
.pmo-pf-table th,.pmo-pf-table td{padding:8px 10px;border-bottom:1px solid var(--border-color);text-align:left;white-space:nowrap}
.pmo-pf-table th{background:var(--subtle-fg,var(--gray-100));color:var(--text-muted);font-weight:600}
.pmo-pf-table td.num,.pmo-pf-table th.num{text-align:right}
.pmo-pf-table td.bad{color:var(--red-600);font-weight:600}
.pmo-pf-table .proj{font-weight:600;cursor:pointer}
.pmo-pf-table .muted{font-size:10px;color:var(--text-muted)}
.pmo-pf-pct{display:inline-block;width:70px;height:8px;border-radius:4px;background:var(--gray-200);overflow:hidden;vertical-align:middle;margin-right:6px}
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
