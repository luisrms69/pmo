# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Financial Health / Salud financiera — señal INDEPENDIENTE del score PHI (ADR-0013b).

Compara el consumo de costo real vs el **avance oficial nativo del proyecto** (`Project.percent_complete`),
como cociente point-in-time (NO EVM: no inventa costo/valor planificado al corte ni curva temporal).

⚠️ **Avance:** se usa `Project.percent_complete` **tal como lo calcula ERPNext según la configuración de ese
Project** (`percent_complete_method`: Manual / Task Completion / Task Progress / Task Weight). **PMO no
interpreta ni recalcula ese avance** — es la única medida de avance total canónica del sistema (la misma que
Project Control → Resumen, Print y Closure ya muestran).

Compone fuentes canónicas existentes (economía autorizada de erpnext_proposals + costos nativos); no duplica
lógica económica ni crea una medida de avance paralela.

- `compute_financial_health(signals)` es PURO (sin IO): recibe señales ya reunidas.
- El adaptador (`gather_financial_signals` / `get_project_financial_health`) es el único con IO.

**Separación:** Financial Health NO entra al score PHI v1. Del lado financiero, lo que afecta al PHI ya vive
como guardrail/cap (sobrecosto, inconsistencia). Esto es una vista complementaria."""

import frappe
from frappe import N_, _
from frappe.utils import flt

# Calibración v1 — hipótesis NORMATIVA inicial (NO derivada de históricos reales; sujeta a recalibración).
# Thresholds versionados en código; NO en PMO Settings.
FIN_CALIBRATION_ID = "fin-v1"
FIN_HEALTHY_MAX_GAP = 5.0  # pp: cost_gap ≤ +5 → healthy
FIN_PRESSURE_MAX_GAP = 15.0  # pp: +5 < cost_gap ≤ +15 → cost_pressure; > +15 → unfavorable

# Estados (fuente EN, traducible; presentación a definir en la UI, no aquí).
FIN_STATE_LABELS = {
	"healthy": N_("Healthy"),
	"cost_pressure": N_("Cost pressure"),
	"unfavorable": N_("Unfavorable"),
	"over_budget": N_("Over budget"),
	"unavailable": N_("Financial health unavailable"),
	"na": N_("Not applicable"),
}
# Motivos para estados sin veredicto (na/unavailable).
FIN_REASON_INCONSISTENT = "inconsistent"
FIN_REASON_NO_AUTHORIZED = "no_authorized"
FIN_REASON_NOT_STARTED = "not_started"


def _out(state, applicable, reason=None, cc=None, pp=None, gap=None):
	return {
		"calibration_id": FIN_CALIBRATION_ID,
		"applicable": applicable,
		"state": state,
		"reason": reason,
		"cost_consumption": round(cc, 3) if cc is not None else None,
		"physical_progress": round(pp, 3) if pp is not None else None,
		"cost_gap": round(gap, 1) if gap is not None else None,  # puntos porcentuales
	}


def compute_financial_health(signals: dict) -> dict:
	"""Salud financiera v1 — compositor PURO (sin IO). ADR-0013b.

	Señales esperadas: `financial_inconsistent` (bool), `has_authorized` (bool), `authorized_cost` (float|None),
	`comparable_cost` (float), `percent_complete` (0..100 nativo del Project). Devuelve
	state/reason/cost_consumption/physical_progress/cost_gap/applicable/calibration_id."""
	# 1. Economía inconsistente → no calcular (unavailable).
	if signals.get("financial_inconsistent"):
		return _out("unavailable", False, reason=FIN_REASON_INCONSISTENT)

	# 2. Sin referencia autorizada (sin propuesta vinculada) → N/A.
	if not signals.get("has_authorized"):
		return _out("na", False, reason=FIN_REASON_NO_AUTHORIZED)

	az = signals.get("authorized_cost")
	az_val = float(az) if az is not None else 0.0
	comp = float(signals.get("comparable_cost") or 0.0)
	# Avance = Project.percent_complete (0..100) tal cual; PMO no lo recalcula.
	physical_progress = float(signals.get("percent_complete") or 0.0) / 100.0

	# 3. Sobrecosto: costo real > autorizado (incluye authorized_cost==0 con costo>0) → precedencia.
	if comp > az_val:
		cc = (comp / az_val) if az_val > 0 else None  # ratio indefinido si autorizado 0
		gap = (cc - physical_progress) * 100 if cc is not None else None
		return _out("over_budget", True, cc=cc, pp=physical_progress, gap=gap)

	# comp ≤ az_val. Si az_val==0 aquí, entonces comp==0.
	cost_consumption = (comp / az_val) if az_val > 0 else 0.0

	# 4. Avance 0%.
	if physical_progress == 0 and comp == 0:
		return _out("na", False, reason=FIN_REASON_NOT_STARTED)  # not_started
	if physical_progress == 0 and comp > 0:
		# Gasto con avance nulo → desfavorable, independientemente del monto.
		return _out("unfavorable", True, cc=cost_consumption, pp=0.0, gap=cost_consumption * 100)

	# 5. Banda normal por brecha costo-avance (pp). Redondeo estable para eliminar ruido de float en bordes.
	gap = round((cost_consumption - physical_progress) * 100, 6)
	if gap <= FIN_HEALTHY_MAX_GAP:
		state = "healthy"
	elif gap <= FIN_PRESSURE_MAX_GAP:
		state = "cost_pressure"
	else:
		state = "unfavorable"
	return _out(state, True, cc=cost_consumption, pp=physical_progress, gap=gap)


# ─────────────────────────────────────────────────────────────────────────────
# Adaptador (IO) — reúne señales canónicas. Independiente de gobernanza (aplica a exentos).
# ─────────────────────────────────────────────────────────────────────────────
def gather_financial_signals(project: str) -> dict:
	"""Reúne las señales para Financial Health. Reutiliza las fuentes canónicas: economía autorizada
	(`get_authorized_economics`), costo real (`get_native_real_cost`) y el avance NATIVO
	(`Project.percent_complete`). NO crea cálculo económico ni de avance paralelo. User-invariant."""
	from pmo.project_economics import get_authorized_economics, get_native_real_cost

	econ = get_authorized_economics(project)
	available = bool(econ.get("available"))
	az = econ.get("data") or {}
	return {
		"financial_inconsistent": econ.get("reason") == "inconsistent",
		"has_authorized": available,
		"authorized_cost": flt(az.get("authorized_cost")) if available else None,
		# Costo real COMPARABLE (fuente canónica única; labor+externo, excluye material).
		"comparable_cost": get_native_real_cost(project)["comparable_cost"],
		# Avance oficial nativo, sin recálculo PMO (hereda el percent_complete_method del Project).
		"percent_complete": flt(frappe.db.get_value("Project", project, "percent_complete")),
	}


@frappe.whitelist()
def get_project_financial_health(project: str) -> dict:
	"""Endpoint P4-safe: Financial Health de UN Project (independiente del PHI y de gobernanza)."""
	frappe.has_permission("Project", ptype="read", doc=project, throw=True)
	return compute_financial_health(gather_financial_signals(project))


# ─────────────────────────────────────────────────────────────────────────────
# Presentación (traducción server-side; NO expone códigos internos al usuario).
# ─────────────────────────────────────────────────────────────────────────────
_FIN_REASON_MESSAGES = {
	FIN_REASON_INCONSISTENT: N_("Authorized economic reference is inconsistent."),
	FIN_REASON_NO_AUTHORIZED: N_("No authorized economic reference (project without a linked proposal)."),
	FIN_REASON_NOT_STARTED: N_("Not started: no progress or cost recorded yet."),
}


def decorate_financial_health(r: dict) -> dict:
	"""Añade campos de PRESENTACIÓN traducidos (state_label, message, percent) sobre el resultado."""
	state = r.get("state")
	r["state_label"] = _(FIN_STATE_LABELS[state]) if state in FIN_STATE_LABELS else None
	r["message"] = _(_FIN_REASON_MESSAGES[r["reason"]]) if r.get("reason") in _FIN_REASON_MESSAGES else None
	# Porcentajes para la UI (0..100), sin exponer fracciones crudas.
	r["cost_consumption_pct"] = (
		round(r["cost_consumption"] * 100) if r.get("cost_consumption") is not None else None
	)
	r["physical_progress_pct"] = (
		round(r["physical_progress"] * 100) if r.get("physical_progress") is not None else None
	)
	return r


def get_financial_view(project: str, cutoff: str | None = None) -> dict:
	"""Financial Health decorado para PRESENTACIÓN (Resumen). P4 + etiquetas traducidas."""
	return decorate_financial_health(get_project_financial_health(project))
