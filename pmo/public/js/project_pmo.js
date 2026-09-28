// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — botón PMO del form nativo de Project. Organiza las acciones de GOBERNANZA del ciclo del Project en
// un grupo nativo del menú ("Gobernanza"), operando SIEMPRE sobre el Project abierto. Reutiliza el contrato
// contextual `project_governance_state` (mismo motor `_evaluate`) para decidir crear/abrir por control, y los
// flujos existentes de baseline (establecer/nueva/historial). NO duplica lifecycle ni permisos en JS: la
// autoridad son los gates backend (`can_create`). Conserva "Project control" y los indicadores de riesgo.

const BL = "pmo.pmo.doctype.pmo_project_baseline.pmo_project_baseline";
const PGS = "pmo.project_control.project_governance_state";

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;

		// Navegación a la consola de control del proyecto (Page pmo_project_control). En MAYÚSCULAS para
		// distinguirlo visualmente de las acciones de Gobernanza dentro del mismo dropdown PMO.
		frm.add_custom_button(
			__("PROJECT CONTROL"),
			() => frappe.set_route("pmo_project_control", frm.doc.name),
			__("PMO")
		);

		pmo_governance_group(frm);
		pmo_risk_indicators(frm);
		pmo_governance_cycle(frm);
		pmo_committed_display(frm);
	},

	// Solo re-pinta el display de lectura; NO establece ni valida el compromiso (eso vive fuera de esta
	// pestaña y se implementará desde el Handoff en el siguiente bloque).
	pmo_committed_end_date(frm) {
		pmo_committed_display(frm);
	},
});

// --- FIN COMPROMETIDO (pestaña PMO → sección Responsables): dato material del Project, mostrado de forma
// compacta y de SOLO LECTURA. No es configuración de esta pestaña: sin diálogo, sin acción, sin escribir el
// campo. El compromiso se establecerá desde el Handoff (bloque siguiente). El campo editable sigue viviendo
// en el formulario nativo del Project (comportamiento backend intacto). ------------------------------------
function pmo_committed_display(frm) {
	const fld = frm.fields_dict && frm.fields_dict.pmo_committed_html;
	if (!fld) return;
	const raw = frm.doc.pmo_committed_end_date;
	let val = "No establecido";
	if (raw) {
		const d = frappe.datetime.str_to_obj(raw);
		val = `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(
			2,
			"0"
		)}/${d.getFullYear()}`;
	}
	fld.$wrapper.html(
		`<div class="small" style="margin-top:4px"><span class="text-muted">Fin comprometido:</span> <strong>${frappe.utils.escape_html(
			val
		)}</strong></div>`
	);
}

// --- CICLO DE GOBERNANZA (pestaña PMO → sección "Ciclo de Gobernanza"): render operable de las 6 etapas.
// Reutiliza EXACTAMENTE el contrato `project_governance_state` (mismo motor `_evaluate`) para clasificar y
// los flujos existentes (crear/abrir + diálogos de baseline). NO lifecycle en JS, NO segundo motor, NO
// dashboard nuevo: solo presenta el estado del backend y dispara acciones ya gobernadas por sus gates.
const GOV_STAGE_BADGE = {
	completo: ["green", "Completo"],
	pendiente: ["orange", "Pendiente"],
	no_aplica: ["gray", "No aplica"],
};

// Microcopy SOLO de presentación para el estado interno `not_applicable`. El backend sigue devolviendo
// exactamente `completo | pendiente | no_aplica`; aquí NO se reconstruye lifecycle: se traduce ese estado
// a una etiqueta/mensaje contextual por control para no confundir "aplicabilidad del control" con
// "disponibilidad de la funcionalidad". Si un control no tiene override, cae al genérico + `na_reason`
// que el propio backend provee (causa real).
const GOV_NA_COPY = {
	risk: {
		label: "Aún no requerido",
		color: "blue",
		note: "La evaluación de riesgos será requerida por Gobernanza a partir de la primera línea base. Puedes evaluar y gestionar riesgos desde ahora.",
	},
	change: {
		label: "Sin pendientes",
		color: "gray",
		note: "Sin cambios pendientes. Crea o gestiona solicitudes cuando lo necesites.",
	},
	closure: {
		label: "Aún no requerido",
		color: "blue",
		note: "El cierre formal será requerido cuando corresponda cerrar el proyecto.",
	},
	review: {
		label: "Aún no requerido",
		color: "blue",
		note: "La revisión posterior será requerida después del cierre formal.",
	},
	// Acta y Línea base: `not_applicable` solo ocurre en estados terminales (proyecto fuera de ejecución).
	// Se expresa la causa real, no un "No aplica" ambiguo. No cambia ninguna regla del motor.
	acta: {
		label: "No aplica",
		color: "gray",
		note: "Solo aplica con el proyecto en ejecución (Open/On hold).",
	},
	baseline: {
		label: "No aplica",
		color: "gray",
		note: "Solo aplica con el proyecto en ejecución (Open/On hold).",
	},
};

