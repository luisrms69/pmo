# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0 — Aislamiento READ/WRITE de Project/Task (ADR-0002).

Modelo (fail-closed):
    Project visible si:  owner OR PMO Project Member OR PMO Executive Access
    Task visible si:     project vacío (reglas estándar) OR Project visible
                         OR ToDo activo (asignación directa) OR PMO Executive Access
    WRITE Project:       solo owner (member y executive NO).
    WRITE Task:          owner/member del Project o assignee; executive es solo lectura.

Enforcement:
- `permission_query_conditions` (listas / report builder / Gantt / Calendar / link / API-list).
- `has_permission` (documento único / URL / get_doc).

Semántica del controlador `has_permission` en Frappe v16 (verificada): SOLO RESTRINGE — `True` concede
dentro de la capacidad de rol (AND con el DocPerm), `False` deniega, y `None` también deniega. Por eso
`has_permission` devuelve siempre True/False, nunca None. La capacidad read/write la aporta el rol
nativo; aquí definimos el alcance. SHARE se trata en un incremento aparte.

Notas de compatibilidad:
- `Administrator` e `ignore_permissions`/`get_all` hacen bypass nativo (no protegible).
- `PMO Executive Access` = lectura global (condición vacía en pqc; read-only en has_permission).
"""

import frappe

EXECUTIVE_ROLE = "PMO Executive Access"
_WRITE_PTYPES = ("write", "create", "delete", "submit", "cancel", "amend")


def _is_global_reader(user):
	"""True si el usuario NO debe ser restringido (superusuario o acceso ejecutivo)."""
	if user == "Administrator":
		return True
	return EXECUTIVE_ROLE in frappe.get_roles(user)


def _member_projects_subquery(user):
	"""Fragmento SQL: proyectos donde `user` es owner o PMO Project Member."""
	u = frappe.db.escape(user)
	return f"""select p.name from `tabProject` p
		where p.owner = {u}
		or exists (
			select 1 from `tabPMO Project Member` m
			where m.parenttype = 'Project' and m.parentfield = 'pmo_members'
				and m.parent = p.name and m.member = {u}
		)"""


# --- permission_query_conditions ---------------------------------------------


def get_permission_query_conditions_project(user=None):
	user = user or frappe.session.user
	if _is_global_reader(user):
		return ""
	u = frappe.db.escape(user)
	return f"""(`tabProject`.owner = {u} or exists (
		select 1 from `tabPMO Project Member` m
		where m.parenttype = 'Project' and m.parentfield = 'pmo_members'
			and m.parent = `tabProject`.name and m.member = {u}))"""


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


def _is_executive(user):
	return EXECUTIVE_ROLE in frappe.get_roles(user)


def is_project_visible(project, user):
	"""True si `user` puede ver `project` según el boundary de P0 (owner/member/executive/Administrator).

	Reutilizado por el reporte de Capacity Planning para el split P4 (visible vs confidencial). NO
	concede acceso: solo evalúa la misma regla que `has_permission_project` para lectura.
	"""
	if not project:
		return True  # carga sin proyecto → no confidencial
	if user == "Administrator" or _is_global_reader(user):
		return True
	if frappe.db.get_value("Project", project, "owner") == user:
		return True
	return _is_project_member(project, user)


def _is_project_member(project, user):
	return bool(
		frappe.db.exists(
			"PMO Project Member",
			{"parenttype": "Project", "parentfield": "pmo_members", "parent": project, "member": user},
		)
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


def has_permission_project(doc, ptype=None, user=None):
	"""READ: owner/member/executive. WRITE: solo owner (member y executive NO escriben el Project).

	Devuelve siempre True/False (nunca None): en Frappe v16 el controlador `has_permission` solo
	RESTRINGE — `True` concede dentro de la capacidad de rol (AND), `False` deniega, `None` deniega.
	La capacidad read/write la aporta el rol nativo; aquí definimos el alcance.
	"""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	is_owner = getattr(doc, "owner", None) == user
	is_member = _is_project_member(doc.name, user)
	is_exec = _is_executive(user)
	if not (is_owner or is_member or is_exec):
		return False  # fail-closed (todos los ptypes)
	if ptype == "share":
		return is_exec  # SHARE manual: solo Executive (Administrator ya devolvió True arriba)
	if ptype in _WRITE_PTYPES:
		return bool(is_owner)  # solo owner escribe el Project; member/executive → no
	return True  # read + otros ptypes → no restringir (el rol nativo sigue aplicando)


def has_permission_task(doc, ptype=None, user=None):
	"""READ: Project visible o ToDo activo o executive. WRITE: owner/member del Project o assignee;
	executive es solo lectura. Task sin Project: reglas estándar. Siempre True/False (ver Project)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	project = doc.get("project")
	if not project:
		return True  # Task sin Project: fuera del boundary → no restringir (rol nativo aplica)
	is_owner = frappe.db.get_value("Project", project, "owner") == user
	is_member = _is_project_member(project, user)
	is_assignee = _has_active_todo(doc.name, user)
	is_exec = _is_executive(user)
	if not (is_owner or is_member or is_assignee or is_exec):
		return False  # fail-closed
	if ptype == "share":
		return is_exec  # SHARE manual: solo Executive (Administrator ya devolvió True arriba)
	if ptype in _WRITE_PTYPES:
		return bool(is_owner or is_member or is_assignee)  # executive → solo lectura
	return True  # read + otros ptypes → no restringir
