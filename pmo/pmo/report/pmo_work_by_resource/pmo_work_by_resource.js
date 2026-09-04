// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.query_reports["PMO Work by Resource"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],

	// Links solo cuando el servidor envió el identificador (Task/Project visibles). Las filas
	// confidenciales / "Sin proyecto" no traen task_id/project_id → permanecen texto plano.
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "task" && data.task_id) {
			value = `<a href="${frappe.utils.get_form_link("Task", data.task_id)}">${value}</a>`;
		}
		if (column.fieldname === "project" && data.project_id) {
			value = `<a href="${frappe.utils.get_form_link(
				"Project",
				data.project_id
			)}">${value}</a>`;
		}
		return value;
	},
};
