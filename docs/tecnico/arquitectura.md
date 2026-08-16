# Arquitectura técnica — pmo

Estado real implementado. Ver decisiones en `docs/adr/`.

## Gantt de Task ordenado por `lft`

- **Hook:** `doctype_calendar_js = {"Task": "public/js/task_calendar_pmo.js"}` en `hooks.py`.
- **Asset:** `pmo/public/js/task_calendar_pmo.js` — se carga **después** del `task_calendar.js` de
  ERPNext y extiende `frappe.views.calendar["Task"]` añadiendo `gantt.order_by = "lft"`.
- **Efecto:** `GanttView.setup_defaults()` aplica `sort_by="lft"`, `sort_order="asc"` **solo** en el
  Gantt de Task. No afecta List, Tree ni Calendar. No modifica core.
- **Nota:** las flechas del Gantt son dependencias nativas (`depends_on_tasks`), ajenas a este cambio.

## Importador de Tags nativos (`pmo/tag_import.py`)

Métodos whitelisted (consumidos por la Page `tag_import`):

| Método | Escribe | Descripción |
|---|---|---|
| `tag_import_dry_run(csv_content)` | No | Valida y devuelve resumen + `detalle` por documento |
| `tag_import_apply(csv_content)` | Sí (si válido) | Valida todo; si pasa, aplica con `add_tags` |

- **CSV:** encabezado `doctype,document,tags` (tags separados por comas por documento).
- **Validación global previa a escribir:** estructura, DocType, existencia del documento, permiso de
  escritura, tags. Cualquier error → **no escribe nada** (todo-o-nada).
- **API nativa:** `frappe.desk.doctype.tag.tag.add_tags` (crea `Tag`, escribe `Tag Link`/`_user_tags`,
  idempotente). No se escribe SQL directo ni tablas internas.
- **Resumen devuelto:** documentos leídos/válidos, asociaciones solicitadas/aplicadas (diff real),
  documentos inexistentes, errores y `detalle` (tipo, documento, tags, estado) para el guard visual.

## UI

- **Page:** `pmo/pmo/page/tag_import/` (rol System Manager). Sube CSV → Dry Run → Aplicar; muestra
  conteos, aviso de todo-o-nada ante errores y tabla de detalle por documento.

## Fuera de alcance
Sin DocTypes, Custom Fields, fixtures ni patches. No se toca core ERPNext.
