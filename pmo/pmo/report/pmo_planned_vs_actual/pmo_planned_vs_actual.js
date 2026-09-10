// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

/* PMO Planned vs Actual (ADR-0008) — esfuerzo planificado vs real por Project/Task.
   Filtros: project (reqd) + status_date (opcional). Al elegir Project se prellena status_date con
   Project.pmo_status_date. Sin status_date, Actual = Task.actual_time (acumulado nativo). */
frappe.query_reports["PMO Planned vs Actual"] = {
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
			label: __("Status Date (cutoff, optional)"),
			fieldtype: "Date",
			max_date: frappe.datetime.get_today(),
		},
	],
};
