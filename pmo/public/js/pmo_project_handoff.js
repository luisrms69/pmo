// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO Project Handoff (ADR-0014). El Responsable operativo interno y el Contacto principal del cliente
// viven en el Project (fuente única) y NUNCA se editan ni se escriben desde el Handoff: aquí solo se
// consultan, se muestran read-only y se congelan al Submit (el guard server-side impide emitir sin ellos).
// Este JS, en Draft, consulta los valores actuales del Project al elegirlo y en cada refresh, refleja los
// valores vigentes y avisa —antes del Submit— si falta alguno, ofreciendo abrir el Project para completarlo.

frappe.ui.form.on("PMO Project Handoff", {
	refresh(frm) {
		pmo_handoff_open_project_button(frm);
		pmo_handoff_sync_parties(frm);
	},
	project(frm) {
		pmo_handoff_sync_parties(frm);
	},
});

function pmo_handoff_open_project_button(frm) {
	// Botón para completar los datos EN EL PROJECT (nunca en el Handoff). Se abre en otra pestaña para no
	// perder cambios no guardados del Handoff. Solo tiene sentido en Draft y con Project elegido.
	if (frm.doc.docstatus !== 0 || !frm.doc.project) return;
	frm.add_custom_button(__("Abrir Project para completar datos"), () => {
		window.open(`/app/project/${encodeURIComponent(frm.doc.project)}`, "_blank");
	});
}

function pmo_handoff_sync_parties(frm) {
	// Solo Draft: en documentos emitidos los valores están congelados y no deben reconsultarse.
	frm.set_intro("");
	if (frm.doc.docstatus !== 0 || !frm.doc.project) return;

	frappe.db
		.get_value("Project", frm.doc.project, ["pmo_operational_owner", "pmo_customer_contact"])
		.then((r) => {
			const v = (r && r.message) || {};
			const owner = v.pmo_operational_owner || null;
			const contact = v.pmo_customer_contact || null;

			// Reflejar los valores vigentes del Project (read-only). Solo se escribe en el form si cambió,
			// para no ensuciar el borrador innecesariamente. NUNCA se escribe hacia el Project.
			if ((frm.doc.operational_owner || null) !== owner)
				frm.set_value("operational_owner", owner);
			if ((frm.doc.customer_contact || null) !== contact)
				frm.set_value("customer_contact", contact);

			const missing = [];
			if (!owner)
				missing.push(__("Falta definir el Responsable operativo interno en el Project."));
			if (!contact)
				missing.push(__("Falta definir el Contacto principal del cliente en el Project."));
			if (missing.length) frm.set_intro(missing.join("<br>"), "orange");
		});
}
