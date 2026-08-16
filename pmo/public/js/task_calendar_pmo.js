// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — Task > Gantt ordenado por jerarquía (nested set), no por fechas.
//
// Frappe carga este archivo DESPUÉS del task_calendar.js de ERPNext (hook
// doctype_calendar_js), de modo que frappe.views.calendar["Task"] ya existe.
// GanttView.setup_defaults() mergea el objeto `gantt` en calendar_settings y,
// si hay `order_by`, fija sort_by=order_by con sort_order="asc" de forma nativa.
//
// Solo tocamos Task > Gantt: extendemos el objeto existente (sin reemplazar
// field_map, filtros ni get_events_method de ERPNext) y añadimos gantt.order_by.
// No afecta List, Tree ni Calendar. Sin setTimeout, sin observers, sin cur_list.

frappe.views.calendar["Task"] = Object.assign(frappe.views.calendar["Task"] || {}, {
	gantt: Object.assign(
		typeof (frappe.views.calendar["Task"] || {}).gantt === "object"
			? frappe.views.calendar["Task"].gantt
			: {},
		{ order_by: "lft" }
	),
});
