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
from pmo.project_economics import can_see_project_economics, get_authorized_economics
from pmo.status_date import build_status_report

SECTION_PROJECT = "project"
SECTION_EXECUTIVE = "executive"
SECTION_SCHEDULE = "schedule"
SECTION_PLANNING = "planning"
SECTION_SCOPE_CHANGES = "scope_changes"
# Económica: NO forma parte de DEFAULT_SECTIONS. Solo la solicita la Page (get_executive_html), nunca el
# Print Format/PDF (Q2: la economía no viaja en un documento potencialmente compartible). Además el gate
# económico se aplica antes de componerla.
SECTION_COSTS = "costs"
DEFAULT_SECTIONS = (
	SECTION_PROJECT,
	SECTION_EXECUTIVE,
	SECTION_SCHEDULE,
	SECTION_PLANNING,
	SECTION_SCOPE_CHANGES,
)

_ACTIVE_STATUSES = ("Open", "Working", "Pending Review", "Overdue")
# "Sin responsable" se evalúa sobre tareas activas: hoja y no terminadas/canceladas (una Completed sin
# asignación NO es un problema de asignación actual). Responsable vigente = ToDo abierto (Frappe: Open =
# asignación vigente; Closed = completada; Cancelled = desasignada). Ver _assigned_task_names.
_INACTIVE_STATUSES = ("Completed", "Cancelled")

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
	N_("Planning quality"),
	N_("Planning Maturity"),
	N_("With owner"),
	N_("With start date"),
	N_("With end date"),
	N_("With estimate"),
	N_("In current baseline"),
	N_("Unassigned active tasks"),
	N_("Not evaluable (no baseline in effect)"),
	N_("{0} active task(s) without owner"),
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
	# Bloque económico (BLOQUE 3). El mensaje de inconsistencia se traduce en runtime en project_economics.
	N_("Project economics (current)"),
	N_("No authorized reference (project without linked proposal)."),
	N_("Revenue — authorized"),
	N_("Revenue — ordered"),
	N_("Revenue — billed"),
	N_("Cost — authorized"),
	N_("Cost — registered"),
	N_("material"),
	N_("gross margin basis"),
	N_("Margin — authorized"),
	N_("Gross margin — registered"),
	N_("Changes:"),
	N_("applied"),
	N_("pending"),
	N_("Authorized economics unavailable: the linked proposal data is inconsistent."),
	N_("Authorized reference unavailable."),
	# Vista financiera de detalle (BLOQUE 4).
	N_("Financial"),
	N_("You do not have economic access to this project."),
	N_("Economic state:"),
	N_("current"),
	N_("Contract"),
	N_("Original"),
	N_("Applied changes"),
	N_("Authorized (current)"),
	N_("Contract revenue"),  # pmo-propio: evita heredar "Revenue"→"Ganancia" (utilidad) de erpnext
	N_("Cost"),
	N_("Labor"),
	N_("External"),
	N_("Margin"),
	N_("Margin %"),
	N_("Revenues"),
	N_("Authorized"),
	N_("Ordered (Sales Orders)"),  # pmo-propio: evita "Ordered"→"Ordenado/a"
	N_("Billed"),
	N_("Costs"),
	N_("Authorized (total)"),
	N_("Authorized labor"),
	N_("Authorized external"),
	N_("Timesheets (registered labor)"),
	N_("Purchases (registered external)"),
	N_("Registered comparable cost"),
	N_("Material"),
	N_("part of ERPNext gross margin basis; not part of the comparable contractual cost."),
	N_("Margins"),
	N_("Authorized margin"),
	N_("Authorized margin %"),
	N_("Registered gross margin"),
	N_("Registered gross margin %"),
	N_("Changes"),
	N_("Revenue impact (applied)"),
	N_("Cost impact (applied)"),
	N_("Margin impact (applied)"),
	N_("Applied addenda"),
	N_("Pending changes"),
	N_("Proposal group"),  # pmo-propio: evita "Group"→"Agrupar"
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
	if SECTION_PLANNING in wanted:
		ctx[SECTION_PLANNING] = _planning_section(project, sr)
	if SECTION_SCOPE_CHANGES in wanted:
		ctx[SECTION_SCOPE_CHANGES] = _scope_changes_section(project, audience)
	# Económica: SOLO audience interno + gate económico único (rol + READ). Si no pasa, `costs` NO se
	# compone ni aparece en el payload (nunca llega a template/JS/PDF). El gate va ANTES de componer.
	if SECTION_COSTS in wanted and audience == "internal" and can_see_project_economics(project):
		ctx[SECTION_COSTS] = _costs_section(project)
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


