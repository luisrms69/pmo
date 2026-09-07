# ADR-0002: Project/Task Privacy, Security Boundary y Permisos

**Estado:** Aceptado · **Revisado v0.6.0** (D2/D6/D7/D8: membresía derivada de fuentes nativas)
**Fecha:** 2026-09-02 · **Revisión:** 2026-09-07
**App:** pmo · **Rama protegida:** version-16

> **Revisión v0.6.0 (2026-09-07):** se **retira** el child DocType `PMO Project Member` y el Custom Field
> `Project-pmo_members`. La **membresía de Project ya no se persiste**: se **deriva** de fuentes nativas
> `owner + DocShare(Project) + ToDo activo(Task)`. `DocShare` honra sus flags (`read`/`write`). El **owner
> puede compartir su propio Project**. Cambian D1/D2/D6/D7/D8 (abajo). Motivo: no duplicar en una lista
> custom lo que Frappe ya resuelve nativamente; `User Permissions` sigue descartada (alcance global
> cross-doctype). Migración por patch `PMO Project Member → DocShare(read+write)`.

## Contexto

`Project` y `Task` deben ser **privados por defecto** (proyectos sensibles: RRHH, reorganizaciones,
financieros, estratégicos). En v16 (verificado en código): `Project` da `read` a `Projects Manager`,
`Projects User` y **`Desk User`** (`SYSTEM_USER_ROLE`, implícito a todo usuario interno) → exposición
universal; `Task` a `Projects User`/`HR Manager`. No hay `permission_query_conditions` para
Project/Task. El motor combina `(role AND pqc) OR (documentos compartidos)`, y `has_permission`
reconcede por share.

## Problema

Aislamiento **fail-closed** por necesidad de acceso, sin romper administradores, integraciones/jobs ni
el sharing nativo; con acceso ejecutivo excepcional auditable; y política de escritura y de share bien
definidas.

## Decisiones

### D1 — Modelo de visibilidad (READ, fail-closed)

```
Project visible si:  user == owner
                     OR existe DocShare(Project, read) para user   (miembro = share explícito)
                     OR user tiene PMO Executive Access
Task visible si:     Task.project vacío → reglas estándar ERPNext
                     OR Project(Task) visible-para-user           (Task hereda la frontera del Project;
                                                                    un DocShare de Project alcanza sus Tasks
                                                                    por decisión de frontera del hook)
                     OR existe ToDo activo (Task, user)            (asignación directa: SOLO esa Task)
                     OR user tiene PMO Executive Access
```

- `Task assignment ≠ Project membership`: no concede el Project ni otras Tasks, ni convierte en miembro.

### D2 — Membresía **derivada** de fuentes nativas (revisado v0.6.0)

**No** hay child DocType ni Custom Field de membresía. El "equipo del Project" se **deriva** de
`owner + DocShare(Project) + ToDo activo(Task)` y, si se necesita mostrarlo en UX, se **calcula** de esas
fuentes (no se persiste). Un "miembro" es un usuario con `DocShare(Project)` explícito. `Project User`
sigue descartado (dispara `control_access_for_project_users` → DocShare + emails de portal); `User
Permissions` descartada (alcance global cross-doctype, no fail-closed sin ajuste global).
*(Histórico: en el MVP la membresía se persistía en el child `PMO Project Member`; retirado en v0.6.0.)*

### D3 — Enforcement por hooks (alcance), no por DocPerm de read/write

- **Role Permission nativo = capacidad** (`read`/`write`/`create`/…). **No se modifican** los DocPerm
  de read/write/create de Project/Task.
- **`pqc` + `has_permission` (pmo) = alcance** (qué documentos). `pqc` cubre List/Report Builder/Tree/
  Gantt/Calendar/link/API-list; `has_permission` cubre documento único/URL/get_doc. Semántica v16
  (`True`/`False`; **evitar `None`** dentro del boundary para read/write; `None` solo donde deferimos
  deliberadamente).

### D4 — Roles separados

- **`PMO Manager`**: administra funciones PMO; **sin** read/write/share adicional sobre contenido de
  Project/Task por el rol; sujeto a privacidad normal.
- **`PMO Executive Access`**: **Read global** (pqc vacío para el rol), **No Write global**, **Sí Share
  manual**. Excepcional (CEO/ejecutivos).

