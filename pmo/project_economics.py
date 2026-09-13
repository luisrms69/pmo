# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Frontera económica de PMO hacia `erpnext_proposals` (opcional) + decisión única de acceso económico.

Principios (ADR-0011 + privacidad P4):
- PMO **no** reproduce fórmulas económicas: consume el contrato canónico
  `erpnext_proposals…project_economics.get_project_authorized_economics(project)` tal cual.
- Acoplamiento **lazy** y opcional: `erpnext_proposals` NO es `required_app`; si no está instalada, el
  autorizado simplemente "no disponible".
- Acceso económico = **una sola** decisión server-side (`can_see_project_economics`): READ efectivo del
  Project **AND** rol económico. No basta READ/DocShare; se aplica ANTES de componer economía, nunca en
  JS/template/Print Format.
- Tres estados diferenciados; una inconsistencia real **no** se degrada a ausencia."""

import frappe

# Única lista de roles con acceso económico. `Projects Manager` (nativo, demasiado amplio) NO se incluye.
ECONOMIC_ROLES = ("PMO Manager", "PMO Executive Access", "System Manager")


def can_see_project_economics(project: str, user: str | None = None) -> bool:
	"""Decisión única de autorización económica: **rol económico AND READ efectivo del Project**.

	No basta con poder leer el Project (READ por owner/DocShare/Task no concede economía). Portal y accesos
	operativos por Task/DocShare quedan fuera. Se evalúa server-side antes de cargar cualquier dato económico."""
	user = user or frappe.session.user
	if not set(frappe.get_roles(user)) & set(ECONOMIC_ROLES):
		return False
	return bool(frappe.has_permission("Project", ptype="read", doc=project, user=user))


def _has_linked_quotation(project: str) -> bool:
	"""¿Existe CUALQUIER Quotation asociada al Project por `proposal_project`? (independiente de estado).

	`no_proposal` = ausencia REAL de asociación. Si existe alguna asociación (aunque esté en estado inválido,
	superseded, root ambiguo, etc.), NO se decide aquí: se llama al contrato canónico, y si falla → `inconsistent`.
	No filtrar por `Ganada`/`docstatus`: eso escondería una asociación rota como si no hubiera propuesta."""
	return bool(frappe.db.exists("Quotation", {"proposal_project": project}))


def _authorized_from_proposals(project: str) -> dict:
	"""Único punto de acoplamiento con `erpnext_proposals` (import lazy; mockeable en tests)."""
	from erpnext_proposals.erpnext_proposals.utils.project_economics import (
		get_project_authorized_economics,
	)

	return get_project_authorized_economics(project)


def get_authorized_economics(project: str) -> dict:
	"""Frontera opcional al contrato autorizado. **No** chequea permiso (el caller gatea antes con
	`can_see_project_economics`). Devuelve `{available, reason, data}` con TRES estados diferenciados:

	- `reason="app_absent"`: `erpnext_proposals` no instalado → autorizado no disponible (los reales
	  nativos de ERPNext sí pueden mostrarse aparte).
	- `reason="no_proposal"`: app instalada pero el Project no tiene propuesta raíz Ganada vinculada
	  (estado válido → "sin referencia autorizada"; autorizado = None/—, nunca 0; sin usar estimated_costing).
	- `reason="inconsistent"`: la propuesta EXISTE pero el contrato falla (snapshot incompleto, root
	  ambigua, moneda ≠ base). Es una inconsistencia real: se marca explícitamente y se registra; **no** se
	  degrada silenciosamente a ausencia.
	- éxito: `available=True`, `data` = contrato canónico completo (sin financiamiento)."""
	if "erpnext_proposals" not in frappe.get_installed_apps():
		return {"available": False, "reason": "app_absent", "data": None, "message": None}
	if not _has_linked_quotation(project):
		return {"available": False, "reason": "no_proposal", "data": None, "message": None}
	# Existe asociación: SIEMPRE se consulta el contrato canónico (resuelve root/superseded/estado/moneda).
	try:
		data = _authorized_from_proposals(project)
	except Exception as e:
		# Asociación presente pero contrato fallido = inconsistencia real (NO ausencia). No se silencia ni
		# se degrada a no_proposal. El detalle técnico va SOLO al logger; a la UI, un mensaje estable/traducible.
		frappe.logger("pmo").warning(f"economía autorizada inconsistente para {project}: {e}")
		return {
			"available": False,
			"reason": "inconsistent",
			"data": None,
			# Mensaje funcional ESTABLE/traducible (sin exponer excepción, SQL ni datos de Quotation).
			"message": frappe._(
				"Authorized economics unavailable: the linked proposal data is inconsistent."
			),
		}
	return {"available": True, "reason": None, "data": data, "message": None}
