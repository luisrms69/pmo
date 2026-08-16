# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Importador genérico de Tags nativos de Frappe desde CSV.

Reutiliza exclusivamente la API nativa `frappe.desk.doctype.tag.tag.add_tags`
para aplicar (crea el Tag master, escribe Tag Link y `_user_tags`, respeta el
permiso de escritura del documento e idempotente). Nunca escribe SQL directo ni
toca `tabTag Link` / `_user_tags` a mano.

Formato CSV esperado (con encabezado):

    doctype,document,tags
    Task,TASK-0001,"CIERRE,CLIENTE,GO-NO-GO"
    Task,TASK-0002,"DATOS,COMPARTIDA"

Dos fases:
- Dry Run: solo lecturas + `frappe.has_permission`; calcula el diff contra los
  Tags existentes y devuelve el resumen. No escribe nada.
- Aplicar: valida TODO el CSV primero; si hay cualquier error que invalide la
  importación, no escribe nada. Solo si la validación global pasa, aplica vía
  `add_tags` y cuenta como "aplicadas" únicamente los Tags nuevos reales.
"""

import csv
import io

import frappe
from frappe import _
from frappe.desk.doctype.tag.tag import DocTags, add_tags

EXPECTED_COLUMNS = ["doctype", "document", "tags"]


def _normalize_tags(raw):
	"""Divide el campo tags por comas, quita espacios y vacíos, sin duplicados (orden estable)."""
	seen = []
	for tag in (raw or "").split(","):
		tag = tag.strip()
		if tag and tag not in seen:
			seen.append(tag)
	return seen


def _parse_csv(csv_content):
	"""Parsea el CSV a filas normalizadas. Devuelve (rows, structural_error).

	`rows` es una lista de dicts {row, doctype, document, tags:list}.
	`structural_error` es un string si el CSV no tiene la estructura mínima
	(en cuyo caso `rows` viene vacío).
	"""
	if not (csv_content or "").strip():
		return [], _("El CSV está vacío.")

	reader = csv.reader(io.StringIO(csv_content))
	try:
		header = next(reader)
	except StopIteration:
		return [], _("El CSV está vacío.")

	header = [h.strip().lower() for h in header]
	if header[: len(EXPECTED_COLUMNS)] != EXPECTED_COLUMNS:
		return [], _("Encabezado inválido. Se esperaba: {0}").format(", ".join(EXPECTED_COLUMNS))

	rows = []
	for i, raw in enumerate(reader, start=2):  # fila 1 = encabezado
		if not any((c or "").strip() for c in raw):
			continue  # ignorar líneas en blanco
		if len(raw) < 3:
			rows.append({"row": i, "doctype": None, "document": None, "tags": [], "malformed": True})
			continue
		rows.append(
			{
				"row": i,
				"doctype": (raw[0] or "").strip(),
				"document": (raw[1] or "").strip(),
				"tags": _normalize_tags(raw[2]),
				"malformed": False,
			}
		)
	return rows, None


def _validate(csv_content):
	"""Validación global (sin escrituras). Devuelve un dict de resultado completo.

	Calcula el diff contra los Tags nativos existentes para saber qué
	asociaciones se aplicarían realmente.
	"""
	rows, structural_error = _parse_csv(csv_content)

	result = {
		"ok": False,
		"documentos_leidos": len(rows),
		"documentos_validos": 0,
		"asociaciones_solicitadas": 0,
		"asociaciones_aplicadas": 0,  # las que se aplicarían (diff)
		"documentos_inexistentes": [],
		"errores": [],
		# Desglose por documento (guard visual): una entrada por fila del CSV.
		"detalle": [],
	}

	def _add_error(row_no, dt, dn, msg):
		result["errores"].append({"row": row_no, "error": msg})
		result["detalle"].append(
			{
				"row": row_no,
				"tipo": dt or "",
				"documento": dn or "",
				"tags": [],
				"estado": "error",
				"error": msg,
			}
		)

	if structural_error:
		result["errores"].append({"row": 1, "error": structural_error})
		return result, []

	if not rows:
		result["errores"].append({"row": 1, "error": _("El CSV no contiene filas de datos.")})
		return result, []

	requested_pairs = set()  # (doctype, document, tag) únicos solicitados
	to_apply = []  # (doctype, document, [tags nuevos]) para la fase de aplicación
	valid_docs = set()

	# cache de existencia de doctype para no repetir consultas
	doctype_exists_cache = {}

	for r in rows:
		row_no = r["row"]

		if r["malformed"]:
			_add_error(
				row_no, None, None, _("Fila mal formada: se requieren columnas doctype, document, tags.")
			)
			continue

		dt, dn, tags = r["doctype"], r["document"], r["tags"]

		if not dt or not dn:
			_add_error(row_no, dt, dn, _("doctype y document son obligatorios."))
			continue

		if not tags:
			_add_error(row_no, dt, dn, _("No hay Tags válidos en la fila (columna tags vacía)."))
			continue

		# ¿existe el DocType?
		if dt not in doctype_exists_cache:
			doctype_exists_cache[dt] = bool(frappe.db.exists("DocType", dt))
		if not doctype_exists_cache[dt]:
			_add_error(row_no, dt, dn, _("DocType inexistente: {0}").format(dt))
			continue

		# ¿existe el documento?
		if not frappe.db.exists(dt, dn):
			result["documentos_inexistentes"].append(f"{dt}:{dn}")
			_add_error(row_no, dt, dn, _("Documento inexistente: {0} {1}").format(dt, dn))
			continue

		# ¿permiso de escritura sobre el documento?
		if not frappe.has_permission(doctype=dt, ptype="write", doc=dn):
			_add_error(row_no, dt, dn, _("Sin permiso de escritura sobre {0} {1}").format(dt, dn))
			continue

		# documento válido; calcular diff contra Tags existentes
		valid_docs.add((dt, dn))
		existing = set(t for t in DocTags(dt).get_tags(dn).split(",") if t)
		nuevos = []
		for tag in tags:
			pair = (dt, dn, tag)
			if pair in requested_pairs:
				continue  # ya contabilizado (mismo par repetido en el CSV)
			requested_pairs.add(pair)
			if tag not in existing:
				nuevos.append(tag)
		if nuevos:
			to_apply.append((dt, dn, nuevos))
		result["detalle"].append(
			{
				"row": row_no,
				"tipo": dt,
				"documento": dn,
				"tags": nuevos,  # solo los que se agregarían
				"estado": "se_agregaran" if nuevos else "sin_cambios",
				"error": None,
			}
		)

	result["documentos_validos"] = len(valid_docs)
	result["asociaciones_solicitadas"] = len(requested_pairs)
	result["asociaciones_aplicadas"] = sum(len(n) for _, _, n in to_apply)
	result["ok"] = not result["errores"]
	return result, to_apply


@frappe.whitelist()
def tag_import_dry_run(csv_content: str):
	"""Valida el CSV y reporta el resumen SIN realizar ninguna escritura."""
	result, _to_apply = _validate(csv_content)
	result["mode"] = "dry_run"
	return result


@frappe.whitelist()
def tag_import_apply(csv_content: str):
	"""Aplica los Tags. Valida TODO el CSV antes de la primera escritura.

	Si la validación global falla, no escribe nada (all-or-nothing) y devuelve
	el resumen con los errores. Si pasa, aplica vía `add_tags` y reporta como
	`asociaciones_aplicadas` únicamente los Tags nuevos reales.
	"""
	result, to_apply = _validate(csv_content)
	result["mode"] = "apply"

	if not result["ok"]:
		# Error que invalida la importación → no se escribe nada.
		result["asociaciones_aplicadas"] = 0
		return result

	aplicadas = 0
	for dt, dn, nuevos in to_apply:
		add_tags(tags=nuevos, dt=dt, docs=[dn])
		aplicadas += len(nuevos)

	result["asociaciones_aplicadas"] = aplicadas
	return result