### D5 — Acceso ejecutivo por rol explícito; jerarquía fuera del ACL

`reports_to`/departamento **no** forma parte del ACL (propaga permisos de forma peligrosa). Jerarquía,
si acaso, solo para **reportes agregados** en P2, nunca para abrir Project/Task.

### D6 — Política de WRITE (revisado v0.6.0: `DocShare` honra flags)

Capacidad (rol nativo) × alcance (hooks):

- **Owner**: write Project + write todas sus Tasks.
- **`DocShare(Project, write)`**: write del **Project y de sus Tasks** (honra el flag del share).
- **`DocShare(Project, read)`**: solo lectura del Project y sus Tasks.
- **Task-only assignee (ToDo)**: read/write **solo** su Task.
- **PMO Executive Access**: read global, **write no**.
- **PMO Manager**: nada por el rol.

### D7 — Política de SHARE manual (revisado v0.6.0: el owner comparte su Project)

- **Project share — Permitido:** el **owner** de su propio Project (así **incorpora colaboradores**),
  `PMO Executive Access` y `Administrator`. **Denegado** al resto.
- **Task share — Permitido:** solo `PMO Executive Access`/`Administrator` (excepcional).
- `assign_to` sigue **sin** auto-share (la visibilidad del asignado viene del ToDo).
- **Implementación upgrade-safe:** controlar `ptype == "share"` en el **`has_permission` hook**
  existente (deniega a no-ejecutivos; concede a Executive). **No** usar Custom DocPerm parcial
  (reemplaza el conjunto nativo completo y congela permisos). **Fallback** solo si el hook no puede
  *conceder* share: Custom DocPerm **completo** por **fixture** + **re-sync documentado** en cada
  upgrade de ERPNext, preservando read/write/create nativos y cambiando solo `share`.

> **RESUELTO (verificado en v16, P0 Incremento 3):** la semántica real del controlador
> `has_permission` es **solo restringir**: `True` concede **dentro** de la capacidad de rol (AND con el
> DocPerm), `False` deniega, y `None` también deniega. Consecuencias comprobadas con tests:
> - `has_permission(ptype="share")` devolviendo `False` **restringe** el share a los no-ejecutivos
>   (aunque su rol tenga `share=1`) → share manual bloqueado con `PermissionError`.
> - `PMO Executive Access` **comparte** porque el hook devuelve `True` **y** su rol aporta la capacidad
>   nativa `share` (p. ej. `Projects User` con `share=1`).
> - `assign_to` sigue funcionando **sin auto-share**: el asignado ya está permitido por el **ToDo**
>   (nuestro `has_permission`), por lo que `assign_to` omite `share.add`.
>
> **Decisión final:** el hook nativo `has_permission(ptype="share")` es **suficiente**. **No** se usa el
> fallback de Custom DocPerm completo. (El ejecutivo debe tener un rol con capacidad `share`.)

### D8 — Política de `DocShare` (revisado v0.6.0: `DocShare(Project)` = membresía)

- Share = mecanismo nativo legítimo, **aditivo y revocable**; **no** se bloquea/neutraliza/sustituye
  globalmente.
- **`DocShare(Project)` es la fuente de membresía**: por **decisión de frontera del hook** (D3), concede
  acceso al **Project y a sus Tasks** (read/write según flags). Ya **no** dependemos del comportamiento
  nativo empírico "share de Project = solo el Project". Share manual de **Task** → **solo esa Task**.
- **Auto-share de asignación:** en nuestro modelo, el asignado obtiene visibilidad por el **`ToDo`
  activo** (D1), y como el `ToDo` se crea **antes** del check en `assign_to`, éste **omite** el
  `share.add` → **no se crea auto-share** → desaparece el "share huérfano". Criterio de aceptación P0:
  verificarlo. (Este mismo hecho permite restringir `share` sin romper la asignación — D7.)

### D9 — Superusuarios (comportamiento real)

- `Administrator` / `ignore_permissions` / `get_all`: bypass inevitable → **no protegible**,
  documentado.
- `System Manager`: **sujeto a `pqc`** → **sin** visibilidad global automática; sin `share` por defecto.

### D10 — Extensión del boundary a doctypes de `pmo` que referencian Project

