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
	},
});

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
