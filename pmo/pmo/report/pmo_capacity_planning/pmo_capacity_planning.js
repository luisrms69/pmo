// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.query_reports["PMO Capacity Planning"] = {
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
		{
			fieldname: "granularity",
			label: __("Granularity"),
			fieldtype: "Select",
			options: ["Day", "Week", "Month", "Total"],
			default: "Day",
		},
	],

	// Solo presentación: colorea sobreasignación/uso alto. No altera datos (P4 intacto).
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const f = column.fieldname;
		if ((f === "util_planned" || f === "util_actual") && data[f] != null) {
			if (data[f] > 100) {
				value = `<span style="color:red">${value}</span>`;
			} else if (data[f] >= 80) {
				value = `<span style="color:orange">${value}</span>`;
			}
		}
		if (f === "overallocation" && data[f] > 0) {
			value = `<span style="color:red">${value}</span>`;
		}
		if (f === "free" && data[f] < 0) {
			value = `<span style="color:red">${value}</span>`;
		}
		return value;
	},
};
