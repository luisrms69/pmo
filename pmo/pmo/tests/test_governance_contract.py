# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Gobernanza V1 — tests del CONTRATO de desviaciones (no del HTML).

Cubre la fuente única `pmo.governance_inbox` + `is_project_started` + la exclusión gobernada. Verifica cada
regla del contrato con datos ficticios y que el resumen de cumplimiento use EXACTAMENTE las mismas reglas
que la bandeja. Los artefactos submittables se simulan con un stub (insert draft + docstatus=1): estos tests
prueban el MOTOR de gobernanza, no los guards de cada artefacto (que tienen sus propios tests)."""

import frappe
from frappe.exceptions import MandatoryError, PermissionError, ValidationError
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime, today

from pmo.governance import is_project_started
from pmo.governance_inbox import (
	CONTROL_ACTA,
	CONTROL_BASELINE,
	CONTROL_CHANGE,
	CONTROL_CLOSURE,
	CONTROL_ORDER,
	CONTROL_REVIEW,
	CONTROL_RISK,
	STATE_PENDIENTE,
	_evaluate,
	_facts,
	compute_deviations,
	get_project_governance,
	governance_board,
)
from pmo.project_control import _can_create, project_governance_state


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


def _project(name, owner="Administrator", company=None):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": name,
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-03-31",
				"status": "Open",
				"company": company,
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	if company:
		frappe.db.set_value("Project", pid, "company", company, update_modified=False)
	return pid


def _start(project):
	"""Fuerza 'iniciado' de forma determinista (avance real registrado)."""
	frappe.db.set_value("Project", project, "percent_complete", 10, update_modified=False)


def _terminal(project, status="Completed", actual_end="2026-03-20"):
	frappe.db.set_value(
		"Project", project, {"status": status, "actual_end_date": actual_end}, update_modified=False
	)


def _stub_submitted(doctype, project, extra=None):
	"""Inserta un artefacto de gobierno mínimo y lo marca submitted (docstatus=1) sin correr sus guards de
	submit (aislamiento: aquí se prueba el motor de gobernanza, no el artefacto)."""
	doc = frappe.get_doc({"doctype": doctype, "project": project, **(extra or {})})
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	frappe.db.set_value(doctype, doc.name, "docstatus", 1, update_modified=False)
	return doc.name


def _handoff(project):
	return _stub_submitted("PMO Project Handoff", project, {"handoff_date": today(), "handoff_summary": "x"})


def _baseline(project):
	return _stub_submitted(
		"PMO Project Baseline",
		project,
		{"baseline_type": "Original", "reason": "QA", "effective_date": today(), "revision": None},
	)


def _closure(project):
	return _stub_submitted("PMO Project Closure", project, {"closure_date": today(), "final_result": "ok"})


def _review(project):
	return _stub_submitted("PMO Post-Project Review", project, {"objectives_achieved": "ok"})


def _cr(
	project,
	state,
	docstatus=0,
	baseline_after=None,
	request_date="2026-02-01",
	impacts_schedule=0,
	impacts_scope=0,
	impacts_effort=0,
	impacts_commercial=0,
):
	doc = frappe.get_doc(
		{"doctype": "PMO Change Request", "project": project, "title": f"CR {state}", "reason": "x"}
	)
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	frappe.db.set_value(
		"PMO Change Request",
		doc.name,
		{
			"workflow_state": state,
			"docstatus": docstatus,
			"request_date": request_date,
			"approved_at": now_datetime() if state in ("Approved", "Implemented") else None,
			"applied_at": now_datetime() if state == "Implemented" else None,
			"baseline_after": baseline_after,
			"impacts_schedule": impacts_schedule,
			"impacts_scope": impacts_scope,
			"impacts_effort": impacts_effort,
			"impacts_commercial": impacts_commercial,
		},
		update_modified=False,
	)
	return doc.name


def _assessment(project):
	return (
		frappe.get_doc({"doctype": "PMO Project Risk Assessment", "project": project})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _risk(project, owner=None, response=None, exposure=None, status="Open"):
	return (
		frappe.get_doc(
			{
				"doctype": "PMO Project Risk",
				"project": project,
				"description": "riesgo",
				"status": status,
				"risk_owner": owner,
				"response": response,
				"exposure": exposure,
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _controls_in_deviations(project):
	return {r["control"] for r in compute_deviations(project)}


class TestGovernanceContract(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	# --- BLOQUE 2: iniciado = status in ("Open","On hold") (regla funcional aprobada, definitiva) -------
	def test_started_rule_open_or_on_hold(self):
		# Iniciado ⇔ Project.status ∈ {Open, On hold}. Ni fechas, ni %, ni baseline, ni Handoff lo determinan.
		p = _project("GC-START")  # Open
		self.assertTrue(is_project_started(p))
		frappe.db.set_value("Project", p, "status", "On hold", update_modified=False)
		self.assertTrue(is_project_started(p))  # On hold = iniciado y pausado (mantiene obligaciones)
		frappe.db.set_value("Project", p, "status", "Completed", update_modified=False)
		self.assertFalse(is_project_started(p))  # terminal (se gobierna por Cierre/Revisión)
		frappe.db.set_value("Project", p, "status", "Cancelled", update_modified=False)
		self.assertFalse(is_project_started(p))

	def test_terminal_project_acta_baseline_not_applicable(self):
		# Un Project terminal (Cancelled) NO es "iniciado": Acta/Baseline quedan not_applicable (no pending).
		p = _project("GC-CANCELLED")
		frappe.db.set_value("Project", p, "status", "Cancelled", update_modified=False)
		ctrls = _evaluate(_facts(p))
		self.assertEqual(ctrls[CONTROL_ACTA]["state"], "no_aplica")
		self.assertEqual(ctrls[CONTROL_BASELINE]["state"], "no_aplica")

	def test_on_hold_project_acta_and_baseline_apply(self):
		# On hold = iniciado: Acta y Línea base aplican EXACTAMENTE igual que Open (la pausa no exime).
		p = _project("GC-ONHOLD")
		frappe.db.set_value("Project", p, "status", "On hold", update_modified=False)
		ctrls = _evaluate(_facts(p))
		# On hold sin Handoff ni baseline → ambas pendientes / PM, simultáneas.
		self.assertEqual(ctrls[CONTROL_ACTA]["state"], "pendiente")
		self.assertEqual(ctrls[CONTROL_ACTA]["action_owner"], "PM")
		self.assertEqual(ctrls[CONTROL_BASELINE]["state"], "pendiente")
		self.assertEqual(ctrls[CONTROL_BASELINE]["action_owner"], "PM")
		devs = _controls_in_deviations(p)
		self.assertIn(CONTROL_ACTA, devs)
		self.assertIn(CONTROL_BASELINE, devs)
		# On hold con Handoff → Acta complete.
		_handoff(p)
		self.assertEqual(_evaluate(_facts(p))[CONTROL_ACTA]["state"], "completo")

	# --- Casos anti-regresion A-E (definición aprobada de "iniciado") -------------------------------
	def test_case_A_open_no_handoff_acta_pending_pm(self):
		# Open, percent 0, sin actual_start, sin Handoff → Acta = pending / PM.
		p = _project("GC-CASE-A")  # Open, percent_complete=0, actual_start_date vacío por defecto
		self.assertTrue(is_project_started(p))
		acta = _evaluate(_facts(p))[CONTROL_ACTA]
		self.assertEqual(acta["state"], "pendiente")
		self.assertEqual(acta["action_owner"], "PM")

	def test_case_B_open_with_handoff_acta_complete(self):
		p = _project("GC-CASE-B")
		_handoff(p)
		self.assertEqual(_evaluate(_facts(p))[CONTROL_ACTA]["state"], "completo")

	def test_case_C_open_no_baseline_baseline_pending_pm(self):
		# Open, percent 0, sin actual_start, sin baseline → Línea base = pending / PM.
		p = _project("GC-CASE-C")
		base = _evaluate(_facts(p))[CONTROL_BASELINE]
		self.assertEqual(base["state"], "pendiente")
		self.assertEqual(base["action_owner"], "PM")

	def test_case_D_open_no_handoff_no_baseline_both_pending(self):
		# Ambas desviaciones simultáneas; una no oculta la otra.
		p = _project("GC-CASE-D")
		devs = _controls_in_deviations(p)
		self.assertIn(CONTROL_ACTA, devs)
		self.assertIn(CONTROL_BASELINE, devs)

	def test_case_E_open_with_baseline_still_started(self):
		# Open + baseline + percent 0 + sin actual_start → sigue iniciado; baseline = complete.
		p = _project("GC-CASE-E")
		_baseline(p)
		self.assertTrue(is_project_started(p))  # Open ⇒ iniciado, sin importar % ni fechas
		self.assertEqual(_evaluate(_facts(p))[CONTROL_BASELINE]["state"], "completo")

	# --- A. ACTA --------------------------------------------------------------
	def test_started_without_acta(self):
		p = _project("GC-NOACTA")
		_start(p)
		devs = {r["control"]: r for r in compute_deviations(p)}
		self.assertIn(CONTROL_ACTA, devs)
		self.assertEqual(devs[CONTROL_ACTA]["action_owner"], "PM")
		self.assertIsNotNone(devs[CONTROL_ACTA]["situation"])

	# --- B. BASELINE (independiente del Acta) ---------------------------------
	def test_started_with_acta_without_baseline(self):
		p = _project("GC-NOBASE")
		_start(p)
		_handoff(p)
		ctrls = _evaluate(_facts(p))
		self.assertEqual(ctrls[CONTROL_ACTA]["state"], "completo")
		self.assertEqual(ctrls[CONTROL_BASELINE]["state"], STATE_PENDIENTE)
		devs = _controls_in_deviations(p)
		self.assertNotIn(CONTROL_ACTA, devs)
		self.assertIn(CONTROL_BASELINE, devs)

	def test_missing_acta_does_not_hide_missing_baseline(self):
		# Iniciado sin Acta NI baseline: AMBAS desviaciones deben aparecer (la ausencia de Acta no oculta baseline).
		p = _project("GC-BOTH")
		_start(p)
		devs = _controls_in_deviations(p)
		self.assertIn(CONTROL_ACTA, devs)
		self.assertIn(CONTROL_BASELINE, devs)

	# --- C. RIESGOS -----------------------------------------------------------
	def test_risk_not_applicable_before_baseline(self):
		p = _project("GC-RISK-NOBASE")
		_start(p)
		_assessment(p)
		_risk(p)  # sin owner ni respuesta, pero SIN baseline ⇒ riesgos no aplica
		self.assertEqual(_evaluate(_facts(p))[CONTROL_RISK]["state"], "no_aplica")
		self.assertNotIn(CONTROL_RISK, _controls_in_deviations(p))

	def test_risk_missing_assessment_after_baseline_is_deviation(self):
		# Con la primera baseline, la gobernanza de riesgos es obligatoria: SIN evaluación de riesgos = desviación.
		p = _project("GC-RISK-NOASSESS")
		_start(p)
		_baseline(p)  # sin ningún Risk Assessment
		devs = {r["control"]: r for r in compute_deviations(p)}
		self.assertIn(CONTROL_RISK, devs)
		self.assertEqual(devs[CONTROL_RISK]["action_owner"], "PM")
		self.assertIn("sin evaluación de riesgos", devs[CONTROL_RISK]["situation"])

	def test_high_risk_well_managed_is_not_deviation(self):
		p = _project("GC-RISK-OK")
		_start(p)
		_baseline(p)
		_assessment(p)
		_risk(p, owner="Administrator", response="mitigar", exposure="High exposure")
		self.assertEqual(_evaluate(_facts(p))[CONTROL_RISK]["state"], "completo")
		self.assertNotIn(CONTROL_RISK, _controls_in_deviations(p))

	def test_risk_deficiency_is_deviation(self):
		p = _project("GC-RISK-BAD")
		_start(p)
		_baseline(p)
		_assessment(p)
		_risk(p, owner=None, response=None)  # activo sin responsable ni respuesta
		devs = {r["control"]: r for r in compute_deviations(p)}
		self.assertIn(CONTROL_RISK, devs)
		self.assertEqual(devs[CONTROL_RISK]["action_owner"], "PM")

	# --- D. CHANGE CONTROL ----------------------------------------------------
	def test_change_in_review_is_pmo(self):
		p = _project("GC-CR-REVIEW")
		_cr(p, "In Review", docstatus=0)
		devs = {r["control"]: r for r in compute_deviations(p) if r["control"] == CONTROL_CHANGE}
		self.assertIn(CONTROL_CHANGE, devs)
		self.assertEqual(devs[CONTROL_CHANGE]["action_owner"], "PMO")

	def test_change_draft_and_approved_are_pm(self):
		p = _project("GC-CR-PM")
		_cr(p, "Draft", docstatus=0)
		_cr(p, "Approved", docstatus=1)
		owners = {r["action_owner"] for r in compute_deviations(p) if r["control"] == CONTROL_CHANGE}
		self.assertEqual(owners, {"PM"})
		self.assertEqual(len([r for r in compute_deviations(p) if r["control"] == CONTROL_CHANGE]), 2)

	def test_change_implemented_affecting_baseline_needs_rebaseline(self):
		# Implementado que AFECTA el plan congelado (impacts_schedule) y sin baseline_after → rebaseline PM.
		p = _project("GC-CR-IMPL")
		_cr(p, "Implemented", docstatus=1, baseline_after=None, impacts_schedule=1)
		rows = [r for r in compute_deviations(p) if r["control"] == CONTROL_CHANGE]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["action_owner"], "PM")
		self.assertIn("re-baseline", rows[0]["situation"])

	def test_change_implemented_not_affecting_baseline_no_rebaseline(self):
		# Implementado que NO afecta el plan congelado (solo comercial) → NO exige rebaseline.
		p = _project("GC-CR-IMPL-COMM")
		_cr(p, "Implemented", docstatus=1, baseline_after=None, impacts_commercial=1)
		self.assertNotIn(CONTROL_CHANGE, _controls_in_deviations(p))

	def test_change_implemented_with_rebaseline_resolved(self):
		p = _project("GC-CR-REBASE")
		bl = _baseline(p)
		_cr(p, "Implemented", docstatus=1, baseline_after=bl, impacts_schedule=1)
		self.assertNotIn(CONTROL_CHANGE, _controls_in_deviations(p))

	# --- E. CIERRE ------------------------------------------------------------
	def test_terminal_without_closure(self):
		p = _project("GC-NOCLOSE")
		_terminal(p, "Completed")
		devs = {r["control"]: r for r in compute_deviations(p)}
		self.assertIn(CONTROL_CLOSURE, devs)
		self.assertEqual(devs[CONTROL_CLOSURE]["action_owner"], "PM")

	# --- F. REVISIÓN POSTERIOR ------------------------------------------------
	def test_closure_without_review_is_pmo(self):
		p = _project("GC-NOREVIEW")
		_terminal(p, "Completed")
		_closure(p)
		devs = {r["control"]: r for r in compute_deviations(p)}
		self.assertIn(CONTROL_REVIEW, devs)
		self.assertEqual(devs[CONTROL_REVIEW]["action_owner"], "PMO")
		self.assertNotIn(CONTROL_CLOSURE, devs)  # cierre completo

	# --- Gobernanza completa --------------------------------------------------
	def test_fully_governed_no_deviations(self):
		p = _project("GC-CLEAN")
		_start(p)
		_handoff(p)
		_baseline(p)
		_assessment(p)  # con baseline, la evaluación de riesgos es obligatoria; sin riesgos con carencia
		# sin CR abiertos, sin riesgos con carencia, no terminal
		self.assertEqual(compute_deviations(p), [])

	# --- Exclusión ------------------------------------------------------------
	def test_exempt_project_has_no_deviations(self):
		p = _project("GC-EXEMPT")
		_start(p)  # iniciado sin Acta ⇒ tendría desviación si no estuviera exento
		frappe.db.set_value(
			"Project", p, {"pmo_governance_exempt": 1, "pmo_exempt_reason": "piloto"}, update_modified=False
		)
		g = get_project_governance(p)
		self.assertTrue(g["exempt"])
		self.assertEqual(g["deviations"], [])

	# --- Resumen == bandeja (misma regla) -------------------------------------
	def test_compliance_matches_inbox_rules(self):
		p = _project("GC-CONSIST")
		_start(p)
		_handoff(p)  # acta completo; baseline pendiente
		_cr(p, "In Review", docstatus=0)  # change pendiente
		ctrls = _evaluate(_facts(p))
		pendientes = {k for k, v in ctrls.items() if v.get("state") == STATE_PENDIENTE}
		en_bandeja = _controls_in_deviations(p)
		self.assertEqual(pendientes, en_bandeja)


class TestGovernanceExemptionGuard(IntegrationTestCase):
	"""BLOQUE 1 — la exclusión de gobernanza es gobernada: PM no puede autoexcluir; PMO sí; motivo obligatorio."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_pm_cannot_self_exempt(self):
		pm = _user("gc-pm@example.com", ["Projects User"])
		p = _project("GC-EX-PM", owner=pm)
		frappe.set_user(pm)
		try:
			doc = frappe.get_doc("Project", p)
			doc.pmo_governance_exempt = 1
			doc.pmo_exempt_reason = "intento del PM"
			with self.assertRaises(PermissionError):
				doc.save()
		finally:
			frappe.set_user("Administrator")

	def test_pmo_manager_can_exempt_and_audit_is_server_side(self):
		mgr = _user("gc-mgr@example.com", ["Projects User", "PMO Manager"])
		p = _project("GC-EX-MGR", owner=mgr)
		frappe.set_user(mgr)
		try:
			doc = frappe.get_doc("Project", p)
			doc.pmo_governance_exempt = 1
			doc.pmo_exempt_reason = "proyecto piloto interno"
			doc.pmo_exempt_by = "Administrator"  # intento de manipular el cliente → debe ignorarse
			doc.flags.ignore_mandatory = True  # el site de tests no tiene Company; el guard corre igual
			doc.save()
			doc.reload()
			self.assertEqual(doc.pmo_exempt_by, mgr)  # sellado server-side con el usuario real
			self.assertTrue(doc.pmo_exempt_on)
		finally:
			frappe.set_user("Administrator")

	def test_reason_mandatory_when_exempt(self):
		mgr = _user("gc-mgr2@example.com", ["Projects User", "PMO Manager"])
		p = _project("GC-EX-NOREASON", owner=mgr)
		frappe.set_user(mgr)
		try:
			doc = frappe.get_doc("Project", p)
			doc.pmo_governance_exempt = 1
			doc.flags.ignore_mandatory = True  # aísla: el motivo lo exige el guard, no otro campo mandatorio
			# sin motivo → el guard debe rechazar
			with self.assertRaises((MandatoryError, ValidationError)):
				doc.save()
		finally:
			frappe.set_user("Administrator")


