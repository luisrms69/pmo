# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 vistas / ADR-0002 P4 — Reporte PMO Resource Usage by Project. Datos ficticios.

Verifica el árbol Employee -> Project con enmascarado P4: proyectos visibles identificados (con
project_id auxiliar), no visibles consolidados en UNA fila "Comprometido (confidencial)" sin ningún
identificador, bucket separado "Sin proyecto", y la igualdad exacta
Total Employee = Σ visibles + Sin proyecto + Comprometido (confidencial) para Planned y Actual.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from pmo.pmo.report.pmo_resource_usage_by_project.pmo_resource_usage_by_project import (
	CONFIDENTIAL_LABEL,
	NO_PROJECT_LABEL,
	execute,
)

HL = "PMO-HL-TEST"


def _hl():
	if not frappe.db.exists("Holiday List", HL):
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": HL,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [{"holiday_date": "2026-01-06", "description": "Festivo"}],
			}
		).insert(ignore_permissions=True)
	return HL


def _user(email, roles=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
	if roles:
		frappe.get_doc("User", email).add_roles(*roles)
	return email


def _employee(name, user_id):
	emp = frappe.db.exists("Employee", {"employee_name": name}) or (
		frappe.get_doc({"doctype": "Employee", "first_name": name, "status": "Active", "holiday_list": _hl()})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Employee", emp, "user_id", user_id)
	return emp


def _capacity_global(hours=8.0):
	if not frappe.get_all("PMO Capacity", filters={"employee": ("in", ("", None))}, limit=1):
		frappe.get_doc(
			{"doctype": "PMO Capacity", "from_date": "2026-01-01", "capacity_hours_per_day": hours}
		).insert(ignore_permissions=True, ignore_links=True)


def _project(name, owner):
	p = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", p, "owner", owner)
	return p


def _task(subject, project, expected, start="2026-01-05", end="2026-01-05"):
	existing = frappe.db.exists("Task", {"subject": subject})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
				"expected_time": expected,
				"exp_start_date": start,
				"exp_end_date": end,
				"status": "Open",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _assign(task, user):
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": user,
			"reference_type": "Task",
			"reference_name": task,
			"status": "Open",
			"description": f"Asignación {task}",
		}
	).insert(ignore_permissions=True)


def _activity_type():
	if not frappe.db.exists("Activity Type", "PMO-ACT"):
		frappe.get_doc({"doctype": "Activity Type", "activity_type": "PMO-ACT"}).insert(
			ignore_permissions=True
		)
	return "PMO-ACT"


def _timesheet(employee, project, hours):
	ts = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": employee,
			"time_logs": [
				{
					"activity_type": _activity_type(),
					"from_time": "2026-01-05 09:00:00",
					"to_time": "2026-01-05 14:00:00",
					"hours": hours,
					"project": project,
				}
			],
		}
	)
	ts.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.set_value("Timesheet", ts.name, "docstatus", 1)


