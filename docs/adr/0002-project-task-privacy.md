# ADR-0002: Project/Task Privacy, Security Boundary y Permisos

**Estado:** Propuesto
**Fecha:** 2026-09-02
**App:** pmo · **Rama protegida:** version-16

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
                     OR user ∈ PMO Project Member(project)
                     OR user tiene PMO Executive Access
                     OR existe DocShare legítimo del Project
Task visible si:     Task.project vacío → reglas estándar ERPNext
                     OR Project(Task) visible-para-user           (Task hereda la frontera del Project)
                     OR existe ToDo activo (Task, user)            (asignación directa: SOLO esa Task)
                     OR user tiene PMO Executive Access
                     OR existe DocShare legítimo de la Task
```

- `Task assignment ≠ Project membership`: no concede el Project ni otras Tasks, ni convierte en miembro.

### D2 — Membresía = `PMO Project Member` (simple), no `Project User`

Child DocType propio en `Project` (Custom Field `Table`), campo `member: User`. **Sin niveles**
(`pmo_role` eliminado del MVP: no hay diferencia funcional de permisos; la única distinción real es
owner vs member). Se añadirá Observer/PM más adelante solo con justificación. Motivo de no usar
`Project User`: dispara `control_access_for_project_users` → DocShare + emails de portal.

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

### D6 — Política de WRITE

Capacidad (rol nativo) × alcance (hooks):

- **Owner**: write Project + write todas sus Tasks.
- **PMO Project Member**: **no** write del documento Project; **sí** read/write de las Tasks de su
  Project (dentro de su capacidad de rol).
- **Task-only assignee**: read/write **solo** su Task.
- **PMO Executive Access**: read global, **write no**.
- **PMO Manager**: nada por el rol.

### D7 — Política de SHARE manual (nativa, sin lógica custom de autorización)

- **Permitido:** `PMO Executive Access` y `Administrator`. **Denegado** al resto (`PMO Manager`,
  `System Manager` (no por defecto), owner/member/assignee).
- **Implementación upgrade-safe:** controlar `ptype == "share"` en el **`has_permission` hook**
  existente (deniega a no-ejecutivos; concede a Executive). **No** usar Custom DocPerm parcial
  (reemplaza el conjunto nativo completo y congela permisos). **Fallback** solo si el hook no puede
  *conceder* share: Custom DocPerm **completo** por **fixture** + **re-sync documentado** en cada
  upgrade de ERPNext, preservando read/write/create nativos y cambiando solo `share`.

> **Pendiente P0 (bloqueante de esta decisión):** validar si `has_permission(ptype="share")` puede
> **conceder** la capacidad `share` a `PMO Executive Access` cuando su rol base no la trae (semántica
> *grant vs restrict* del controlador en Frappe v16). Si **puede conceder** → solución final = solo
> hook. Si **no puede** → se usa el **fallback documentado** (Custom DocPerm completo por fixture +
> procedimiento de re-sync en upgrades).

### D8 — Política de `DocShare` (se conserva el mecanismo nativo)

- Share = mecanismo nativo legítimo, **aditivo y revocable**; **no** se bloquea/neutraliza/sustituye
  globalmente.
- Share manual de **Project** → acceso **solo al Project**, **no** a sus Tasks (empírico). Share manual
  de **Task** → **solo esa Task** (empírico).
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

## Matriz de permisos (alcance del ACL de pmo, sobre la capacidad de rol nativa)

| Actor | Read Project | Write Project | Read Task | Write Task | Manual Share |
|---|---|---|---|---|---|
| Project creator (owner) | ✅ | ✅ | ✅ todas | ✅ todas | ❌ |
| PMO Project Member | ✅ | ❌ | ✅ (de su Project) | ✅ (de su Project) | ❌ |
| Task-only assignee | ❌ | ❌ | ✅ solo esa Task | ✅ solo esa Task | ❌ |
| PMO Manager | ❌ | ❌ | ❌ | ❌ | ❌ |
| PMO Executive Access | ✅ todos | ❌ | ✅ todas | ❌ | ✅ |
| Share explícito | según flags | según flags | según flags | según flags | ❌ |
| System Manager | ❌ (no auto) | ❌ | ❌ (no auto) | ❌ | ❌ (no por defecto) |
| Administrator | ✅ | ✅ | ✅ | ✅ | ✅ |

> Notas: "✅" = el ACL de pmo lo **permite en alcance**; el derecho efectivo requiere además la
> **capacidad de rol** nativa. `System Manager`/`Administrator` como única vía admin de share manual
> (System Manager solo si se le concede explícitamente). `PMO Manager`/`System Manager` solo acceden a
> contenido si además son owner/member/assignee/executive.

## Matriz de vectores (boundary = {Project, Task})

- List/Report Builder/Tree/Gantt/Calendar/link/API-list → `pqc` ✅.
- Documento único/URL → `has_permission` ✅.
- **Query reports (SQL propio)** ⚠️ no reciben `pqc` (revisar/restringir en P0).
- **Whitelisted + `get_all`/`ignore_permissions`** (ej. `create_duplicate_project`, `project.py:610`)
  ⚠️ auditar (`override_whitelisted_methods` o aceptar documentado).
- Global Search ⚠️ verificar en P0. Attachments/timeline/comments ⚠️ evaluar en P0.
- DocShare = acceso aditivo intencional (D8). Administrator/SQL/jobs = documentado (D9).
- Documentos con **autorización independiente** (Timesheet, Expense Claim, Sales Invoice) **no** se
  ocultan por tener Project relacionado.

## Impacto en nativo / nuevos objetos

- **Nativo:** sin cambios de core; **sin** cambios de DocPerm de read/write/create. La capacidad
  `share` se gestiona por hook (no por Custom DocPerm) salvo fallback.
- **Nuevos (pmo):** `PMO Project Member` (child, `member`); roles `PMO Manager`, `PMO Executive
  Access`; hooks `permission_query_conditions` y `has_permission` para Project y Task (alcance
  read/write + gate de `ptype=share`).

## Consecuencias

Aislamiento fail-closed en vectores basados en `get_list`/`has_permission`, upgrade-safe (hooks). Resto
de vectores auditados explícitamente en P0. Sharing nativo intacto. Sin congelar DocPerm nativos.

## Riesgos

- `pqc` no cascada a satélites ni a métodos con `get_all` → auditoría (matriz).
- Performance: subconsulta de membresía por listado (indexar `PMO Project Member`).
- SHARE: dependemos de la semántica grant/restrict del controlador (verificación P0); fallback = Custom
  DocPerm completo + re-sync (con drift a gestionar).
- Dependencia `assign_to` ↔ ToDo (verificación P0).

## Alternativas descartadas

`Project User`/Share como enforcement; User Permissions; modificar DocPerm de read/write; jerarquía en
el ACL; bloquear/neutralizar/desactivar DocShare; `_assign` como llave del Project; Custom DocPerm
parcial para `share` (reemplaza el conjunto nativo y congela permisos); `pmo_role` de 3 niveles en el
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