class TestGovernanceBoard(IntegrationTestCase):
	"""Dashboard (agregación pura del motor): seis etapas + invariante de universo + excluidos + PM/PMO."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_six_stages_in_order(self):
		b = governance_board()
		self.assertEqual([s["control"] for s in b["stages"]], list(CONTROL_ORDER))
		self.assertEqual(len(b["stages"]), 6)
		for s in b["stages"]:
			self.assertTrue(s.get("description"))

	def test_stage_counts_are_engine_aggregation_not_total_minus_complete(self):
		# completos + pendientes + no_aplica = universo gobernado (clasificación por lifecycle del motor).
		b = governance_board()
		for s in b["stages"]:
			self.assertEqual(s["completo"] + s["pendiente"] + s["no_aplica"], b["governed"])

	def test_excluded_active_project_returned_to_dashboard(self):
		# El dashboard trae los excluidos activos SIN depender del Query Report.
		p = _project("GB-EXCL")
		_start(p)
		frappe.db.set_value(
			"Project",
			p,
			{"pmo_governance_exempt": 1, "pmo_exempt_reason": "piloto QA", "pmo_exempt_by": "Administrator"},
			update_modified=False,
		)
		b = governance_board()
		excl = {e["project"]: e for e in b["excluded"]}
		self.assertIn(p, excl)
		self.assertEqual(excl[p]["reason"], "piloto QA")
		# Excluido no aparece en la bandeja ni cuenta como gobernado.
		self.assertNotIn(p, [it["project"] for it in b["items"]])

	def test_pm_and_pmo_remain_distinct_categories(self):
		# CR In Review → PMO; Acta → PM. Ambos owners aparecen y son distintos.
		p_pmo = _project("GB-PMO")
		_cr(p_pmo, "In Review", docstatus=0)
		p_pm = _project("GB-PM")
		_start(p_pm)  # acta pendiente (PM)
		b = governance_board()
		owners = {it["action_owner"] for it in b["items"]}
		self.assertIn("PMO", owners)
		self.assertIn("PM", owners)
		self.assertNotEqual("PM", "PMO")

	def test_attention_keeps_all_records_no_cap(self):
		# La bandeja conserva TODAS las filas de un proyecto (no se truncan).
		p = _project("GB-ALL")
		_start(p)  # acta + baseline (2 desviaciones)
		b = governance_board()
		mine = [it for it in b["items"] if it["project"] == p]
		self.assertEqual({it["control"] for it in mine}, {CONTROL_ACTA, CONTROL_BASELINE})


class TestProjectGovernanceState(IntegrationTestCase):
	"""Contrato contextual del Panel PMO: reutiliza `_evaluate` (misma fuente que el dashboard) y expone lo
	mínimo para presentar/operar el ciclo de UN Project. Los permisos backend siguen siendo la autoridad."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_six_controls_ordered_and_states_match_engine(self):
		p = _project("PGS-STATES")
		_handoff(p)  # acta completa; baseline pendiente
		state = project_governance_state(p)
		self.assertEqual([c["control"] for c in state["controls"]], list(CONTROL_ORDER))
		engine = _evaluate(_facts(p))
		for c in state["controls"]:
			self.assertEqual(c["state"], engine[c["control"]]["state"])  # sin reglas nuevas: refleja el motor

	def test_existing_doc_exposed_when_complete(self):
		p = _project("PGS-EXIST")
		h = _handoff(p)
		acta = next(c for c in project_governance_state(p)["controls"] if c["control"] == CONTROL_ACTA)
		self.assertEqual(acta["state"], "completo")
		self.assertEqual(acta["existing"], {"doctype": "PMO Project Handoff", "name": h})

	def test_counts_for_change_and_risk(self):
		p = _project("PGS-COUNTS")
		_baseline(p)
		_assessment(p)
		_risk(p, owner=None, response=None)  # 1 activo con carencia
		_cr(p, "In Review", docstatus=0)
		_cr(p, "Draft", docstatus=0)
		cmap = {c["control"]: c for c in project_governance_state(p)["controls"]}
		self.assertEqual(cmap[CONTROL_CHANGE]["counts"]["open"], 2)
		self.assertEqual(cmap[CONTROL_CHANGE]["counts"]["in_review"], 1)
		self.assertGreaterEqual(cmap[CONTROL_RISK]["counts"]["needs_attention"], 1)
		self.assertTrue(cmap[CONTROL_RISK]["counts"]["assessment_exists"])

	def test_pending_count_matches_deviations(self):
		p = _project("PGS-PENDING")  # Open sin nada → acta + baseline pendientes
		state = project_governance_state(p)
		self.assertEqual(state["pending_count"], len(compute_deviations(p)))
		self.assertGreaterEqual(state["pending_count"], 2)

	def test_na_reason_only_when_not_applicable(self):
		p = _project("PGS-NA")  # Open, no terminal → closure/review not_applicable
		cmap = {c["control"]: c for c in project_governance_state(p)["controls"]}
		self.assertEqual(cmap[CONTROL_CLOSURE]["state"], "no_aplica")
		self.assertTrue(cmap[CONTROL_CLOSURE]["na_reason"])  # microcopy presente
		self.assertIsNone(cmap[CONTROL_ACTA]["na_reason"])  # acta aplica (Open) → sin na_reason

	def test_exempt_short_circuits(self):
		p = _project("PGS-EXEMPT")
		frappe.db.set_value(
			"Project", p, {"pmo_governance_exempt": 1, "pmo_exempt_reason": "piloto"}, update_modified=False
		)
		state = project_governance_state(p)
		self.assertTrue(state["exempt"])
		self.assertEqual(state["pending_count"], 0)
		self.assertEqual(state["exempt_reason"], "piloto")

	def test_can_create_reflects_backend_gate(self):
		# La autoridad es el backend (has_permission_*). El owner del Project puede crear baseline; un no-owner
		# sin autoridad, no. La UI solo refleja esta capacidad.
		owner = _user("pgs-owner@example.com", ["Projects User"])
		other = _user("pgs-other@example.com", ["Projects User"])
		p = _project("PGS-PERM", owner=owner)
		frappe.set_user(owner)
		try:
			self.assertTrue(_can_create("PMO Project Baseline", p))
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(other)
		try:
			self.assertFalse(_can_create("PMO Project Baseline", p))
		finally:
			frappe.set_user("Administrator")


