// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

/* PMO Portfolio — salud multi-proyecto (una fila por proyecto visible al observador).
   Reutiliza los indicadores del Status Report; el detalle vive en PMO Status Report / Planned vs Actual. */
frappe.query_reports["PMO Portfolio"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "include_completed",
			label: __("Include completed"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
