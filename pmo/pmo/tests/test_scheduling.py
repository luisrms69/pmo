# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — pmo.scheduling (Schedule Intelligence, ADR-0017 · I.1).

Capa de dominio READ-ONLY: diagnóstico de integridad de la red nativa `Task Depends On` (FS implícito) +
calendario laboral. Verifica que SOLO señala divergencias (nunca reprograma ni escribe), que degrada seguro
sin calendario, y que distingue días hábiles de naturales.

Dos niveles:
- Puros (sin BD): aritmética de calendario (natural), ciclos, forward pass.
- Integración (site de tests): `analyze_schedule_integrity` sobre Project/Task/Task Depends On reales con
  una Holiday List real.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from pmo.scheduling import (
	SEV_BAD,
	SEV_OK,
	SEV_WARN,
	_backward_pass,
	_critical_branches,
	_days_label,
	_detect_cycles,
	_forward_pass,
	_sev_count,
	_sev_flag,
	_sev_margin,
	_sev_min_slack,
	_working_span,
	add_working_days,
	analyze_critical_path,
	analyze_schedule_integrity,
	analyze_schedule_slack,
	resolve_holiday_list,
	working_days,
)

# Ventana de prueba — enero 2026. Festivos del calendario de test: fines de semana + 2026-01-06 (martes).
HL = "PMO-SCHED-HL-TEST"


