// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO -- Capacity Planning (arquitectura D: Page propia, sin Insights).
//
// UX estilo PMO de MS Project. TODOS los datos analiticos salen del Script Report
// `PMO Capacity Planning` via `frappe.desk.query_report.run` -> execute() -> P4 server-side. El
// cliente NUNCA recalcula Capacity/Availability/Planned ni reconstruye el split visible/confidencial:
// `planned_total` ya incluye Visible + Confidencial. La identidad confidencial no viaja al navegador
// (el server nunca la envia). El panel de Empleados usa `pmo.capacity_page.get_resources` (mismo
// alcance de observador que el reporte); solo metadata segura de Employee, sin Project/Task.

frappe.pages["capacity_planning"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Capacity Planning"),
		single_column: true,
	});

	new CapacityPlanning(page);
};

const REPORT = "PMO Capacity Planning";
const REPORT_BY_PROJECT = "PMO Resource Usage by Project";
const REPORT_WORK = "PMO Work by Resource";

// Vistas del selector (paridad con MS Project). Incremento 2: heatmap + Uso de recursos.
const VIEWS = [
	{ key: "heatmap", label: __("Mapa de calor de capacidad"), enabled: true },
	{ key: "usage", label: __("Uso de recursos"), enabled: true },
	{ key: "by_project", label: __("Uso de recursos por proyecto"), enabled: true },
	{ key: "remaining", label: __("Disponibilidad restante"), enabled: true },
	{ key: "work", label: __("Trabajo por recurso"), enabled: true },
];

// Escalas: etiqueta visible -> valor de granularidad del reporte.
const SCALES = [
	{ value: "Day", label: __("Día") },
	{ value: "Week", label: __("Semana") },
	{ value: "Month", label: __("Mes") },
];

class CapacityPlanning {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this.state = {
			resources: [], // metadata segura de Employee (alcance del observador)
			selected: new Set(), // employee ids seleccionados (persisten entre vistas/filtros)
			rows: [], // filas del reporte (ya enmascaradas P4)
			periods: [], // etiquetas de periodo en orden cronologico
			view: "heatmap",
			scale: "Day",
			first_load: true,
			search: "",
		};

