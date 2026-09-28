// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — menú PMO en el form nativo de Project: navegación + operación de LÍNEA BASE + señales de riesgo.
// SOLO navegación, indicadores derivados y operación de baseline vía endpoints canónicos (snapshot/submit
// reutilizados). No modifica core, no crea campos/DocTypes, no cambia permisos ni persiste estado extra.
// El PM opera la baseline desde aquí; NO necesita abrir el DocType PMO Project Baseline. ADR-0004/0011/0016.

const BL = "pmo.pmo.doctype.pmo_project_baseline.pmo_project_baseline";
const GI = "pmo.governance_inbox";

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;

		// Navegación única a Project Control (control contra el compromiso). Sin acciones Ver/Comparar/Gantt.
		frm.add_custom_button(
			__("Project control"),
			() => frappe.set_route("pmo_project_control", frm.doc.name),
			__("PMO")
		);

		pmo_governance_menu(frm);
		pmo_baseline_menu(frm);
		pmo_risk_menu(frm);
	},
});

// --- GOBERNANZA: estado del proyecto + creación contextual del Acta (integración mínima) ---------------
// Sin sobrecargar el menú: solo aparece cuando hay algo que hacer. "Acta de inicio" crea el Handoff desde
// el contexto del Project (el PM no navega listas). El resto (Línea base, Project Control) ya existe.
function pmo_governance_menu(frm) {
	frappe
		.xcall(`${GI}.get_project_governance`, { project: frm.doc.name })
		.then((g) => {
			if (!g) return;
			if (g.exempt) {
				frm.add_custom_button(
					__("Governance: excluded"),
					() =>
						frappe.msgprint({
							title: __("Excluded from PMO governance"),
							message: frappe.utils.escape_html(frm.doc.pmo_exempt_reason || "—"),
							indicator: "blue",
						}),
					__("PMO")
				);
				return;
			}
			const devs = g.deviations || [];
			const byControl = {};
			devs.forEach((d) => {
				byControl[d.control] = d;
			});
			// Creación CONTEXTUAL de los documentos de gobernanza cuya etapa está activa (lifecycle-aware):
			// el PM opera desde el Project, sin navegar catálogos. Acta/Baseline/Riesgo ya cubiertos por sus
			// menús; aquí se cubren los que faltaban (Acta refuerzo, Cierre, Revisión posterior).
			if (byControl.acta) {
				frm.add_custom_button(
					__("Start record"),
					() => frappe.new_doc("PMO Project Handoff", { project: frm.doc.name }),
					__("PMO")
				);
			}
			if (byControl.closure) {
				frm.add_custom_button(
					__("Issue closure"),
					() => frappe.new_doc("PMO Project Closure", { project: frm.doc.name }),
					__("PMO")
				);
			}
			if (byControl.review) {
				frm.add_custom_button(
					__("Perform post-project review"),
					() => frappe.new_doc("PMO Post-Project Review", { project: frm.doc.name }),
					__("PMO")
				);
			}
			// Solicitudes de cambio: acceso persistente (crear/abrir desde el contexto del Project). El orden
			// del Change Control lo sigue gobernando su propio workflow; aquí solo se abre la lista filtrada.
			frm.add_custom_button(
				__("Change requests"),
				() => frappe.set_route("List", "PMO Change Request", { project: frm.doc.name }),
				__("PMO")
			);
			// Resumen de gobernanza del proyecto: solo si hay desviaciones (si está al día, no ensucia el menú).
			if (devs.length) {
				frm.add_custom_button(
					`${__("Governance")} (${devs.length})`,
					() => pmo_governance_summary(frm, devs),
					__("PMO")
				);
			}
		})
		.catch(() => {
			// Silencioso: sin acceso, el form no se ve afectado.
		});
}

function pmo_governance_summary(frm, devs) {
	const rows = devs
		.map((d) => {
			const age = d.age_days != null ? `${d.age_days} d` : d.since_date || "—";
			return `<tr><td><b>${frappe.utils.escape_html(d.control_label)}</b></td>
				<td>${frappe.utils.escape_html(d.situation || "")}</td>
				<td style="white-space:nowrap">${frappe.utils.escape_html(d.action_owner)}</td>
				<td style="white-space:nowrap">${frappe.utils.escape_html(age)}</td></tr>`;
		})
		.join("");
	frappe.msgprint({
		title: __("Governance deviations"),
		message: `<table class="table table-bordered"><thead><tr>
			<th>${__("Control")}</th><th>${__("Situation")}</th><th>${__("Owner")}</th><th>${__(
			"Age / Date"
		)}</th>
			</tr></thead><tbody>${rows}</tbody></table>`,
		wide: true,
	});
}

