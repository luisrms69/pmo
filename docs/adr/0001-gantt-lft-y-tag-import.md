# ADR-0001: Gantt de Task por `lft` y importador de Tags nativos

**Fecha:** 2026-08-16
**Status:** Activo

## Contexto

Dos necesidades sobre ERPNext v16 nativo, sin tocar core:

1. El Gantt de `Task` ordena las filas por fecha, lo que **mezcla ramas** de la jerarquía
   (`parent_task` / nested set). Se requería que el orden siguiera la jerarquía.
2. Se necesitaba una utilidad administrativa para **importar Tags nativos** de Frappe a documentos
   desde un CSV, de forma genérica, segura e idempotente.

## Decisiones

### 1. Gantt ordenado por `lft` vía configuración nativa
`frappe.views.GanttView.setup_defaults()` lee `calendar_settings.order_by`; si existe, fija
`sort_by = order_by` con `sort_order = "asc"` de forma nativa. Se registra un
`doctype_calendar_js = {"Task": "public/js/task_calendar_pmo.js"}` que **extiende** el objeto
existente `frappe.views.calendar["Task"]` añadiendo `gantt.order_by = "lft"`.

- **Alternativa descartada:** manipular `cur_list.sort_selector` con `setTimeout`/observers. Frágil,
  depende de timing y de la vista activa. La vía nativa es determinista y solo afecta al Gantt.
- **Consecuencias:** solo `Task > Gantt` cambia (List/Tree/Calendar intactos); el orden deriva
  exclusivamente del nested set (`lft`), no de fechas; no se toca core.

### 2. Importador de Tags con API nativa y validación global
`pmo/tag_import.py` expone `tag_import_dry_run` y `tag_import_apply` (whitelisted). Aplica con
`frappe.desk.doctype.tag.tag.add_tags` (crea el `Tag` master, escribe `Tag Link` y `_user_tags`,
respeta el permiso de escritura del documento, idempotente).

- **Todo-o-nada:** `apply` valida el CSV **completo** antes de la primera escritura; si algo lo
  invalida, no escribe nada.
- **Dry Run real:** solo lecturas + `has_permission`; calcula el diff contra los Tags existentes.
- **Alternativa descartada:** escribir directo en `Tag Link`/`_user_tags`/SQL. Se rechaza: se usa
  exclusivamente la API nativa.
- **Consecuencias:** genérico para cualquier DocType con Tags; sin Custom Fields; idempotente
  (reaplicar el mismo CSV agrega 0).

## Notas
UI mínima (Page `tag_import`, rol System Manager). Sin DocTypes, fixtures ni patches.
