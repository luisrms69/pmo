# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1: normaliza el texto de las preguntas seed EN → ES en sites ya sembrados en inglés.

El seed original insertó el texto en inglés; el canónico del contenido pasó a español (Frappe no traduce en
display valores Small Text). Este patch actualiza cada fila seed a su texto español SOLO si su valor actual sigue
siendo el texto inglés original (fila sin editar por el admin). Idempotente y seguro: nunca pisa ediciones ni
toca preguntas fuera del set seed. En instalaciones nuevas el seed ya inserta español → aquí es no-op.
"""

import frappe

from pmo.setup.risk_catalog import RISK_QUESTION_SEED

# Texto inglés del seed original (v0.0.1) por code. Marcador de "fila sin editar" para la actualización EN→ES.
_ORIGINAL_EN = {
	"EXT-01": "Does the project depend on a third party (vendor/customer) to meet a critical milestone?",
	"SCO-01": "Is there relevant uncertainty in scope or requirements?",
	"SCH-01": "Are there dependencies or assumptions that could deviate the committed schedule?",
	"COST-01": "Are there economic assumptions that may not hold (rates, effort, scope)?",
	"RES-01": "Are there critical resources whose availability could affect the project?",
	"STK-01": "Are there stakeholder or governance risks (alignment, decision-making, approvals)?",
	"IT-01": "Does the project integrate third-party systems or interfaces with uncertain contracts or latencies?",
	"IT-02": "Does it require data migration with uncertain data quality or volume?",
	"IT-03": "Are there security or compliance requirements that could introduce rework?",
	"IT-04": "Are there risks in environments, infrastructure, or deployment?",
	"IT-05": "Does the project use unproven technology or carry relevant technical debt?",
}


def execute():
	new_by_code = {code: question for code, _section, question, _sort in RISK_QUESTION_SEED}
	for code, original_en in _ORIGINAL_EN.items():
		new_es = new_by_code.get(code)
		if not new_es or not frappe.db.exists("PMO Risk Question", code):
			continue
		current = frappe.db.get_value("PMO Risk Question", code, "question")
		if current == original_en:  # fila sin editar → migrar a español canónico
			frappe.db.set_value("PMO Risk Question", code, "question", new_es)