El boundary de privacidad **se extiende** a los DocTypes de `pmo` que referencian `Project` (p. ej.
`PMO Resource Allocation`): su dimensión `project` se rige por este ADR (`pqc`/`has_permission`), y sus
reportes enmascaran la identidad de proyectos fuera del boundary del observador. Ver **ADR-0003** (P4:
agregación server-side, bucket "Comprometido (confidencial)", enmascarado también en Actual/Timesheet).

### D11 — Cierre de vectores que ignoran `pqc` (P0 Incremento 4)

`pqc`/`has_permission` cubren `get_list`/documento único, pero **no** los caminos que fuerzan
`ignore_permissions` (`get_all`, `db.sql`). Auditados y mitigados **sin tocar core** ni DocPerms:

- **`create_duplicate_project`** (whitelisted; `get_all("Task", project=prev_doc.name)`): permitía a
  quien **conociera el nombre** de un Project confidencial exfiltrar sus Tasks a un proyecto propio.
  → **Override** vía `override_whitelisted_methods` (`pmo.overrides.create_duplicate_project`) que exige
  `has_permission("Project", "read", throw=True)` sobre el origen antes de delegar en el nativo.
- **Reports que ignoran `pqc`** (`Project Summary`, `Delayed Tasks Summary`,
  `Project wise Stock Tracking`): como todo interno lleva `Projects User`, cualquiera podía verlos todos.
  → **`Custom Role`** (uno por report, fixture) que **override** los roles estándar del report y lo
  restringe a `PMO Executive Access` (`Administrator` pasa por tener todos los roles). Mecanismo nativo
  (`Report.is_permitted()` consulta `Custom Role` primero), en **doctype aparte** que el sync del Report
  **no pisa**, y el fixture lo **re-aplica en cada `migrate`** (self-heal).
- **Global Search**: verificado que aplica `has_permission` → ya cubierto por el hook, sin cambios.

**Riesgo de drift (documentado):** tras un `bench migrate`/upgrade de ERPNext hay que **verificar**:
(a) que los reports siguen llamándose igual y con el mismo `ref_doctype` (si ERPNext los renombra, el
`Custom Role` queda huérfano y el report vuelve a ser accesible por su rol estándar); (b) que el
`Custom Role` sigue presente (el fixture lo re-crea, pero si ERPNext introduce nuevos reports que
exponen Project/Task hay que añadirlos). El fixture cubre el borrado accidental, **no** los renombres
de upstream. **Aún no** se construyen reports sustitutos de `pmo` (diferido).

## Matriz de permisos (alcance del ACL de pmo, sobre la capacidad de rol nativa)

| Actor | Read Project | Write Project | Read Task | Write Task | Manual Share |
|---|---|---|---|---|---|
| Project creator (owner) | ✅ | ✅ | ✅ todas | ✅ todas | ✅ (su Project) |
| `DocShare(Project, read)` | ✅ | ❌ | ✅ (de su Project) | ❌ | ❌ |
| `DocShare(Project, write)` | ✅ | ✅ | ✅ (de su Project) | ✅ (de su Project) | ❌ |
| Task-only assignee (ToDo) | ❌ | ❌ | ✅ solo esa Task | ✅ solo esa Task | ❌ |
| PMO Manager | ❌ | ❌ | ❌ | ❌ | ❌ |
| PMO Executive Access | ✅ todos | ❌ | ✅ todas | ❌ | ✅ |
| System Manager | ❌ (no auto) | ❌ | ❌ (no auto) | ❌ | ❌ (no por defecto) |
| Administrator | ✅ | ✅ | ✅ | ✅ | ✅ |

> Notas: "✅" = el ACL de pmo lo **permite en alcance**; el derecho efectivo requiere además la
> **capacidad de rol** nativa. `System Manager`/`Administrator` como única vía admin de share manual
> (System Manager solo si se le concede explícitamente). `PMO Manager`/`System Manager` solo acceden a
> contenido si además son owner/member/assignee/executive.

## Matriz de vectores (boundary = {Project, Task})

