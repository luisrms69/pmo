# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Gobernanza — enforcement server-side de la EXCLUSIÓN de gobernanza sobre el Project nativo.

Decisión funcional (Gobernanza V1): un Project puede declararse explícitamente NO sujeto a gobernanza PMO
(`pmo_governance_exempt`). Es una decisión deliberada, justificada (motivo obligatorio) y auditable (quién
autorizó + cuándo). Reglas duras:

- El PM (Projects User) **no** puede autoexcluir su proyecto: cambiar la exclusión o su motivo exige rol
  **PMO Manager** o **System Manager**. Se valida en el servidor (no se confía en el cliente).
- Los campos de auditoría (`pmo_exempt_by`, `pmo_exempt_on`) se fijan **server-side**; se ignora cualquier
  valor enviado por el cliente.
- Al volver de excluido → sujeto, se limpian los campos de exclusión. La trazabilidad histórica queda en el
  registro nativo de **Version** de Frappe (Project es track_changes); no se construye un historial paralelo.

No crea DocType, workflow, scheduler ni política. Solo un `validate` sobre Project (hook existente).
"""

import frappe
from frappe.utils import cint, now_datetime

# Autoridad para excluir un proyecto de gobernanza (modelo de roles existente; sin cambios de permisos).
GOVERNANCE_EXEMPTION_ROLES = ("PMO Manager", "System Manager")


def _has_exemption_authority(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & set(GOVERNANCE_EXEMPTION_ROLES))


def guard_governance_exemption(doc, method=None):
	"""`validate` de Project: gobierna la exclusión de gobernanza. Enforcement de autoridad + auditoría
	server-side. No toca ningún otro campo del Project ni el core."""
	before = doc.get_doc_before_save()  # None en alta
	new_exempt = cint(doc.get("pmo_governance_exempt"))
	old_exempt = cint(before.get("pmo_governance_exempt")) if before else 0
	old_reason = (before.get("pmo_exempt_reason") or "") if before else ""
	new_reason = doc.get("pmo_exempt_reason") or ""

	# ¿Este save intenta CAMBIAR la decisión de exclusión (toggle) o su motivo mientras está excluido?
	decision_changed = (new_exempt != old_exempt) or (new_exempt and new_reason != old_reason)

	if decision_changed and not _has_exemption_authority():
		frappe.throw(
			frappe._(
				"Only a PMO Manager (or System Manager) can change a project's PMO governance exemption. "
				"A Project Manager cannot exempt their own project."
			),
			frappe.PermissionError,
		)

	# Motivo obligatorio server-side al excluir (además del `mandatory_depends_on` de la UI): la exclusión
	# debe quedar justificada. Se refuerza aquí para no depender solo del check de mandatorio del framework.
	if new_exempt and not (new_reason and new_reason.strip()):
		frappe.throw(
			frappe._("Provide a reason to exclude this project from PMO governance."),
			frappe.MandatoryError,
		)

	# Auditoría server-side (nunca se confía en el cliente).
	if new_exempt:
		if not old_exempt:
			# Recién excluido: sella autor + fecha.
			doc.pmo_exempt_by = frappe.session.user
			doc.pmo_exempt_on = now_datetime()
		else:
			# Ya estaba excluido: conserva el sello original (no se sobreescribe por un save posterior).
			if before:
				doc.pmo_exempt_by = before.get("pmo_exempt_by")
				doc.pmo_exempt_on = before.get("pmo_exempt_on")
	else:
		# Sujeto a gobernanza: limpia los campos de exclusión (Version conserva el histórico).
		doc.pmo_exempt_by = None
		doc.pmo_exempt_on = None
		doc.pmo_exempt_reason = None


def is_governance_exempt(project: str) -> bool:
	"""¿El Project está explícitamente excluido de gobernanza? Fuente única para el motor de desviaciones."""
	return bool(cint(frappe.db.get_value("Project", project, "pmo_governance_exempt")))
