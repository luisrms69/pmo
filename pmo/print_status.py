# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Contexto Jinja para el Print Format `PMO Project Status` (salida presentable a stakeholder).

Wrapper delgado (ADR-0011 D4/D7): delega en `pmo.project_control.build_project_control()` — la fuente
única del contexto de Project Control. NO calcula nada propio. Registrado como método Jinja
(`hooks.jinja.methods`); el Print Format hace `{% set pc = pmo_project_status(doc.name) %}` y renderiza
el template canónico `pmo/templates/project_control/executive.html` (el mismo que consume la Page).

Consolidación (ADR-0011): las horas reales del reporte pasan a `indicators.actual_hours_to_date`
(gobernado por la fecha de corte), corrigiendo la inconsistencia previa que usaba el acumulado actual.
"""

from pmo.project_control import build_project_control


def pmo_project_status(project: str, status_date=None) -> dict:
	"""Contexto canónico del proyecto para el Print Format. P4 la impone el builder (build_status_report).
	Wrapper de compatibilidad: la fuente de verdad es `build_project_control()`."""
	return build_project_control(project, cutoff=status_date, audience="internal")
