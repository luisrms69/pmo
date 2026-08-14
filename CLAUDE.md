# CLAUDE.md — pmo

> **Reglas de operación Claude Code** (commits, PRs, base de datos, flujo de trabajo, prohibiciones git):
> Ver `/home/erpnext/Developer/frappe-infrastructure/.claude/CLAUDE.md`

---

## Estado del proyecto

- **App nueva:** creada en frappe-bench-v16
- **Bench activo:** `/home/erpnext/frappe-bench-v16`
- **Branch protegida:** `version-16` (nunca commitear directamente — estándar Frappe)
- **Versión:** 0.0.1 (desarrollo inicial)
- **En producción:** No

---

## Sites de desarrollo y prueba

| Site | Bench | Propósito | Notas |
|---|---|---|---|
| `pmo-v16.dev` | frappe-bench-v16 | Desarrollo activo | Features, migrate, export-fixtures — puerto 8412 |
| `test-pmo.localhost` | frappe-bench-v16 | Tests unitarios | Solo para `bench run-tests` — nunca modificar manualmente |

**Reglas de uso:**
- `bench migrate` → siempre con `--site`. Nunca sin site en bench compartido.
- `bench run-tests` → siempre `test-pmo.localhost` — nunca en el site de desarrollo.
- `bench export-fixtures` → `pmo-v16.dev`

**Apps en test-pmo.localhost:** frappe, erpnext, pmo

## Entorno
Ver contexto global en `frappe-infrastructure/.claude/CLAUDE.md`.

**Comandos frecuentes (bench v16):**
```bash
bench --site pmo-v16.dev migrate
bench --site pmo-v16.dev export-fixtures --app pmo
bench --site test-pmo.localhost run-tests --app pmo
bench build --app pmo
```
**NUNCA:** `bench migrate` sin `--site` — afecta todos los sites del bench compartido

---

## Qué hace esta app

Project Management Office. App para gestión de proyectos sobre el DocType nativo `Project` de ERPNext.

Primera funcionalidad prevista (aún no implementada): mover fechas de un Project que todavía no ha
iniciado.

---

## DocTypes principales

*(pendiente de documentar al implementar)*

---

## Fixtures

*(pendiente — declarar en hooks.py al crear Custom Fields, Roles, Workspaces)*

---

## Dependencias

**Apps requeridas:** erpnext (`required_apps = ["erpnext"]` en hooks.py)
**Apps en frappe-bench-v16:** frappe, erpnext, pmo
**Dependencias externas:** Ninguna

---

## Tests

```bash
bench --site test-pmo.localhost run-tests --app pmo
```

**Sin cobertura inicial.** Documentar tests aquí cuando se implementen.
**Site de tests dedicado:** `test-pmo.localhost` — nunca correr tests en el site de desarrollo.

---

## REGLAS GIT — PMO

### Antes de cada commit

- Correr linters en archivos modificados:
  ```bash
  ruff format <archivos .py modificados>
  npx prettier@2.7.1 --write <archivos .js modificados>
  ```

### Antes de cada PR

- [ ] Linters pasados
- [ ] Fixtures exportados si hubo cambios de Custom Fields, Roles, Workspaces
- [ ] Patch creado si hay cambios de esquema — **requiere autorización explícita**
- [ ] `bench --site pmo-v16.dev migrate` limpio
- [ ] Ver checklist global en `frappe-infrastructure/CONTRIBUTING.md`

### PROHIBICIÓN ABSOLUTA — NUNCA TRABAJAR EN version-16

**`version-16` es la rama protegida de pmo. Es el estándar Frappe upstream.**

- **Nunca implementar cambios estando en `version-16`.**
- **Nunca crear commits estando en `version-16`.**
- **Nunca hacer push directo a `version-16`.** Todo cambio entra por PR.
- Todo cambio (incluso documental) debe iniciar en una **rama de trabajo** creada desde `version-16`
  limpio y sincronizado. Convención de prefijos: `feat/ fix/ docs/ chore/ refactor/ hotfix/`
  (ver `CONTRIBUTING.md`).
- `/ship commit` y `/ship push` deben **rechazar** si la rama es `version-16`.
- `/ship pr` debe exigir rama distinta de `version-16` (PR hacia `version-16` como base).

**Única excepción de bootstrap:** el primer commit + primer push a `version-16` solo para crear el
repo remoto vacío. Esa excepción **termina en cuanto se crea y valida el ruleset**. Después de eso,
ni un cambio documental va directo a `version-16`.

### Reglas específicas del proyecto

- PRs siempre a `version-16`
- Site de desarrollo: `pmo-v16.dev`
- Site de tests: `test-pmo.localhost`
