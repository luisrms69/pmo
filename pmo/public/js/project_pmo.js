// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — navegación y señales de riesgo en el form nativo de Project (SOLO navegación + indicadores derivados).
// No modifica core, no crea campos/DocTypes, no cambia permisos ni persiste estado. Las señales de riesgo
// provienen de `pmo.risk_signals.get_risk_signals` (P4-safe, derivadas de datos existentes). ADR-0011 / ADR-0016.

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(
			__("PMO Project Control"),
			() => frappe.set_route("pmo_project_control", frm.doc.name),
			__("PMO")
		);

		// ADR-0016 — Riesgos: acciones contextuales + situación (indicadores derivados). Una sola llamada.
		frappe
			.xcall("pmo.risk_signals.get_risk_signals", { project: frm.doc.name })
			.then((s) => {
				if (!s) return;

				// Acción 1: evaluar (open-or-create). El texto refleja la situación real.
				frm.add_custom_button(
					s.assessment_exists
						? __("View risk assessment")
						: __("Perform risk assessment"),
					() => {
						if (s.assessment) {
							frappe.set_route("Form", "PMO Project Risk Assessment", s.assessment);
						} else {
							frappe.new_doc("PMO Project Risk Assessment", {
								project: frm.doc.name,
							});
						}
					},
					__("PMO")
				);

				// Acción 2: gestionar los PMO Project Risk de ESTE Project (lista filtrada; nunca global).
				frm.add_custom_button(
					__("Manage risks"),
					() => frappe.set_route("List", "PMO Project Risk", { project: frm.doc.name }),
					__("PMO")
				);

				// Situación compacta con jerarquía: estado de evaluación + solo las brechas > 0.
				if (s.assessment_state === "none") {
					frm.dashboard.add_indicator(__("Risk: not assessed"), "orange");
					return;
				}
				if (!s.open) {
					frm.dashboard.add_indicator(__("No open risks"), "green");
				} else {
					frm.dashboard.add_indicator(
						`${__("Open risks")}: ${s.open}`,
						s.needs_attention ? "red" : "blue"
					);
				}
				if (s.high_exposure) {
					frm.dashboard.add_indicator(
						`${__("High-exposure risks")}: ${s.high_exposure}`,
						"red"
					);
				}
				if (s.no_owner) {
					frm.dashboard.add_indicator(`${__("Without owner")}: ${s.no_owner}`, "orange");
				}
				if (s.no_response) {
					frm.dashboard.add_indicator(
						`${__("Without treatment")}: ${s.no_response}`,
						"orange"
					);
				}
			})
			.catch(() => {
				// Silencioso: si falla la señal (p. ej. sin permiso), el form nativo no se ve afectado.
			});
	},
});