// --- LÍNEA BASE: estado compacto + operación (establecer / nueva / historial) -------------------------
function pmo_baseline_menu(frm) {
	frappe
		.xcall(`${BL}.get_baseline_state`, { project: frm.doc.name })
		.then((s) => {
			if (!s) return;

			// Estado de línea base visible a nivel form. Se usa `set_intro` (banner nativo del form) y NO
			// `dashboard.add_indicator`: los indicadores del dashboard se vacían en cada `dashboard.refresh()`
			// (reset), por lo que un indicador añadido de forma asíncrona desaparece en re-renders. El intro
			// persiste a través de esos refrescos y es claramente visible.
			if (!s.has_baseline) {
				frm.set_intro(__("No baseline"), "orange");
			} else {
				frm.set_intro(
					__("Baseline: {0} · {1}", [s.revision || s.baseline, s.effective_date || "—"]),
					"blue"
				);
			}

			if (!s.has_baseline) {
				// Establecer línea base (Original): congela el plan/Tasks actuales. Solo si no existe baseline.
				frm.add_custom_button(
					__("Set baseline"),
					() => pmo_establish_baseline(frm),
					__("PMO")
				);
			} else {
				// Nueva línea base (sustitución formal): conserva las anteriores; no borra desviaciones.
				frm.add_custom_button(
					__("New baseline"),
					() => pmo_new_baseline(frm, s.eligible_crs || [], !!s.can_replan),
					__("PMO")
				);
			}

			// Historial (acceso secundario, trazabilidad): solo si existe al menos una línea base. Sin
			// baseline_count no hay nada que mostrar y el botón no debe aparecer.
			if (s.baseline_count > 0) {
				frm.add_custom_button(
					__("Baseline history"),
					() =>
						frappe.set_route("List", "PMO Project Baseline", {
							project: frm.doc.name,
						}),
					__("PMO")
				);
			}
		})
		.catch(() => {
			// Silencioso: sin permiso o sin acceso, el form nativo no se ve afectado.
		});
}

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
				.xcall(`${BL}.establish_baseline`, {
					project: frm.doc.name,
					reason: v.reason,
				})
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
	// Sin CR elegible y sin autoridad de Replan PMO: el PM no puede rebaselinar libremente; requiere el
	// mecanismo formal (Change Request aprobado e implementado). Server-side lo refuerza igualmente.
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
	if (has_cr) {
		fields.push({
			fieldtype: "Select",
			fieldname: "change_request",
			// Con autoridad PMO, la CR es opcional (vacío = Replan). Sin autoridad, es obligatoria.
			label: can_replan
				? __("Backing Change Request (optional)")
				: __("Backing Change Request"),
			options: (can_replan ? [""] : []).concat(eligible_crs.map((c) => c.name)).join("\n"),
			reqd: can_replan ? 0 : 1,
			description: can_replan
				? __("Leave empty for a PMO replan (management decision).")
				: "",
		});
	}
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

// --- RIESGOS: acciones contextuales + situación (ADR-0016; indicadores derivados, P4-safe) -------------
function pmo_risk_menu(frm) {
	frappe
		.xcall("pmo.risk_signals.get_risk_signals", { project: frm.doc.name })
		.then((s) => {
			if (!s) return;

			frm.add_custom_button(
				s.assessment_exists ? __("View risk assessment") : __("Perform risk assessment"),
				() => {
					if (s.assessment) {
						frappe.set_route("Form", "PMO Project Risk Assessment", s.assessment);
					} else {
						frappe.new_doc("PMO Project Risk Assessment", { project: frm.doc.name });
					}
				},
				__("PMO")
			);

			frm.add_custom_button(
				__("Manage risks"),
				() => frappe.set_route("List", "PMO Project Risk", { project: frm.doc.name }),
				__("PMO")
			);

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
		.catch(() => {});
}
