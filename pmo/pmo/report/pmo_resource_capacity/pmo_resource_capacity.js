// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

/* PMO Resource Capacity (ADR-0003) — cobertura/mantenimiento de PMO Capacity.
   Muestra la capacidad efectiva por recurso a una fecha (as_of) y quién no la tiene configurada. */
frappe.query_reports["PMO Resource Capacity"] = {
	filters: [
		{
			fieldname: "as_of",
			label: __("A la fecha"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "department",
			label: __("Departamento"),
			fieldtype: "Link",
			options: "Department",
		},
	],
};
