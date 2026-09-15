# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Integración de Change Control con `erpnext_proposals` (ADR-0005).

Frontera dura: `pmo` **no** reproduce ni puentea la lógica de `erpnext_proposals`. Delega en su contrato
publicado (>= 0.22.0):

- `create_addendum_quotation(root_quotation) -> str` (`utils.addendum`): crea ATÓMICAMENTE la siguiente
  addenda `ROOT-ADD-NN` (delta comercial) a partir de una Quotation del contrato; resuelve el root, calcula
  la secuencia y exige **autoría comercial** (`assert_can_manage_proposals`). `pmo` NO interpreta
  `<ROOT>-ADD-<NN>`, NO calcula secuencia, NO crea `proposal_group`.
- `apply_addendum_to_project(quotation, project) -> dict` (`utils.project`): valida (Ganada, docstatus,
  superseded, single-live, customer/company), **escribe `proposal_project`** y anexa los Scope Items como
  Tasks (reuse + dedup). `pmo` NUNCA escribe `proposal_project` ni copia esos guards.

Ambos se resuelven por `frappe.get_attr` (feature-detection): si el entorno tiene una versión de
`erpnext_proposals` sin el contrato (< 0.22.0) o el app no está instalado, se lanza un error claro. `pmo`
no eleva permisos ni hace bypass: la autoría comercial la impone `erpnext_proposals`.
"""

import frappe
from frappe import _

# Contrato publicado en erpnext_proposals (>= 0.22.0; live-version resolver desde 0.24.0).
_ADDENDUM_APPLIER = "erpnext_proposals.erpnext_proposals.utils.project.apply_addendum_to_project"
_ADDENDUM_CREATOR = "erpnext_proposals.erpnext_proposals.utils.addendum.create_addendum_quotation"
_LIVE_RESOLVER = "erpnext_proposals.erpnext_proposals.utils.proposal_versioning.get_live_proposal_for_group"
_FINGERPRINT = "erpnext_proposals.erpnext_proposals.utils.addendum.get_addendum_delta_fingerprint"


def _resolve(path, contrato):
	"""Resuelve un contrato de erpnext_proposals por dotted-path; error claro si no está disponible."""
	try:
		return frappe.get_attr(path)
	except Exception:
		frappe.throw(
			_(
				"The erpnext_proposals integration is not available: contract {0} is missing. Requires erpnext_proposals >= 0.22.0 installed on the site."
			).format(contrato)
		)


def create_addendum_quotation(root_quotation: str) -> str:
	"""Delega en `erpnext_proposals` la creación de la siguiente addenda `ROOT-ADD-NN`. Devuelve el `name`
	de la nueva Quotation. La autoría comercial (`Proposals Manager`/`System Manager`) la valida
	`erpnext_proposals`; `pmo` no eleva permisos."""
	fn = _resolve(_ADDENDUM_CREATOR, "create_addendum_quotation(root_quotation)")
	return fn(root_quotation)


def apply_addendum_to_project(quotation: str, project: str):
	"""Delega en el contrato de `erpnext_proposals` la aplicación del addendum al Project existente. Devuelve
	el resumen del append. NO valida reglas comerciales ni escribe `proposal_project`."""
	fn = _resolve(_ADDENDUM_APPLIER, "apply_addendum_to_project(quotation, project)")
	return fn(quotation, project)


def get_live_proposal_for_group(proposal_group: str) -> str | None:
	"""Resuelve la **versión viva** (no superseded, no estado muerto, docstatus != 2) del `proposal_group`,
	delegando en `erpnext_proposals` (>= 0.24.0). **Único punto de PMO** que consume este helper interno de
	`erpnext_proposals`: el resto de `pmo` NO debe importarlo directamente (frontera de contrato). `pmo` NO
	parsea `ROOT-ADD-NN` ni resuelve versiones por su cuenta; sobre el resultado, quien llame impone la
	aserción de estado que necesite (`En Revisión` para aprobar; `Ganada` para aplicar — B5/B6)."""
	fn = _resolve(_LIVE_RESOLVER, "get_live_proposal_for_group(proposal_group)")
	return fn(proposal_group)


def get_addendum_delta_fingerprint(quotation: str) -> str:
	"""Delega en `erpnext_proposals` (>= 0.24.0) la huella canónica del delta SEMÁNTICO congelado de una
	addenda formal (ADR-0019 §7.2). `pmo` NO reimplementa la huella: la consume. Fail-closed: `erpnext_proposals`
	lanza si la addenda no es formal/congelada; `pmo` propaga el error (guarda solo huellas válidas)."""
	fn = _resolve(_FINGERPRINT, "get_addendum_delta_fingerprint(quotation)")
	return fn(quotation)
