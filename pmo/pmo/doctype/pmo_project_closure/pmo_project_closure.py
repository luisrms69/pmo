# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Closure (ADR-0014 D4/D11) — cierre formal del Project.

Submittable + track_changes. Al emitir se **congela** evidencia canonica con hash (patron Baseline):

- Evidencia NO economica (cronograma/esfuerzo/cambios) → se **compone desde `build_project_control`**
  (cutoff=closure_date), no se recalcula (ADR-0014 D4). Se guarda en `snapshot` (permlevel 0, legible con
  READ del Project).
- Evidencia economica → se congela por la **frontera canonica** `get_authorized_economics` + totales nativos.
  Se guarda en `economics_snapshot` con **permlevel 1**: solo la leen los roles economicos (PMO Manager/
  Executive Access/System Manager) que ya pasan el gate `can_see_project_economics`. Un `Projects User` con
  READ del Project NO puede leerla. No se debilita P4 ni se crea una segunda politica economica.

Semantica temporal (ADR-0014 D4): cronograma/esfuerzo son **al corte `closure_date`** (build_status_report);
la economia nativa NO tiene snapshot historico, por lo que se congela como **`current_at_issuance`** (estado
al momento de emitir), nunca etiquetada como historica a `closure_date`.

El Print Format se reconstruye SOLO desde estos snapshots congelados, nunca desde datos vivos. Autosuficiente
(sin Risk); no toca PHI.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, today

from pmo.baseline import canonical_json, snapshot_hash
from pmo.governance import count_open_change_requests, derive_lifecycle_state
from pmo.project_control import (
	SECTION_EXECUTIVE,
	SECTION_PROJECT,
	SECTION_SCOPE_CHANGES,
	build_project_control,
)
from pmo.project_economics import can_see_project_economics, get_authorized_economics

CLOSURE_SNAPSHOT_SCHEMA_VERSION = 1
_TERMINAL_STATUSES = ("Completed", "Cancelled")

# Checklist de cierre (checks de confirmación; todos requeridos para emitir). Mapeo estable
# campo del DocType -> clave del snapshot congelado (la evidencia queda cubierta por snapshot_hash).
CLOSURE_CHECKLIST_SNAPSHOT_KEYS = (
	("chk_pending_items", "pending_items_resolved_or_transferred"),
	("chk_ops_handover", "operations_support_handover_completed"),
	("chk_contractual_legal", "contractual_legal_obligations_reviewed"),
	("chk_admin_financial", "administrative_financial_close_reviewed"),
	("chk_documentation", "project_documentation_completed"),
	("chk_communicated", "closure_communicated_to_stakeholders"),
	("chk_resources_released", "resources_released_reassigned"),
)
CLOSURE_CHECKLIST_FIELDS = tuple(field for field, _key in CLOSURE_CHECKLIST_SNAPSHOT_KEYS)

_NATIVE_COST_FIELDS = (
	"total_sales_amount",
	"total_billed_amount",
	"total_costing_amount",
	"total_purchase_cost",
	"gross_margin",
	"per_gross_margin",
)


def build_closure_snapshot(project: str, closing_date: str, checklist: dict | None = None) -> dict:
	"""Evidencia NO economica al corte `closure_date`, **compuesta desde build_project_control** (D4).

	`checklist` = confirmaciones de cierre (7 booleanos con claves estables) tomadas del Closure al emitir;
	quedan **dentro del snapshot canonico** y por tanto cubiertas por `snapshot_hash` (evidencia congelada,
	ADR-0014 D4/D11). No es una segunda captura: son los mismos campos `chk_*` del documento."""
	pc = build_project_control(
		project,
		cutoff=closing_date,
		audience="internal",
		sections=[SECTION_PROJECT, SECTION_EXECUTIVE, SECTION_SCOPE_CHANGES],
	)
	proj = pc.get("project") or {}
	kpis = (pc.get("executive") or {}).get("kpis") or {}
	crs = (pc.get("scope_changes") or {}).get("change_requests") or []
	return {
		"snapshot_schema_version": CLOSURE_SNAPSHOT_SCHEMA_VERSION,
		"closing_date": str(closing_date),
		"lifecycle_state_at_closure": derive_lifecycle_state(project),
		"closure_checklist": checklist or {},
		"schedule": {
			"as_of": "closure_date",
			"baseline_end": proj.get("baseline_end"),
			"committed_end": proj.get("committed_end"),
			"forecast_end": proj.get("forecast_end"),
			"slip_vs_baseline_days": kpis.get("slip_baseline_days"),
			"slip_vs_committed_days": kpis.get("slip_committed_days"),
			"overdue_at_cutoff": kpis.get("overdue_tasks"),
		},
		"effort": {
			"as_of": "closure_date",
			"planned_hours": kpis.get("planned_hours"),
			"actual_hours": kpis.get("actual_hours"),
			"percent_complete": kpis.get("percent_complete"),
		},
		"changes": {"total": len(crs)},
	}


