# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Guard de integridad de fixtures de Custom Field (portabilidad). Estático, sin BD.

Impide reintroducir la inconsistencia corregida en `fix/pmo-fixtures-align-filter`: el filtro de
exportación de `hooks.py` (`fixtures` → Custom Field, `name in [...]`) debe coincidir **exactamente** con
los registros realmente presentes en `fixtures/custom_field.json`. Si divergen, un `export-fixtures`
futuro reescribiría el archivo dejando fuera campos necesarios (p. ej. toda la pestaña PMO del Project) y
rompería la instalación en sitios externos.

Verifica, leyendo las fuentes reales (no la BD):
- fixture ↔ filtro de hooks: mismo conjunto de nombres, sin faltantes en ninguno de los dos lados;
- sin duplicados en ninguno de los dos;
- los residuos retirados del diseño (`pmo_committed_html`, `pmo_sec_ctrl`) no reaparecen;
- cada `insert_after` apunta a un campo válido = nativo del DocType (meta) o a otro campo del mismo fixture.

Puro (`unittest.TestCase`): usa `frappe.get_hooks`, `frappe.get_app_path` y `frappe.get_meta` (schema,
read-only); no escribe en BD y es independiente de los datos del sitio.
"""

import json
import unittest

import frappe

APP = "pmo"
OBSOLETE = {"Project-pmo_committed_html", "Project-pmo_sec_ctrl"}


def _load_fixture_records() -> list:
	"""Registros reales de `fixtures/custom_field.json` (la fuente que importa `bench migrate`)."""
	path = frappe.get_app_path(APP, "fixtures", "custom_field.json")
	with open(path) as f:
		return json.load(f)


def _hooks_filter_names() -> list:
	"""Nombres declarados en el filtro de exportación de Custom Field en `hooks.py` (lista `name in [...]`)."""
	names = []
	for entry in frappe.get_hooks("fixtures", app_name=APP):
		if not isinstance(entry, dict):
			continue
		if (entry.get("dt") or entry.get("doctype")) != "Custom Field":
			continue
		for clause in entry.get("filters") or []:
			# clause esperado: ["name", "in", [<lista>]]
			if len(clause) == 3 and clause[0] == "name" and clause[1] == "in":
				names.extend(clause[2])
	return names


class TestFixtureIntegrity(unittest.TestCase):
	"""Alineación fixture ↔ filtro de hooks + validez estructural del layout (sin BD)."""

	@classmethod
	def setUpClass(cls):
		cls.records = _load_fixture_records()
		cls.fixture_names = [r["name"] for r in cls.records]
		cls.filter_names = _hooks_filter_names()

	def test_no_duplicates(self):
		dup_fx = sorted({n for n in self.fixture_names if self.fixture_names.count(n) > 1})
		dup_ft = sorted({n for n in self.filter_names if self.filter_names.count(n) > 1})
		self.assertEqual(dup_fx, [], f"Custom Fields duplicados en el fixture: {dup_fx}")
		self.assertEqual(dup_ft, [], f"Custom Fields duplicados en el filtro de hooks.py: {dup_ft}")

	def test_fixture_matches_hooks_filter(self):
		fx, ft = set(self.fixture_names), set(self.filter_names)
		missing_in_filter = sorted(fx - ft)  # en el archivo pero no exportables → export los borraría
		missing_in_fixture = sorted(
			ft - fx
		)  # en el filtro pero sin registro → export produciría archivo incompleto
		self.assertEqual(
			missing_in_filter,
			[],
			f"Custom Fields en custom_field.json pero FUERA del filtro de hooks.py "
			f"(un export-fixtures los eliminaría): {missing_in_filter}",
		)
		self.assertEqual(
			missing_in_fixture,
			[],
			f"Custom Fields en el filtro de hooks.py pero SIN registro en custom_field.json: "
			f"{missing_in_fixture}",
		)

	def test_obsolete_fields_absent(self):
		present = OBSOLETE & (set(self.fixture_names) | set(self.filter_names))
		self.assertEqual(
			present, set(), f"Campos obsoletos reintroducidos (fixture u hooks): {sorted(present)}"
		)

	def test_insert_after_anchors_valid(self):
		"""Cada `insert_after` debe anclar a un campo nativo del DocType (meta) o a otro campo del fixture."""
		fixture_fieldnames = {}
		for r in self.records:
			fixture_fieldnames.setdefault(r["dt"], set()).add(r["fieldname"])

		invalid = []
		for r in self.records:
			anchor = r.get("insert_after")
			if not anchor:
				continue
			dt = r["dt"]
			native = {df.fieldname for df in frappe.get_meta(dt).fields}
			valid = native | fixture_fieldnames.get(dt, set())
			if anchor not in valid:
				invalid.append(f"{r['name']} → insert_after={anchor!r}")
		self.assertEqual(invalid, [], f"insert_after inválidos (ancla inexistente): {invalid}")
