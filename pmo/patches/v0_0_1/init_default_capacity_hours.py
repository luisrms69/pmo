# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Inicializa el default global de capacidad en PMO Settings (ADR-0003 / Capacity Paso 1).

Motivo: el campo `default_capacity_hours_per_day` tiene `default: 8` en metadata, pero el valor de un
Single solo se materializa en `tabSingles` al guardarse; tras `migrate` puede quedar vacío. Este patch lo
inicializa de forma segura sin depender de abrir/guardar PMO Settings a mano.

Reglas:
    - idempotente: corre una sola vez por sitio (Patch Log) y, dentro de esa corrida, SOLO escribe si el
      valor actual está sin configurar (None/0/vacío);
    - NO sobrescribe un valor ya configurado por un administrador;
    - NO crea registros `PMO Capacity` (el default global vive en PMO Settings, no en una fila fantasma).
"""

import frappe

DEFAULT_HOURS = 8


def execute():
	current = frappe.db.get_single_value("PMO Settings", "default_capacity_hours_per_day")
	if not current:  # None / 0 / 0.0 / "" → sin configurar
		frappe.db.set_single_value("PMO Settings", "default_capacity_hours_per_day", DEFAULT_HOURS)
