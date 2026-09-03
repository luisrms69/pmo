# Privacidad de proyectos y tareas

En PMO, los **Proyectos** y las **Tareas** son **privados por defecto**. Aunque un compañero tenga
permiso general para ver proyectos, **no** verá los tuyos salvo que tenga una razón explícita de acceso.
Esto protege proyectos sensibles (RRHH, reorganizaciones, financieros, estratégicos).

## ¿Quién puede ver un Proyecto?

Solo estas personas ven un Proyecto y aparece en sus listas, Gantt, calendario y búsquedas:

- **El creador (owner)** del Proyecto.
- Los **miembros** del Proyecto (tabla *Miembros PMO* dentro del Proyecto).
- Quien tenga el acceso especial **PMO Executive Access** (dirección/ejecutivos).
- Quien haya recibido el Proyecto por **Compartir** (Share) explícito.

Cualquier otra persona **no ve el Proyecto**: no aparece en sus listados ni puede abrirlo por URL.

## ¿Quién puede ver una Tarea?

Una Tarea sigue la privacidad de **su Proyecto**:

- Si ves el Proyecto, ves sus Tareas.
- Si te **asignan** una Tarea concreta, ves **solo esa Tarea** — no el Proyecto ni las demás Tareas.
  Estar asignado a una Tarea **no** te convierte en miembro del Proyecto.
- Las Tareas **sin Proyecto** siguen las reglas estándar de ERPNext.

## Diferencia clave: miembro del Proyecto vs. asignado a una Tarea

| | Ve el Proyecto | Ve todas sus Tareas | Ve solo una Tarea |
|---|---|---|---|
| **Miembro del Proyecto** | Sí | Sí | — |
| **Asignado a una Tarea** | No | No | Sí (la suya) |

## ¿Quién puede editar?

- **Creador (owner):** edita el Proyecto y todas sus Tareas.
- **Miembro del Proyecto:** edita las **Tareas** del Proyecto, pero **no** el Proyecto en sí.
- **Asignado a una Tarea:** edita **solo** su Tarea.
- **PMO Executive Access:** ve todo, pero es **solo lectura** (no edita).

## Dar acceso a alguien

- **Añadir un miembro:** abre el Proyecto → tabla **Miembros PMO** → agrega al usuario. Pasa a ver el
  Proyecto y a poder trabajar sus Tareas.
- **Asignar una Tarea:** usa la asignación normal (ToDo) de la Tarea. La persona verá **solo** esa Tarea.
  Al **cancelar/quitar** la asignación, deja de verla.
- **Compartir (Share) manual:** solo **PMO Executive Access** (y Administrador) pueden compartir un
  Proyecto o Tarea con otra persona. El resto de usuarios no tiene el botón de compartir habilitado.

## Reportes con datos de todos los proyectos

Algunos reportes estándar de ERPNext muestran información de **todos** los proyectos/tareas
(*Project Summary*, *Delayed Tasks Summary*, *Project wise Stock Tracking*). Para no romper la
privacidad, **solo** los usuarios con **PMO Executive Access** (y Administrador) pueden ejecutarlos.

## Notas

- El **Administrador** y los procesos automáticos del sistema pueden ver todo (comportamiento estándar
  de la plataforma).
- Compartir un **Proyecto** da acceso solo al Proyecto, no automáticamente a sus Tareas; compartir una
  **Tarea** da acceso solo a esa Tarea.
- Si te preguntas *"¿por qué esta persona ve esto?"*, la respuesta siempre es una de estas causas:
  es el creador · es miembro del Proyecto · está asignada a esa Tarea · tiene PMO Executive Access · se
  lo compartieron explícitamente.
