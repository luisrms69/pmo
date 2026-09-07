# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0/P4 — Aislamiento READ/WRITE/SHARE de Project/Task (ADR-0002).

Modelo (fail-closed), **membresía derivada de fuentes nativas** (sin child table propia):
    Equipo del Project = owner + DocShare(Project) + ToDo activo(Task)

    Project visible si:  owner OR DocShare(Project, read) OR PMO Executive Access
    Task visible si:     Project vacío (reglas estándar) OR Project visible
                         OR ToDo activo (asignación directa → SOLO esa Task) OR Executive
    WRITE Project/Task:  owner OR DocShare(Project, write). Assignee (ToDo) → SOLO su Task.
                         Executive es solo lectura.
    SHARE Project:       owner (comparte su propio Project) o Executive/Administrator.
    SHARE Task:          Executive/Administrator (excepcional).

`DocShare` honra sus flags nativos: `read` → leer Project+Tasks; `write` → escribir Project+Tasks
(siempre dentro de la capacidad de rol). `assign_to` NO crea auto-share (la visibilidad del asignado
viene del ToDo). El "equipo del proyecto", si se necesita en UX, se **deriva** de estas fuentes; no se
persiste.

Enforcement: `permission_query_conditions` (listas/report builder/Gantt/calendar/link/API-list) +
`has_permission` (documento único/URL). El controlador `has_permission` v16 SOLO RESTRINGE — `True`
concede dentro de la capacidad de rol (AND con DocPerm), `False`/`None` deniegan; por eso devolvemos
siempre True/False.
"""

import frappe

EXECUTIVE_ROLE = "PMO Executive Access"
_WRITE_PTYPES = ("write", "create", "delete", "submit", "cancel", "amend")


def _is_global_reader(user):
	"""True si el usuario NO debe ser restringido en lectura (superusuario o acceso ejecutivo)."""
	if user == "Administrator":
		return True
	return EXECUTIVE_ROLE in frappe.get_roles(user)


def _is_executive(user):
	return EXECUTIVE_ROLE in frappe.get_roles(user)


# --- fuentes nativas de membresía: DocShare(Project) ---------------------------


def _shared_projects_sql(user, write=False):
	"""Fragmento SQL: Projects con DocShare (read, o write si `write`) para `user` (o everyone)."""
	u = frappe.db.escape(user)
	flag = "`write`" if write else "`read`"
	return f"""select ds.share_name from `tabDocShare` ds
		where ds.share_doctype = 'Project' and ds.{flag} = 1
			and (ds.user = {u} or ds.everyone = 1)"""


def _member_projects_subquery(user):
	"""Projects donde `user` participa para LECTURA: owner OR DocShare(Project, read). La membresía no se
	persiste; se deriva. Reutilizado por las pqc de Project/Task/PMO Project Baseline/PMO Change Request."""
	u = frappe.db.escape(user)
	return f"""select p.name from `tabProject` p where p.owner = {u}
		union {_shared_projects_sql(user, write=False)}"""


def _has_project_share(project, user, write=False):
	"""True si existe un DocShare del Project para `user` (o everyone) con el flag read/write pedido."""
	if not project:
		return False
	flag = "write" if write else "read"
	base = {"share_doctype": "Project", "share_name": project, flag: 1}
	return bool(
		frappe.db.exists("DocShare", {**base, "user": user})
		or frappe.db.exists("DocShare", {**base, "everyone": 1})
	)


def _has_active_todo(task, user):
	return bool(
		frappe.db.exists(
			"ToDo",
			{
				"reference_type": "Task",
				"reference_name": task,
				"allocated_to": user,
				"status": ("!=", "Cancelled"),
			},
		)
	)


# --- permission_query_conditions ---------------------------------------------


def get_permission_query_conditions_project(user=None):
	user = user or frappe.session.user
	if _is_global_reader(user):
		return ""
	return f"`tabProject`.name in ({_member_projects_subquery(user)})"


def get_permission_query_conditions_task(user=None):
	user = user or frappe.session.user
	if _is_global_reader(user):
		return ""
	u = frappe.db.escape(user)
	return f"""(
		(`tabTask`.project is null or `tabTask`.project = '')
		or `tabTask`.project in ({_member_projects_subquery(user)})
		or exists (
			select 1 from `tabToDo` t
			where t.reference_type = 'Task' and t.reference_name = `tabTask`.name
				and t.allocated_to = {u} and t.status != 'Cancelled'
		))"""


# --- has_permission (documento único) ----------------------------------------


def is_project_visible(project, user):
	"""True si `user` puede LEER `project` (owner/DocShare-read/executive/Administrator). Reutilizado por
	los reports de Capacity para el split P4 (visible vs confidencial). NO concede: solo evalúa la regla."""
	if not project:
		return True  # carga sin proyecto → no confidencial
	if user == "Administrator" or _is_global_reader(user):
		return True
	if frappe.db.get_value("Project", project, "owner") == user:
		return True
	return _has_project_share(project, user, write=False)


def is_task_visible(task, user=None):
	"""True si `user` puede LEER la Task de forma CANÓNICA (delega en `frappe.has_permission`, que combina
	capacidad de rol + `has_permission_task` + DocShare + Administrator). Usado por el split P4 del report
	Work by Resource; NO concede acceso."""
	user = user or frappe.session.user
	return bool(frappe.has_permission("Task", ptype="read", doc=task, user=user))


def _is_project_writer(project, user):
	"""True si `user` puede escribir en el alcance del Project: owner OR DocShare(Project, write)."""
	if not project:
		return False
	if frappe.db.get_value("Project", project, "owner") == user:
		return True
	return _has_project_share(project, user, write=True)


def has_permission_project(doc, ptype=None, user=None):
	"""READ: owner/DocShare-read/executive. WRITE: owner o DocShare(write) (D6, honra flag). SHARE: owner o
	executive (D7: owner comparte su propio Project). Siempre True/False (el hook v16 solo restringe)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	is_owner = getattr(doc, "owner", None) == user
	if ptype == "share":
		return bool(is_owner or _is_executive(user))
	if ptype in _WRITE_PTYPES:
		# create: `is_owner` True por defecto (owner = creador). write/…: owner o DocShare(write).
		return bool(is_owner or _has_project_share(doc.name, user, write=True))
	return is_project_visible(doc.name, user)  # read + otros ptypes de lectura


