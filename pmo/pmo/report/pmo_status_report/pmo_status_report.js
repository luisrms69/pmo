// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

/* PMO Status Report (ADR-0006) — control a fecha de corte.
   Filtros: project (reqd) + status_date. Al elegir Project, se prellena status_date con
   Project.pmo_status_date (Data Date vigente). status_date no admite fecha futura (ADR-0006 D2). */
frappe.query_reports["PMO Status Report"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
			on_change() {
				const project = frappe.query_report.get_filter_value("project");
				if (!project) return;
				frappe.db.get_value("Project", project, "pmo_status_date").then((r) => {
					const sd = r && r.message && r.message.pmo_status_date;
					if (sd) frappe.query_report.set_filter_value("status_date", sd);
				});
			},
		},
		{
			fieldname: "status_date",
			label: __("Status Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			max_date: frappe.datetime.get_today(),
		},
	],
};