def build_closure_economics(project: str, user: str | None = None) -> dict:
	"""Evidencia economica congelada por la frontera canonica. Semantica `current_at_issuance` (los totales
	nativos no tienen snapshot historico; no se inventa historico a closure_date). Se persiste en un campo
	con permlevel 1 (gate economico).

	Respeta la frontera de `pmo/project_economics`: el gate `can_see_project_economics` se aplica ANTES de
	cargar cualquier dato economico (get_authorized_economics presupone al caller ya gateado). Si el emisor
	NO pasa el gate, NO se cargan cifras: se congela un marcador `captured=False` (sin segunda politica ni
	excepcion silenciosa). Para congelar evidencia economica completa, el Closure debe emitirlo un usuario con
	rol economico + READ del Project."""
	if not can_see_project_economics(project, user):
		return {
			"snapshot_schema_version": CLOSURE_SNAPSHOT_SCHEMA_VERSION,
			"as_of": "current_at_issuance",
			"captured": False,
			"reason": "economic_gate_not_passed",
		}
	econ = get_authorized_economics(project)
	edata = econ.get("data") or {}
	native = frappe.db.get_value("Project", project, _NATIVE_COST_FIELDS, as_dict=True) or frappe._dict()
	costing = flt(native.get("total_costing_amount"))
	purchase = flt(native.get("total_purchase_cost"))
	return {
		"snapshot_schema_version": CLOSURE_SNAPSHOT_SCHEMA_VERSION,
		"as_of": "current_at_issuance",
		"captured": True,
		"authorized_available": econ.get("available"),
		"authorized_reason": econ.get("reason"),
		"authorized_revenue": edata.get("authorized_revenue"),
		"authorized_cost": edata.get("authorized_cost"),
		"authorized_margin": edata.get("authorized_margin"),
		"currency": edata.get("currency"),
		"total_sales_amount": flt(native.get("total_sales_amount")),
		"total_billed_amount": flt(native.get("total_billed_amount")),
		"comparable_cost": flt(costing + purchase, 2),
		"gross_margin": flt(native.get("gross_margin")),
		"per_gross_margin": flt(native.get("per_gross_margin")),
	}


class PMOProjectClosure(Document):
	def validate(self):
		# Un solo Closure emitido por Project (las enmiendas reemplazan; el anterior queda cancelado).
		if not self.amended_from:
			existing = frappe.db.exists(
				"PMO Project Closure",
				{"project": self.project, "docstatus": 1, "name": ["!=", self.name or ""]},
			)
			if existing:
				frappe.throw(frappe._("This Project already has an issued Closure ({0}).").format(existing))

	def before_submit(self):
		# Guard de cierre (ADR-0014 D4): solo se emite Closure para un Project terminal (Completed/Cancelled).
		status = frappe.db.get_value("Project", self.project, "status")
		if status not in _TERMINAL_STATUSES:
			frappe.throw(
				frappe._(
					"Closure can only be issued for a terminal Project (Completed or Cancelled). "
					"Current status: {0}."
				).format(status or "—")
			)

		# Aceptación formal: un Project Completed exige aceptación explícita antes de cerrar.
		if status == "Completed" and not (self.accepted_by and self.accepted_on):
			frappe.throw(
				frappe._(
					"A Completed Project requires the formal acceptance (Accepted by and Accepted on) before closing."
				)
			)

		# Closure Checklist: todas las confirmaciones de cierre deben estar marcadas.
		if any(not self.get(fn) for fn in CLOSURE_CHECKLIST_FIELDS):
			frappe.throw(frappe._("Confirm all Closure Checklist items before issuing the Closure."))

		# Guard automático de Change Requests abiertos (fuente única de Governance; excluye cancelados).
		open_crs = count_open_change_requests(self.project)
		if open_crs:
			frappe.throw(
				frappe._(
					"Cannot close: the Project has {0} open Change Request(s). Resolve or close them (Rejected/Closed) before closing the Project."
				).format(open_crs)
			)

		closing_date = str(self.closure_date) if self.closure_date else today()
		# Confirmaciones del checklist tomadas del documento → congeladas en el snapshot (cubiertas por el hash).
		checklist = {key: bool(self.get(field)) for field, key in CLOSURE_CHECKLIST_SNAPSHOT_KEYS}
		# Evidencia NO economica (compuesta desde build_project_control), permlevel 0.
		snap = build_closure_snapshot(self.project, closing_date, checklist)
		self.snapshot_schema_version = snap["snapshot_schema_version"]
		self.snapshot_hash = snapshot_hash(snap)
		self.snapshot = canonical_json(snap)
		# Evidencia economica congelada, permlevel 1 (aislada del READ no economico). El gate economico se
		# aplica ANTES de cargar economia: un emisor sin rol economico congela `captured=False` (sin cifras).
		eco = build_closure_economics(self.project, frappe.session.user)
		self.economics_snapshot = canonical_json(eco)
		self.economics_snapshot_hash = snapshot_hash(eco)

		self.issued_by = frappe.session.user
		self.issued_at = now_datetime()
