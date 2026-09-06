// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// ADR-0005 D7: acción explícita "Aplicar Cotización al Project". Solo visible al owner sobre un CR
// Aprobado y aún no aplicado. Delega en el contrato de erpnext_proposals (server-side); el cliente no
// escribe proposal_project ni reproduce sus guards. No mueve el Workflow: tras aplicar, el owner ejecuta
// "Marcar Implementado" cuando el Current Plan esté completo.
frappe.ui.form.on("PMO Change Request", {
	refresh(frm) {
		// ADR-0005 D11: comparar la baseline previa con la resultante (cambios entre baselines).
		if (frm.doc.baseline_before && frm.doc.baseline_after) {
			frm.add_custom_button(__("¿Qué cambió? (baselines)"), () => {
				window.pmo_show_baseline_diff(
					frm.doc.baseline_before,
					frm.doc.baseline_after,
					__("Cambios entre baselines del Change Request")
				);
			});
		}

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
