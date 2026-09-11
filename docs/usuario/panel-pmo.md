# Panel PMO (workspace de entrada)

El workspace **PMO** (menú lateral → único acceso **PMO**) es el **centro de control**: al entrar
responde de inmediato *"¿qué está pasando en mi portafolio y dónde debo poner atención?"* antes de
permitir profundizar. No es un índice de enlaces: es un tablero informativo construido con
componentes nativos de Frappe (Number Cards, Dashboard Charts, Quick List), más los accesos a las
experiencias y las secciones de Informes/Configuración.

## Qué muestra al entrar

### Salud del portafolio (indicadores)

Tarjetas numéricas (Number Cards) que reutilizan el motor de **PMO Portfolio** (respetan tu
visibilidad P4 — solo cuentan proyectos que puedes ver):

- **Projects** — proyectos activos en tu alcance.
- **Deviated** — proyectos desviados (forecast supera el compromiso, o tareas vencidas, o forecast de
  tareas más allá de su fecha comprometida).
- **At risk** — proyectos en riesgo (forecast corrido respecto de la línea base, sin incumplir aún).
- **Without baseline** — proyectos sin línea base vigente.
- **Overdue tasks** — total de tareas vencidas en el portafolio.
- **Forecast > commitment** — total de tareas cuyo forecast excede su fecha comprometida.
- **Open change requests** — solicitudes de cambio abiertas (Draft / In Review).

### Gráficos

- **Projects by status** — distribución de proyectos por estado.
- **Change requests by state** — solicitudes de cambio por estado del workflow.

### Quick list

- **Open change requests** — lista accionable de solicitudes de cambio abiertas (abre cada una).

> Todos los indicadores y listas respetan la privacidad **P4**: cada usuario ve únicamente lo que ya
> puede leer (proyectos propios, compartidos, o todos con acceso ejecutivo). No se recalcula nada nuevo
> ni se ejecuta lógica de análisis en el navegador: los conteos reutilizan los motores existentes.

## Profundizar (accesos)

Tres accesos directos a las experiencias completas:

- **Portfolio** — salud multi-proyecto ([portafolio](portafolio.md)).
- **Project Control** — control de un proyecto ([project-control](project-control.md)).
- **Capacity Planning** — capacidad y sobrecarga ([capacity-planning](capacity-planning.md)).

## Informes y configuración

- **Reports** — listado compacto de los 9 reportes (siguen disponibles y ejecutables; no son
  protagonistas del panel).
- **PMO configuration** — PMO Capacity, PMO Project Baseline, PMO Change Request y la utilidad
  administrativa **Import Tags**.

## Navegación (barra lateral)

La barra lateral de `/desk/pmo` presenta **un único acceso: PMO**. Los reportes individuales, el grupo
Pages y los DocTypes sueltos ya **no** aparecen sueltos en la barra (se llega a ellos desde el panel).
Nada se eliminó: todo sigue existiendo y con ruta propia.
