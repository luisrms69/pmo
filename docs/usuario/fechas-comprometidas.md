# Fechas comprometidas de cronograma

Permite distinguir, en Task y Project, **dos fechas distintas** (ADR-0007):

- **Fecha planeada/calculada** (nativa de ERPNext): `Expected End Date` de la Task/Project. Es lo que el
  cronograma calcula hoy y **se mueve** cuando cambian dependencias, duraciones o se replanifica.
- **Fecha comprometida** (nueva): el **compromiso** acordado (de negocio o con el cliente; no
  necesariamente contractual). **No se desplaza** automáticamente al reprogramar; solo cambia si alguien la
  edita a propósito.

## Campos

- **Task → "PMO — Fecha comprometida (deadline)"** (`pmo_deadline`): fecha límite comprometida de la tarea.
- **Project → "PMO — Fin comprometido"** (`pmo_committed_end_date`): fecha comprometida de fin del proyecto.

Ambos son opcionales. Si los dejas vacíos, no hay compromiso registrado y no se genera ningún aviso.

## Qué hace (y qué NO hace)

- Si la **fecha planeada supera** la comprometida (la tarea/proyecto se está yendo más allá del
  compromiso), al guardar aparece un **aviso** ("Compromiso de cronograma en riesgo").
- El aviso es **informativo**: **no bloquea** el guardado, **no mueve** la tarea y **no** afecta el registro
  de tiempo real (Timesheet). Es gobernanza, no un control duro.
- La fecha comprometida **no reprograma** nada: es una referencia para comparar contra lo calculado.

## Qué NO incluye esta versión

- No hay tipos de restricción de programación (p. ej. "no empezar antes de", "terminar a más tardar" como
  constraint que gobierne el cálculo). Eso queda para un ciclo futuro si hay necesidad real.
- No cambia las líneas base (Baseline) ni el reporte de control a fecha de corte (Status Date).
- No hay ruta crítica, EVM ni forecast.
