# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Project Control — compositor canónico del contexto integral de un Project (ADR-0011 D1).

`build_project_control()` COMPONE motores de dominio; no reimplementa lógica (ADR-0011 D2):
- estado/cronograma/forecast/horas-a-corte → `build_status_report()` (ADR-0006/0009; **impone P4**);
- salud → `pmo.health` (fuente única, ADR-0011 D2);
- horas planificadas → nativo (Σ `Task.expected_time` de hojas, ADR-0008);
- Change Requests → `PMO Change Request` (ADR-0005; su pqc impone P4 en el listado).

Secciones soportadas HOY (v1 del Reporte Ejecutivo): `project`, `executive`, `schedule`, `scope_changes`.
El resto del contrato (resources, hours, costs, freshness, updates…) se añadirá cuando su vista lo
necesite (ADR-0011 D7: sin abstracciones sin consumidor real). Project Updates queda **diferido**.

P4: la impone `build_status_report` (chokepoint). No hay `get_all` sobre datos P4 ni `ignore_permissions`.
`audience` controla exposición/composición, NUNCA permisos (ADR-0011 D3): `portal` oculta información
interna, pero primero se aplica P4.
"""

import frappe
from frappe import N_
from frappe.utils import flt, getdate, today

from pmo.health import HEALTH_LABELS, _health
from pmo.status_date import build_status_report

SECTION_PROJECT = "project"
SECTION_EXECUTIVE = "executive"
SECTION_SCHEDULE = "schedule"
SECTION_SCOPE_CHANGES = "scope_changes"
DEFAULT_SECTIONS = (SECTION_PROJECT, SECTION_EXECUTIVE, SECTION_SCHEDULE, SECTION_SCOPE_CHANGES)

_ACTIVE_STATUSES = ("Open", "Working", "Pending Review", "Overdue")

# Strings visibles del template `executive.html`. El flujo gettext puede no extraer de todos los
# templates de app; se marcan aquí con N_() (no-op) para garantizar su entrada al POT. La plantilla
# los traduce en render con {{ _("...") }}.
_TEMPLATE_STRINGS = (
	N_("Cutoff date (Status Date):"),
	N_("Executive summary"),
	N_("Progress"),
	N_("Baseline"),
	N_("no baseline"),
	N_("Slip vs Baseline:"),
	N_("Current forecast (plan)"),
	N_("Project planned end (ERPNext)"),
	N_("Committed date"),
	N_("Slip vs commitment:"),
	N_("Overdue tasks at cutoff"),
	N_("Forecast exceeds commitment"),
	N_("Tasks expected complete by cutoff"),
	N_("Task compliance"),
	N_("Effort (hours)"),
	N_("% consumed:"),
	N_("Tasks:"),
	N_("completed"),
	N_("active"),
	N_("overdue at cutoff"),
	N_("Schedule (Gantt)"),
	N_("Milestones"),
	N_("Milestone"),
	N_("End (Baseline)"),
	N_("End (Forecast)"),
	N_("Slip"),
	N_("Overdue at cutoff"),
	N_("Yes"),
	N_("Tasks to evaluate (with deviation)"),
	N_("Task"),
	N_("Commitment"),
	N_("Overdue"),
	N_("No tasks with relevant deviation at the cutoff date."),
	N_("{0} task(s) with baseline but without relevant deviation are not listed (of {1} with baseline)."),
	N_("Change Requests"),
	N_("No Change Requests for this Project."),
	N_("Request"),
	N_("Date"),
	N_("State"),
	N_("Impact"),
	N_("Baselines"),
	N_("Hours"),
	N_("Days"),
	N_("Amount"),
)


def build_project_control(project: str, cutoff=None, sections=None, audience: str = "internal") -> dict:
	"""Contexto canónico de Project Control (ADR-0011). Compone; no recalcula.

	- `cutoff=None` → `Project.pmo_status_date` o hoy (ADR-0006).
	- `sections=None` → contexto completo soportado; lista explícita → subconjunto (performance).
	- `audience` ∈ {internal, portal}: exposición/composición, no permisos (P4 la impone el motor).
	"""
	wanted = set(sections) if sections else set(DEFAULT_SECTIONS)
	sd = str(cutoff) if cutoff else (frappe.db.get_value("Project", project, "pmo_status_date") or today())
	# build_status_report es el chokepoint P4 (has_permission read, throw). Se llama siempre.
	sr = build_status_report(project, sd)
	ind = sr.get("indicators") or {}

	ctx = {"audience": audience, "cutoff": sr.get("status_date"), "note": sr.get("note")}
	if SECTION_PROJECT in wanted:
		ctx[SECTION_PROJECT] = _project_section(project, sr)
	if SECTION_EXECUTIVE in wanted:
		ctx[SECTION_EXECUTIVE] = _executive_section(project, sr, ind)
	if SECTION_SCHEDULE in wanted:
		ctx[SECTION_SCHEDULE] = _schedule_section(project, ind)
	if SECTION_SCOPE_CHANGES in wanted:
		ctx[SECTION_SCOPE_CHANGES] = _scope_changes_section(project, audience)
	# Devolver frappe._dict en profundidad: garantiza acceso por atributo en cualquier entorno Jinja
	# (el template canónico se renderiza tanto por render_template como por el Print Format/printview).
	return _deep_dict(ctx)


def _deep_dict(obj):
	"""Convierte dicts anidados a frappe._dict (dot-access) recursivamente; preserva listas y escalares."""
	if isinstance(obj, dict):
		return frappe._dict({k: _deep_dict(v) for k, v in obj.items()})
	if isinstance(obj, list):
		return [_deep_dict(v) for v in obj]
	return obj


def _project_section(project: str, sr: dict) -> dict:
	"""Identidad y fechas del proyecto (encabezado). Sin cálculo de negocio."""
	meta = (
		frappe.db.get_value(
			"Project", project, ["project_name", "status", "company", "customer"], as_dict=True
		)
		or frappe._dict()
	)
	customer_name = None
	if meta.get("customer"):
		customer_name = frappe.db.get_value("Customer", meta.customer, "customer_name") or meta.customer
	return {
		"name": project,
		"project_name": meta.get("project_name"),
		"status": meta.get("status"),
		"company": meta.get("company"),
		"customer": meta.get("customer"),
		"customer_name": customer_name,
		"cutoff": sr.get("status_date"),
		"has_baseline": sr.get("baseline") is not None,
		"forecast_end": (sr.get("current") or {}).get("expected_end_date"),
		"baseline_end": (sr.get("baseline") or {}).get("expected_end_date"),
		"committed_end": sr.get("committed_end_date"),
	}


def _executive_section(project: str, sr: dict, ind: dict) -> dict:
	"""Encabezado ejecutivo (KPIs). Absorbe la semántica validada del B1 `get_header` (ADR-0011 D1),
	con dos correcciones de esta consolidación: (1) horas reales = `actual_hours_to_date` (gobernado por
	fecha de corte, no acumulado actual); (2) el KPI de tareas previstas al corte NO se llama "avance"."""
	has_bl = sr.get("baseline") is not None
	tvb = ind.get("tasks_vs_baseline") or []
	counts = ind.get("counts") or {}
	due = counts.get("baseline_due_by_cutoff")
	done = counts.get("completed_by_cutoff")
	overdue = (ind.get("tasks_overdue_at_cutoff") or {}).get("count")
	exceeds = (ind.get("forecast_exceeds_commitment") or {}).get("count") or 0
	slip_bl = ind.get("final_date_slip_days")
	slip_cm = ind.get("slip_vs_committed_days")

	pc = frappe.db.get_value("Project", project, "percent_complete")

	# Horas planificadas: Σ Task.expected_time de hojas (ADR-0008). get_list respeta la pqc de Task.
	planned = 0.0
	for t in frappe.get_list(
		"Task", filters={"project": project, "is_group": 0}, fields=["expected_time"], limit=0
	):
		planned += flt(t.get("expected_time"))
	# Horas reales: Timesheet ≤ fecha de corte (fuente canónica del reporte gobernado por corte, ADR-0011 D1).
	actual = flt(ind.get("actual_hours_to_date"))

	health_key = _health(slip_bl, slip_cm, overdue, exceeds)
	return {
		"kpis": {
			"health": health_key,
			"health_label": HEALTH_LABELS[health_key],  # etiqueta fuente (inglés); el template la traduce
			"percent_complete": round(flt(pc)),
			# % de tareas del baseline PREVISTAS (debían estar terminadas) al corte. Cuenta tareas; NO es
			# "avance esperado" ni comparable directamente con percent_complete. Reservado: overdue = incumplidas.
			"tasks_due_by_cutoff_pct": round(due / len(tvb) * 100)
			if (has_bl and tvb and due is not None)
			else None,
			"slip_baseline_days": slip_bl,
			"slip_committed_days": slip_cm,
			"compliance_pct": round(done / due * 100) if (has_bl and due) else None,
			"overdue_tasks": overdue if has_bl else None,
			# Tasks (no grupo) cuyo forecast excede su pmo_deadline (ADR-0009). No es "vencida".
			"forecast_exceeds": exceeds,
			"planned_hours": flt(planned, 1),
			"actual_hours": flt(actual, 1),
			"hours_consumed_pct": round(actual / planned * 100) if planned else None,
		},
	}


def _schedule_section(project: str, ind: dict) -> dict:
	"""Cronograma para el reporte: tabla de tareas relevantes + milestones + counts + Gantt estático.
	Reutiliza `tasks_vs_baseline` de build_status_report (no recalcula slips)."""
	rows = _annotate(project, ind.get("tasks_vs_baseline") or [])
	relevant = _relevant(rows)
	relevant.sort(key=lambda r: (r["slip_days"] is None, -(r["slip_days"] or 0)))
	milestones = [r for r in rows if r["is_milestone"]]

	counts = _status_counts(project)
	counts["overdue_at_cutoff"] = (ind.get("tasks_overdue_at_cutoff") or {}).get("count")
	return {
		"counts": counts,
		"milestones": milestones,
		"relevant_tasks": relevant,
		"omitted_tasks": len(rows) - len(relevant),
		"total_baseline_tasks": len(rows),
		"gantt": _gantt(project),
	}


def _scope_changes_section(project: str, audience: str) -> dict:
	"""Change Requests del proyecto (ADR-0005). P4: `get_list` respeta la pqc del Change Request.
	`audience="portal"` oculta borradores (Draft); `internal` los incluye. Orden: reciente primero."""
	crs = frappe.get_list(
		"PMO Change Request",
		filters={"project": project},
		fields=[
			"name",
			"title",
			"workflow_state",
			"request_date",
			"priority",
			"impact_summary",
			"baseline_before",
			"baseline_after",
			"impact_hours",
			"impact_days",
			"impact_amount",
			"currency",
		],
		order_by="request_date desc, creation desc",
		limit=0,
	)
	if audience == "portal":
		crs = [c for c in crs if (c.get("workflow_state") or "") != "Draft"]
	return {"change_requests": crs}


# ---------------------------------------------------------------------------
# Composición de cronograma (movida desde print_status: la lógica vive con el builder canónico).
# ---------------------------------------------------------------------------
def _annotate(project: str, rows: list) -> list:
	"""Agrega `is_milestone` y `exceeds_deadline` (forecast > pmo_deadline) a cada fila ADR-0009."""
	names = [r["name"] for r in rows]
	milestone = {}
	if names:
		milestone = {
			t.name: int(t.is_milestone or 0)
			for t in frappe.get_all("Task", filters={"name": ("in", names)}, fields=["name", "is_milestone"])
		}
	for r in rows:
		r["is_milestone"] = milestone.get(r["name"], 0)
		fc, dl = r.get("current_exp_end_date"), r.get("pmo_deadline")
		r["exceeds_deadline"] = bool(fc and dl and getdate(fc) > getdate(dl))
	return rows


def _relevant(rows: list) -> list:
	"""Relevantes para evaluación: vencida al corte, slip != 0, forecast excede deadline, o hito."""
	out = []
	for r in rows:
		slip = r.get("slip_days")
		if (
			r.get("overdue_at_status_date")
			or (slip is not None and slip != 0)
			or r.get("exceeds_deadline")
			or r.get("is_milestone")
		):
			out.append(r)
	return out


def _status_counts(project: str) -> dict:
	"""Conteos compactos de Tasks hoja por macro-estado (para la línea de resumen)."""
	tasks = frappe.get_all("Task", filters={"project": project, "is_group": 0}, fields=["status"])
	total = len(tasks)
	completed = sum(1 for t in tasks if t.status == "Completed")
	active = sum(1 for t in tasks if t.status in _ACTIVE_STATUSES)
	return {"total": total, "completed": completed, "active": active}


def _gantt(project: str) -> dict:
	"""Cronograma estático (barras CSS, orden WBS por `lft`) para el reporte. Sin motor nuevo ni JS.
	P4: el READ del Project ya lo impuso `build_status_report`; `get_list` respeta la pqc de Task."""
	tasks = frappe.get_list(
		"Task",
		filters={"project": project},
		fields=[
			"name",
			"subject",
			"exp_start_date",
			"exp_end_date",
			"progress",
			"is_group",
			"is_milestone",
			"lft",
			"parent_task",
		],
		order_by="lft asc",
		limit=0,
	)
	parent = {t.name: t.parent_task for t in tasks}

	def depth(name, _guard=0):
		p = parent.get(name)
		return 0 if not p or _guard > 50 else 1 + depth(p, _guard + 1)

	starts = [getdate(t.exp_start_date) for t in tasks if t.exp_start_date]
	ends = [getdate(t.exp_end_date) for t in tasks if t.exp_end_date]
	if not starts or not ends:
		return {"tasks": [], "min_start": None, "max_end": None}
	min_start, max_end = min(starts), max(ends)
	span = max((max_end - min_start).days, 1)

	out = []
	for t in tasks:
		row = {
			"name": t.name,
			"subject": t.subject or t.name,
			"depth": depth(t.name),
			"is_group": int(t.is_group or 0),
			"is_milestone": int(t.is_milestone or 0),
			"progress": int(flt(t.progress)),
			"start": str(t.exp_start_date)[:10] if t.exp_start_date else None,
			"end": str(t.exp_end_date)[:10] if t.exp_end_date else None,
			"offset_pct": None,
			"width_pct": None,
		}
		if t.exp_start_date and t.exp_end_date:
			s, e = getdate(t.exp_start_date), getdate(t.exp_end_date)
			row["offset_pct"] = round((s - min_start).days / span * 100, 2)
			row["width_pct"] = round(max(((e - s).days + 1) / span * 100, 1.5), 2)
		out.append(row)
	return {"tasks": out, "min_start": str(min_start), "max_end": str(max_end)}


@frappe.whitelist()
def get_executive_html(project: str, cutoff: str | None = None, audience: str = "internal") -> str:
	"""Endpoint delgado para la Page `PMO Control de Proyecto` (pestaña Reporte Ejecutivo).

	Valida P4 (vía el builder → build_status_report), compone el contexto v1 y renderiza el template
	canónico server-side. La Page solo inyecta el HTML: no recalcula KPIs (ADR-0011 D4)."""
	ctx = build_project_control(project, cutoff=cutoff, audience=audience)
	return frappe.render_template("pmo/templates/project_control/executive.html", {"pc": ctx})
