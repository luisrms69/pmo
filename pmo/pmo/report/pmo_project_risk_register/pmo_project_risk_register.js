// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.query_reports["PMO Project Risk Register"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			// El valor filtra por el token almacenado; la etiqueta se traduce (ES).
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				{ value: "", label: "" },
				{ value: "Open", label: __("Open") },
				{ value: "Managing", label: __("Managing") },
				{ value: "Closed", label: __("Closed") },
				{ value: "Materialized", label: __("Materialized") },
			],
		},
		{
			fieldname: "exposure",
			label: __("Exposure"),
			fieldtype: "Select",
			options: [
				{ value: "", label: "" },
				{ value: "Low exposure", label: __("Low exposure") },
				{ value: "Medium exposure", label: __("Medium exposure") },
				{ value: "High exposure", label: __("High exposure") },
			],
		},
	],
};