# ----------------------------------------------------------------------------------------------------
# Nivel puro (sin BD): holiday_list=None → días naturales; grafo en memoria.
# ----------------------------------------------------------------------------------------------------
class TestSchedulingPure(unittest.TestCase):
	def test_working_days_natural_inclusive(self):
		# Sin calendario: cuenta inclusiva de días naturales.
		self.assertEqual(working_days("2026-01-05", "2026-01-09", None), 5)
		self.assertEqual(working_days("2026-01-05", "2026-01-05", None), 1)

	def test_working_days_end_before_start_is_zero(self):
		self.assertEqual(working_days("2026-01-09", "2026-01-05", None), 0)
		self.assertEqual(working_days(None, "2026-01-05", None), 0)

	def test_add_working_days_natural(self):
		self.assertEqual(str(add_working_days("2026-01-05", 0, None)), "2026-01-05")
		self.assertEqual(str(add_working_days("2026-01-05", 3, None)), "2026-01-08")

	def test_detect_cycles(self):
		# A→B→C→A es un ciclo; una cadena lineal no lo es.
		self.assertTrue(_detect_cycles(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")]))
		self.assertFalse(_detect_cycles(["A", "B", "C"], [("A", "B"), ("B", "C")]))

	def test_forward_pass_fs_chain_natural(self):
		# A(01-01→01-02) → B(dur 2). ES(B)=día siguiente a EF(A); EF se propaga en días naturales.
		active = {
			"A": {
				"name": "A",
				"subject": "A",
				"is_milestone": 0,
				"start": "2026-01-01",
				"end": "2026-01-02",
				"deadline": None,
			},
			"B": {
				"name": "B",
				"subject": "B",
				"is_milestone": 0,
				"start": "2026-01-05",
				"end": "2026-01-06",
				"deadline": None,
			},
		}
		ef = _forward_pass(active, [("A", "B")], None)
		self.assertEqual(str(ef["A"]["ef"]), "2026-01-02")
		# ES(B)=01-03 (siguiente a EF(A)); dur(B)=2 → EF(B)=01-04.
		self.assertEqual(str(ef["B"]["es"]), "2026-01-03")
		self.assertEqual(str(ef["B"]["ef"]), "2026-01-04")

	def test_forward_pass_milestone_zero_duration(self):
		active = {
			"M": {
				"name": "M",
				"subject": "M",
				"is_milestone": 1,
				"start": "2026-01-05",
				"end": "2026-01-05",
				"deadline": None,
			},
		}
		ef = _forward_pass(active, [], None)
		self.assertEqual(str(ef["M"]["ef"]), "2026-01-05")  # EF == ES para hito

	def test_add_working_days_negative_natural(self):
		# Backward pass: desplazamiento negativo en días naturales.
		self.assertEqual(str(add_working_days("2026-01-08", -3, None)), "2026-01-05")

	def test_working_span_signed(self):
		# Distancia dirigida en días (naturales, sin calendario): 0, positiva y negativa.
		self.assertEqual(_working_span("2026-01-05", "2026-01-05", None), 0)
		self.assertEqual(_working_span("2026-01-05", "2026-01-08", None), 3)
		self.assertEqual(_working_span("2026-01-08", "2026-01-05", None), -3)

	def test_backward_pass_linear_natural(self):
		# A→B→C lineal (días naturales). Ancla = max EF = EF(C). Toda la cadena con holgura 0.
		active = {
			k: {"name": k, "subject": k, "is_milestone": 0, "start": s, "end": e, "deadline": None}
			for k, s, e in (
				("A", "2026-01-01", "2026-01-02"),
				("B", "2026-01-03", "2026-01-04"),
				("C", "2026-01-05", "2026-01-06"),
			)
		}
		edges = [("A", "B"), ("B", "C")]
		fp = _forward_pass(active, edges, None)
		finish = max(v["ef"] for v in fp.values())
		bp = _backward_pass(active, edges, None, fp, finish)
		# Cadena crítica: LS==ES en cada nodo (holgura 0).
		for k in active:
			self.assertEqual(str(bp[k]["ls"]), str(fp[k]["es"]))

	def test_critical_branches_enumeration(self):
		# Subgrafo crítico diamante A→{B,C}→D → dos rutas (no se inventa una sola cadena); orden por ES.
		nb = {k: {"es": es} for k, es in (("A", "d1"), ("B", "d2"), ("C", "d2"), ("D", "d3"))}
		paths, trunc = _critical_branches(
			{"A", "B", "C", "D"}, [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")], nb
		)
		self.assertFalse(trunc)
		self.assertEqual(sorted(paths), [["A", "B", "D"], ["A", "C", "D"]])

	def test_critical_branches_isolated_node(self):
		# Nodo crítico aislado (sin aristas críticas) → rama de una sola tarea.
		paths, _ = _critical_branches({"X"}, [], {"X": {"es": "d1"}})
		self.assertEqual(paths, [["X"]])

	def test_severity_classifiers_ssot(self):
		# SSOT de clasificación: contadores 0→ok/>0→bad; margen negativo→bad; holgura mínima 0 es NORMAL→ok.
		self.assertEqual(_sev_count(0), SEV_OK)
		self.assertEqual(_sev_count(3), SEV_BAD)
		self.assertEqual(_sev_margin(5), SEV_OK)
		self.assertEqual(_sev_margin(-1), SEV_BAD)
		self.assertIsNone(_sev_margin(None))
		self.assertEqual(_sev_min_slack(0), SEV_OK)  # 0 = hay ruta crítica, es normal (no rojo)
		self.assertEqual(_sev_min_slack(-2), SEV_BAD)
		self.assertEqual(_sev_flag(True), SEV_WARN)
		self.assertEqual(_sev_flag(False), SEV_OK)

	def test_days_label_ssot(self):
		# Label de días ya formateado por el dominio (el template no deriva el signo).
		self.assertEqual(_days_label(121), "+121 d")
		self.assertEqual(_days_label(0), "0 d")
		self.assertEqual(_days_label(-5), "-5 d")
		self.assertIsNone(_days_label(None))


# ----------------------------------------------------------------------------------------------------
# Nivel integración: Project/Task/Task Depends On + Holiday List reales.
# ----------------------------------------------------------------------------------------------------
def _holiday_list():
	if frappe.db.exists("Holiday List", HL):
		return HL
	holidays = [{"holiday_date": "2026-01-06", "description": "Festivo"}]
	# Fines de semana de enero 2026 como festivos explícitos (para que is_holiday los reconozca).
	for sat, sun in (
		("2026-01-03", "2026-01-04"),
		("2026-01-10", "2026-01-11"),
		("2026-01-17", "2026-01-18"),
		("2026-01-24", "2026-01-25"),
		("2026-01-31", "2026-02-01"),
	):
		holidays.append({"holiday_date": sat, "description": "Sábado"})
		holidays.append({"holiday_date": sun, "description": "Domingo"})
	frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": HL,
			"from_date": "2026-01-01",
			"to_date": "2026-02-28",
			"holidays": holidays,
		}
	).insert(ignore_permissions=True)
	return HL


def _project(name, holiday_list=HL, expected_end_date=None):
	# El site de tests no tiene Company (igual que el resto de tests de pmo): se omite con ignore_mandatory.
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": name,
			"holiday_list": holiday_list,
			"expected_start_date": "2026-01-01",
			"expected_end_date": expected_end_date,
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)
	return doc.name


