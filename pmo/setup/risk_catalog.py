# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Semilla inicial del catálogo de preguntas de riesgo (ADR-0016 Risk Analysis R1).

Idioma del contenido: el texto de las preguntas se almacena en **español** (idioma de trabajo del cliente),
porque Frappe NO traduce en display los valores de campos `Data`/`Small Text` (solo Select/Link/Autocomplete).
El campo `question` está marcado `translatable: 1`, de modo que el contenido sigue siendo traducible a otros
idiomas por el mecanismo nativo de Frappe (i18n preservada); labels/estados/secciones usan canónico inglés + es.po.

Se aplica de forma IDEMPOTENTE y NO destructiva: inserta cada pregunta SOLO si su `code` aún no existe. Nunca
sobrescribe ni borra ediciones del administrador (catálogo vivo). Reutilizado por el patch de migración y por los
tests. `sort_order` usa incrementos de 10 dentro de cada sección (el controller autogenera el siguiente si se deja
vacío). Set inicial: general (6 secciones) + especializada Tecnologías de Información.
"""

import frappe

# (code, section, question, sort_order). `section` debe coincidir EXACTO con una opción del Select
# `PMO Risk Question.section`. `code` es estable (referencia de snapshot e i18n). `sort_order` en pasos de 10.
RISK_QUESTION_SEED = (
	# --- Secciones generales -------------------------------------------------
	(
		"EXT-01",
		"External dependencies",
		"¿El proyecto depende de un tercero (proveedor/cliente) para cumplir un hito crítico?",
		10,
	),
	("SCO-01", "Scope & requirements", "¿Existe incertidumbre relevante en el alcance o los requisitos?", 10),
	(
		"SCH-01",
		"Schedule",
		"¿Hay dependencias o supuestos que puedan desviar el cronograma comprometido?",
		10,
	),
	(
		"COST-01",
		"Cost / economic",
		"¿Hay supuestos económicos que podrían no cumplirse (tarifas, esfuerzo, alcance)?",
		10,
	),
	(
		"RES-01",
		"Resources & team",
		"¿Hay recursos críticos cuya disponibilidad podría afectar al proyecto?",
		10,
	),
	(
		"STK-01",
		"Stakeholders & governance",
		"¿Existen riesgos de interesados o gobernanza (alineación, toma de decisiones, aprobaciones)?",
		10,
	),
	# --- Sección especializada: Tecnologías de Información --------------------
	(
		"IT-01",
		"Information Technology",
		"¿El proyecto integra sistemas o interfaces de terceros con contratos o latencias inciertas?",
		10,
	),
	(
		"IT-02",
		"Information Technology",
		"¿Requiere migración de datos con calidad o volumen de datos inciertos?",
		20,
	),
	(
		"IT-03",
		"Information Technology",
		"¿Existen requisitos de seguridad o cumplimiento que puedan introducir retrabajo?",
		30,
	),
	(
		"IT-04",
		"Information Technology",
		"¿Hay riesgos en ambientes, infraestructura o despliegue?",
		40,
	),
	(
		"IT-05",
		"Information Technology",
		"¿El proyecto usa tecnología no probada o arrastra deuda técnica relevante?",
		50,
	),
)


def seed_risk_questions() -> int:
	"""Inserta las preguntas del catálogo inicial que aún no existan (por `code`). Devuelve cuántas insertó.

	Idempotente: correr N veces deja el mismo resultado. No toca preguntas existentes (respeta ediciones del
	admin) ni desactiva/borra nada."""
	inserted = 0
	for code, section, question, sort_order in RISK_QUESTION_SEED:
		if frappe.db.exists("PMO Risk Question", code):
			continue
		frappe.get_doc(
			{
				"doctype": "PMO Risk Question",
				"code": code,
				"section": section,
				"question": question,
				"sort_order": sort_order,
				"active": 1,
			}
		).insert(ignore_permissions=True)
		inserted += 1
	return inserted
