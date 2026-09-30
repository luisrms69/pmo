# Fechas comprometidas de cronograma

Permite distinguir, en Task y Project, **dos fechas distintas** (ADR-0007):

- **Fecha planeada/calculada** (nativa de ERPNext): `Expected End Date` de la Task/Project. Es lo que el
  cronograma calcula hoy y **se mueve** cuando cambian dependencias, duraciones o se replanifica.
- **Fecha comprometida** (nueva): el **compromiso** acordado (de negocio o con el cliente; no
  necesariamente contractual). **No se desplaza** automáticamente al reprogramar. En el **Project no se edita a
  mano**: se establece al emitir el **Acta de Inicio** y solo se cambia después mediante una acción gobernada
  (ver "Cómo se establece y se cambia el Fin comprometido").

## Campos

- **Task → "PMO — Fecha comprometida (deadline)"** (`pmo_deadline`): fecha límite comprometida de la tarea.
  Es **opcional y editable** a mano; si la dejas vacía no hay compromiso registrado ni aviso.
- **Project → "PMO — Fin comprometido"** (`pmo_committed_end_date`): fecha comprometida de fin del proyecto.
  Es un campo de **solo lectura** en el formulario: no se captura ni edita a mano (se registra al emitir el
  Acta de Inicio; ver abajo).

## Cómo se establece y se cambia el Fin comprometido (Project)

- **Se establece** al emitir el **Acta de Inicio** (PMO Project Handoff): la fecha comprometida capturada y
  autorizada en el Acta se copia al Project. Por eso el campo del Project es de solo lectura.
- **Se cambia después** con la acción **"Cambiar fin comprometido"** del menú **PMO** en el Project. Solo
  aparece si ya hay un Fin comprometido y tienes autoridad PMO (PMO Manager o System Manager). Abre un diálogo
  con la fecha actual (solo lectura), la **nueva fecha** y un **motivo obligatorio**.
- Cada cambio queda **registrado**: en el historial del Project (antes → después) y como **comentario** en la
  línea de tiempo con el motivo y el autor.
- No es edición libre: sin autoridad PMO o sin motivo, el sistema **rechaza** el cambio (la validación es del
  servidor, no solo de la pantalla).

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
