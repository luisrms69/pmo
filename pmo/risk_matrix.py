# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 Risk Analysis — matriz cualitativa 3x3 compartida (fuente única de la regla de exposición).

Reutilizada por el Assessment (rating as-identified) y por el PMO Project Risk (estado vivo), para que ambos
deriven la exposición con la MISMA regla sin acoplar controllers entre sí.

Tokens de origen DIFERENCIADOS por campo (i18n): `Low/Medium/High` genéricos están excluidos del POT de pmo
(los hereda de erpnext, en masculino) y no permiten dos géneros del mismo token en español. Por eso:
  - probability → `Low/Medium/High likelihood` (propios de pmo → femenino: Baja/Media/Alta)
  - impact      → `Low/Medium/High` (heredado de erpnext → masculino: Bajo/Medio/Alto, correcto)
  - exposure    → `Low/Medium/High exposure` (propios de pmo → femenino: Baja/Media/Alta)
La regla numérica de la matriz es idéntica a la 3x3 original; solo cambian las etiquetas de los tokens.
"""

# Índice de severidad por token, por campo (0=bajo, 1=medio, 2=alto).
PROBABILITY_LEVELS = ("Low likelihood", "Medium likelihood", "High likelihood")
IMPACT_LEVELS = ("Low", "Medium", "High")
EXPOSURE_LEVELS = ("Low exposure", "Medium exposure", "High exposure")

_PROB_SEV = {tok: i for i, tok in enumerate(PROBABILITY_LEVELS)}
_IMPACT_SEV = {tok: i for i, tok in enumerate(IMPACT_LEVELS)}

# [probabilidad][impacto] -> índice de exposición. Idéntico a la matriz 3x3 simétrica original.
_EXPOSURE_INDEX = (
	(0, 0, 1),  # prob baja
	(0, 1, 2),  # prob media
	(1, 2, 2),  # prob alta
)


def derive_exposure(probability: str | None, impact: str | None) -> str | None:
	"""Exposición cualitativa derivada; None si falta probabilidad o impacto. Fuente única de la regla."""
	p = _PROB_SEV.get(probability)
	i = _IMPACT_SEV.get(impact)
	if p is None or i is None:
		return None
	return EXPOSURE_LEVELS[_EXPOSURE_INDEX[p][i]]
