# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1: siembra idempotente del catálogo inicial de preguntas de riesgo.

Solo inserta preguntas cuyo `code` no exista aún (no sobrescribe ediciones del admin). Post model sync porque
requiere que el DocType `PMO Risk Question` ya exista."""

from pmo.setup.risk_catalog import seed_risk_questions


def execute():
	seed_risk_questions()