def has_permission_task(doc, ptype=None, user=None):
	"""READ: Project visible o ToDo activo o executive. WRITE: owner del Project, DocShare(Project, write) o
	assignee (SOLO su Task); executive es read-only. SHARE: executive/Admin (excepcional). Task sin Project:
	reglas estándar. Siempre True/False."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	project = doc.get("project")
	if not project:
		return True  # Task sin Project: fuera del boundary → no restringir (rol nativo aplica)
	if ptype == "share":
		return _is_executive(user)
	is_assignee = _has_active_todo(doc.name, user)
	if ptype in _WRITE_PTYPES:
		is_owner = frappe.db.get_value("Project", project, "owner") == user
		return bool(is_owner or is_assignee or _has_project_share(project, user, write=True))
	return bool(is_project_visible(project, user) or is_assignee)  # read


# --- PMO Project Baseline (ADR-0004 D7): P4 heredado del Project -----------------


def get_permission_query_conditions_baseline(user=None):
	"""Listados: solo baselines cuyo Project es visible (owner/DocShare-read). Executive/Admin: sin condición."""
	user = user or frappe.session.user
	if _is_global_reader(user):
		return ""
	return f"`tabPMO Project Baseline`.project in ({_member_projects_subquery(user)})"


def has_permission_baseline(doc, ptype=None, user=None):
	"""READ del Baseline = visibilidad del Project. WRITE/SUBMIT/CANCEL/etc. = solo el owner del Project
	(gobernanza; Executive read-only; SHARE denegado). Siempre True/False."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	project = doc.get("project") if hasattr(doc, "get") else getattr(doc, "project", None)
	if not project:
		return False  # fail-closed: una baseline sin Project no es visible
	if ptype == "share":
		return False
	if ptype in _WRITE_PTYPES:
		return frappe.db.get_value("Project", project, "owner") == user
	return is_project_visible(project, user)  # read y demas ptypes de lectura


# --- PMO Change Request (ADR-0005 D13): P4 heredado del Project ------------------


def get_permission_query_conditions_change_request(user=None):
	"""Listados: solo CR cuyo Project es visible (owner/DocShare-read). Executive/Admin: sin condición."""
	user = user or frappe.session.user
	if _is_global_reader(user):
		return ""
	return f"`tabPMO Change Request`.project in ({_member_projects_subquery(user)})"


def has_permission_change_request(doc, ptype=None, user=None):
	"""READ = visibilidad del Project. CREATE/WRITE = project writer (owner o DocShare-write); el WRITE de
	un no-owner solo mientras el CR es editable (`docstatus == 0`) — tras aprobar, solo el owner escribe.
	SUBMIT/CANCEL/AMEND = solo el owner (sella owner-only para aprobar/rechazar). Executive read-only;
	SHARE denegado. Siempre True/False."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	project = doc.get("project") if hasattr(doc, "get") else getattr(doc, "project", None)
	if not project:
		return False  # fail-closed
	if ptype == "share":
		return False
	is_owner = frappe.db.get_value("Project", project, "owner") == user
	if ptype in ("submit", "cancel", "amend"):
		return bool(is_owner)  # aprobar/rechazar/aplicar/cerrar: owner-only
	if ptype in ("write", "create", "delete"):
		if is_owner:
			return True
		if int(getattr(doc, "docstatus", 0) or 0) == 0:
			return _is_project_writer(project, user)  # owner o DocShare(write) del Project
		return False
	return is_project_visible(project, user)  # read
