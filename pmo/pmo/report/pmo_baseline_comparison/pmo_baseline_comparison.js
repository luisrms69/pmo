// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.query_reports["PMO Baseline Comparison"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Proyecto"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
		},
		{
			fieldname: "baseline_before",
			label: __("Línea base previa"),
			fieldtype: "Link",
			options: "PMO Project Baseline",
			reqd: 1,
			get_query: () => {
				const p = frappe.query_report.get_filter_value("project");
				return p ? { filters: { project: p, docstatus: 1 } } : {};
			},
		},
		{
			fieldname: "baseline_after",
			label: __("Línea base posterior"),
			fieldtype: "Link",
			options: "PMO Project Baseline",
			reqd: 1,
			get_query: () => {
				const p = frappe.query_report.get_filter_value("project");
				return p ? { filters: { project: p, docstatus: 1 } } : {};
			},
		},
		{
			// Solo contexto de apertura (no filtra datos; el reporte compara líneas base, no atribuye por CR).
			fieldname: "change_request",
			label: __("Change Request (contexto)"),
			fieldtype: "Link",
			options: "PMO Change Request",
		},
	],
};