- List/Report Builder/Tree/Gantt/Calendar/link/API-list → `pqc` ✅.
- Documento único/URL → `has_permission` ✅.
- **Global Search** → aplica `doc.has_permission()` (`global_search.py`) → **cubierto** ✅ (verificado P0).
- **Reports que ignoran `pqc`** (`get_all`/`db.sql`): `Project Summary`, `Delayed Tasks Summary`,
  `Project wise Stock Tracking` → **mitigado P0** vía `Custom Role` (D11) restringidos a
  `PMO Executive Access`/`Administrator` ✅.
- **Whitelisted + `get_all`** `create_duplicate_project` (`project.py`) → **mitigado P0** vía
  `override_whitelisted_methods` con check de READ del Project origen (D11) ✅.
- DocShare = acceso aditivo intencional (D8). Administrator/SQL/jobs = documentado (D9).
- Documentos con **autorización independiente** (Timesheet, Expense Claim, Sales Invoice) **no** se
  ocultan por tener Project relacionado. Los reports de Timesheet (`Daily Timesheet Summary`,
  `Timesheet Billing Summary`) exponen la columna `project` pero se rigen por la autorización propia
  de Timesheet → fuera del boundary de este ADR.

## Impacto en nativo / nuevos objetos

- **Nativo:** sin cambios de core; **sin** cambios de DocPerm de read/write/create. La capacidad
  `share` se gestiona por hook (no por Custom DocPerm) salvo fallback.
- **Nuevos (pmo):** roles `PMO Manager`, `PMO Executive Access`; hooks `permission_query_conditions` y
  `has_permission` para Project y Task (alcance read/write + gate de `ptype=share`). **Membresía derivada
  de `DocShare(Project)` + `ToDo`** (revisado v0.6.0; **sin** child DocType propio).

## Consecuencias

Aislamiento fail-closed en vectores basados en `get_list`/`has_permission`, upgrade-safe (hooks). Resto
de vectores auditados explícitamente en P0. Sharing nativo intacto. Sin congelar DocPerm nativos.

## Riesgos

- `pqc` no cascada a satélites ni a métodos con `get_all` → auditoría (matriz).
- Performance: subconsulta de membresía por listado sobre `tabDocShare` (indexada nativamente por
  `share_doctype`/`share_name`/`user`).
- SHARE: dependemos de la semántica grant/restrict del controlador (verificación P0); fallback = Custom
  DocPerm completo + re-sync (con drift a gestionar).
- Dependencia `assign_to` ↔ ToDo (verificación P0).

## Alternativas descartadas

`Project User` como enforcement (dispara `control_access_for_project_users` → DocShare + emails);
**`PMO Project Member` (child de membresía) — retirado en v0.6.0** a favor de `DocShare(Project)` + `ToDo`;
User Permissions (alcance global cross-doctype, no fail-closed sin ajuste global); modificar DocPerm de
read/write; jerarquía en el ACL; bloquear/neutralizar/desactivar DocShare; `_assign` como llave del
Project; Custom DocPerm parcial para `share` (reemplaza el conjunto nativo y congela permisos);
`pmo_role` de 3 niveles en el
MVP.

## Estrategia de pruebas (P0-implementación, site con Company/Stock)

Usuarios ficticios (owner/member/assignee/pmo_manager/executive/system_manager/unrelated): 0 fugas para
no-miembro en List/Gantt/Calendar/link/API/URL/report builder; assignee solo su Task; executive
read-all sin write; system_manager sin acceso automático; **asignar/desasignar** → verificar que
`assign_to` no crea auto-share y que la visibilidad se revoca al cancelar el ToDo; **share manual**
solo por Executive/Admin; job con `ignore_permissions` no se rompe; `create_duplicate_project`
auditado.

## Criterios de aceptación

- 0 fugas READ en vectores `get_list`/`has_permission` para no-miembro.
- WRITE conforme a la matriz (owner escribe Project; member escribe Tasks; assignee solo su Task;
  executive read-only).
- SHARE manual solo `PMO Executive Access`/`Administrator`, **sin** alterar read/write/create nativos y
  **upgrade-safe**.
- `PMO Manager` ≠ acceso global; `System Manager` restringido; `Administrator` documentado.
- Sharing nativo intacto; `assign_to` no genera auto-share (o queda documentado).
- Pregunta **"¿por qué X ve esto?"** → causa explícita: owner · PMO Project Member · Task Assignee ·
  Executive Access · Share explícito.