_NATIVE_COST_FIELDS = (
	"company",
	"total_sales_amount",
	"total_billed_amount",
	"total_costing_amount",
	"total_purchase_cost",
	"total_consumed_material_cost",
	"gross_margin",
	"per_gross_margin",
)


def _costs_section(project: str) -> dict:
	"""Economía (estado ACTUAL, separado del cutoff). Compone, NO calcula: autorizado desde el contrato
	canónico de erpnext_proposals (frontera `get_authorized_economics`), reales desde campos nativos de
	Project (`update_costing`). Sin propuesta → `authorized=None/—` (nunca 0; sin usar estimated_costing).

	`real_cost_native` = EXACTAMENTE la base del `gross_margin` nativo (costing + purchase + material), como
	presentación derivada de campos nativos (no una autoridad nueva). El gate económico ya se aplicó en el
	caller; esta función asume acceso concedido."""
	econ = get_authorized_economics(project)  # {available, reason, data, message}
	data = econ.get("data") or {}
	# Conteos derivados de las listas del contrato (presentación; no reimplementa economía).
	applied_count = len([q for q in (data.get("quotations") or []) if q.get("role") == "applied_change"])
	pending_count = len(data.get("pending_changes") or [])
	nat = frappe.db.get_value("Project", project, _NATIVE_COST_FIELDS, as_dict=True) or frappe._dict()
	costing = flt(nat.get("total_costing_amount"))
	purchase = flt(nat.get("total_purchase_cost"))
	material = flt(nat.get("total_consumed_material_cost"))
	base_currency = (
		frappe.db.get_value("Company", nat.get("company"), "default_currency") if nat.get("company") else None
	)
	return {
		"as_of": "current",  # NO gobernado por cutoff: los totales nativos no tienen snapshot histórico
		"authorized_available": econ["available"],
		"authorized_reason": econ["reason"],  # None | app_absent | no_proposal | inconsistent
		"authorized_message": econ.get("message"),  # estable/traducible (solo si inconsistent)
		"authorized": econ["data"],  # contrato canónico completo, o None (nunca 0) si no disponible
		"commercial": {
			"total_sales_amount": flt(nat.get("total_sales_amount")),
			"total_billed_amount": flt(nat.get("total_billed_amount")),
		},
		"real_cost": {
			"costing": costing,  # labor real (Timesheet) = total_costing_amount
			"purchase": purchase,  # externo real (Purchase Invoice) = total_purchase_cost
			"material": material,  # consumo de stock; excepción/componente adicional, NO parte del comparable
			# Costo real COMPARABLE contra authorized_cost (proceso: labor + externo vía OC→PI). Excluye material.
			"comparable_cost": flt(costing + purchase, 2),
			# Base del gross_margin NATIVO de ERPNext (incluye material). No se usa para comparar con autorizado.
			"gross_margin_cost_basis": flt(costing + purchase + material, 2),
		},
		"native_margin": {
			"gross_margin": flt(nat.get("gross_margin")),
			"per_gross_margin": flt(nat.get("per_gross_margin")),
		},
		"changes": {
			"applied_count": applied_count,
			"pending_count": pending_count,
		},  # compacto (sin listar Quotations)
		"currency": (econ["data"] or {}).get("currency"),  # autorizado; == base cuando hay contrato
		"base_currency": base_currency,  # moneda de los reales nativos
	}


def _assigned_task_names(names: list) -> set:
	"""Conjunto de Tasks (de `names`) CON responsable **vigente** = ToDo **abierto** (`status == "Open"`).

	Semántica nativa de asignación de Frappe: al asignar se crea un ToDo Open; al completar la asignación
	pasa a Closed; al desasignar, a Cancelled. Para "¿quién es responsable AHORA?" solo cuenta la asignación
	**abierta**. (Deliberadamente **más estricto** que el canónico de *visibilidad* `_has_active_todo`
	—`status != Cancelled`, que incluye Closed para conservar el acceso de lectura—: aquí no es acceso, es
	responsabilidad vigente.) No se inventa campo `responsible`. Una sola consulta para todo el proyecto."""
	if not names:
		return set()
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Task", "reference_name": ("in", names), "status": "Open"},
		fields=["reference_name"],
		limit=0,
	)
	return {t.reference_name for t in todos}


