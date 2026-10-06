# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — pmo.constraints (Schedule Constraints II.1 · SNET, ADR-0018).

Dos niveles:
- **Puros (sin BD, corren antes del migrate):** la aritmética SNET (`compute_snet_start_end`) y la
  elegibilidad (`_is_eligible`) con entradas simuladas. No dependen de los Custom Fields.
- **Integración (requieren los Custom Fields en el site → POST-migrate):** SNET sobre Task real + que la
  cascada nativa siga propagando desde la fecha corregida; garantía de no-escritura de baseline/actuals.
  Marcados para saltarse si los Custom Fields aún no existen (pre-migrate).
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime, getdate

from pmo.constraints import (
	SNET,
	_is_eligible,
	apply_start_constraint,
	compute_snet_start_end,
	notify_start_constraint,
)


# ----------------------------------------------------------------------------------------------------
# Nivel PURO (sin BD) — corre antes del migrate.
# ----------------------------------------------------------------------------------------------------
class TestSnetPure(unittest.TestCase):
	def test_shift_preserves_time_and_duration(self):
		# Inicio 2026-01-05 14:00, fin 2026-01-07 14:00 (dur natural 2). SNET 2026-01-20 → inicio 01-20 14:00,
		# fin 01-22 14:00. Preserva la hora original (14:00) y la duración natural (2).
		res = compute_snet_start_end("2026-01-05 14:00:00", "2026-01-07 14:00:00", "2026-01-20")
		self.assertIsNotNone(res)
		new_start, new_end = res
		self.assertEqual(get_datetime(new_start).strftime("%Y-%m-%d %H:%M:%S"), "2026-01-20 14:00:00")
		self.assertEqual(get_datetime(new_end).strftime("%Y-%m-%d %H:%M:%S"), "2026-01-22 14:00:00")

	def test_duration_zero_same_day(self):
		# Dur 0 (mismo día) se conserva: fin = inicio desplazado.
		res = compute_snet_start_end("2026-01-05 09:30:00", "2026-01-05 09:30:00", "2026-01-20")
		new_start, new_end = res
		self.assertEqual(getdate(new_start), getdate("2026-01-20"))
		self.assertEqual(getdate(new_end), getdate("2026-01-20"))
		self.assertEqual(get_datetime(new_start).strftime("%H:%M:%S"), "09:30:00")

	def test_no_shift_when_start_on_or_after_snet(self):
		# SNET solo empuja hacia adelante: si ya inicia en o después del SNET → None.
		self.assertIsNone(compute_snet_start_end("2026-01-20 10:00:00", "2026-01-22 10:00:00", "2026-01-20"))
		self.assertIsNone(compute_snet_start_end("2026-01-25 10:00:00", "2026-01-26 10:00:00", "2026-01-20"))

	def test_no_op_on_incomplete_data(self):
		self.assertIsNone(compute_snet_start_end(None, "2026-01-07", "2026-01-20"))
		self.assertIsNone(compute_snet_start_end("2026-01-05", None, "2026-01-20"))
		self.assertIsNone(compute_snet_start_end("2026-01-05", "2026-01-07", None))

	def test_eligibility(self):
		base = {"status": "Open", "act_start_date": None, "is_group": 0, "is_milestone": 0}
		self.assertTrue(_is_eligible(frappe._dict(base)))
		self.assertFalse(_is_eligible(frappe._dict({**base, "act_start_date": "2026-01-01"})))
		self.assertFalse(_is_eligible(frappe._dict({**base, "status": "Completed"})))
		self.assertFalse(_is_eligible(frappe._dict({**base, "status": "Cancelled"})))
		self.assertFalse(_is_eligible(frappe._dict({**base, "is_group": 1})))
		self.assertFalse(_is_eligible(frappe._dict({**base, "is_milestone": 1})))
		# Working/Overdue sin act_start_date NO se excluyen por status (ADR-0018).
		self.assertTrue(_is_eligible(frappe._dict({**base, "status": "Working"})))

	def test_apply_mutates_doc_in_place(self):
		# Orquestador sobre un _dict simulado: muta exp_* en memoria; no toca nada más.
		doc = frappe._dict(
			{
				"pmo_constraint_type": SNET,
				"pmo_constraint_date": "2026-01-20",
				"exp_start_date": "2026-01-05 14:00:00",
				"exp_end_date": "2026-01-07 14:00:00",
				"status": "Open",
				"act_start_date": None,
				"is_group": 0,
				"is_milestone": 0,
				"flags": frappe._dict(),
			}
		)
		apply_start_constraint(doc)
		self.assertEqual(getdate(doc.exp_start_date), getdate("2026-01-20"))
		self.assertEqual(getdate(doc.exp_end_date), getdate("2026-01-22"))

	def test_apply_sets_shift_flag(self):
		# El shift deja la marca para el aviso final (on_update); si no hay shift, no hay marca.
		doc = frappe._dict(
			{
				"pmo_constraint_type": SNET,
				"pmo_constraint_date": "2026-01-20",
				"exp_start_date": "2026-01-05 14:00:00",
				"exp_end_date": "2026-01-07 14:00:00",
				"status": "Open",
				"flags": frappe._dict(),
			}
		)
		apply_start_constraint(doc)
		self.assertEqual(doc.flags.get("pmo_snet_shift"), "2026-01-20")

	def test_notify_suppressed_during_cascade(self):
		# El aviso NO se emite para sucesoras movidas por la cascada (flags.ignore_recursion_check).
		# notify_start_constraint no debe lanzar y debe ser no-op cuando corresponde.
		doc = frappe._dict(
			{"flags": frappe._dict({"pmo_snet_shift": "2026-01-20", "ignore_recursion_check": True})}
		)
		notify_start_constraint(doc)  # no-op, no lanza
		doc2 = frappe._dict({"flags": frappe._dict()})
		notify_start_constraint(doc2)  # sin shift → no-op, no lanza

	def test_apply_noop_when_not_snet_or_ineligible(self):
		# FNLT no actúa en II.1.
		doc = frappe._dict(
			{
				"pmo_constraint_type": "Finish No Later Than (FNLT)",
				"pmo_constraint_date": "2026-01-20",
				"exp_start_date": "2026-01-05",
				"exp_end_date": "2026-01-07",
				"status": "Open",
			}
		)
		apply_start_constraint(doc)
		self.assertEqual(getdate(doc.exp_start_date), getdate("2026-01-05"))  # sin cambio
		# SNET pero iniciada → no muta.
		doc2 = frappe._dict(
			{
				"pmo_constraint_type": SNET,
				"pmo_constraint_date": "2026-01-20",
				"exp_start_date": "2026-01-05",
				"exp_end_date": "2026-01-07",
				"act_start_date": "2026-01-06",
			}
		)
		apply_start_constraint(doc2)
		self.assertEqual(getdate(doc2.exp_start_date), getdate("2026-01-05"))  # sin cambio