function pmo_governance_cycle(frm) {
	const fld = frm.fields_dict && frm.fields_dict.pmo_access_html;
	if (!fld) return; // el campo aún no existe (fixture no migrado)
	fld.$wrapper.html('<div class="text-muted small">Cargando ciclo de Gobernanza…</div>');
	frappe
		.xcall(PGS, { project: frm.doc.name })
		.then((d) => {
			if (!d) {
				fld.$wrapper.empty();
				return;
			}
			if (d.exempt) {
				fld.$wrapper.html(pmo_exclusion_banner(d));
				return;
			}
			const built = pmo_cycle_grid(frm, d);
			fld.$wrapper.html(built.html);
			fld.$wrapper.off("click.gov").on("click.gov", "button[data-act]", function () {
				const h = built.handlers[$(this).attr("data-act")];
				if (h) h();
			});
		})
		.catch(() => fld.$wrapper.empty());
}

// Proyecto excluido: mensaje claro de que NO está sujeto al ciclo (el motivo/autorización viven en los
// campos nativos de la sección Gobernanza; aquí solo se refuerza visualmente el estado).
function pmo_exclusion_banner(d) {
	const reason = d.exempt_reason
		? `<div class="small text-muted" style="margin-top:4px">Motivo: ${frappe.utils.escape_html(
				d.exempt_reason
		  )}</div>`
		: "";
	return `<div style="border:1px solid var(--border-color);border-left:3px solid var(--blue-500);border-radius:var(--border-radius);padding:10px 12px;background:var(--bg-blue,#f0f7ff)">
		<div style="font-weight:600">Proyecto excluido del ciclo de Gobernanza PMO</div>
		<div class="small text-muted">Este Project no está sujeto al ciclo de Gobernanza y no genera desviaciones.</div>
		${reason}
	</div>`;
}

// Rejilla de 6 etapas (2 columnas × 3 filas) sobre el Project abierto. Devuelve HTML + mapa de handlers.
function pmo_cycle_grid(frm, d) {
	const open = (e) => frappe.set_route("Form", e.doctype, e.name);
	const create = (dt) => frappe.new_doc(dt, { project: frm.doc.name });
	const listFor = (dt) => frappe.set_route("List", dt, { project: frm.doc.name });
	const c = {};
	(d.controls || []).forEach((x) => (c[x.control] = x));
	const bl = d.baseline || {};
	const handlers = {};
	let seq = 0;
	// Registra un handler y devuelve el markup del botón (delegación por data-act).
	const btn = (label, fn, primary) => {
		const id = "a" + seq++;
		handlers[id] = fn;
		return `<button class="btn btn-${
			primary ? "primary" : "default"
		} btn-xs" data-act="${id}" style="margin-right:6px;margin-top:6px">${frappe.utils.escape_html(
			label
		)}</button>`;
	};

	// Acciones por etapa, reutilizando los gates del contrato (existing / can_create / estado).
	const actions = {
		acta: () => {
			const x = c.acta || {};
			if (x.existing) return btn("Abrir", () => open(x.existing), true);
			if (x.can_create) return btn("Crear", () => create("PMO Project Handoff"), true);
			return "";
		},
		baseline: () => {
			let out = "";
			if (!bl.has_baseline) {
				out += btn("Establecer", () => pmo_establish_baseline(frm), true);
			} else {
				out += btn(
					"Nueva",
					() => pmo_new_baseline(frm, bl.eligible_crs || [], !!bl.can_replan),
					true
				);
				if (bl.baseline_count > 0)
					out += btn("Historial", () => listFor("PMO Project Baseline"));
			}
			return out;
		},
		risk: () => {
			const x = c.risk || {};
			let out = "";
			if (x.existing) out += btn("Abrir", () => open(x.existing), true);
			else if (x.can_create)
				out += btn("Evaluar", () => create("PMO Project Risk Assessment"), true);
			out += btn("Gestionar", () => listFor("PMO Project Risk"));
			return out;
		},
		change: () => {
			let out = btn("Gestionar", () => listFor("PMO Change Request"), true);
			out += btn("Crear", () => create("PMO Change Request"));
			return out;
		},
		closure: () => {
			const x = c.closure || {};
			if (x.existing) return btn("Abrir", () => open(x.existing), true);
			if (x.state === "pendiente" && x.can_create)
				return btn("Crear", () => create("PMO Project Closure"), true);
			return "";
		},
		review: () => {
			const x = c.review || {};
			if (x.existing) return btn("Abrir", () => open(x.existing), true);
			if (x.state === "pendiente" && x.can_create)
				return btn("Crear", () => create("PMO Post-Project Review"), true);
			return "";
		},
	};

	// Complemento breve por etapa (conteos útiles del contrato). Solo presentación.
	const extra = {
		risk: () => {
			const k = (c.risk && c.risk.counts) || {};
			return k.open ? `Riesgos abiertos: ${k.open}` : "";
		},
		change: () => {
			const k = (c.change && c.change.counts) || {};
			const bits = [];
			if (k.open) bits.push(`${k.open} abiertas`);
			if (k.in_review) bits.push(`${k.in_review} en revisión`);
			return bits.join(" · ");
		},
	};

	const cards = (d.controls || [])
		.map((x, i) => {
			// `no_aplica` se re-etiqueta por control (microcopy contextual); complete/pending intactos.
			const na = x.state === "no_aplica" ? GOV_NA_COPY[x.control] : null;
			const base = GOV_STAGE_BADGE[x.state] || GOV_STAGE_BADGE.no_aplica;
			const badge = na ? [na.color, na.label] : base;
			const owner =
				x.action_owner && x.state === "pendiente"
					? `<span class="text-muted small" style="margin-left:6px">· Responsable: ${frappe.utils.escape_html(
							x.action_owner
					  )}</span>`
					: "";
			// Explicación breve: situación cuando hay pendiente; microcopy contextual (o `na_reason` del
			// backend) cuando no aplica; la descripción de la etapa en el resto.
			let note = "";
			if (x.state === "pendiente" && x.situation)
				note = frappe.utils.escape_html(x.situation);
			else if (x.state === "no_aplica")
				note = frappe.utils.escape_html((na && na.note) || x.na_reason || "");
			else note = frappe.utils.escape_html(x.description || "");
			const xtra = extra[x.control] ? extra[x.control]() : "";
			const acts = actions[x.control] ? actions[x.control]() : "";
			return `<div style="border:1px solid var(--border-color);border-radius:var(--border-radius);padding:10px 12px">
				<div style="display:flex;align-items:center;justify-content:space-between">
					<div style="font-weight:600">${i + 1}. ${frappe.utils.escape_html(x.label)}${owner}</div>
					<span class="indicator-pill ${badge[0]}">${badge[1]}</span>
				</div>
				<div class="small text-muted" style="margin-top:2px">${note}</div>
				${xtra ? `<div class="small text-muted" style="margin-top:2px">${xtra}</div>` : ""}
				<div>${acts}</div>
			</div>`;
		})
		.join("");

	const html = `<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px">${cards}</div>`;
	return { html, handlers };
}

