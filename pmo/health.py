# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Salud del proyecto (semáforo) — ÚNICA fuente de verdad del algoritmo y sus claves (ADR-0011 D2).

Helper neutral y estable: no depende de ningún módulo de reporte. Lo consumen `pmo_portfolio`
(que lo re-exporta para `print_status`/`dashboard`) y `project_control` (builder canónico). La regla
deriva de las mismas señales del Status Report (ADR-0006/0009). Tolera `None`: la ausencia de
información NO se convierte en cero engañoso."""

from frappe import N_

# Valores internos ESTABLES (independientes del idioma). La lógica compara SIEMPRE estas claves; la
# traducción (`_()`) es solo de presentación (ver HEALTH_LABELS).
HEALTH_ON_TRACK = "on_track"
HEALTH_AT_RISK = "at_risk"
HEALTH_DEVIATED = "deviated"
# Alias de compatibilidad: pmo_portfolio/dashboard usan históricamente HEALTH_OFF_TRACK (mismo valor).
HEALTH_OFF_TRACK = HEALTH_DEVIATED

# Etiquetas de presentación de `_health` (ADR-0013): NO es "salud" — mide desviación de CRONOGRAMA
# (slip + vencidas + forecast vs deadline). "Salud del proyecto" queda reservado para PHI. Se evita
# "At risk" (reservado al PHI). Estados propios de cronograma.
HEALTH_LABELS = {
	HEALTH_ON_TRACK: N_("On schedule"),
	HEALTH_AT_RISK: N_("Behind"),
	HEALTH_DEVIATED: N_("Off track"),
}


def _health(slip_baseline, slip_committed, overdue, exceeds):
	"""Semáforo derivado de las señales del Status Report. Positivo = peor. Tolera None."""
	if (slip_committed or 0) > 0 or (overdue or 0) > 0 or (exceeds or 0) > 0:
		return HEALTH_DEVIATED
	if (slip_baseline or 0) > 0:
		return HEALTH_AT_RISK
	return HEALTH_ON_TRACK


# ─────────────────────────────────────────────────────────────────────────────
# PMO Project Health Index (PHI) — ADR-0013/0013a v1 (calibración `phi-v1`)
# ─────────────────────────────────────────────────────────────────────────────
# PHI es un COMPOSITOR PURO sobre señales canónicas existentes (compone, no recalcula — ADR-0011 D2).
# `compute_phi(signals)` NO hace IO: el adaptador (`pmo.phi`) reúne las señales y llama aquí. El semáforo
# `_health()` de arriba queda INTACTO (coexistencia — ADR-0013 D1).
#
# Calibración v1 (hipótesis inicial versionada; recalibrar = cambio versionado, NUNCA Settings en runtime):
#   Dimensiones con peso (Σ=100): Execution 50 · Schedule 35 · Governance 15.
#   Financial / Resources / Risk NO tienen peso: actúan como guardrails / critical conditions / caps, porque
#   sus señales no permiten un check de salud BILATERAL sin inventar una referencia temporal (costo/horas
#   planificados al corte) ni EVM — solo condiciones inequívocas (sobrecosto, sobreconsumo, inconsistencia,
#   riesgo alto no gestionado). Un cap empeora la BANDA, nunca el número (score auditable).

PHI_CALIBRATION_ID = "phi-v1"

# Pesos versionados de las dimensiones con score (Σ = 100).
PHI_WEIGHTS = {"execution": 50, "schedule": 35, "governance": 15}

# Cortes de banda sobre el PHI matemático (antes de caps).
PHI_ON_TRACK_MIN = 80
PHI_AT_RISK_MIN = 50

# Piso de Model Scope para EMITIR número (por debajo → Diagnostic only). Además, EXE-1 debe ser
# EVALUABLE para publicar PHI (Execution es el ancla de la salud integral; sin ella el número no
# representa el proyecto, solo "el promedio de lo que casualmente hay").
PHI_MODEL_SCOPE_MIN = 0.50

# Mínimos de comparabilidad de portafolio (NO son "sin número": solo marcan `portfolio_comparable`).
PHI_PORTFOLIO_MODEL_SCOPE_MIN = 0.85
PHI_PORTFOLIO_EVIDENCE_MIN = 0.90

# Niveles de Evidence Coverage (etiqueta de calidad mostrada JUNTO al número; no es un gate por sí sola).
PHI_EC_SUFFICIENT_MIN = 0.80
PHI_EC_PARTIAL_MIN = 0.60

# Estados de check (diagnóstico / trazabilidad — ADR-0013a).
CHECK_EVALUABLE = "evaluable"  # aplica y hay evidencia confiable (aporta s_c)
CHECK_NE = "n_e"  # debería medirse pero falta referencia/evidencia confiable (baja Evidence Coverage)
CHECK_NA = "n_a"  # legítimamente no aplica (baja Model Scope, fuera del universo aplicable)
CHECK_INCONSISTENT = "inconsistent"  # condición evaluable negativa / control roto (participa s=0)

# Motivo de PHI ausente — excepción TÉCNICA (no un estado funcional nuevo).
PHI_REASON_EXEMPT = "governance_exempt"  # proyecto formalmente exento → no tiene PHI
PHI_REASON_INSUFFICIENT = "insufficient_evidence"  # imposible calcular por ausencia extrema de datos
PHI_REASON_EXECUTION_NE = "execution_not_evaluable"  # el ancla (Execution) no es evaluable → sin número
PHI_REASON_LOW_SCOPE = "insufficient_model_scope"  # Model Scope < mínimo → sin número

_S_GREEN, _S_YELLOW, _S_RED = 1.0, 0.5, 0.0


def _split_weights(weights: dict) -> dict:
	"""Reparte los pesos de dimensión en pesos POR CHECK. Schedule conserva la proporción interna
	SCH-1:SCH-2 = 20:15 escalada a su peso configurado. Devuelve {EXE-1, SCH-1, SCH-2, GOV-1}."""
	exe = weights["execution"]
	sch = weights["schedule"]
	gov = weights["governance"]
	sch1 = round(sch * 20 / 35)  # proporción histórica (20 de 35)
	sch2 = sch - sch1
	return {"EXE-1": exe, "SCH-1": sch1, "SCH-2": sch2, "GOV-1": gov}


def _coverage_level(ec):
	"""Etiqueta de calidad de cobertura desde Evidence Coverage. None si no hay número."""
	if ec is None:
		return None
	if ec >= PHI_EC_SUFFICIENT_MIN:
		return "sufficient"
	if ec >= PHI_EC_PARTIAL_MIN:
		return "partial"
	return "insufficient"


def _chk(check_id, dimension, weight, state, s_c, detail):
	return {
		"id": check_id,
		"dimension": dimension,
		"weight": weight,
		"state": state,
		"s_c": s_c,
		"detail": detail,
	}


def _cond(code, message, cap=False, before_completion=None):
	c = {"code": code, "message": message, "cap": cap}
	if before_completion is not None:
		c["before_completion"] = before_completion
	return c


def _phi_dimensions(checks: list, weights: dict) -> dict:
	"""Agrega por dimensión (score renormalizado + estados) para diagnóstico/presentación."""
	out = {}
	for dim, weight in weights.items():
		dchecks = [c for c in checks if c["dimension"] == dim]
		ev = sum(c["weight"] for c in dchecks if c["state"] in (CHECK_EVALUABLE, CHECK_INCONSISTENT))
		raw = sum(
			c["weight"] * c["s_c"] for c in dchecks if c["state"] in (CHECK_EVALUABLE, CHECK_INCONSISTENT)
		)
		out[dim] = {
			"weight": weight,
			"score": round(100 * raw / ev) if ev else None,
			"checks": [{"id": c["id"], "state": c["state"], "s_c": c["s_c"]} for c in dchecks],
		}
	return out


def _phi_checks(signals: dict, weights: dict) -> list:
	"""Clasifica cada check (estado + s_c) desde las señales canónicas. Thresholds candidatos v1.
	Los pesos por check derivan de las dimensiones (configurables vía PMO Settings)."""
	w = _split_weights(weights)
	checks = []
	has_baseline = bool(signals.get("has_baseline"))

	# ── Execution — EXE-1: entrega al corte (completadas/debidas del baseline) ──
	due = signals.get("due_by_cutoff")
	done = signals.get("completed_by_cutoff")
	if not has_baseline or due is None:
		checks.append(
			_chk(
				"EXE-1", "execution", w["EXE-1"], CHECK_NE, None, "No effective baseline to measure delivery."
			)
		)
	elif due == 0:
		checks.append(
			_chk(
				"EXE-1", "execution", w["EXE-1"], CHECK_NA, None, "No baseline tasks were due by the cutoff."
			)
		)
	else:
		r = (done or 0) / due
		s = _S_GREEN if r >= 0.90 else _S_YELLOW if r >= 0.70 else _S_RED
		checks.append(
			_chk(
				"EXE-1",
				"execution",
				w["EXE-1"],
				CHECK_EVALUABLE,
				s,
				f"{done or 0}/{due} due tasks delivered ({round(r * 100)}%).",
			)
		)

	# ── Schedule — SCH-1: slip vs baseline normalizado por duración del plan ──
	slip_bl = signals.get("slip_baseline_days")
	dur = signals.get("baseline_duration_days")
	if not has_baseline or slip_bl is None or not dur or dur <= 0:
		checks.append(
			_chk(
				"SCH-1",
				"schedule",
				w["SCH-1"],
				CHECK_NE,
				None,
				"Baseline slip not normalizable (no baseline duration).",
			)
		)
	else:
		r = slip_bl / dur
		s = _S_GREEN if r <= 0 else _S_YELLOW if r <= 0.10 else _S_RED
		checks.append(
			_chk(
				"SCH-1",
				"schedule",
				w["SCH-1"],
				CHECK_EVALUABLE,
				s,
				f"Forecast end slips {slip_bl}d vs baseline ({round(r * 100)}% of {dur}d).",
			)
		)

	# ── Schedule — SCH-2: slip vs fecha comprometida (días absolutos) ──
	has_committed = bool(signals.get("has_committed"))
	slip_cm = signals.get("slip_committed_days")
	if not has_committed or slip_cm is None:
		checks.append(_chk("SCH-2", "schedule", w["SCH-2"], CHECK_NA, None, "No committed end date set."))
	else:
		s = _S_GREEN if slip_cm <= 0 else _S_YELLOW if slip_cm <= 10 else _S_RED
		checks.append(
			_chk(
				"SCH-2",
				"schedule",
				w["SCH-2"],
				CHECK_EVALUABLE,
				s,
				f"Forecast end slips {slip_cm}d vs committed date.",
			)
		)

	# ── Governance — GOV-1: cumplimiento de controles requeridos (motor ADR-0014) ──
	req = int(signals.get("gov_required") or 0)
	ful = int(signals.get("gov_fulfilled") or 0)
	if req == 0:
		checks.append(
			_chk("GOV-1", "governance", w["GOV-1"], CHECK_NA, None, "No governance controls apply yet.")
		)
	else:
		r = ful / req
		s = _S_GREEN if r >= 1.0 else _S_YELLOW if r >= 0.5 else _S_RED
		checks.append(
			_chk(
				"GOV-1",
				"governance",
				w["GOV-1"],
				CHECK_EVALUABLE,
				s,
				f"{ful}/{req} required governance controls fulfilled.",
			)
		)

	return checks


def _phi_conditions(signals: dict) -> list:
	"""Critical conditions / guardrails (Financial, Resources, Risk, Governance estructural).
	NO alteran el score matemático; algunas capean la banda (techo At Risk). Se reportan SIEMPRE."""
	conditions = []
	pct = signals.get("percent_complete")
	before = (pct is not None and pct < 100) or pct is None

	# Financial — inconsistencia de la referencia económica autorizada → cap At Risk (congelado).
	if signals.get("financial_inconsistent"):
		conditions.append(
			_cond(
				"economic_reference_inconsistent",
				N_("Authorized economic reference is inconsistent."),
				cap=True,
			)
		)

	# Financial — sobrecosto: costo real comparable > costo autorizado (guardrail; sin cap severo v1).
	az = signals.get("authorized_cost")
	comp = signals.get("comparable_cost")
	if az is not None and az > 0 and comp is not None and comp > az:
		conditions.append(
			_cond(
				"cost_overrun",
				N_("Real comparable cost exceeds the authorized cost."),
				cap=False,
				before_completion=before,
			)
		)

	# Resources — sobreconsumo: horas reales > presupuesto TOTAL de horas (guardrail; sin cap severo v1).
	budget = signals.get("budget_hours")
	actual = signals.get("actual_hours")
	if budget is not None and budget > 0 and actual is not None and actual > budget:
		conditions.append(
			_cond(
				"effort_overrun",
				N_("Actual hours exceed the total estimated effort budget."),
				cap=False,
				before_completion=before,
			)
		)

	# Risk — exposición alta activa y materialmente no gestionada (sin dueño/respuesta) → cap At Risk.
	# EXIGE evaluación de riesgos establecida (`risk_assessment_exists`): sin evaluación, la ausencia de
	# gestión es una carencia de GOBERNANZA (CONTROL_RISK pendiente ya baja Governance), NO un "riesgo
	# crítico" — no se finge un riesgo crítico donde no hay registro formal de riesgos (ADR-0013).
	if (
		signals.get("risk_assessment_exists")
		and int(signals.get("risk_high_exposure") or 0) > 0
		and (int(signals.get("risk_no_owner") or 0) > 0 or int(signals.get("risk_no_response") or 0) > 0)
	):
		conditions.append(
			_cond(
				"high_exposure_risk_unmanaged",
				N_("High-exposure active risk without owner or response."),
				cap=True,
			)
		)

	# Governance estructural — proyecto sujeto a PMO, iniciado y sin baseline vigente → cap At Risk.
	if signals.get("started") and not signals.get("has_baseline"):
		conditions.append(
			_cond(
				"governance_baseline_missing", N_("Project started without an effective baseline."), cap=True
			)
		)

	return conditions


def compute_phi(signals: dict, weights: dict | None = None) -> dict:
	"""PMO Project Health Index (PHI) v1 — compositor PURO (sin IO). ADR-0013/0013a.

	`signals`: señales canónicas ya reunidas por el adaptador (`pmo.phi.gather_phi_signals`).
	`weights`: pesos de dimensión (Execution/Schedule/Governance). Por defecto `PHI_WEIGHTS` (50/35/15);
	el adaptador puede pasarlos desde PMO Settings. Debe sumar 100 (validado en Settings).

	Publica número SOLO si (i) NO exento, (ii) **EXE-1 es EVALUABLE** (Execution es el ancla de la salud
	integral) y (iii) Model Scope ≥ `PHI_MODEL_SCOPE_MIN`. En otro caso → `phi=None` con motivo diagnóstico
	(Diagnostic only), conservando dimensiones/checks/condiciones. Renormalización POR check. El cap empeora
	solo la BANDA (techo At Risk), nunca el número; Deviated es solo score-driven."""
	weights = weights or PHI_WEIGHTS
	total_w = weights["execution"] + weights["schedule"] + weights["governance"]
	base = {"calibration_id": PHI_CALIBRATION_ID, "weights": dict(weights)}

	# A. Exento → no tiene PHI (no calcular reducido, no renormalizar).
	if signals.get("exempt"):
		return {
			**base,
			"applicable": False,
			"phi": None,
			"band": None,
			"band_raw": None,
			"reason": PHI_REASON_EXEMPT,
			"dimensions": {},
			"checks": [],
			"critical_conditions": [],
			"cap_applied": None,
			"evidence_coverage": None,
			"model_scope": None,
			"coverage_level": None,
			"portfolio_comparable": False,
		}

	checks = _phi_checks(signals, weights)
	conditions = _phi_conditions(signals)
	dimensions = _phi_dimensions(checks, weights)

	applicable = sum(
		c["weight"] for c in checks if c["state"] in (CHECK_EVALUABLE, CHECK_INCONSISTENT, CHECK_NE)
	)
	evidence = sum(c["weight"] for c in checks if c["state"] in (CHECK_EVALUABLE, CHECK_INCONSISTENT))
	model_scope = applicable / total_w if total_w else 0.0
	evidence_coverage = evidence / applicable if applicable else None

	def _diag(reason):
		"""Resultado Diagnostic only (sin número): conserva evidencia para diagnóstico."""
		return {
			**base,
			"applicable": True,
			"phi": None,
			"band": None,
			"band_raw": None,
			"reason": reason,
			"dimensions": dimensions,
			"checks": checks,
			"critical_conditions": conditions,
			"cap_applied": None,
			"evidence_coverage": round(evidence_coverage, 3) if evidence_coverage is not None else None,
			"model_scope": round(model_scope, 3),
			"coverage_level": _coverage_level(evidence_coverage),
			"portfolio_comparable": False,
		}

	# B. Gate estructural: Execution (ancla) debe ser EVALUABLE para publicar número.
	exe = next((c for c in checks if c["id"] == "EXE-1"), None)
	if exe is None or exe["state"] != CHECK_EVALUABLE:
		return _diag(PHI_REASON_EXECUTION_NE)

	# C. Sin evidencia (backstop; con EXE evaluable no debería ocurrir) o Model Scope insuficiente.
	if evidence == 0:
		return _diag(PHI_REASON_INSUFFICIENT)
	if model_scope < PHI_MODEL_SCOPE_MIN:
		return _diag(PHI_REASON_LOW_SCOPE)

	# D. Número + banda cruda.
	raw = sum(c["weight"] * c["s_c"] for c in checks if c["state"] in (CHECK_EVALUABLE, CHECK_INCONSISTENT))
	phi = round(100 * raw / evidence)
	band_raw = (
		HEALTH_ON_TRACK
		if phi >= PHI_ON_TRACK_MIN
		else HEALTH_AT_RISK
		if phi >= PHI_AT_RISK_MIN
		else HEALTH_DEVIATED
	)

	# E. Caps categóricos: techo At Risk (nunca fuerzan Deviated; el número NO cambia).
	cap_codes = [c["code"] for c in conditions if c.get("cap")]
	band = band_raw
	cap_applied = None
	if cap_codes and band == HEALTH_ON_TRACK:
		band = HEALTH_AT_RISK
		cap_applied = {"ceiling": HEALTH_AT_RISK, "conditions": cap_codes}

	portfolio_comparable = bool(
		model_scope >= PHI_PORTFOLIO_MODEL_SCOPE_MIN
		and evidence_coverage is not None
		and evidence_coverage >= PHI_PORTFOLIO_EVIDENCE_MIN
	)

	return {
		**base,
		"applicable": True,
		"phi": phi,
		"band": band,
		"band_raw": band_raw,
		"reason": None,
		"dimensions": dimensions,
		"checks": checks,
		"critical_conditions": conditions,
		"cap_applied": cap_applied,
		"evidence_coverage": round(evidence_coverage, 3) if evidence_coverage is not None else None,
		"model_scope": round(model_scope, 3),
		"coverage_level": _coverage_level(evidence_coverage),
		"portfolio_comparable": portfolio_comparable,
	}
