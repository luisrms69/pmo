# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del importador genérico de Tags nativos desde CSV.

Datos exclusivamente ficticios. Verifican: CSV válido, múltiples Tags por
documento, Tag nativo real, idempotencia, Dry Run sin escrituras, documento
inexistente, CSV inválido sin escritura parcial y ausencia de Custom Fields.
"""

import frappe
from frappe.desk.doctype.tag.tag import DocTags
from frappe.tests import IntegrationTestCase

from pmo.tag_import import tag_import_apply, tag_import_dry_run

MARKER = "PMO-TAGIMPORT-TEST"


class TestTagImport(IntegrationTestCase):
	def _mk_task(self, suffix):
		return (
			frappe.get_doc({"doctype": "Task", "subject": f"{MARKER} {suffix}"})
			.insert(ignore_permissions=True)
			.name
		)

	def _tags(self, name):
		return set(t for t in DocTags("Task").get_tags(name).split(",") if t)

	@staticmethod
	def _csv(*lines):
		return "doctype,document,tags\n" + "\n".join(lines) + "\n"

	# --- Dry Run ------------------------------------------------------------

	def test_dry_run_valid_writes_nothing(self):
		t = self._mk_task("dry")
		csv = self._csv(f'Task,{t},"ALFA,BETA,GAMMA"')
		res = tag_import_dry_run(csv)

		self.assertTrue(res["ok"])
		self.assertEqual(res["documentos_leidos"], 1)
		self.assertEqual(res["documentos_validos"], 1)
		self.assertEqual(res["asociaciones_solicitadas"], 3)
		self.assertEqual(res["asociaciones_aplicadas"], 3)  # "se aplicarían"
		self.assertEqual(self._tags(t), set())  # nada escrito

	# --- Apply --------------------------------------------------------------

	def test_apply_multiple_tags(self):
		t = self._mk_task("apply")
		csv = self._csv(f'Task,{t},"ALFA,BETA,GAMMA"')
		res = tag_import_apply(csv)

		self.assertTrue(res["ok"])
		self.assertEqual(res["asociaciones_aplicadas"], 3)
		self.assertEqual(self._tags(t), {"ALFA", "BETA", "GAMMA"})

	def test_idempotent_second_run(self):
		t = self._mk_task("idem")
		csv = self._csv(f'Task,{t},"ALFA,BETA"')

		first = tag_import_apply(csv)
		self.assertEqual(first["asociaciones_aplicadas"], 2)

		second = tag_import_apply(csv)
		self.assertTrue(second["ok"])
		self.assertEqual(second["asociaciones_solicitadas"], 2)
		self.assertEqual(second["asociaciones_aplicadas"], 0)  # nada nuevo
		self.assertEqual(self._tags(t), {"ALFA", "BETA"})

	def test_partial_diff_counts_only_new(self):
		t = self._mk_task("partial")
		tag_import_apply(self._csv(f'Task,{t},"ALFA"'))
		# ahora pide ALFA (existe) + BETA,GAMMA (nuevos)
		res = tag_import_apply(self._csv(f'Task,{t},"ALFA,BETA,GAMMA"'))
		self.assertEqual(res["asociaciones_solicitadas"], 3)
		self.assertEqual(res["asociaciones_aplicadas"], 2)
		self.assertEqual(self._tags(t), {"ALFA", "BETA", "GAMMA"})

	# --- Errores: sin escritura ---------------------------------------------

	def test_nonexistent_document(self):
		res_dry = tag_import_dry_run(self._csv('Task,TASK-NO-EXISTE-9999,"ALFA"'))
		self.assertFalse(res_dry["ok"])
		self.assertIn("Task:TASK-NO-EXISTE-9999", res_dry["documentos_inexistentes"])
		self.assertEqual(res_dry["asociaciones_aplicadas"], 0)

		res_apply = tag_import_apply(self._csv('Task,TASK-NO-EXISTE-9999,"ALFA"'))
		self.assertFalse(res_apply["ok"])
		self.assertEqual(res_apply["asociaciones_aplicadas"], 0)

	def test_invalid_csv_header_no_write(self):
		t = self._mk_task("badheader")
		bad = f'foo,bar,baz\nTask,{t},"ALFA"\n'
		res = tag_import_apply(bad)
		self.assertFalse(res["ok"])
		self.assertEqual(res["asociaciones_aplicadas"], 0)
		self.assertEqual(self._tags(t), set())

	def test_no_partial_write_when_any_row_invalid(self):
		"""Una fila válida + una inválida en el mismo CSV → NO se escribe la válida (todo-o-nada)."""
		good = self._mk_task("good")
		csv = self._csv(
			f'Task,{good},"ALFA,BETA"',
			'Task,TASK-NO-EXISTE-9999,"GAMMA"',
		)
		res = tag_import_apply(csv)
		self.assertFalse(res["ok"])
		self.assertEqual(res["asociaciones_aplicadas"], 0)
		self.assertEqual(self._tags(good), set())  # la fila válida NO se aplicó

	# --- Tags nativos, sin Custom Fields ------------------------------------

	def test_tags_are_native_no_custom_field(self):
		t = self._mk_task("native")
		tag_import_apply(self._csv(f'Task,{t},"ALFA"'))
		# El Tag quedó en el mecanismo nativo (Tag Link), no en un Custom Field.
		self.assertTrue(
			frappe.db.exists("Tag Link", {"document_type": "Task", "document_name": t, "tag": "ALFA"})
		)
		self.assertFalse(
			frappe.db.exists("Custom Field", {"dt": "Task", "fieldname": ["in", ["tags", "_user_tags"]]})
		)

	# --- Desglose por documento (guard visual) ------------------------------

	def test_detalle_lists_per_document(self):
		t1 = self._mk_task("det1")
		t2 = self._mk_task("det2")
		res = tag_import_dry_run(self._csv(f'Task,{t1},"ALFA,BETA"', f'Task,{t2},"GAMMA"'))
		self.assertEqual(len(res["detalle"]), 2)
		d1 = next(d for d in res["detalle"] if d["documento"] == t1)
		self.assertEqual(d1["tipo"], "Task")
		self.assertEqual(set(d1["tags"]), {"ALFA", "BETA"})
		self.assertEqual(d1["estado"], "se_agregaran")

	def test_detalle_estado_sin_cambios(self):
		t = self._mk_task("det_sin")
		tag_import_apply(self._csv(f'Task,{t},"ALFA"'))
		res = tag_import_dry_run(self._csv(f'Task,{t},"ALFA"'))  # ya lo tiene
		d = res["detalle"][0]
		self.assertEqual(d["estado"], "sin_cambios")
		self.assertEqual(d["tags"], [])

	def test_detalle_marks_error_rows(self):
		res = tag_import_dry_run(self._csv('Task,TASK-NO-EXISTE-9999,"ALFA"'))
		d = res["detalle"][0]
		self.assertEqual(d["estado"], "error")
		self.assertTrue(d["error"])