// --- GOBERNANZA: grupo único de acciones del ciclo, sobre el Project actual (crear/abrir según estado) ---
function pmo_governance_group(frm) {
	const G = __("PMO"); // TODO bajo un ÚNICO botón/dropdown "PMO" (junto a "Project control")
	const open = (e) => frappe.set_route("Form", e.doctype, e.name);
	const create = (dt) => frappe.new_doc(dt, { project: frm.doc.name });

	frappe
		.xcall(PGS, { project: frm.doc.name })
		.then((d) => {
			if (!d) return;
			if (d.exempt) {
				frm.add_custom_button(
					__("Governance: excluded"),
					() =>
						frappe.msgprint({
							title: __("Excluded from PMO governance"),
							message: frappe.utils.escape_html(d.exempt_reason || "—"),
							indicator: "blue",
						}),
					G
				);
				return;
			}
			const c = {};
			(d.controls || []).forEach((x) => (c[x.control] = x));
			const bl = d.baseline || {};

			// Acta de inicio: existe → abrir; falta → crear (Handoff).
			if (c.acta && c.acta.existing)
				frm.add_custom_button(__("Start record: open"), () => open(c.acta.existing), G);
			else if (c.acta && c.acta.can_create)
				frm.add_custom_button(__("Start record"), () => create("PMO Project Handoff"), G);

			// Línea base: reutiliza los flujos existentes (establecer / nueva / historial) según el estado.
			if (!bl.has_baseline) {
				frm.add_custom_button(__("Set baseline"), () => pmo_establish_baseline(frm), G);
			} else {
				frm.add_custom_button(
					__("New baseline"),
					() => pmo_new_baseline(frm, bl.eligible_crs || [], !!bl.can_replan),
					G
				);
				if (bl.baseline_count > 0)
					frm.add_custom_button(
						__("Baseline history"),
						() =>
							frappe.set_route("List", "PMO Project Baseline", {
								project: frm.doc.name,
							}),
						G
					);
			}

			// Riesgos: evaluación (abrir/crear) + gestionar (lista filtrada por el Project).
			if (c.risk && c.risk.existing)
				frm.add_custom_button(__("Risk assessment: open"), () => open(c.risk.existing), G);
			else if (c.risk && c.risk.can_create)
				frm.add_custom_button(
					__("Perform risk assessment"),
					() => create("PMO Project Risk Assessment"),
					G
				);
			frm.add_custom_button(
				__("Manage risks"),
				() => frappe.set_route("List", "PMO Project Risk", { project: frm.doc.name }),
				G
			);

			// Solicitudes de cambio: lista filtrada por el Project (permite crear desde la lista).
			frm.add_custom_button(
				__("Change requests"),
				() => frappe.set_route("List", "PMO Change Request", { project: frm.doc.name }),
				G
			);

			// Cierre: abrir el existente; crear solo cuando corresponde (pendiente) y con permiso.
			if (c.closure && c.closure.existing)
				frm.add_custom_button(
					__("Issue closure: open"),
					() => open(c.closure.existing),
					G
				);
			else if (c.closure && c.closure.state === "pendiente" && c.closure.can_create)
				frm.add_custom_button(__("Issue closure"), () => create("PMO Project Closure"), G);

			// Revisión posterior: abrir la existente; crear solo cuando corresponde (pendiente) y con permiso.
			if (c.review && c.review.existing)
				frm.add_custom_button(
					__("Perform post-project review: open"),
					() => open(c.review.existing),
					G
				);
			else if (c.review && c.review.state === "pendiente" && c.review.can_create)
				frm.add_custom_button(
					__("Perform post-project review"),
					() => create("PMO Post-Project Review"),
					G
				);

			// Ver estado de gobernanza: abre la pestaña Gobernanza (instructivo/estado completo del ciclo).
			const n = d.pending_count || 0;
			frm.add_custom_button(
				n ? `${__("View governance status")} (${n})` : __("View governance status"),
				() => frappe.set_route("pmo_project_control", frm.doc.name, "governance"),
				G
			);

			// Señal de estado de línea base (banner del form; no un mini-dashboard).
			if (!bl.has_baseline) frm.set_intro(__("No baseline"), "orange");
			else
				frm.set_intro(
					__("Baseline: {0} · {1}", [bl.revision || "", bl.effective_date || "—"]),
					"blue"
				);
		})
		.catch(() => {
			// Silencioso: sin acceso, el form no se ve afectado.
		});
}