def _planning_section(project: str, sr: dict) -> dict:
	"""Calidad de Planeación (ADR-0011 v1): Planning Maturity (5 componentes) + tareas activas sin
	responsable. Todo sobre tareas HOJA (is_group=0). Ausencia de dato → None (no cero engañoso).

	Denominadores (explícitos):
	- Componentes 1-4 (responsable / inicio / fin / estimacion): TODAS las tareas hoja (incluye Completed;
	  miden completitud del plan completo). None si no hay tareas hoja.
	- Componente 5 (en baseline): tareas hoja actuales; numerador = las presentes en la baseline vigente al
	  corte. **None si no hay baseline vigente.** Las tareas creadas DESPUÉS de la baseline no están en su
	  snapshot → cuentan en el denominador pero no en el numerador (bajan la cobertura: señal de drift).
	Planning Maturity = promedio simple de los componentes **evaluables** (no None); None si ninguno lo es.
	Alerta "sin responsable": tareas hoja **activas** (status ∉ {Completed, Cancelled}) sin ToDo activo."""
	leaves = frappe.get_list(
		"Task",
		filters={"project": project, "is_group": 0},
		fields=["name", "subject", "status", "exp_start_date", "exp_end_date", "expected_time"],
		limit=0,
	)
	total = len(leaves)
	empty_components = {
		"with_responsible_pct": None,
		"with_start_pct": None,
		"with_end_pct": None,
		"with_estimate_pct": None,
		"in_baseline_pct": None,
	}
	if not total:
		return {"maturity_pct": None, "components": empty_components, "unassigned": {"count": 0, "tasks": []}}

	assigned = _assigned_task_names([t.name for t in leaves])

	def pct(n):
		return round(n / total * 100)

	# Componente 5: cobertura de baseline vigente al corte (None si no hay baseline).
	in_baseline_pct = None
	if sr.get("baseline"):
		snap = frappe.parse_json(
			frappe.db.get_value("PMO Project Baseline", sr["baseline"]["name"], "snapshot") or "{}"
		)
		bl_names = {t.get("name") for t in (snap.get("tasks") or [])}
		in_baseline_pct = pct(sum(1 for t in leaves if t.name in bl_names))

	components = {
		"with_responsible_pct": pct(sum(1 for t in leaves if t.name in assigned)),
		"with_start_pct": pct(sum(1 for t in leaves if t.exp_start_date)),
		"with_end_pct": pct(sum(1 for t in leaves if t.exp_end_date)),
		"with_estimate_pct": pct(sum(1 for t in leaves if flt(t.expected_time) > 0)),
		"in_baseline_pct": in_baseline_pct,
	}
	evaluable = [v for v in components.values() if v is not None]
	maturity = round(sum(evaluable) / len(evaluable)) if evaluable else None

	unassigned = [
		{"name": t.name, "subject": t.subject}
		for t in leaves
		if t.status not in _INACTIVE_STATUSES and t.name not in assigned
	]
	return {
		"maturity_pct": maturity,
		"components": components,
		"unassigned": {"count": len(unassigned), "tasks": unassigned},
	}


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
	canónico server-side. La Page solo inyecta el HTML: no recalcula KPIs (ADR-0011 D4).

	Solicita además la sección económica (`costs`): el builder la compone solo si audience=interno y el
	usuario pasa el gate económico (rol + READ). El Print Format NO la solicita (Q2)."""
	ctx = build_project_control(
		project, cutoff=cutoff, audience=audience, sections=[*DEFAULT_SECTIONS, SECTION_COSTS]
	)
	return frappe.render_template("pmo/templates/project_control/executive.html", {"pc": ctx})


@frappe.whitelist()
def get_financial_html(project: str, cutoff: str | None = None) -> str:
	"""Endpoint específico de la Page (pestaña Financiera). Reutiliza `build_project_control` (P4 vía
	build_status_report + gate económico único) y `pc.costs`; NO consulta economía ni llama a
	erpnext_proposals fuera de la frontera. Solo `project` + `costs` (no necesita el resto del reporte).
	Si el usuario no pasa el gate económico, `costs` no se compone y el template muestra "sin acceso".
	No es un endpoint JSON genérico: devuelve HTML server-side de ESTA vista, gobernado por el mismo gate."""
	ctx = build_project_control(
		project, cutoff=cutoff, audience="internal", sections=[SECTION_PROJECT, SECTION_COSTS]
	)
	return frappe.render_template("pmo/templates/project_control/financial.html", {"pc": ctx})