class TestReviewPermissions(IntegrationTestCase):
	"""Punto 2 — la Revisión posterior es responsabilidad PMO: PMO Manager puede operarla en cualquier
	proyecto (no solo el owner), manteniendo P4 de lectura. El PM no-owner/no-PMO no puede escribirla."""

	def _review_doc(self, project):
		return frappe.get_doc({"doctype": "PMO Post-Project Review", "project": project})

	def test_pmo_manager_can_operate_review_of_any_project(self):
		from pmo.permissions import has_permission_review

		owner = _user("gc-rev-owner@example.com", ["Projects User"])
		mgr = _user("gc-rev-mgr@example.com", ["PMO Manager"])
		p = _project("GC-REV-PMO", owner=owner)  # el mgr NO es owner
		doc = self._review_doc(p)
		for ptype in ("create", "write", "submit", "cancel"):
			self.assertTrue(has_permission_review(doc, ptype, mgr), f"PMO Manager debe poder {ptype}")

	def test_non_owner_non_pmo_cannot_write_review(self):
		from pmo.permissions import has_permission_review

		owner = _user("gc-rev-owner2@example.com", ["Projects User"])
		other = _user("gc-rev-other@example.com", ["Projects User"])  # ni owner ni PMO
		p = _project("GC-REV-OTHER", owner=owner)
		doc = self._review_doc(p)
		self.assertFalse(has_permission_review(doc, "create", other))
		self.assertTrue(has_permission_review(doc, "create", owner))  # el owner sí (flujo previo)