def _task(
	project,
	subject,
	start=None,
	end=None,
	deps=None,
	is_group=0,
	is_milestone=0,
	status="Open",
	deadline=None,
):
	doc = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"project": project,
			"status": status,
			"is_group": is_group,
			"is_milestone": is_milestone,
			"exp_start_date": start,
			"exp_end_date": end,
			"pmo_deadline": deadline,
			"depends_on": [{"task": d} for d in (deps or [])],
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)
	return doc.name


class TestScheduleIntegrity(IntegrationTestCase):
	def setUp(self):
		_holiday_list()

	# --- calendario y degradación ------------------------------------------------------------------

	def test_calendar_resolution_direct(self):
		# Project con holiday_list propia → se usa esa.
		p = _project("Sched Cal")
		self.assertEqual(resolve_holiday_list(p), HL)

	def test_calendar_fallback_to_company(self):
		# Sin holiday_list del Project → Company.default_holiday_list (vía el `company` del Project).
		with patch("pmo.scheduling.frappe.db.get_value", return_value=HL):
			self.assertEqual(resolve_holiday_list("X", meta={"holiday_list": None, "company": "ACME"}), HL)

	def test_no_calendar_degrades_safely(self):
		# Sin holiday_list ni compañía: no lanza, marca sin_calendario y omite chequeos de calendario.
		p = _project("Sched NoCal", holiday_list=None)
		_task(p, "T", "2026-01-05", "2026-01-09")
		res = analyze_schedule_integrity(p)
		self.assertFalse(res["calendar_available"])
		self.assertTrue(res["summary"]["sin_calendario"])
		self.assertEqual(res["diagnostics"]["non_working_day"], [])
		self.assertEqual(res["diagnostics"]["natural_vs_working"], [])

	# --- diagnósticos de red -----------------------------------------------------------------------

	def test_valid_fs_chain_no_findings(self):
		# Cadena FS coherente en días hábiles: sin incidencias.
		p = _project("Sched Valid", expected_end_date="2026-01-09")
		a = _task(p, "A", "2026-01-01", "2026-01-02")
		_task(p, "B", "2026-01-07", "2026-01-09", deps=[a])
		res = analyze_schedule_integrity(p)
		d = res["diagnostics"]
		self.assertEqual(d["incoherent"], [])
		self.assertEqual(d["cycles"], [])
		self.assertEqual(d["incomplete_dates"], [])

	def test_incoherent_dependency(self):
		# B inicia (01-07) antes de que A termine (01-09) → FS violado.
		p = _project("Sched Incoh")
		a = _task(p, "A", "2026-01-05", "2026-01-09")
		_task(p, "B", "2026-01-07", "2026-01-13", deps=[a])
		res = analyze_schedule_integrity(p)
		self.assertEqual(len(res["diagnostics"]["incoherent"]), 1)
		self.assertGreaterEqual(res["summary"]["incoherencias"], 1)
		# SSOT: la severidad la decide el dominio (no el template).
		self.assertEqual(res["summary"]["sev"]["incoherencias"], SEV_BAD)
		self.assertEqual(res["summary"]["sev"]["total"], SEV_BAD)

	def test_integrity_severity_clean_is_ok(self):
		# Proyecto sin problemas → todas las severidades "ok" (el template pinta neutro, no rojo).
		p = _project("Sched Clean")
		a = _task(p, "A", "2026-01-05", "2026-01-07")
		_task(p, "B", "2026-01-08", "2026-01-09", deps=[a])
		summ = analyze_schedule_integrity(p)["summary"]
		self.assertEqual(set(summ["sev"].values()), {SEV_OK})
		self.assertFalse(summ["show_ciclos"])  # SSOT: visibilidad de la fila decidida en el dominio

	def test_multi_predecessor_inconsistent(self):
		# C depende de A y B; inicia antes del fin de alguna predecesora.
		p = _project("Sched Multi")
		a = _task(p, "A", "2026-01-05", "2026-01-07")
		b = _task(p, "B", "2026-01-05", "2026-01-13")
		_task(p, "C", "2026-01-08", "2026-01-14", deps=[a, b])
		res = analyze_schedule_integrity(p)
		self.assertEqual(len(res["diagnostics"]["multi_predecessor"]), 1)

	def test_cycle_detection(self):
		# A→B y B→A (ciclo). Se reporta y se omite el forward pass (max_ef None).
		p = _project("Sched Cycle")
		a = _task(p, "A", "2026-01-05", "2026-01-07")
		b = _task(p, "B", "2026-01-08", "2026-01-09", deps=[a])
		# Añade la arista inversa B→A directamente (evita validación de fechas).
		frappe.get_doc(
			{
				"doctype": "Task Depends On",
				"parent": a,
				"parenttype": "Task",
				"parentfield": "depends_on",
				"task": b,
			}
		).insert(ignore_permissions=True)
		res = analyze_schedule_integrity(p)
		self.assertGreaterEqual(len(res["diagnostics"]["cycles"]), 1)
		self.assertIsNone(res["ends"]["max_ef"])
		self.assertTrue(res["summary"]["show_ciclos"])  # SSOT: la fila se muestra por decisión del dominio

	def test_incomplete_dates(self):
		# Tarea activa sin exp_end → gap de planeación.
		p = _project("Sched Incomplete")
		_task(p, "T", "2026-01-05", None)
		res = analyze_schedule_integrity(p)
		self.assertEqual(len(res["diagnostics"]["incomplete_dates"]), 1)
		self.assertEqual(res["diagnostics"]["incomplete_dates"][0]["missing"], ["end"])

	def test_group_and_completed_cancelled_excluded(self):
		# Grupo (is_group) no es nodo; Completed/Cancelled fuera de la red activa.
		p = _project("Sched Excluded")
		_task(p, "G", "2026-01-05", "2026-01-09", is_group=1)
		_task(p, "Done", "2026-01-05", None, status="Completed")
		_task(p, "Cxl", "2026-01-05", None, status="Cancelled")
		res = analyze_schedule_integrity(p)
		# Ninguno aparece como fechas incompletas (grupo excluido por is_group; Done/Cxl por estado).
		self.assertEqual(res["diagnostics"]["incomplete_dates"], [])

	def test_milestone_no_duration_divergence(self):
		# Hito (start==end) no genera divergencia hábil/natural ni día-no-laborable por duración.
		p = _project("Sched Milestone")
		_task(p, "M", "2026-01-07", "2026-01-07", is_milestone=1)
		res = analyze_schedule_integrity(p)
		self.assertEqual(res["diagnostics"]["natural_vs_working"], [])

	def test_non_working_day_boundary(self):
		# Fin en festivo (2026-01-06) → señal de límite en día no laborable.
		p = _project("Sched NWD")
		_task(p, "T", "2026-01-05", "2026-01-06")
		res = analyze_schedule_integrity(p)
		hits = [r for r in res["diagnostics"]["non_working_day"] if r["which"] == "end"]
		self.assertEqual(len(hits), 1)

	def test_natural_vs_working_divergence(self):
		# 01-05→01-09 incluye el festivo 01-06 → 5 naturales vs 4 hábiles.
		p = _project("Sched Diverge")
		_task(p, "T", "2026-01-05", "2026-01-09")
		res = analyze_schedule_integrity(p)
		rows = res["diagnostics"]["natural_vs_working"]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["calendar_days"], 5)
		self.assertEqual(rows[0]["working_days"], 4)

	def test_deadline_exceeded_and_met(self):
		# T1 excede su pmo_deadline (fin > deadline); T2 lo cumple.
		p = _project("Sched Deadline")
		_task(p, "T1", "2026-01-05", "2026-01-13", deadline="2026-01-09")
		_task(p, "T2", "2026-01-05", "2026-01-07", deadline="2026-01-09")
		res = analyze_schedule_integrity(p)
		ex = res["diagnostics"]["deadline_exceeded"]
		self.assertEqual(len(ex), 1)
		self.assertEqual(ex[0]["slip_days"], 4)  # 01-13 - 01-09

	def test_ends_reconciliation_divergence(self):
		# max(exp_end) y Project.expected_end_date distintos → fines divergen (diagnóstico).
		p = _project("Sched Ends", expected_end_date="2026-01-20")
		_task(p, "T", "2026-01-05", "2026-01-09")
		res = analyze_schedule_integrity(p)
		self.assertTrue(res["ends"]["diverges"])
		self.assertEqual(res["ends"]["max_exp_end"], "2026-01-09")
		self.assertEqual(res["ends"]["project_expected_end"], "2026-01-20")

	# --- garantía read-only ------------------------------------------------------------------------

	def test_analyze_never_writes(self):
		# Ni muta fechas ni invoca set_value: Schedule Intelligence es estrictamente read-only (ADR-0017).
		p = _project("Sched ReadOnly")
		t = _task(p, "T", "2026-01-05", "2026-01-09", deadline="2026-01-07")
		before = frappe.db.get_value("Task", t, ["exp_start_date", "exp_end_date"], as_dict=True)
		with patch("frappe.db.set_value") as mock_set:
			analyze_schedule_integrity(p)
			mock_set.assert_not_called()
		after = frappe.db.get_value("Task", t, ["exp_start_date", "exp_end_date"], as_dict=True)
		self.assertEqual(before, after)


