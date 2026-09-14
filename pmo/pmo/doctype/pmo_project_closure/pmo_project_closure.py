# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Closure (ADR-0014 D4/D11) — cierre formal del Project.

Submittable + track_changes: al emitir se **congela** un snapshot canonico con hash (patron Baseline). El
Closure **no inventa metricas**: las **compone** de fuentes canonicas al corte de cierre (build_status_report
para fechas/desvios/horas; totales nativos del Project para comercial/costo/margen; frontera
get_authorized_economics para el autorizado; conteo de Change Requests). Solo se captura la parte de gobierno
que no existe en otro lado (resultado final, aceptacion formal, pendientes transferidos, observaciones).

El Print Format posterior se reconstruye SOLO desde este snapshot, nunca desde datos vivos: cambios en el
Project despues del submit no alteran como "cerro". Autosuficiente (sin Risk); no toca PHI.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from pmo.baseline import canonical_json, snapshot_hash
from pmo.governance import derive_lifecycle_state
from pmo.project_economics import get_authorized_economics
from pmo.status_date import build_status_report

CLOSURE_SNAPSHOT_SCHEMA_VERSION = 1

_NATIVE_COST_FIELDS = (
	"total_sales_amount",
	"total_billed_amount",
	"total_costing_amount",
	"total_purchase_cost",
	"total_consumed_material_cost",
	"gross_margin",
	"per_gross_margin",
)


def build_closure_snapshot(project: str, closing_date: str) -> dict:
	"""Snapshot de cierre: compone (no recalcula) fuentes canonicas al corte `closing_date`."""
	sr = build_status_report(project, closing_date)  # impone P4; fechas/desvios/horas al corte
	ind = sr.get("indicators") or {}

	native = frappe.db.get_value("Project", project, _NATIVE_COST_FIELDS, as_dict=True) or frappe._dict()
	econ = get_authorized_economics(project)
	edata = econ.get("data") or {}

	planned = 0.0
	for t in frappe.get_all(
		"Task", filters={"project": project, "is_group": 0}, fields=["expected_time"], limit=0
	):
		planned += flt(t.get("expected_time"))

	crs = frappe.get_all(
		"PMO Change Request", filters={"project": project}, fields=["name", "workflow_state"], limit=0
	)

	costing = flt(native.get("total_costing_amount"))
	purchase = flt(native.get("total_purchase_cost"))

	return {
		"snapshot_schema_version": CLOSURE_SNAPSHOT_SCHEMA_VERSION,
		"closing_date": str(closing_date),
		"lifecycle_state_at_closure": derive_lifecycle_state(project),
		"schedule": {
			"baseline_end": (sr.get("baseline") or {}).get("expected_end_date"),
			"committed_end": sr.get("committed_end_date"),
			"forecast_end": (sr.get("current") or {}).get("expected_end_date"),
			"slip_vs_baseline_days": ind.get("final_date_slip_days"),
			"slip_vs_committed_days": ind.get("slip_vs_committed_days"),
			"overdue_at_cutoff": (ind.get("tasks_overdue_at_cutoff") or {}).get("count"),
		},
		"economics": {
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
		},
		"effort": {
			"planned_hours": flt(planned, 1),
			"actual_hours": flt(ind.get("actual_hours_to_date"), 1),
		},
		"changes": {"total": len(crs)},
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
		# Congela TODA la evidencia al emitir (ADR-0014 D4/D11). El Print Format se reconstruye SOLO desde
		# este snapshot, nunca desde datos vivos.
		closing_date = str(self.closure_date) if self.closure_date else frappe.utils.today()
		snapshot = build_closure_snapshot(self.project, closing_date)
		self.snapshot_schema_version = snapshot["snapshot_schema_version"]
		self.snapshot_hash = snapshot_hash(snapshot)
		self.snapshot = canonical_json(snapshot)
		self.issued_by = frappe.session.user
		self.issued_at = now_datetime()
