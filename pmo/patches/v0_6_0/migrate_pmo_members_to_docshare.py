# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0002 (revisado v0.6.0): la membresía de Project deja de persistirse en el child `PMO Project
Member`; se deriva de fuentes nativas (owner + DocShare + ToDo). Este patch convierte cada membresía
existente en un DocShare(read+write) del Project y retira el Custom Field y el DocType. Idempotente.
"""

import frappe


def execute():
	if not frappe.db.table_exists("PMO Project Member"):
		return  # ya migrado / instalación nueva

	rows = frappe.db.sql(
		"""select parent, member from `tabPMO Project Member`
		where parenttype = 'Project' and parentfield = 'pmo_members' and ifnull(member, '') != ''""",
		as_dict=True,
	)
	for r in rows:
		if (
			r.parent
			and r.member
			and frappe.db.exists("Project", r.parent)
			and frappe.db.exists("User", r.member)
		):
			# read+write (el equivalente más cercano a la membresía anterior: leer Project + escribir Tasks).
			frappe.share.add("Project", r.parent, r.member, read=1, write=1, notify=0)

	if frappe.db.exists("Custom Field", "Project-pmo_members"):
		frappe.delete_doc("Custom Field", "Project-pmo_members", ignore_permissions=True, force=True)
	if frappe.db.exists("DocType", "PMO Project Member"):
		frappe.delete_doc("DocType", "PMO Project Member", ignore_permissions=True, force=True)
	frappe.db.commit()