// --- LÍNEA BASE: diálogos reutilizados (establecer / nueva) — flujo canónico existente -----------------
function pmo_establish_baseline(frm) {
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
				.xcall(`${BL}.establish_baseline`, { project: frm.doc.name, reason: v.reason })
				.then((r) => {
					frappe.show_alert({
						message: __("Baseline set: {0}", [r.revision]),
						indicator: "green",
					});
					frm.reload_doc();
				});
		},
		__("Set baseline"),
		__("Confirm")
	);
}

function pmo_new_baseline(frm, eligible_crs, can_replan) {
	const has_cr = eligible_crs.length > 0;
	if (!has_cr && !can_replan) {
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
			label: can_replan
				? __("Backing Change Request (optional)")
				: __("Backing Change Request"),
			options: (can_replan ? [""] : []).concat(eligible_crs.map((c) => c.name)).join("\n"),
			reqd: can_replan ? 0 : 1,
			description: can_replan
				? __("Leave empty for a PMO replan (management decision).")
				: "",
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
				.xcall(`${BL}.new_baseline`, {
					project: frm.doc.name,
					reason: v.reason,
					change_request: v.change_request || null,
				})
				.then((r) => {
					frappe.show_alert({
						message: __("New baseline created: {0}", [r.revision]),
						indicator: "green",
					});
					frm.reload_doc();
				});
		},
		__("New baseline"),
		__("Confirm")
	);
}

// --- RIESGOS: indicadores de estado (señal; las acciones viven en el grupo Gobernanza) -----------------
function pmo_risk_indicators(frm) {
	frappe
		.xcall("pmo.risk_signals.get_risk_signals", { project: frm.doc.name })
		.then((s) => {
			if (!s) return;
			if (s.assessment_state === "none") {
				frm.dashboard.add_indicator(__("Risk: not assessed"), "orange");
				return;
			}
			if (!s.open) frm.dashboard.add_indicator(__("No open risks"), "green");
			else
				frm.dashboard.add_indicator(
					`${__("Open risks")}: ${s.open}`,
					s.needs_attention ? "red" : "blue"
				);
			if (s.high_exposure)
				frm.dashboard.add_indicator(
					`${__("High-exposure risks")}: ${s.high_exposure}`,
					"red"
				);
			if (s.no_owner)
				frm.dashboard.add_indicator(`${__("Without owner")}: ${s.no_owner}`, "orange");
			if (s.no_response)
				frm.dashboard.add_indicator(
					`${__("Without treatment")}: ${s.no_response}`,
					"orange"
				);
		})
		.catch(() => {});
}