class TestScheduleSlack(IntegrationTestCase):
	"""I.2 — Slack/Float read-only sobre la red FS con calendario laboral real (HL)."""

	def setUp(self):
		_holiday_list()

	def _by_task(self, res):
		return {n["task"]: n for n in res["nodes"]}

	def test_slack_linear_chain_all_critical(self):
		# A→B→C lineal en días hábiles (B salta el festivo 01-06). Toda la cadena es crítica (holgura 0).
		p = _project("Slack Linear")
		a = _task(p, "A", "2026-01-01", "2026-01-02")
		b = _task(p, "B", "2026-01-05", "2026-01-07", deps=[a])
		_task(p, "C", "2026-01-08", "2026-01-09", deps=[b])
		res = analyze_schedule_slack(p)
		self.assertTrue(res["evaluable"])
		self.assertEqual(res["project_finish"], "2026-01-09")
		self.assertEqual(res["summary"]["critical_count"], 3)
		self.assertEqual(res["summary"]["min_total_slack"], 0)
		self.assertTrue(all(n["total_slack"] == 0 for n in res["nodes"]))

	def test_slack_diamond_positive_zero_multi(self):
		# Diamante A→{B,C}→D: B es la rama larga (crítica), C la corta (holgura +). D tiene 2 predecesoras;
		# A tiene 2 sucesoras. Cubre holgura positiva, holgura cero y múltiples sucesoras/predecesoras.
		p = _project("Slack Diamond")
		a = _task(p, "A", "2026-01-01", "2026-01-01")
		b = _task(p, "B", "2026-01-02", "2026-01-08", deps=[a])  # rama larga (4 d háb)
		c = _task(p, "C", "2026-01-02", "2026-01-02", deps=[a])  # rama corta (1 d háb)
		d = _task(p, "D", "2026-01-09", "2026-01-09", deps=[b, c])
		res = analyze_schedule_slack(p)
		self.assertTrue(res["evaluable"])
		self.assertEqual(res["project_finish"], "2026-01-09")
		nodes = self._by_task(res)
		self.assertEqual(nodes[a]["total_slack"], 0)  # A crítica
		self.assertEqual(nodes[b]["total_slack"], 0)  # B crítica (rama larga)
		self.assertEqual(nodes[d]["total_slack"], 0)  # D crítica (sumidero)
		self.assertEqual(nodes[c]["total_slack"], 3)  # C con holgura positiva
		self.assertEqual(nodes[c]["free_slack"], 3)  # libre, no mueve el ES de D
		self.assertFalse(nodes[c]["is_critical"])
		self.assertEqual(res["summary"]["critical_count"], 3)

	def test_slack_cycles_not_evaluable(self):
		# Ciclo → la red no admite CPM; holgura no evaluable (razón explícita, sin error).
		p = _project("Slack Cycle")
		a = _task(p, "A", "2026-01-05", "2026-01-07")
		b = _task(p, "B", "2026-01-08", "2026-01-09", deps=[a])
		frappe.get_doc(
			{
				"doctype": "Task Depends On",
				"parent": a,
				"parenttype": "Task",
				"parentfield": "depends_on",
				"task": b,
			}
		).insert(ignore_permissions=True)
		res = analyze_schedule_slack(p)
		self.assertFalse(res["evaluable"])
		self.assertEqual(res["reason"], "cycles")

	def test_slack_incomplete_dates_excluded(self):
		# Tarea sin fecha completa → excluida de la red (se cuenta), no inventa holgura.
		p = _project("Slack Incomplete")
		_task(p, "Full", "2026-01-05", "2026-01-07")
		_task(p, "Partial", "2026-01-05", None)
		res = analyze_schedule_slack(p)
		self.assertTrue(res["evaluable"])
		self.assertEqual(res["incomplete_excluded"], 1)
		self.assertEqual(len(res["nodes"]), 1)

	def test_slack_no_calendar_degrades(self):
		# Sin calendario: evaluable en días naturales, con bandera; nunca error de pantalla.
		p = _project("Slack NoCal", holiday_list=None)
		_task(p, "T", "2026-01-05", "2026-01-09")
		res = analyze_schedule_slack(p)
		self.assertTrue(res["evaluable"])
		self.assertTrue(res["summary"]["sin_calendario"])

	def test_slack_margin_vs_committed_separate(self):
		# Margen de red vs compromiso = señal SEPARADA (no ancla). Compromiso posterior → margen positivo.
		p = _project("Slack Margin")
		_task(p, "T", "2026-01-05", "2026-01-09")  # fin de red = 01-09
		frappe.db.set_value("Project", p, "pmo_committed_end_date", "2026-01-15")
		res = analyze_schedule_slack(p)
		self.assertEqual(res["margin_vs_committed"]["network_finish"], "2026-01-09")
		self.assertEqual(res["summary"]["committed_margin_days"], 4)  # 01-09→01-15 = 4 d háb
		# SSOT: label de signo y bandera de visibilidad resueltos en el dominio (el template no deriva).
		self.assertEqual(res["summary"]["committed_margin_label"], "+4 d")
		self.assertTrue(res["summary"]["show_committed_margin"])

	def test_slack_deadline_breach_vs_margin_separate(self):
		# Señal SEPARADA basada en el FORECAST (EF), no en LF: incumplido ⇔ EF > deadline. Un deadline
		# POSTERIOR al EF no es incumplimiento: deja margen hábil positivo (evita falsos positivos).
		p = _project("Slack Deadline")
		breach = _task(p, "Breach", "2026-01-05", "2026-01-09", deadline="2026-01-07")  # EF 01-09 > 01-07
		margin = _task(p, "Margin", "2026-01-05", "2026-01-09", deadline="2026-01-15")  # EF 01-09 < 01-15
		res = analyze_schedule_slack(p)
		self.assertEqual(res["summary"]["deadline_breach_count"], 1)  # solo "Breach"
		self.assertTrue(res["summary"]["show_deadline_breach"])  # SSOT: visibilidad desde el dominio
		b = res["deadline_breach"][0]
		self.assertEqual(b["task"], breach)
		self.assertEqual(b["ef"], "2026-01-09")
		self.assertEqual(b["over_days"], 2)  # 01-07→01-09 = 2 d háb
		nodes = self._by_task(res)
		self.assertEqual(nodes[breach]["deadline_margin"], -2)  # EF excede el deadline por 2 d háb
		self.assertEqual(nodes[margin]["deadline_margin"], 4)  # 01-09→01-15 = +4 d háb de colchón
		# SSOT: severidad por nodo decidida en el dominio (no re-evaluada en el template).
		self.assertEqual(nodes[breach]["deadline_sev"], SEV_BAD)
		self.assertEqual(nodes[margin]["deadline_sev"], SEV_OK)

	def test_slack_severities_from_domain_ssot(self):
		# El dominio entrega slack_sev por nodo, severidad de margen y resumen; el template solo mapea.
		p = _project("Slack Sev")
		a = _task(p, "A", "2026-01-01", "2026-01-01")
		b = _task(p, "B", "2026-01-02", "2026-01-08", deps=[a])
		c = _task(p, "C", "2026-01-02", "2026-01-02", deps=[a])
		_task(p, "D", "2026-01-09", "2026-01-09", deps=[b, c])
		frappe.db.set_value("Project", p, "pmo_committed_end_date", "2026-01-15")
		res = analyze_schedule_slack(p)
		nodes = self._by_task(res)
		self.assertEqual(nodes[a]["slack_sev"], SEV_BAD)  # crítica → bad
		self.assertEqual(nodes[c]["slack_sev"], SEV_OK)  # con holgura → ok
		# Holgura mínima es 0 (hay ruta crítica): NORMAL → ok, NO rojo (corrección del <= 0).
		self.assertEqual(res["summary"]["sev"]["min_total_slack"], SEV_OK)
		self.assertEqual(res["summary"]["sev"]["critical_count"], SEV_WARN)
		self.assertEqual(res["margin_vs_committed"]["severity"], SEV_OK)  # +margen
		self.assertEqual(res["summary"]["sev"]["committed_margin"], SEV_OK)
		# SSOT: labels de presentación ya resueltos por el dominio.
		self.assertEqual(res["summary"]["min_total_slack_label"], "0 d")
		self.assertEqual(res["summary"]["committed_margin_label"], "+4 d")

	def test_slack_never_writes(self):
		# Read-only estricto (ADR-0017): no muta fechas ni invoca set_value.
		p = _project("Slack ReadOnly")
		a = _task(p, "A", "2026-01-05", "2026-01-07")
		t = _task(p, "B", "2026-01-08", "2026-01-09", deps=[a])
		before = frappe.db.get_value("Task", t, ["exp_start_date", "exp_end_date"], as_dict=True)
		with patch("frappe.db.set_value") as mock_set:
			analyze_schedule_slack(p)
			mock_set.assert_not_called()
		after = frappe.db.get_value("Task", t, ["exp_start_date", "exp_end_date"], as_dict=True)
		self.assertEqual(before, after)


