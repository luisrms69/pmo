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

HEALTH_LABELS = {
	HEALTH_ON_TRACK: N_("On track"),
	HEALTH_AT_RISK: N_("At risk"),
	HEALTH_DEVIATED: N_("Deviated"),
}


def _health(slip_baseline, slip_committed, overdue, exceeds):
	"""Semáforo derivado de las señales del Status Report. Positivo = peor. Tolera None."""
	if (slip_committed or 0) > 0 or (overdue or 0) > 0 or (exceeds or 0) > 0:
		return HEALTH_DEVIATED
	if (slip_baseline or 0) > 0:
		return HEALTH_AT_RISK
	return HEALTH_ON_TRACK
