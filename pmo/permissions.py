# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0 — Aislamiento READ de Project/Task (ADR-0002).

Modelo (fail-closed):
    Project visible si:  owner OR PMO Project Member OR PMO Executive Access
    Task visible si:     project vacío (reglas estándar) OR Project visible
                         OR ToDo activo (asignación directa) OR PMO Executive Access

Enforcement:
- `permission_query_conditions` (listas / report builder / Gantt / Calendar / link / API-list).
- `has_permission` (documento único / URL / get_doc).

Este incremento cubre READ. WRITE y SHARE se refinan en incrementos posteriores; aquí `has_permission`
solo opina sobre lectura (read/select) y difiere el resto a las reglas nativas para no conceder ni
denegar escritura antes de tiempo. Para no-visibles, se deniega por completo (fail-closed).

Notas de compatibilidad:
- `Administrator` e `ignore_permissions`/`get_all` hacen bypass nativo (no protegible).
- `PMO Executive Access` = lectura global (condición vacía).
"""

import frappe

EXECUTIVE_ROLE = "PMO Executive Access"
_READ_PTYPES = ("read", "select", None)


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


def _visible_read(ptype):
	"""Para un documento visible: conceder read/select; diferir el resto a reglas nativas."""
	return True if ptype in _READ_PTYPES else None


def has_permission_project(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _is_global_reader(user):
		return True
	if getattr(doc, "owner", None) == user:
		return _visible_read(ptype)
	if frappe.db.exists(
		"PMO Project Member",
		{"parenttype": "Project", "parentfield": "pmo_members", "parent": doc.name, "member": user},
	):
		return _visible_read(ptype)
	return False  # fail-closed


def has_permission_task(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _is_global_reader(user):
		return True
	project = doc.get("project")
	if not project:
		return None  # Task sin Project: fuera del boundary → reglas estándar
	if (
		frappe.db.exists(
			"PMO Project Member",
			{"parenttype": "Project", "parentfield": "pmo_members", "parent": project, "member": user},
		)
		or frappe.db.get_value("Project", project, "owner") == user
	):
		return _visible_read(ptype)
	if frappe.db.exists(
		"ToDo",
		{
			"reference_type": "Task",
			"reference_name": doc.name,
			"allocated_to": user,
			"status": ("!=", "Cancelled"),
		},
	):
		return _visible_read(ptype)
	return False  # fail-closed
