// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

/* PMO Resource Capacity (Capacity Paso 4) — cobertura de jornada por recurso.
   Muestra la capacidad NETA por recurso a una fecha (as_of), su origen (Shift/Default) y quién NO tiene
   turno asignado. El estado se pinta en ROJO cuando falta turno (missing_shift), aunque haya default. */
frappe.query_reports["PMO Resource Capacity"] = {
	filters: [
		{
			fieldname: "as_of",
			label: __("As of date"),
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
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],
	// Patrón nativo de ERPNext: colorear celdas por fila. Rojo = sin turno resoluble (informativo).
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.missing_shift && ["status", "origin"].includes(column.fieldname)) {
			value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
