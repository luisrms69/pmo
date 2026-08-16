# Importar Tags desde CSV

Utilidad administrativa para agregar **Tags nativos** de Frappe a documentos, en lote, desde un CSV.

**Acceso:** Desk → página **Importar Tags** (`/desk/tag_import`). Requiere rol **System Manager**.

## Formato del CSV

Encabezado obligatorio `doctype,document,tags`. Un documento por fila; varios Tags separados por
comas dentro del campo `tags`:

```csv
doctype,document,tags
Task,TASK-0001,"CIERRE,CLIENTE,GO-NO-GO"
Task,TASK-0002,"DATOS,COMPARTIDA"
```

- **doctype:** el tipo de documento (Task, Project, Customer, Item…). Funciona con cualquier DocType.
- **document:** el nombre/ID del registro concreto.
- **tags:** uno o varios Tags.

## Uso

1. **Selecciona** el archivo CSV.
2. **Dry Run** (recomendado primero): valida sin escribir nada y muestra:
   - conteos (documentos leídos/válidos, asociaciones solicitadas y las que se aplicarían);
   - un **detalle por documento** (Tipo · Documento · Tags a agregar · Estado), con los errores arriba.
3. **Aplicar:** agrega los Tags. Solo cuenta como aplicados los **Tags nuevos** (idempotente:
   reaplicar el mismo CSV agrega 0).

## Reglas de seguridad

- **Todo o nada:** si el CSV tiene **cualquier** error que invalide la importación (DocType o
  documento inexistente, sin permiso de escritura, estructura inválida), **Aplicar no escribe nada** —
  ni siquiera las filas válidas. Corrige el CSV y reintenta.
- Se respeta el **permiso de escritura** sobre cada documento.
- Los Tags son los **nativos** de Frappe (no se crean campos nuevos).
