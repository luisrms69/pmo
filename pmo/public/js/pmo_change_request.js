// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.ui.form.on("PMO Change Request", {
	project(frm) {
		// Default del responsable de implementación desde el Project (solo si está vacío y el CR es editable).
		// Es un dato propio del cambio; el usuario puede cambiarlo. NO escribe al Project.
		if (frm.doc.docstatus === 0 && frm.doc.project && !frm.doc.implementation_owner) {
			frappe.db.get_value("Project", frm.doc.project, "pmo_operational_owner").then((r) => {
				const owner = r && r.message && r.message.pmo_operational_owner;
				if (owner) frm.set_value("implementation_owner", owner);
			});
		}
	},
	refresh(frm) {
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

		// ADR-0005 D11: abrir el reporte PMO Baseline Comparison ya parametrizado (before → after). Con el
		// modelo actual, la Baseline `Approved Change` referencia exactamente un CR y fija su baseline_after.
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

		// NOTA (B4): la acción "Apply Quotation to Project" con Quotation seleccionada por el usuario fue
		// eliminada. El apply automático y gobernado (deriva la versión Ganada + guard de fingerprint) se
		// añade en B6.

		// B5/B6: acciones sobre CR Approved y no aplicado. Toda la validación crítica es server-side
		// (owner-only + estado + fingerprint); el JS solo dispara la llamada, sin inputs manuales.
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.workflow_state === "Approved" &&
			!frm.doc.applied_to_project
		) {
			// B5: re-aprobar la versión vigente cuando cambió el delta (nueva versión En Revisión).
			frm.add_custom_button(__("Reapprove addendum version"), () => {
				frappe
					.call({
						method: "pmo.pmo.doctype.pmo_change_request.pmo_change_request.reapprove_addendum_version",
						args: { change_request: frm.doc.name },
						freeze: true,
						freeze_message: __("Reapproving addendum version…"),
					})
					.then((r) => {
						if (r.exc || !r.message) return;
						frm.reload_doc();
						frappe.show_alert({
							message: __("Addendum version reapproved."),
							indicator: "green",
						});
					});
			});

			// B6: aplicar la Addenda Ganada autorizada (deriva la versión server-side + guard de fingerprint).
			frm.add_custom_button(__("Apply addendum to Project"), () => {
				frappe
					.call({
						method: "pmo.pmo.doctype.pmo_change_request.pmo_change_request.apply_addendum",
						args: { change_request: frm.doc.name },
						freeze: true,
						freeze_message: __("Applying addendum to Project…"),
					})
					.then((r) => {
						if (r.exc) return;
						frm.reload_doc();
						frappe.show_alert({
							message: __("Addendum applied to Project."),
							indicator: "green",
						});
					});
			});
		}
	},
});