class TestResourceUsage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_hl()
		_activity_type()
		_capacity_global(8.0)
		cls.mgr_user = _user("ru-mgr@example.com", ["PMO Manager"])

	def setUp(self):
		frappe.db.delete("ToDo", {"reference_type": "Task"})
		frappe.db.delete("Timesheet Detail")
		frappe.db.delete("Timesheet")

	def _run(self, observer, **filters):
		frappe.set_user(observer)
		try:
			_cols, data = execute(filters)
		finally:
			frappe.set_user("Administrator")
		return data

	def _scenario(self):
		subj = _user("ru-subj@example.com")
		emp = _employee("RU Subject", subj)
		p_open = _project("RU-P-OPEN", owner=subj)  # visible (owner)
		p_conf = _project("RU-P-CONF", owner="Administrator")  # confidencial
		_assign(_task("RU-T-OPEN", p_open, 4), subj)  # 4h visible
		_assign(_task("RU-T-CONF", p_conf, 4), subj)  # 4h confidencial
		_assign(_task("RU-T-NOPROJ", None, 6), subj)  # 6h sin proyecto
		_timesheet(emp, p_open, 5)  # 5h Actual en proyecto visible
		return subj, emp, p_open, p_conf

	def _children(self, data, emp):
		return [r for r in data if r.get("employee") is None]

	def _parent(self, data, emp):
		rows = [r for r in data if r.get("employee") == emp]
		self.assertEqual(len(rows), 1)
		return rows[0]

	# --- estructura ---------------------------------------------------------

	def test_tree_structure(self):
		subj, emp, _po, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		parent = self._parent(data, emp)
		self.assertEqual(parent["indent"], 0)
		children = self._children(data, emp)
		self.assertTrue(all(c["indent"] == 1 for c in children))
		self.assertEqual(len(children), 3)  # visible + sin proyecto + confidencial

	def test_total_equals_children(self):
		subj, emp, _po, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		parent = self._parent(data, emp)
		children = self._children(data, emp)
		self.assertEqual(parent["planned"], round(sum(c["planned"] for c in children), 2))
		self.assertEqual(parent["actual"], round(sum(c["actual"] for c in children), 2))
		self.assertEqual(parent["planned"], 14.0)  # 4 + 6 + 4
		self.assertEqual(parent["actual"], 5.0)  # solo p_open

	# --- P4 -----------------------------------------------------------------

	def test_confidential_single_row_without_identifier(self):
		subj, emp, _po, p_conf = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		conf = [r for r in data if r["project"] == "Comprometido (confidencial)"]
		self.assertEqual(len(conf), 1)  # una sola fila
		self.assertEqual(conf[0]["planned"], 4.0)  # confidencial cuenta en el total
		self.assertNotIn("project_id", conf[0])  # sin identificador auxiliar
		self.assertNotIn(p_conf, frappe.as_json(data))  # nombre real nunca serializado

	def test_visible_project_has_identifier(self):
		subj, emp, p_open, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		vis = [r for r in data if r.get("project_id") == p_open]
		self.assertEqual(len(vis), 1)
		self.assertEqual(vis[0]["planned"], 4.0)

	def test_sin_proyecto_bucket_separate(self):
		subj, emp, _po, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		np = [r for r in data if r["project"] == "Sin proyecto"]
		self.assertEqual(len(np), 1)
		self.assertEqual(np[0]["planned"], 6.0)
		self.assertNotIn("project_id", np[0])  # no revela identidad (no existe)

	def test_manager_no_confidential_identity_leak(self):
		# manager no es owner/member → p_open y p_conf ambos confidenciales para él
		_subj, emp, p_open, p_conf = self._scenario()
		data = self._run(self.mgr_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		blob = frappe.as_json(data)
		self.assertNotIn(p_open, blob)
		self.assertNotIn(p_conf, blob)
		conf = [r for r in data if r["project"] == "Comprometido (confidencial)"]
		self.assertEqual(conf[0]["planned"], 8.0)  # 4 + 4 consolidados, cuentan en el total

	def test_normal_sees_only_own_subtree(self):
		subj, emp, _po, _pc = self._scenario()
		other = _user("ru-other@example.com")
		other_emp = _employee("RU Other", other)
		_assign(_task("RU-T-OTHER", _project("RU-P-OTHER", owner=other), 3), other)
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05")
		parents = [r["employee"] for r in data if r.get("employee")]
		self.assertIn(emp, parents)
		self.assertNotIn(other_emp, parents)


class TestResourceUsageTemporal(IntegrationTestCase):
	"""ADR-0003 vistas / ADR-0002 P4 -- Desglose TEMPORAL (Proyecto x periodo, solo Planned) del reporte
	PMO Resource Usage by Project. Verifica Day/Week/Month, buckets P4 (visible con project_id,
	Sin proyecto, Comprometido (confidencial) consolidado sin identidad), Total = suma de periodos, y
	total del empleado consistente con el Planned del rango.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_hl()
		_capacity_global(8.0)
		cls.mgr_user = _user("rut-mgr@example.com", ["PMO Manager"])
		cls.subj = _user("rut-subj@example.com")
		cls.emp = _employee("RUT Subject", cls.subj)
		cls.p_open = _project("RUT-P-OPEN", owner=cls.subj)  # visible (owner)
		cls.p_conf = _project("RUT-P-CONF", owner="Administrator")  # confidencial
		# rango Jan 12-15 2026 (lun-jue, sin festivo en la HL) -> 4 dias habiles
		_assign(_task("RUT-T-OPEN", cls.p_open, 16, "2026-01-12", "2026-01-15"), cls.subj)
		_assign(_task("RUT-T-CONF", cls.p_conf, 8, "2026-01-12", "2026-01-15"), cls.subj)
		_assign(_task("RUT-T-NOPROJ", None, 4, "2026-01-12", "2026-01-15"), cls.subj)

	def _run(self, observer, **filters):
		frappe.set_user(observer)
		try:
			return execute(filters)
		finally:
			frappe.set_user("Administrator")

	def _periods(self, cols):
		return [c["fieldname"] for c in cols if c["fieldname"].startswith("period_")]

	def _child(self, data, label):
		rows = [r for r in data if r.get("indent") == 1 and r.get("project") == label]
		return rows[0] if rows else None

	def _parent(self, data):
		return next(r for r in data if r.get("indent") == 0)

	# --- Day -----------------------------------------------------------------

	def test_day_visible_project_has_id_and_daily_split(self):
		cols, data = self._run(self.subj, from_date="2026-01-12", to_date="2026-01-15", granularity="Day")
		pf = self._periods(cols)
		self.assertEqual(len(pf), 4)
		row = self._child(data, "RUT-P-OPEN")
		self.assertIsNotNone(row)
		self.assertEqual(row["project_id"], self.p_open)  # visible -> id para el link
		self.assertEqual(row["total"], 16.0)
		self.assertEqual({row[f] for f in pf}, {4.0})  # 16h / 4 dias habiles

	def test_day_no_project_bucket(self):
		_cols, data = self._run(self.subj, from_date="2026-01-12", to_date="2026-01-15", granularity="Day")
		row = self._child(data, NO_PROJECT_LABEL)
		self.assertIsNotNone(row)
		self.assertIsNone(row.get("project_id"))
		self.assertEqual(row["total"], 4.0)

	def test_day_confidential_consolidated_without_identity(self):
		_cols, data = self._run(self.subj, from_date="2026-01-12", to_date="2026-01-15", granularity="Day")
		row = self._child(data, CONFIDENTIAL_LABEL)
		self.assertIsNotNone(row)
		self.assertIsNone(row.get("project_id"))
		self.assertEqual(row["total"], 8.0)
		blob = frappe.as_json(data)
		self.assertNotIn(self.p_conf, blob)  # id oculto nunca viaja
		self.assertNotIn("RUT-T-CONF", blob)  # tarea oculta nunca viaja

	def test_row_total_equals_sum_of_periods(self):
		cols, data = self._run(self.subj, from_date="2026-01-12", to_date="2026-01-15", granularity="Day")
		pf = self._periods(cols)
		for r in data:
			self.assertEqual(r["total"], flt(sum(r[f] for f in pf), 2), f"total != suma periodos en {r}")

	def test_employee_total_consistent_with_planned_range(self):
		_cols, data = self._run(self.subj, from_date="2026-01-12", to_date="2026-01-15", granularity="Day")
		parent = self._parent(data)
		# 16 (visible) + 8 (confidencial) + 4 (sin proyecto) = 28, contado sin importar visibilidad
		self.assertEqual(parent["total"], 28.0)
		children_total = flt(sum(r["total"] for r in data if r.get("indent") == 1), 2)
		self.assertEqual(parent["total"], children_total)

	# --- Week / Month --------------------------------------------------------

	def test_week_single_bucket(self):
		cols, data = self._run(self.subj, from_date="2026-01-12", to_date="2026-01-15", granularity="Week")
		self.assertEqual(len(self._periods(cols)), 1)  # lun-jue caen en una sola semana
		self.assertEqual(self._child(data, "RUT-P-OPEN")["total"], 16.0)
		self.assertEqual(self._parent(data)["total"], 28.0)

	def test_month_single_bucket(self):
		cols, data = self._run(self.subj, from_date="2026-01-12", to_date="2026-01-15", granularity="Month")
		self.assertEqual(len(self._periods(cols)), 1)  # todo enero
		self.assertEqual(self._parent(data)["total"], 28.0)

	# --- P4 por observador ---------------------------------------------------

	def test_manager_temporal_no_identity_leak(self):
		_cols, data = self._run(
			self.mgr_user, from_date="2026-01-12", to_date="2026-01-15", granularity="Day"
		)
		blob = frappe.as_json(data)
		self.assertNotIn(self.p_open, blob)  # manager no es owner/member -> nada identificado
		self.assertNotIn(self.p_conf, blob)
		self.assertNotIn("RUT-T-OPEN", blob)
		conf = self._child(data, CONFIDENTIAL_LABEL)
		self.assertIsNotNone(conf)
		self.assertEqual(conf["total"], 24.0)  # 16 + 8 consolidado
		self.assertEqual(self._parent(data)["total"], 28.0)  # cuantitativo intacto