		this._inject_styles();
		this._build_layout();
		this.refresh();
	}

	// --- layout general ----------------------------------------------------------

	_build_layout() {
		const first = frappe.datetime.month_start();
		const last = frappe.datetime.month_end();

		const scale_btns = SCALES.map(
			(s) =>
				`<button type="button" class="pmo-cap-scale-btn ${
					s.value === this.state.scale ? "is-active" : ""
				}"
					data-scale="${s.value}">${s.label}</button>`
		).join("");

		this.$body.html(`
			<div class="pmo-cap">
				<div class="pmo-cap-toolbar">
					<div class="pmo-cap-field">
						<label>${__("Desde")}</label>
						<input type="date" class="pmo-cap-from" value="${first}">
					</div>
					<div class="pmo-cap-field">
						<label>${__("Hasta")}</label>
						<input type="date" class="pmo-cap-to" value="${last}">
					</div>
					<div class="pmo-cap-field">
						<label>${__("Escala")}</label>
						<div class="pmo-cap-scale">${scale_btns}</div>
					</div>
					<div class="pmo-cap-field">
						<label>${__("Unidad")}</label>
						<span class="pmo-cap-unit">${__("Horas")}</span>
					</div>
					<button class="btn btn-primary btn-sm pmo-cap-refresh">${__("Actualizar")}</button>
				</div>

				<div class="pmo-cap-views" role="tablist"></div>

				<div class="pmo-cap-grid">
					<aside class="pmo-cap-side">
						<div class="pmo-cap-side-head">
							<span class="pmo-cap-side-title">${__("Empleados")}</span>
							<span class="pmo-cap-count text-muted"></span>
						</div>
						<input type="search" class="form-control input-xs pmo-cap-search"
							placeholder="${__("Buscar empleado...")}">
						<div class="pmo-cap-side-actions">
							<a class="pmo-cap-all">${__("Todos")}</a>
							<span class="pmo-cap-sep">&middot;</span>
							<a class="pmo-cap-none">${__("Limpiar")}</a>
						</div>
						<div class="pmo-cap-list"></div>
					</aside>
					<main class="pmo-cap-main">
						<div class="pmo-cap-chart-card pmo-cap-card" hidden>
							<div class="pmo-cap-card-head">
								<span class="pmo-cap-chart-title">${__("Capacidad y carga agregadas")}</span>
								<span class="text-muted pmo-cap-card-sub">${__("empleados seleccionados")}</span>
							</div>
							<div class="pmo-cap-chart"></div>
						</div>
						<div class="pmo-cap-view-card pmo-cap-card">
							<div class="pmo-cap-card-head">
								<span class="pmo-cap-view-title"></span>
								<span class="pmo-cap-legend"></span>
							</div>
							<div class="pmo-cap-view-body"></div>
						</div>
					</main>
				</div>
			</div>
		`);

		this._render_view_tabs();

		// toolbar de rango/escala (visible en el contenido, no solo en la barra de la Page)
		this.$body.find(".pmo-cap-from, .pmo-cap-to").on("change", () => this.refresh());
		this.$body.find(".pmo-cap-scale-btn").on("click", (e) => {
			this.state.scale = $(e.currentTarget).data("scale");
			this.$body.find(".pmo-cap-scale-btn").removeClass("is-active");
			$(e.currentTarget).addClass("is-active");
			this.refresh();
		});
		this.$body.find(".pmo-cap-refresh").on("click", () => this.refresh());

		// panel de Empleados
		this.$body.find(".pmo-cap-search").on("input", (e) => {
			this.state.search = (e.target.value || "").toLowerCase();
			this._render_resources();
		});
		this.$body.find(".pmo-cap-all").on("click", () => {
			this._visible_resources().forEach((r) => this.state.selected.add(r.employee));
			this._render_resources();
			this._render_view();
		});
		this.$body.find(".pmo-cap-none").on("click", () => {
			this.state.selected.clear();
			this._render_resources();
			this._render_view();
		});

		// tooltip flotante compartido para las celdas del heatmap
		this.$tooltip = $('<div class="pmo-cap-tip" hidden></div>').appendTo(this.$body);
	}

	_get_filters() {
		return {
			from_date: this.$body.find(".pmo-cap-from").val(),
			to_date: this.$body.find(".pmo-cap-to").val(),
			granularity: this.state.scale,
		};
	}

	_render_view_tabs() {
		const $tabs = this.$body.find(".pmo-cap-views").empty();
		VIEWS.forEach((v) => {
			const $t = $(`
				<button class="pmo-cap-view-tab ${v.enabled ? "" : "is-disabled"}
					${this.state.view === v.key ? "is-active" : ""}"
					${v.enabled ? "" : "disabled"} type="button">
					${frappe.utils.escape_html(v.label)}
					${v.enabled ? "" : `<span class="pmo-cap-soon">${__("proximamente")}</span>`}
				</button>
			`);
			if (v.enabled) {
				$t.on("click", () => {
					this.state.view = v.key;
					this._render_view_tabs();
					this._render_view();
				});
			}
			$tabs.append($t);
		});
	}

	// --- carga de datos ----------------------------------------------------------

	refresh() {
		const f = this._get_filters();
		if (!f.from_date || !f.to_date) {
			return;
		}
		this.page.set_indicator(__("Cargando..."), "orange");
		Promise.all([this._load_resources(f), this._load_rows(f)])
			.then(() => {
				this.page.clear_indicator();
				this._render_resources();
				this._render_view();
			})
			.catch((err) => {
				this.page.set_indicator(__("Error"), "red");
				frappe.msgprint({
					title: __("Capacity Planning"),
					message: (err && err.message) || __("No se pudieron cargar los datos."),
					indicator: "red",
				});
			});
	}

	_load_resources(f) {
		return frappe
			.call("pmo.capacity_page.get_resources", {
				from_date: f.from_date,
				to_date: f.to_date,
			})
			.then((r) => {
				const resources = r.message || [];
				this.state.resources = resources;
				const ids = new Set(resources.map((x) => x.employee));
				if (this.state.first_load) {
					// primera carga -> seleccionar todos
					resources.forEach((x) => this.state.selected.add(x.employee));
					this.state.first_load = false;
				} else {
					// conservar seleccion; descartar empleados que ya no estan en alcance
					this.state.selected.forEach((id) => {
						if (!ids.has(id)) this.state.selected.delete(id);
					});
				}
			});
	}

	_load_rows(f) {
		return frappe
			.call("frappe.desk.query_report.run", {
				report_name: REPORT,
				filters: {
					from_date: f.from_date,
					to_date: f.to_date,
					granularity: f.granularity,
				},
			})
			.then((r) => {
				const result = (r.message && r.message.result) || [];
				this.state.rows = result.filter((row) => row && row.employee);
				// orden cronologico de periodos = orden de aparicion (execute() ya ordena por bucket)
				const seen = new Set();
				const periods = [];
				this.state.rows.forEach((row) => {
					if (!seen.has(row.period)) {
						seen.add(row.period);
						periods.push(row.period);
					}
				});
				this.state.periods = periods;
			});
	}

	// --- panel de Empleados ------------------------------------------------------

	_visible_resources() {
		const q = this.state.search;
		if (!q) return this.state.resources;
		return this.state.resources.filter((r) => {
			const hay = [r.employee_name, r.email, r.department, r.designation, r.branch]
				.filter(Boolean)
				.join(" ")
				.toLowerCase();
			return hay.includes(q);
		});
	}

	_render_resources() {
		const $list = this.$body.find(".pmo-cap-list").empty();
		const visible = this._visible_resources();

		this.$body
			.find(".pmo-cap-count")
			.text(`${this.state.selected.size}/${this.state.resources.length}`);

		if (!visible.length) {
			$list.html(
				`<div class="pmo-cap-empty text-muted">${__("Sin empleados en el alcance.")}</div>`
			);
			return;
		}

		visible.forEach((r) => {
			const checked = this.state.selected.has(r.employee) ? "checked" : "";
			const meta = [r.designation, r.department, r.branch]
				.filter(Boolean)
				.join(" &middot; ");
			const $item = $(`
				<label class="pmo-cap-res">
					<input type="checkbox" ${checked}>
					<span class="pmo-cap-res-body">
						<span class="pmo-cap-res-name">${frappe.utils.escape_html(r.employee_name || r.employee)}</span>
						${meta ? `<span class="pmo-cap-res-meta text-muted">${meta}</span>` : ""}
						${
							r.email
								? `<span class="pmo-cap-res-mail text-muted">${frappe.utils.escape_html(
										r.email
								  )}</span>`
								: ""
						}
					</span>
				</label>
			`);
			$item.find("input").on("change", (e) => {
				if (e.target.checked) this.state.selected.add(r.employee);
				else this.state.selected.delete(r.employee);
				this.$body
					.find(".pmo-cap-count")
					.text(`${this.state.selected.size}/${this.state.resources.length}`);
				this._render_view();
			});
			$list.append($item);
		});
	}

	// --- render de la vista activa ----------------------------------------------

	_render_view() {
		const view = VIEWS.find((v) => v.key === this.state.view);
		this.$body.find(".pmo-cap-view-title").text(view ? view.label : "");
		this.$body.find(".pmo-cap-legend").empty();
		if (this.state.view === "heatmap") {
			this._render_heatmap();
			this._render_capacity_chart();
		} else if (this.state.view === "usage") {
			this._render_usage();
			this._render_capacity_chart();
		} else if (this.state.view === "by_project") {
			this._render_by_project();
		} else if (this.state.view === "remaining") {
			this._render_remaining();
			this._render_remaining_chart();
		} else if (this.state.view === "work") {
			this._render_work();
		}
	}

	_selected_rows() {
		return this.state.rows.filter((r) => this.state.selected.has(r.employee));
	}

	// Empleados seleccionados, en el orden del panel.
	_selected_resources() {
		return this.state.resources.filter((r) => this.state.selected.has(r.employee));
	}

	_index_rows() {
		const idx = {};
		this.state.rows.forEach((r) => {
			idx[`${r.employee}|${r.period}`] = r;
		});
		return idx;
	}

	_bucket(row) {
		// clasificacion por util_planned (%). avail 0 -> "off" salvo que haya carga.
		if (flt(row.availability) === 0) {
			return flt(row.planned_total) > 0 ? "over" : "off";
		}
		const u = row.util_planned;
		if (u === null || u === undefined) return "off";
		if (u > 100) return "over";
		if (u >= 80) return "warn";
		return "ok";
	}

	_util_text(row, bucket) {
		if (bucket === "off") return "&mdash;";
		if (flt(row.availability) === 0 && flt(row.planned_total) > 0) return "&gt;100%";
		if (row.util_planned === null || row.util_planned === undefined) return "&mdash;";
		return `${format_number(row.util_planned, null, 0)}%`;
	}

	// --- vista: Mapa de calor de capacidad --------------------------------------

	_render_heatmap() {
		const $view = this.$body.find(".pmo-cap-view-body").empty();
		const employees = this._selected_resources();
		const periods = this.state.periods;

		this.$body.find(".pmo-cap-legend").html(`
			<span class="pmo-cap-key"><i class="k-ok"></i>${__("&lt;80%")}</span>
			<span class="pmo-cap-key"><i class="k-warn"></i>${__("80-100%")}</span>
			<span class="pmo-cap-key"><i class="k-over"></i>${__("&gt;100%")}</span>
			<span class="pmo-cap-key"><i class="k-off"></i>${__("sin disponibilidad")}</span>
		`);

		if (!employees.length || !periods.length) {
			$view.html(
				`<div class="pmo-cap-empty text-muted">${__(
					"Selecciona al menos un empleado y un rango con datos."
				)}</div>`
			);
			return;
		}

		const idx = this._index_rows();

		const head = periods
			.map(
				(p) =>
					`<th class="pmo-cap-h-period" title="${frappe.utils.escape_html(
						p
					)}">${frappe.utils.escape_html(p)}</th>`
			)
			.join("");

		const body = employees
			.map((res) => {
				const name = frappe.utils.escape_html(res.employee_name || res.employee);
				const cells = periods
					.map((p) => {
						const row = idx[`${res.employee}|${p}`];
						if (!row) {
							return `<td class="pmo-cap-cell off"><span>&mdash;</span></td>`;
						}
						const b = this._bucket(row);
						const txt = this._util_text(row, b);
						const data = encodeURIComponent(
							JSON.stringify({
								name: res.employee_name || res.employee,
								period: p,
								capacity: row.capacity,
								availability: row.availability,
								planned: row.planned_total,
								free: row.free,
								util: row.util_planned,
							})
						);
						return `<td class="pmo-cap-cell ${b}" data-tip="${data}"><span>${txt}</span></td>`;
					})
					.join("");
				return `
					<tr>
						<th class="pmo-cap-h-res" title="${name}">${name}</th>
						${cells}
					</tr>`;
			})
			.join("");

		$view.html(`
			<div class="pmo-cap-matrix-wrap">
				<table class="pmo-cap-matrix">
					<thead>
						<tr><th class="pmo-cap-h-corner">${__("Empleado")}</th>${head}</tr>
					</thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`);

		const self = this;
		$view.find(".pmo-cap-cell[data-tip]").on("mouseenter", function (e) {
			const d = JSON.parse(decodeURIComponent($(this).attr("data-tip")));
			self._show_tip(d, e);
		});
		$view.find(".pmo-cap-cell[data-tip]").on("mousemove", (e) => this._move_tip(e));
		$view
			.find(".pmo-cap-cell[data-tip]")
			.on("mouseleave", () => this.$tooltip.attr("hidden", true));
	}

	_show_tip(d, e) {
		const hh = (v) =>
			v === null || v === undefined ? "&mdash;" : `${format_number(v, null, 2)} h`;
		const util =
			d.util === null || d.util === undefined
				? "&mdash;"
				: `${format_number(d.util, null, 0)}%`;
		this.$tooltip.html(`
			<div class="pmo-cap-tip-title">${frappe.utils.escape_html(d.name)}</div>
			<div class="pmo-cap-tip-sub text-muted">${frappe.utils.escape_html(d.period)}</div>
			<div class="pmo-cap-tip-row"><span>${__("Capacity")}</span><b>${hh(d.capacity)}</b></div>
			<div class="pmo-cap-tip-row"><span>${__("Availability")}</span><b>${hh(d.availability)}</b></div>
			<div class="pmo-cap-tip-row"><span>${__("Planned")}</span><b>${hh(d.planned)}</b></div>
			<div class="pmo-cap-tip-row"><span>${__("Free")}</span><b>${hh(d.free)}</b></div>
			<div class="pmo-cap-tip-row"><span>${__("Planned Utilization")}</span><b>${util}</b></div>
		`);
		this.$tooltip.removeAttr("hidden");
		this._move_tip(e);
	}

	_move_tip(e) {
		const off = this.$body.offset();
		this.$tooltip.css({
			left: e.pageX - off.left + 14,
			top: e.pageY - off.top + 14,
		});
	}

	// --- vista: Uso de recursos (detalle por empleado y periodo, sin Actual) -----

	_render_usage() {
		const $view = this.$body.find(".pmo-cap-view-body").empty();
		const employees = this._selected_resources();
		const periods = this.state.periods;

		if (!employees.length || !periods.length) {
			$view.html(
				`<div class="pmo-cap-empty text-muted">${__(
					"Selecciona al menos un empleado y un rango con datos."
				)}</div>`
			);
			return;
		}

		const idx = this._index_rows();
		const hh = (v) =>
			v === null || v === undefined ? "&mdash;" : `${format_number(v, null, 2)}`;
		const pct = (v) =>
			v === null || v === undefined ? "&mdash;" : `${format_number(v, null, 0)}%`;
		const METRICS = [
			{ key: "capacity", label: __("Capacity"), fmt: hh },
			{ key: "availability", label: __("Availability"), fmt: hh },
			{ key: "planned_total", label: __("Planned"), fmt: hh },
			{ key: "free", label: __("Free"), fmt: hh },
			{ key: "util_planned", label: __("Planned Utilization"), fmt: pct, util: true },
		];

		const head = periods
			.map(
				(p) =>
					`<th class="pmo-cap-h-period" title="${frappe.utils.escape_html(
						p
					)}">${frappe.utils.escape_html(p)}</th>`
			)
			.join("");

		const body = employees
			.map((res) => {
				const name = frappe.utils.escape_html(res.employee_name || res.employee);
				const emp_row = `
					<tr class="pmo-cap-u-emprow">
						<th class="pmo-cap-u-emp" colspan="${periods.length + 1}">${name}</th>
					</tr>`;
				const metric_rows = METRICS.map((m) => {
					const cells = periods
						.map((p) => {
							const row = idx[`${res.employee}|${p}`];
							if (!row) return `<td class="pmo-cap-u-cell">&mdash;</td>`;
							if (m.util) {
								const b = this._bucket(row);
								return `<td class="pmo-cap-u-cell ${b}">${this._util_text(
									row,
									b
								)}</td>`;
							}
							return `<td class="pmo-cap-u-cell">${m.fmt(row[m.key])}</td>`;
						})
						.join("");
					return `<tr><th class="pmo-cap-u-metric">${m.label}</th>${cells}</tr>`;
				}).join("");
				return emp_row + metric_rows;
			})
			.join("");

		$view.html(`
			<div class="pmo-cap-matrix-wrap">
				<table class="pmo-cap-matrix pmo-cap-usage">
					<thead>
						<tr><th class="pmo-cap-h-corner">${__("Empleado")}</th>${head}</tr>
					</thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`);
	}

	// --- grafica temporal agregada (frappe.Chart, sin Actual) --------------------

	_render_capacity_chart() {
		const $card = this.$body.find(".pmo-cap-chart-card");
		const $el = this.$body.find(".pmo-cap-chart").empty();
		const rows = this._selected_rows();
		const periods = this.state.periods;

		if (!rows.length || !periods.length) {
			$card.attr("hidden", true);
			return;
		}
		$card.removeAttr("hidden");
		this.$body.find(".pmo-cap-chart-title").text(__("Capacidad y carga agregadas"));
		this.$body.find(".pmo-cap-card-sub").text(__("empleados seleccionados"));

		// agregar por periodo sobre los empleados seleccionados
		const agg = {};
		periods.forEach((p) => (agg[p] = { cap: 0, avail: 0, planned: 0, free: 0 }));
		rows.forEach((r) => {
			const a = agg[r.period];
			if (!a) return;
			a.cap += flt(r.capacity);
			a.avail += flt(r.availability);
			a.planned += flt(r.planned_total);
			a.free += flt(r.free);
		});

		const round2 = (v) => flt(v, 2);
		this.chart = new frappe.Chart($el[0], {
			type: "line",
			height: 220,
			animate: false,
			axisOptions: { xAxisMode: "tick", xIsSeries: 1 },
			lineOptions: { hideDots: 0, regionFill: 0 },
			data: {
				labels: periods,
				datasets: [
					{ name: __("Capacity"), values: periods.map((p) => round2(agg[p].cap)) },
					{ name: __("Availability"), values: periods.map((p) => round2(agg[p].avail)) },
					{ name: __("Planned"), values: periods.map((p) => round2(agg[p].planned)) },
					{ name: __("Free"), values: periods.map((p) => round2(agg[p].free)) },
				],
			},
			colors: ["#7cd6fd", "#5e64ff", "#ffa00a", "#28a745"],
		});
	}

	// --- vista: Uso de recursos por proyecto (un empleado; matriz temporal, solo Planned) ------

	_render_by_project() {
		const $card = this.$body.find(".pmo-cap-chart-card");
		const $view = this.$body.find(".pmo-cap-view-body").empty();
		this.$body.find(".pmo-cap-legend").empty();

		const sel = this._selected_resources();
		if (sel.length !== 1) {
			$card.attr("hidden", true);
			$view.html(
				`<div class="pmo-cap-empty text-muted">${__(
					"Esta vista trabaja con un empleado a la vez. Selecciona exactamente un empleado en el panel de la izquierda."
				)}</div>`
			);
			return;
		}

		const emp = sel[0];
		const f = this._get_filters();
		$view.html(`<div class="pmo-cap-empty text-muted">${__("Cargando...")}</div>`);

		// El desglose por proyecto x periodo (con P4) lo produce el Script Report server-side.
		frappe
			.call("frappe.desk.query_report.run", {
				report_name: REPORT_BY_PROJECT,
				filters: {
					from_date: f.from_date,
					to_date: f.to_date,
					granularity: f.granularity,
					employee: emp.employee,
				},
			})
			.then((r) => {
				if (this.state.view !== "by_project") return; // el usuario cambio de vista mientras cargaba
				const msg = r.message || {};
				this._render_by_project_matrix(emp, msg.columns || [], msg.result || []);
			});
	}

	_render_by_project_matrix(emp, columns, rows) {
		const $view = this.$body.find(".pmo-cap-view-body").empty();
		const periodCols = columns.filter((c) => /^period_\d+$/.test(c.fieldname));
		const parent = rows.find((r) => r.indent === 0);
		const children = rows.filter((r) => r.indent === 1);
		const fmt = (v) => (v === null || v === undefined ? "&mdash;" : format_number(v, null, 2));

		if (!children.length || !periodCols.length) {
			this.$body.find(".pmo-cap-chart-card").attr("hidden", true);
			$view.html(
				`<div class="pmo-cap-empty text-muted">${__(
					"Sin planificación para este empleado en el rango."
				)}</div>`
			);
			return;
		}

		const head =
			periodCols
				.map(
					(c) =>
						`<th class="pmo-cap-h-period" title="${frappe.utils.escape_html(
							c.label
						)}">${frappe.utils.escape_html(c.label)}</th>`
				)
				.join("") + `<th class="pmo-cap-h-total">${__("Total")}</th>`;

		const body = children
			.map((row) => {
				const name = frappe.utils.escape_html(row.project || "");
				// Link SOLO cuando el server entrega project_id (proyecto visible). Confidencial / Sin
				// proyecto nunca son links (no llega project_id).
				const label = row.project_id
					? `<a class="pmo-cap-proj-link" data-project="${frappe.utils.escape_html(
							row.project_id
					  )}">${name}</a>`
					: name;
				const cells = periodCols
					.map((c) => `<td class="pmo-cap-u-cell">${fmt(row[c.fieldname])}</td>`)
					.join("");
				return `<tr><th class="pmo-cap-u-metric">${label}</th>${cells}<td class="pmo-cap-u-cell pmo-cap-total">${fmt(
					row.total
				)}</td></tr>`;
			})
			.join("");

		const footcells = periodCols
			.map((c) => `<td class="pmo-cap-u-cell">${fmt(parent && parent[c.fieldname])}</td>`)
			.join("");
		const foot = `<tr class="pmo-cap-u-footrow"><th class="pmo-cap-u-metric">${__(
			"Total planificado"
		)}</th>${footcells}<td class="pmo-cap-u-cell pmo-cap-total">${fmt(
			parent && parent.total
		)}</td></tr>`;

		$view.html(`
			<div class="pmo-cap-matrix-wrap">
				<table class="pmo-cap-matrix pmo-cap-usage">
					<thead>
						<tr><th class="pmo-cap-h-corner">${__("Proyecto")}</th>${head}</tr>
					</thead>
					<tbody>${body}${foot}</tbody>
				</table>
			</div>
		`);

		$view.find(".pmo-cap-proj-link").on("click", (e) => {
			const id = $(e.currentTarget).data("project");
			if (id) frappe.set_route("Form", "Project", String(id));
		});

		this._render_by_project_chart(emp, periodCols, children);
	}

	_render_by_project_chart(emp, periodCols, children) {
		const $card = this.$body.find(".pmo-cap-chart-card");
		const $el = this.$body.find(".pmo-cap-chart").empty();

		// Legibilidad: con demasiados buckets el apilado deja de ser util -> mostramos solo la matriz.
		if (children.length > 6) {
			$card.attr("hidden", true);
			return;
		}
		$card.removeAttr("hidden");
		this.$body.find(".pmo-cap-chart-title").text(__("Planned por proyecto"));
		this.$body.find(".pmo-cap-card-sub").text(emp.employee_name || emp.employee);

		const labels = periodCols.map((c) => c.label);
		const datasets = children.map((row) => ({
			name: row.project,
			values: periodCols.map((c) => flt(row[c.fieldname], 2)),
		}));

		this.chart = new frappe.Chart($el[0], {
			type: "bar",
			height: 220,
			animate: false,
			axisOptions: { xAxisMode: "tick" },
			barOptions: { stacked: 1 },
			data: { labels, datasets },
			colors: ["#5e64ff", "#28a745", "#ffa00a", "#7cd6fd", "#ff5858", "#743ee2"],
		});
	}

	// --- vista: Disponibilidad restante (metrica = Free; comparativa multi-empleado) -----------

	_free_bucket(row) {
		// Availability 0 es un ESTADO distinto (sin disponibilidad), no "0 horas libres".
		if (flt(row.availability) === 0) return "off";
		const free = flt(row.free);
		if (free > 0) return "ok"; // disponibilidad
		if (free < 0) return "over"; // sobreasignado
		return "warn"; // free == 0 -> completamente comprometido
	}

	_render_remaining() {
		const $view = this.$body.find(".pmo-cap-view-body").empty();
		const employees = this._selected_resources();
		const periods = this.state.periods;

		this.$body.find(".pmo-cap-legend").html(`
			<span class="pmo-cap-key"><i class="k-ok"></i>${__("disponible (&gt;0)")}</span>
			<span class="pmo-cap-key"><i class="k-warn"></i>${__("comprometido (0)")}</span>
			<span class="pmo-cap-key"><i class="k-over"></i>${__("sobreasignado (&lt;0)")}</span>
			<span class="pmo-cap-key"><i class="k-off"></i>${__("sin disponibilidad")}</span>
		`);

		if (!employees.length || !periods.length) {
			$view.html(
				`<div class="pmo-cap-empty text-muted">${__(
					"Selecciona al menos un empleado y un rango con datos."
				)}</div>`
			);
			return;
		}

		const idx = this._index_rows();

		const head = periods
			.map(
				(p) =>
					`<th class="pmo-cap-h-period" title="${frappe.utils.escape_html(
						p
					)}">${frappe.utils.escape_html(p)}</th>`
			)
			.join("");

		const body = employees
			.map((res) => {
				const name = frappe.utils.escape_html(res.employee_name || res.employee);
				const cells = periods
					.map((p) => {
						const row = idx[`${res.employee}|${p}`];
						if (!row) return `<td class="pmo-cap-cell off"><span>&mdash;</span></td>`;
						const b = this._free_bucket(row);
						const txt = b === "off" ? "&mdash;" : format_number(row.free, null, 1);
						const data = encodeURIComponent(
							JSON.stringify({
								name: res.employee_name || res.employee,
								period: p,
								availability: row.availability,
								planned: row.planned_total,
								free: row.free,
								overallocation: row.overallocation,
							})
						);
						return `<td class="pmo-cap-cell ${b}" data-tip="${data}"><span>${txt}</span></td>`;
					})
					.join("");
				return `<tr><th class="pmo-cap-h-res" title="${name}">${name}</th>${cells}</tr>`;
			})
			.join("");

		$view.html(`
			<div class="pmo-cap-matrix-wrap">
				<table class="pmo-cap-matrix">
					<thead>
						<tr><th class="pmo-cap-h-corner">${__("Empleado")}</th>${head}</tr>
					</thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`);

		const self = this;
		$view.find(".pmo-cap-cell[data-tip]").on("mouseenter", function (e) {
			const d = JSON.parse(decodeURIComponent($(this).attr("data-tip")));
			self._show_tip_remaining(d, e);
		});
		$view.find(".pmo-cap-cell[data-tip]").on("mousemove", (e) => this._move_tip(e));
		$view
			.find(".pmo-cap-cell[data-tip]")
			.on("mouseleave", () => this.$tooltip.attr("hidden", true));
	}

	_show_tip_remaining(d, e) {
		const hh = (v) =>
			v === null || v === undefined ? "&mdash;" : `${format_number(v, null, 2)} h`;
		this.$tooltip.html(`
			<div class="pmo-cap-tip-title">${frappe.utils.escape_html(d.name)}</div>
			<div class="pmo-cap-tip-sub text-muted">${frappe.utils.escape_html(d.period)}</div>
			<div class="pmo-cap-tip-row"><span>${__("Availability")}</span><b>${hh(d.availability)}</b></div>
			<div class="pmo-cap-tip-row"><span>${__("Planned")}</span><b>${hh(d.planned)}</b></div>
			<div class="pmo-cap-tip-row"><span>${__("Free")}</span><b>${hh(d.free)}</b></div>
			<div class="pmo-cap-tip-row"><span>${__("Overallocation")}</span><b>${hh(
			d.overallocation
		)}</b></div>
		`);
		this.$tooltip.removeAttr("hidden");
		this._move_tip(e);
	}

	_render_remaining_chart() {
		const $card = this.$body.find(".pmo-cap-chart-card");
		const $el = this.$body.find(".pmo-cap-chart").empty();
		const rows = this._selected_rows();
		const periods = this.state.periods;

		if (!rows.length || !periods.length) {
			$card.attr("hidden", true);
			return;
		}
		$card.removeAttr("hidden");
		this.$body.find(".pmo-cap-chart-title").text(__("Disponibilidad agregada"));
		this.$body.find(".pmo-cap-card-sub").text(__("empleados seleccionados"));

		const agg = {};
		periods.forEach((p) => (agg[p] = { avail: 0, planned: 0, free: 0 }));
		rows.forEach((r) => {
			const a = agg[r.period];
			if (!a) return;
			a.avail += flt(r.availability);
			a.planned += flt(r.planned_total);
			a.free += flt(r.free);
		});

		const round2 = (v) => flt(v, 2);
		this.chart = new frappe.Chart($el[0], {
			type: "line",
			height: 220,
			animate: false,
			axisOptions: { xAxisMode: "tick", xIsSeries: 1 },
			lineOptions: { hideDots: 0, regionFill: 0 },
			data: {
				labels: periods,
				datasets: [
					{ name: __("Availability"), values: periods.map((p) => round2(agg[p].avail)) },
					{ name: __("Planned"), values: periods.map((p) => round2(agg[p].planned)) },
					{ name: __("Free"), values: periods.map((p) => round2(agg[p].free)) },
				],
			},
			colors: ["#5e64ff", "#ffa00a", "#28a745"],
		});
	}

	// --- vista: Trabajo por recurso (detalle operativo Empleado -> Proyecto -> Tarea) ----------

	_render_work() {
		const $card = this.$body.find(".pmo-cap-chart-card");
		const $view = this.$body.find(".pmo-cap-view-body").empty();
		this.$body.find(".pmo-cap-legend").empty();
		$card.attr("hidden", true); // vista de detalle: sin grafica

		const sel = this._selected_resources();
		if (sel.length !== 1) {
			$view.html(
				`<div class="pmo-cap-empty text-muted">${__(
					"Esta vista trabaja con un empleado a la vez. Selecciona exactamente un empleado en el panel de la izquierda."
				)}</div>`
			);
			return;
		}

		const emp = sel[0];
		const f = this._get_filters();
		$view.html(`<div class="pmo-cap-empty text-muted">${__("Cargando...")}</div>`);

		// El detalle Task/Project con P4 (doble boundary) lo produce el Script Report server-side.
		frappe
			.call("frappe.desk.query_report.run", {
				report_name: REPORT_WORK,
				filters: { from_date: f.from_date, to_date: f.to_date, employee: emp.employee },
			})
			.then((r) => {
				if (this.state.view !== "work") return;
				this._render_work_tree(emp, (r.message && r.message.result) || []);
			});
	}

	_render_work_tree(emp, rows) {
		const $view = this.$body.find(".pmo-cap-view-body").empty();
		const hh = (v) =>
			v === null || v === undefined ? "&mdash;" : `${format_number(v, null, 2)} h`;

		// Fila consolidada de tareas OCULTAS: sin task_id y sin project (solo horas).
		const hidden = rows.find(
			(r) => !r.task_id && r.project === null && r.planned_hours != null
		);
		const taskRows = rows.filter((r) => r.task_id);

		if (!taskRows.length && !hidden) {
			$view.html(
				`<div class="pmo-cap-empty text-muted">${__(
					"Sin trabajo planificado para este empleado en el rango."
				)}</div>`
			);
			return;
		}

		// Agrupar tareas visibles por proyecto (clave = project_id si es visible, si no la etiqueta).
		const groups = new Map();
		taskRows.forEach((r) => {
			const key = r.project_id ? `p:${r.project_id}` : `l:${r.project || ""}`;
			let g = groups.get(key);
			if (!g) {
				g = { label: r.project, project_id: r.project_id || null, tasks: [], hours: 0 };
				groups.set(key, g);
			}
			g.tasks.push(r);
			g.hours += flt(r.planned_hours);
		});

		// Proyectos identificables primero (por nombre); buckets sin id despues.
		const ordered = [...groups.values()].sort((a, b) => {
			const ap = a.project_id ? 0 : 1;
			const bp = b.project_id ? 0 : 1;
			if (ap !== bp) return ap - bp;
			return String(a.label || "").localeCompare(String(b.label || ""));
		});

		const fmt_dates = (r) => {
			const s = r.exp_start_date
				? frappe.datetime.str_to_user(String(r.exp_start_date).slice(0, 10))
				: null;
			const e = r.exp_end_date
				? frappe.datetime.str_to_user(String(r.exp_end_date).slice(0, 10))
				: null;
			if (!s && !e) return `<span class="pmo-cap-nodate">${__("Sin fechas")}</span>`;
			if (s && e && s !== e) return `${s} &ndash; ${e}`;
			return s || e;
		};

		const group_html = (g) => {
			const title = g.project_id
				? `<a class="pmo-cap-proj-link" data-project="${frappe.utils.escape_html(
						g.project_id
				  )}">${frappe.utils.escape_html(g.label)}</a>`
				: frappe.utils.escape_html(g.label || "");
			const tasks = g.tasks
				.map((r) => {
					const tname = frappe.utils.escape_html(r.task || "");
					const tlabel = r.task_id
						? `<a class="pmo-cap-task-link" data-task="${frappe.utils.escape_html(
								r.task_id
						  )}">${tname}</a>`
						: tname;
					const status = r.status
						? `<span class="pmo-cap-badge">${frappe.utils.escape_html(
								r.status
						  )}</span>`
						: "";
					const exp =
						r.expected_time != null
							? `<span class="pmo-cap-wsub-item">${__("Estimado")}: ${format_number(
									r.expected_time,
									null,
									2
							  )} h</span>`
							: "";
					return `
						<div class="pmo-cap-wtask">
							<div class="pmo-cap-wtask-main">
								<span class="pmo-cap-wtask-name">${tlabel}</span>
								<span class="pmo-cap-wtask-hours">${hh(r.planned_hours)}</span>
							</div>
							<div class="pmo-cap-wtask-sub text-muted">
								<span class="pmo-cap-wsub-item">${fmt_dates(r)}</span>
								${exp}
								${status}
							</div>
						</div>`;
				})
				.join("");
			return `
				<div class="pmo-cap-wgroup">
					<div class="pmo-cap-wgroup-head">
						<span class="pmo-cap-caret">&#9662;</span>
						<span class="pmo-cap-wgroup-title">${title}</span>
						<span class="pmo-cap-wgroup-hours">${hh(g.hours)}</span>
					</div>
					<div class="pmo-cap-wgroup-body">${tasks}</div>
				</div>`;
		};

		let html = `<div class="pmo-cap-work">`;
		html += `<div class="pmo-cap-work-emp">${frappe.utils.escape_html(
			emp.employee_name || emp.employee
		)}</div>`;
		html += ordered.map(group_html).join("");

		// Consolidado confidencial: solo horas, sin tareas ni identidad.
		if (hidden) {
			html += `
				<div class="pmo-cap-wgroup is-confidential">
					<div class="pmo-cap-wgroup-head pmo-cap-wgroup-head--static">
						<span class="pmo-cap-wgroup-title">${frappe.utils.escape_html(hidden.task)}</span>
						<span class="pmo-cap-wgroup-hours">${hh(hidden.planned_hours)}</span>
					</div>
				</div>`;
		}
		html += `</div>`;
		$view.html(html);

		// expandir/contraer grupos (los que tienen cabecera interactiva)
		$view.find(".pmo-cap-wgroup-head:not(.pmo-cap-wgroup-head--static)").on("click", (e) => {
			if ($(e.target).closest("a").length) return; // no colapsar al hacer clic en un link
			$(e.currentTarget).closest(".pmo-cap-wgroup").toggleClass("is-collapsed");
		});
		$view.find(".pmo-cap-proj-link").on("click", (e) => {
			const id = $(e.currentTarget).data("project");
			if (id) frappe.set_route("Form", "Project", String(id));
		});
		$view.find(".pmo-cap-task-link").on("click", (e) => {
			const id = $(e.currentTarget).data("task");
			if (id) frappe.set_route("Form", "Task", String(id));
		});
	}

	// --- estilos (scoped .pmo-cap; compatibles con Desk light/dark) ---------------

	_inject_styles() {
		if (document.getElementById("pmo-cap-styles")) return;
		const css = `
.pmo-cap { --cap-gap: 12px; }
.pmo-cap-toolbar { display:flex; align-items:flex-end; gap:16px; flex-wrap:wrap; padding:12px 14px; margin-bottom:var(--cap-gap); border:1px solid var(--border-color); border-radius:var(--border-radius-lg,8px); background:var(--card-bg); }
.pmo-cap-field { display:flex; flex-direction:column; gap:4px; }
.pmo-cap-field > label { font-size:var(--text-xs); color:var(--text-muted); margin:0; font-weight:500; }
.pmo-cap-toolbar input[type=date] { border:1px solid var(--border-color); border-radius:var(--border-radius-md,6px); background:var(--control-bg,var(--bg-color)); color:var(--text-color); padding:4px 8px; font-size:var(--text-sm); height:28px; }
.pmo-cap-scale { display:inline-flex; border:1px solid var(--border-color); border-radius:var(--border-radius-md,6px); overflow:hidden; height:28px; }
.pmo-cap-scale-btn { border:0; background:var(--card-bg); color:var(--text-color); padding:0 12px; font-size:var(--text-sm); cursor:pointer; border-right:1px solid var(--border-color); }
.pmo-cap-scale-btn:last-child { border-right:0; }
.pmo-cap-scale-btn:hover { background:var(--fg-hover-color,var(--bg-color)); }
.pmo-cap-scale-btn.is-active { background:var(--bg-blue,#e7efff); color:var(--blue-600,#2b52c9); font-weight:600; }
.pmo-cap-unit { display:inline-flex; align-items:center; height:28px; padding:0 10px; font-size:var(--text-sm); color:var(--text-muted); border:1px dashed var(--border-color); border-radius:var(--border-radius-md,6px); }
.pmo-cap-refresh { margin-left:auto; }

.pmo-cap-views { display:flex; gap:4px; flex-wrap:wrap; margin-bottom:var(--cap-gap); }
.pmo-cap-view-tab {
	border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-color);
	border-radius:var(--border-radius-md,6px); padding:5px 12px; font-size:var(--text-sm);
	cursor:pointer; display:inline-flex; align-items:center; gap:6px; transition:background .1s;
}
.pmo-cap-view-tab:hover { background:var(--fg-hover-color,var(--bg-color)); }
.pmo-cap-view-tab.is-active { background:var(--bg-blue,#e7efff); border-color:var(--blue-400,#5e8fff); color:var(--blue-600,#2b52c9); font-weight:600; }
.pmo-cap-view-tab.is-disabled { opacity:.55; cursor:not-allowed; }
.pmo-cap-soon { font-size:10px; text-transform:uppercase; letter-spacing:.03em; color:var(--text-muted); border:1px solid var(--border-color); border-radius:8px; padding:0 5px; }

.pmo-cap-grid { display:grid; grid-template-columns:260px minmax(0,1fr); gap:var(--cap-gap); align-items:start; }
.pmo-cap-side { border:1px solid var(--border-color); border-radius:var(--border-radius-lg,8px); background:var(--card-bg); padding:12px; position:sticky; top:0; }
.pmo-cap-side-head { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:8px; }
.pmo-cap-side-title { font-weight:600; font-size:var(--text-md); }
.pmo-cap-count { font-size:var(--text-xs); }
.pmo-cap-search { margin-bottom:8px; }
.pmo-cap-side-actions { font-size:var(--text-xs); margin-bottom:8px; }
.pmo-cap-side-actions a { cursor:pointer; color:var(--text-muted); }
.pmo-cap-side-actions a:hover { color:var(--primary,var(--blue-600)); text-decoration:underline; }
.pmo-cap-sep { color:var(--border-color); margin:0 4px; }
.pmo-cap-list { max-height:60vh; overflow:auto; margin:-4px; padding:4px; }
.pmo-cap-res { display:flex; gap:8px; align-items:flex-start; padding:6px 6px; border-radius:6px; margin:0; cursor:pointer; }
.pmo-cap-res:hover { background:var(--fg-hover-color,var(--bg-color)); }
.pmo-cap-res input { margin-top:3px; }
.pmo-cap-res-body { display:flex; flex-direction:column; line-height:1.25; min-width:0; }
.pmo-cap-res-name { font-size:var(--text-sm); font-weight:500; }
.pmo-cap-res-meta, .pmo-cap-res-mail { font-size:var(--text-xs); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:210px; }

.pmo-cap-card { border:1px solid var(--border-color); border-radius:var(--border-radius-lg,8px); background:var(--card-bg); margin-bottom:var(--cap-gap); }
.pmo-cap-card-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 14px; border-bottom:1px solid var(--border-color); font-weight:600; font-size:var(--text-md); }
.pmo-cap-card-sub { font-weight:400; font-size:var(--text-xs); }
.pmo-cap-chart { padding:4px 8px; }
.pmo-cap-view-body { padding:0; }
.pmo-cap-empty { padding:28px; text-align:center; }

.pmo-cap-legend { display:flex; gap:12px; font-weight:400; font-size:var(--text-xs); color:var(--text-muted); }
.pmo-cap-key { display:inline-flex; align-items:center; gap:5px; }
.pmo-cap-key i { width:11px; height:11px; border-radius:3px; display:inline-block; }
.k-ok { background:rgba(40,167,69,.20); } .k-warn { background:rgba(240,173,20,.30); } .k-over { background:rgba(214,64,64,.28); } .k-off { background:var(--bg-color); border:1px solid var(--border-color); }

.pmo-cap-matrix-wrap { overflow-x:auto; }
.pmo-cap-matrix { border-collapse:separate; border-spacing:0; width:max-content; min-width:100%; font-size:var(--text-xs); }
.pmo-cap-matrix th, .pmo-cap-matrix td { border-bottom:1px solid var(--border-color); border-right:1px solid var(--border-color); }
.pmo-cap-matrix thead th { position:sticky; top:0; z-index:2; background:var(--subtle-fg,var(--bg-color)); font-weight:600; color:var(--text-muted); padding:8px 10px; text-align:center; white-space:nowrap; }
.pmo-cap-h-corner { left:0; z-index:3 !important; text-align:left !important; }
.pmo-cap-h-res { position:sticky; left:0; z-index:1; background:var(--card-bg); text-align:left; font-weight:500; padding:6px 12px; white-space:nowrap; max-width:180px; overflow:hidden; text-overflow:ellipsis; }
.pmo-cap-cell { text-align:center; padding:6px 10px; min-width:58px; }
.pmo-cap-cell span { display:inline-block; min-width:34px; }
.pmo-cap-cell.ok { background:rgba(40,167,69,.14); }
.pmo-cap-cell.warn { background:rgba(240,173,20,.22); }
.pmo-cap-cell.over { background:rgba(214,64,64,.20); color:var(--red-600,#c0392b); font-weight:600; }
.pmo-cap-cell.off { background:repeating-linear-gradient(45deg,transparent,transparent 5px,var(--bg-color) 5px,var(--bg-color) 7px); color:var(--text-muted); }
.pmo-cap-matrix tbody tr:hover td { outline:1px solid var(--blue-300,#9db8ff); outline-offset:-1px; }

.pmo-cap-usage .pmo-cap-u-emprow th { position:sticky; left:0; z-index:1; background:var(--subtle-fg,var(--bg-color)); text-align:left; font-weight:600; padding:8px 12px; color:var(--text-color); }
.pmo-cap-u-metric { position:sticky; left:0; z-index:1; background:var(--card-bg); text-align:left; font-weight:400; color:var(--text-muted); padding:6px 12px 6px 22px; white-space:nowrap; }
.pmo-cap-u-cell { text-align:center; padding:6px 10px; min-width:58px; }
.pmo-cap-u-cell.ok { background:rgba(40,167,69,.14); }
.pmo-cap-u-cell.warn { background:rgba(240,173,20,.22); }
.pmo-cap-u-cell.over { background:rgba(214,64,64,.20); color:var(--red-600,#c0392b); font-weight:600; }
.pmo-cap-u-cell.off { color:var(--text-muted); }
.pmo-cap-h-total { position:sticky; top:0; z-index:2; background:var(--subtle-fg,var(--bg-color)); font-weight:600; color:var(--text-muted); padding:8px 10px; text-align:center; }
.pmo-cap-total { font-weight:600; }
.pmo-cap-u-footrow th, .pmo-cap-u-footrow td { border-top:2px solid var(--border-color); font-weight:600; background:var(--subtle-fg,var(--bg-color)); }
.pmo-cap-proj-link { cursor:pointer; color:var(--primary,var(--blue-600)); }
.pmo-cap-proj-link:hover { text-decoration:underline; }

/* vista Trabajo por recurso */
.pmo-cap-work { padding:12px 14px; }
.pmo-cap-work-emp { font-weight:600; font-size:var(--text-md); margin-bottom:10px; }
.pmo-cap-wgroup { border:1px solid var(--border-color); border-radius:var(--border-radius-md,6px); margin-bottom:8px; overflow:hidden; }
.pmo-cap-wgroup-head { display:flex; align-items:center; gap:8px; padding:8px 12px; background:var(--subtle-fg,var(--bg-color)); cursor:pointer; }
.pmo-cap-wgroup-head--static { cursor:default; }
.pmo-cap-caret { color:var(--text-muted); transition:transform .12s; display:inline-block; }
.pmo-cap-wgroup.is-collapsed .pmo-cap-caret { transform:rotate(-90deg); }
.pmo-cap-wgroup.is-collapsed .pmo-cap-wgroup-body { display:none; }
.pmo-cap-wgroup-title { font-weight:600; font-size:var(--text-sm); flex:1; min-width:0; }
.pmo-cap-wgroup-hours { font-weight:600; font-size:var(--text-sm); white-space:nowrap; }
.pmo-cap-wgroup.is-confidential .pmo-cap-wgroup-head { background:rgba(214,64,64,.10); }
.pmo-cap-wgroup-body { padding:2px 0; }
.pmo-cap-wtask { padding:7px 12px 7px 30px; border-top:1px solid var(--border-color); }
.pmo-cap-wtask-main { display:flex; align-items:baseline; justify-content:space-between; gap:12px; }
.pmo-cap-wtask-name { font-size:var(--text-sm); min-width:0; }
.pmo-cap-wtask-hours { font-size:var(--text-sm); white-space:nowrap; color:var(--text-color); }
.pmo-cap-wtask-sub { font-size:var(--text-xs); margin-top:2px; display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
.pmo-cap-nodate { color:var(--red-600,#c0392b); }
.pmo-cap-badge { border:1px solid var(--border-color); border-radius:8px; padding:0 7px; font-size:11px; color:var(--text-muted); }
.pmo-cap-task-link { cursor:pointer; color:var(--primary,var(--blue-600)); }
.pmo-cap-task-link:hover { text-decoration:underline; }

.pmo-cap-tip { position:absolute; z-index:1000; pointer-events:none; background:var(--card-bg); border:1px solid var(--border-color); border-radius:8px; box-shadow:var(--shadow-lg,0 4px 16px rgba(0,0,0,.14)); padding:10px 12px; min-width:190px; font-size:var(--text-xs); }
.pmo-cap-tip-title { font-weight:600; font-size:var(--text-sm); }
.pmo-cap-tip-sub { margin-bottom:6px; }
.pmo-cap-tip-row { display:flex; justify-content:space-between; gap:16px; padding:1px 0; }
`;
		$("<style>", { id: "pmo-cap-styles", html: css }).appendTo(document.head);
	}
}