class TestCriticalPath(IntegrationTestCase):
	"""I.3 — Interpretación/visualización de la ruta crítica (sobre el CPM de I.2). READ-ONLY."""

	def setUp(self):
		_holiday_list()

	def test_critical_linear_single_branch(self):
		# Cadena lineal → una sola ruta crítica legible A→B→C; ventana y duración hábil de la ruta.
		p = _project("CP Linear")
		a = _task(p, "A", "2026-01-01", "2026-01-02")
		b = _task(p, "B", "2026-01-05", "2026-01-07", deps=[a])
		_task(p, "C", "2026-01-08", "2026-01-09", deps=[b])
		res = analyze_critical_path(p)
		self.assertTrue(res["evaluable"])
		self.assertEqual(res["summary"]["critical_count"], 3)
		self.assertEqual(res["summary"]["branch_count"], 1)
		self.assertFalse(res["summary"]["multi_branch"])
		self.assertEqual(res["summary"]["start"], "2026-01-01")
		self.assertEqual(res["summary"]["end"], "2026-01-09")
		self.assertEqual(res["summary"]["duration_working_days"], 6)  # 01-01..01-09 sin 03/04/06
		self.assertEqual([s["subject"] for s in res["branches"][0]["sequence"]], ["A", "B", "C"])
		# SSOT: bloque visible y severidad de rama única resueltos en el dominio.
		self.assertTrue(res["summary"]["show"])
		self.assertEqual(res["summary"]["sev"]["multi_branch"], SEV_OK)

	def test_critical_diamond_excludes_noncritical(self):
		# Diamante con rama corta no crítica (C, holgura +): la ruta crítica es A→B→D; C queda fuera.
		p = _project("CP Diamond")
		a = _task(p, "A", "2026-01-01", "2026-01-01")
		b = _task(p, "B", "2026-01-02", "2026-01-08", deps=[a])
		c = _task(p, "C", "2026-01-02", "2026-01-02", deps=[a])
		d = _task(p, "D", "2026-01-09", "2026-01-09", deps=[b, c])
		res = analyze_critical_path(p)
		self.assertEqual(res["summary"]["branch_count"], 1)
		self.assertEqual(set(res["task_names"]), {a, b, d})  # C excluido (no crítico)
		self.assertNotIn(c, res["task_names"])
		self.assertEqual([s["task"] for s in res["branches"][0]["sequence"]], [a, b, d])

	def test_critical_multiple_branches(self):
		# Dos ramas paralelas de igual duración con slack 0 → DOS rutas (no se inventa una sola cadena).
		p = _project("CP MultiBranch")
		a = _task(p, "A", "2026-01-01", "2026-01-01")
		b = _task(p, "B", "2026-01-02", "2026-01-02", deps=[a])
		c = _task(p, "C", "2026-01-02", "2026-01-02", deps=[a])
		d = _task(p, "D", "2026-01-05", "2026-01-05", deps=[b, c])
		res = analyze_critical_path(p)
		self.assertEqual(res["summary"]["critical_count"], 4)
		self.assertTrue(res["summary"]["multi_branch"])
		self.assertEqual(res["summary"]["branch_count"], 2)
		seqs = sorted([s["task"] for s in br["sequence"]] for br in res["branches"])
		self.assertEqual(seqs, sorted([[a, b, d], [a, c, d]]))
		# SSOT: "varias ramas" → warn decidido por el dominio (NO hardcodeado en el template).
		self.assertEqual(res["summary"]["sev"]["multi_branch"], SEV_WARN)
		self.assertTrue(res["summary"]["show"])

	def test_critical_cycles_not_evaluable(self):
		p = _project("CP Cycle")
		a = _task(p, "A", "2026-01-05", "2026-01-07")
		b = _task(p, "B", "2026-01-08", "2026-01-09", deps=[a])
		frappe.get_doc(
			{
				"doctype": "Task Depends On",
				"parent": a,
				"parenttype": "Task",
				"parentfield": "depends_on",
				"task": b,
			}
		).insert(ignore_permissions=True)
		res = analyze_critical_path(p)
		self.assertFalse(res["evaluable"])
		self.assertEqual(res["reason"], "cycles")

	def test_critical_no_dated_tasks(self):
		p = _project("CP NoDates")
		_task(p, "T", None, None)
		res = analyze_critical_path(p)
		self.assertFalse(res["evaluable"])
		self.assertEqual(res["reason"], "no_dated_tasks")
		# SSOT: sin ruta → el Resumen no muestra el bloque (bandera del dominio, no `if` en el template).
		self.assertFalse(res["summary"]["show"])

	def test_critical_never_writes(self):
		p = _project("CP ReadOnly")
		a = _task(p, "A", "2026-01-05", "2026-01-07")
		t = _task(p, "B", "2026-01-08", "2026-01-09", deps=[a])
		before = frappe.db.get_value("Task", t, ["exp_start_date", "exp_end_date"], as_dict=True)
		with patch("frappe.db.set_value") as mock_set:
			analyze_critical_path(p)
			mock_set.assert_not_called()
		after = frappe.db.get_value("Task", t, ["exp_start_date", "exp_end_date"], as_dict=True)
		self.assertEqual(before, after)


if __name__ == "__main__":
	unittest.main()
