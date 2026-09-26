// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.query_reports["PMO Continuous Improvement"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "Open\nClosed\nCancelled\nAll",
			default: "Open",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "responsible",
			label: __("Responsible"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "overdue",
			label: __("Overdue"),
			fieldtype: "Check",
		},
	],
};
