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

		// ADR-0005: crear la addenda comercial (delta) desde el CR editable, sin proposal_group aún.
		// Delega en erpnext_proposals (autoría comercial la valida ese app; PMO no eleva permisos).
		if (
			!frm.is_new() &&
			frm.doc.docstatus === 0 &&
			!frm.doc.proposal_group &&
			frm.doc.project
		) {
			frm.add_custom_button(__("Create commercial addendum"), () => {
				frappe.confirm(
					__(
						"A commercial Quotation/Addendum will be created from the original contract. Requires commercial authorship (Proposals Manager). Continue?"
					),
					() => {
						frappe
							.call({
								method: "pmo.pmo.doctype.pmo_change_request.pmo_change_request.crear_addenda",
								args: { change_request: frm.doc.name },
								freeze: true,
								freeze_message: __("Creating addendum…"),
							})
							.then((r) => {
								if (r.exc || !r.message) return;
								frm.reload_doc();
								frappe.show_alert({
									message: __("Addendum created: {0}", [r.message]),
									indicator: "green",
								});
								frappe.set_route("Form", "Quotation", r.message);
							});
					}
				);
			});
		}

		// ADR-0005 D11: abrir el reporte PMO Baseline Comparison ya parametrizado (before → after). El CR
		// va como contexto de apertura, no como atribución del diff (varios CR pueden compartir after).
		if (frm.doc.baseline_before && frm.doc.baseline_after) {
			frm.add_custom_button(__("Compare baselines"), () => {
				frappe.set_route("query-report", "PMO Baseline Comparison", {
					project: frm.doc.project,
					baseline_before: frm.doc.baseline_before,
					baseline_after: frm.doc.baseline_after,
					change_request: frm.doc.name,
				});
			});
		}

		// Conveniencia: prellenar baseline_after con la vigente (sin impedir escoger otra).
		if (
			frm.doc.docstatus === 1 &&
			!frm.doc.baseline_after &&
			["Approved", "Implemented"].includes(frm.doc.workflow_state)
		) {
			frm.add_custom_button(__("Use current baseline"), () => {
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
									"Prefilled with the current baseline. Review and save."
								),
								indicator: "blue",
							});
						} else {
							frappe.msgprint(__("The Project has no current baseline."));
						}
					});
			});
		}

		// ADR-0005 D7: acción "Aplicar Cotización al Project" (owner, CR Aprobado no aplicado). Delega en el
		// contrato de erpnext_proposals (server-side); el cliente no escribe proposal_project.
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.workflow_state === "Approved" &&
			!frm.doc.applied_to_project
		) {
			frm.add_custom_button(__("Apply Quotation to Project"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Apply Quotation to Project"),
					fields: [
						{
							fieldname: "quotation",
							fieldtype: "Link",
							options: "Quotation",
							label: __("Quotation (Won)"),
							reqd: 1,
							get_query: () =>
								frm.doc.proposal_group
									? { filters: { proposal_group: frm.doc.proposal_group } }
									: {},
						},
					],
					primary_action_label: __("Apply"),
					primary_action(values) {
						frappe
							.call({
								method: "pmo.pmo.doctype.pmo_change_request.pmo_change_request.aplicar_quotation_al_project",
								args: {
									change_request: frm.doc.name,
									quotation: values.quotation,
								},
								freeze: true,
								freeze_message: __("Applying scope to Project…"),
							})
							.then((r) => {
								if (r.exc) return;
								d.hide();
								frm.reload_doc();
								frappe.show_alert({
									message: __("Scope applied to Project."),
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