# ----------------------------------------------------------------------------------------------------
# Nivel INTEGRACIÓN — requiere los Custom Fields (post-migrate). Se salta si aún no existen.
# ----------------------------------------------------------------------------------------------------
def _cf_ready():
	return frappe.db.exists("Custom Field", "Task-pmo_constraint_type") and frappe.db.exists(
		"Custom Field", "Task-pmo_constraint_date"
	)


def _project(name):
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": name, "expected_start_date": "2026-01-01"}
	).insert(ignore_permissions=True, ignore_mandatory=True)
	return doc.name


def _task(subject, start=None, end=None, deps=None, status="Open", project=None, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"status": status,
			"project": project,
			"exp_start_date": start,
			"exp_end_date": end,
			# `project` en la fila de dependencia: la cascada nativa filtra por child.project (en la UI se
			# puebla por fetch; en inserción server-side hay que setearlo para reproducir la cascada real).
			"depends_on": [{"task": d, "project": project} for d in (deps or [])],
			**kw,
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)
	return doc


class TestSnetIntegration(IntegrationTestCase):
	def setUp(self):
		# Guard en runtime (no en import): si los Custom Fields aún no están migrados, se salta.
		if not _cf_ready():
			self.skipTest("Custom Fields de constraint aún no migrados")

	def test_snet_shifts_on_save(self):
		t = _task(
			"SNET shift",
			"2026-01-05 14:00:00",
			"2026-01-07 14:00:00",
			pmo_constraint_type=SNET,
			pmo_constraint_date="2026-01-20",
		)
		self.assertEqual(getdate(t.exp_start_date), getdate("2026-01-20"))
		self.assertEqual(getdate(t.exp_end_date), getdate("2026-01-22"))
		self.assertEqual(get_datetime(t.exp_start_date).strftime("%H:%M:%S"), "14:00:00")

	def test_no_shift_if_already_after_snet(self):
		t = _task(
			"SNET noop",
			"2026-02-01",
			"2026-02-03",
			pmo_constraint_type=SNET,
			pmo_constraint_date="2026-01-20",
		)
		self.assertEqual(getdate(t.exp_start_date), getdate("2026-02-01"))

	def test_native_cascade_propagates_from_corrected_date(self):
		# Spike decisivo A→B→C: B tiene SNET futuro; C depende de B SIN constraint. Al guardar B con el SNET,
		# PMO normaliza B (before_validate) y ERPNext (reschedule_dependent_tasks, nativo) propaga a C desde
		# la fecha corregida de B. C NO tiene constraint → su movimiento es 100% del core, no de PMO.
		# La cascada nativa es project-scoped: la cadena comparte un Project.
		p = _project("SNET Cascade")
		a = _task("A", "2026-01-05", "2026-01-06", project=p)
		b = _task("B", "2026-01-07", "2026-01-09", deps=[a.name], project=p)  # dur natural 2, aún sin SNET
		c = _task("C", "2026-01-10", "2026-01-11", deps=[b.name], project=p)  # dur natural 1, sin constraint
		# Aplicar SNET a B y guardar → before_validate normaliza B; on_update nativo cascada a C.
		b.pmo_constraint_type = SNET
		b.pmo_constraint_date = "2026-01-20"
		b.save(ignore_permissions=True)
		b.reload()
		c.reload()
		a.reload()
		# B normalizado por PMO: 01-20..01-22 (conserva dur 2).
		self.assertEqual(getdate(b.exp_start_date), getdate("2026-01-20"))
		self.assertEqual(getdate(b.exp_end_date), getdate("2026-01-22"))
		# C movido por ERPNext (cascada nativa FS): inicio = fin(B)+1 = 01-23, dur 1 → fin 01-24.
		self.assertEqual(getdate(c.exp_start_date), getdate("2026-01-23"))
		self.assertEqual(getdate(c.exp_end_date), getdate("2026-01-24"))
		# C sin constraint propio (PMO no lo tocó; el movimiento es del core).
		self.assertFalse(c.get("pmo_constraint_type"))
		# No hay cascada PMO: A (predecesora) intacta.
		self.assertEqual(getdate(a.exp_start_date), getdate("2026-01-05"))

	def test_working_without_actual_is_eligible(self):
		# Working/Overdue SIN act_start_date → elegible (se mueve), según ADR-0018 (act_start_date canónico).
		t = _task(
			"Working no actual",
			"2026-01-05",
			"2026-01-07",
			status="Working",
			pmo_constraint_type=SNET,
			pmo_constraint_date="2026-01-20",
		)
		self.assertEqual(getdate(t.exp_start_date), getdate("2026-01-20"))

	def test_never_writes_actuals(self):
		t = _task(
			"SNET actuals",
			"2026-01-05",
			"2026-01-07",
			pmo_constraint_type=SNET,
			pmo_constraint_date="2026-01-20",
		)
		self.assertIsNone(t.act_start_date)
		self.assertIsNone(t.act_end_date)


if __name__ == "__main__":
	unittest.main()
