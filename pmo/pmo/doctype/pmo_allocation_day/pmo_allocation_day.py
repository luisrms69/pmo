# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Allocation Day — child table de PMO Resource Allocation (ADR-0003 D3).

Valores diarios canónicos (date, hours) de un plan de asignación. Como child table, HEREDA el boundary
y los permisos del padre: NO lleva permission_query_conditions ni has_permission propios.
"""

from frappe.model.document import Document


class PMOAllocationDay(Document):
	pass
