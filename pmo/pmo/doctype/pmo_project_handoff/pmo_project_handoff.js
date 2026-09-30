// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO Project Handoff — Acta de Inicio. El Contacto principal del cliente se selecciona filtrado por el
// Customer del Project usando el MECANISMO NATIVO de ERPNext/Frappe (contact_query + Dynamic Link). No es
// un selector libre de contactos. El Customer se toma del Project (campo `customer`, fetch_from). La
// autoridad y las obligatoriedades reales se validan server-side en before_submit.

frappe.ui.form.on("PMO Project Handoff", {
	refresh(frm) {
		// Selector de contacto: solo contactos relacionados con el Customer del Project (Dynamic Link).
		frm.set_query("customer_contact", () => ({
			query: "frappe.contacts.doctype.contact.contact.contact_query",
			filters: { link_doctype: "Customer", link_name: frm.doc.customer || "" },
		}));
		pmo_hof_customer_hint(frm);
	},

	project(frm) {
		// Al cambiar de Project, el Customer y el contacto previo dejan de ser válidos: se limpia el contacto.
		frm.set_value("customer_contact", null);
	},

	customer(frm) {
		// `customer` llega por fetch_from del Project; refresca el aviso cuando se resuelve.
		pmo_hof_customer_hint(frm);
	},
});

// Aviso claro cuando el Project no tiene Customer: sin él no pueden listarse contactos (selector vacío) y el
// Submit se bloqueará server-side. Indica la acción concreta al usuario.
function pmo_hof_customer_hint(frm) {
	if (frm.doc.docstatus === 0 && frm.doc.project && !frm.doc.customer) {
		frm.set_intro(
			"Define el Customer en el Project para poder seleccionar el Contacto principal del cliente.",
			"orange"
		);
	} else {
		frm.set_intro("");
	}
}
