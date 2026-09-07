// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.ui.form.on("PMO Change Request", {
	refresh(frm) {
		// baseline_after: selección explícita más guiada — filtra al mismo Project, Submitted, distinta de
		// la previa y temporalmente compatible (ADR-0005 D5).
		frm.set_query("baseline_after", () => ({
			query: "pmo.pmo.doctype.pmo_change_request.pmo_change_request.baseline_after_query",
			filters: { project: frm.doc.project, baseline_before: frm.doc.baseline_before },
		}));

		// ADR-0005 D11: comparar la línea base previa con la resultante (cambios entre líneas base).
		if (frm.doc.baseline_before && frm.doc.baseline_after) {
			frm.add_custom_button(__("Comparar líneas base"), () => {
				window.pmo_show_baseline_diff(
					frm.doc.baseline_before,
					frm.doc.baseline_after,
					__("Comparación de líneas base")
				);
			});
		}

		// Conveniencia: prellenar baseline_after con la vigente (sin impedir escoger otra).
		if (
			frm.doc.docstatus === 1 &&
			!frm.doc.baseline_after &&
			["Aprobado", "Implementado"].includes(frm.doc.workflow_state)
		) {
			frm.add_custom_button(__("Usar línea base vigente"), () => {
				frappe
					.call({
						method: "pmo.pmo.doctype.pmo_change_request.pmo_change_request.get_current_baseline",
						args: { project: frm.doc.project },
					})
					.then((r) => {
						if (r.exc) return;
						if (r.message) {
							frm.set_value("baseline_after", r.message);
							frappe.show_alert({
								message: __(
									"Prellenada con la línea base vigente. Revisa y guarda."
								),
								indicator: "blue",
							});
						} else {
							frappe.msgprint(__("El Proyecto no tiene una línea base vigente."));
						}
					});
			});
		}

		// ADR-0005 D7: acción "Aplicar Cotización al Project" (owner, CR Aprobado no aplicado). Delega en el
		// contrato de erpnext_proposals (server-side); el cliente no escribe proposal_project.
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.workflow_state === "Aprobado" &&
			!frm.doc.applied_to_project
		) {
			frm.add_custom_button(__("Aplicar Cotización al Project"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Aplicar Cotización al Project"),
					fields: [
						{
							fieldname: "quotation",
							fieldtype: "Link",
							options: "Quotation",
							label: __("Cotización (Ganada)"),
							reqd: 1,
							get_query: () =>
								frm.doc.proposal_group
									? { filters: { proposal_group: frm.doc.proposal_group } }
									: {},
						},
					],
					primary_action_label: __("Aplicar"),
					primary_action(values) {
						frappe
							.call({
								method: "pmo.pmo.doctype.pmo_change_request.pmo_change_request.aplicar_quotation_al_project",
								args: {
									change_request: frm.doc.name,
									quotation: values.quotation,
								},
								freeze: true,
								freeze_message: __("Aplicando alcance al Project…"),
							})
							.then((r) => {
								if (r.exc) return;
								d.hide();
								frm.reload_doc();
								frappe.show_alert({
									message: __("Alcance aplicado al Project."),
									indicator: "green",
								});
							});
					},
				});
				d.show();
			});
		}
	},
});
