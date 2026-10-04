# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Schedule Intelligence — análisis de cronograma READ-ONLY (ADR-0017).

Esta capa **solo lee y compone señales**: NUNCA escribe `exp_*`, baseline, `pmo_deadline`,
`pmo_committed_end_date`, actuals, PHI, Governance ni Change Requests. No crea un segundo modelo de
forecast: analiza directamente los `exp_*` nativos (el plan vigente que ERPNext ya cascada por FS).

Fundamento (I.0):
- Duración canónica = días HÁBILES entre `getdate(exp_start_date)` y `getdate(exp_end_date)` (inclusiva).
  `expected_time` es esfuerzo, NO duración. Todo a `getdate()` (sin hora).
- Calendario: `Project.holiday_list` → `Company.default_holiday_list` (nativos). Reutiliza `is_holiday`.
  Si no hay calendario resoluble: `calendar_available=False`, cae a días naturales y OMITE los chequeos
  que dependen del calendario. NUNCA lanza: Project Control no debe romperse.
- Dependencias = FS implícito (`Task Depends On` solo tiene `task`). Grupos = rollup (no nodos);
  milestones = duración 0; fechas incompletas = gap (fuera del forward-pass); Completed/Cancelled/Template
  fuera de la red activa.

I.1 entrega el **diagnóstico de integridad** + el **forward pass** (ES/EF hábil) como infraestructura
común. Backward pass / slack (I.2) y ruta crítica (I.3) quedan DIFERIDOS.
"""

import frappe
from frappe.utils import add_days, getdate

# Estados fuera de la red activa (no se programan ni diagnostican como pendientes).
_INACTIVE = ("Completed", "Cancelled", "Template")


# --------------------------------------------------------------------------------------
# Calendario laboral (read-only; degradación segura)
# --------------------------------------------------------------------------------------
def resolve_holiday_list(project: str, meta: dict | None = None) -> str | None:
	"""`Project.holiday_list` → `Company.default_holiday_list` → None (sin lanzar)."""
	m = meta or (frappe.db.get_value("Project", project, ["holiday_list", "company"], as_dict=True) or {})
	hl = m.get("holiday_list")
	if hl:
		return hl
	company = m.get("company")
	if company:
		return frappe.db.get_value("Company", company, "default_holiday_list") or None
	return None


def _is_holiday(holiday_list: str, d) -> bool:
	from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday

	return bool(is_holiday(holiday_list, getdate(d)))


def working_days(start, end, holiday_list: str | None) -> int:
	"""Días hábiles INCLUSIVOS en [start, end]. Sin `holiday_list` → días naturales. end<start → 0.
	Puro: no consulta nada salvo `is_holiday` (solo si hay calendario)."""
	if not start or not end:
		return 0
	s, e = getdate(start), getdate(end)
	if e < s:
		return 0
	if not holiday_list:
		return (e - s).days + 1
	n, day = 0, s
	while day <= e:
		if not _is_holiday(holiday_list, day):
			n += 1
		day = add_days(day, 1)
	return n


def add_working_days(start, n: int, holiday_list: str | None):
	"""Desplaza `n` días hábiles desde `start` (n>0 adelante, n<0 atrás, n=0 → `start`). El backward pass
	(I.2) lo usa con `n` negativo. Sin `holiday_list` → días naturales (soporta signo)."""
	d = getdate(start)
	if n == 0:
		return d
	if not holiday_list:
		return add_days(d, n)
	step = 1 if n > 0 else -1
	remaining, day = abs(n), d
	while remaining > 0:
		day = add_days(day, step)
		if not _is_holiday(holiday_list, day):
			remaining -= 1
	return day


# --------------------------------------------------------------------------------------
# Lectura del grafo (read-only)
# --------------------------------------------------------------------------------------
def _read_tasks(project: str) -> list[dict]:
	"""Tareas HOJA del Project (is_group=0) con los campos de cronograma. Solo lectura."""
	return frappe.get_all(
		"Task",
		filters={"project": project, "is_group": 0},
		fields=[
			"name",
			"subject",
			"status",
			"is_milestone",
			"exp_start_date",
			"exp_end_date",
			"pmo_deadline",
			"act_start_date",
			"progress",
		],
		limit=0,
	)


def _read_edges(project: str, task_names: set[str]) -> list[tuple[str, str]]:
	"""Aristas (predecesora → sucesora) desde `Task Depends On`. `parent` = sucesora, `task` = predecesora.
	Solo aristas entre tareas hoja del Project (ignora referencias fuera del conjunto)."""
	if not task_names:
		return []
	rows = frappe.get_all(
		"Task Depends On",
		filters={"parent": ["in", list(task_names)]},
		fields=["parent", "task"],
		limit=0,
	)
	return [(r.task, r.parent) for r in rows if r.task in task_names and r.parent in task_names]


def _detect_cycles(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
	"""Ciclos en el grafo dirigido pred→succ (DFS con pila). Devuelve listas de nodos involucrados."""
	adj: dict[str, list[str]] = {n: [] for n in nodes}
	for pred, succ in edges:
		adj.setdefault(pred, []).append(succ)
		adj.setdefault(succ, [])
	WHITE, GRAY, BLACK = 0, 1, 2
	color = dict.fromkeys(adj, WHITE)
	cycles, stack = [], []

	def dfs(u):
		color[u] = GRAY
		stack.append(u)
		for v in adj[u]:
			if color[v] == GRAY:  # back-edge → ciclo
				if v in stack:
					cycles.append([*stack[stack.index(v) :], v])
			elif color[v] == WHITE:
				dfs(v)
		stack.pop()
		color[u] = BLACK

	for n in list(adj):
		if color[n] == WHITE:
			dfs(n)
	return cycles


def _node_duration(node: dict, holiday_list: str | None) -> int:
	"""Duración en días hábiles: milestone → 0; resto → working_days(start,end) con piso 1."""
	return 0 if node["is_milestone"] else max(working_days(node["start"], node["end"], holiday_list), 1)


def _adjacency(active: dict, edges: list[tuple[str, str]]):
	"""Listas de predecesoras/sucesoras restringidas al conjunto `active`. Reutilizable por ambos passes."""
	preds: dict[str, list[str]] = {t: [] for t in active}
	succs: dict[str, list[str]] = {t: [] for t in active}
	for p, s in edges:
		if p in active and s in active:
			preds[s].append(p)
			succs[p].append(s)
	return preds, succs


def _topo_order(active: dict, preds: dict, succs: dict) -> list[str]:
	"""Orden topológico (Kahn). Si queda algo sin ordenar (ciclo), esos nodos no aparecen."""
	indeg = {t: len(preds[t]) for t in active}
	queue = [t for t in active if indeg[t] == 0]
	topo = []
	while queue:
		u = queue.pop()
		topo.append(u)
		for v in succs.get(u, []):
			indeg[v] -= 1
			if indeg[v] == 0:
				queue.append(v)
	return topo


def _forward_pass(active: dict, edges: list[tuple[str, str]], holiday_list: str | None) -> dict:
	"""ES/EF en días hábiles sobre la red FS (solo tareas activas con fechas completas y sin ciclo).
	ES(raíz)=exp_start_date; ES(sucesora)=siguiente hábil tras max(EF predecesoras); EF=ES+(dur-1) hábiles;
	milestone → dur 0 (EF=ES). Devuelve {task: {"es": date, "ef": date}} de lo computable. NO escribe nada."""
	preds, succs = _adjacency(active, edges)
	out: dict[str, dict] = {}
	for t in _topo_order(active, preds, succs):
		node = active[t]
		dur = _node_duration(node, holiday_list)
		if preds[t]:
			base = max((out[p]["ef"] for p in preds[t] if p in out), default=None)
			es = add_working_days(base, 1, holiday_list) if base else getdate(node["start"])
		else:
			es = getdate(node["start"])
		ef = add_working_days(es, dur - 1, holiday_list) if dur > 0 else getdate(es)
		out[t] = {"es": getdate(es), "ef": ef}
	return out


def _load_network(project: str):
	"""Carga READ-ONLY común a I.1/I.2: meta del Project, calendario resoluble, mapa de tareas hoja, red
	activa (fuera Completed/Cancelled/Template) y aristas FS. Fuente única para no duplicar la lectura."""
	meta = (
		frappe.db.get_value(
			"Project",
			project,
			["holiday_list", "company", "expected_end_date", "pmo_committed_end_date"],
			as_dict=True,
		)
		or {}
	)
	holiday_list = resolve_holiday_list(project, meta)
	tasks = _read_tasks(project)
	by_name = {t.name: t for t in tasks}
	active = {}
	for t in tasks:
		if t.status in _INACTIVE:
			continue
		active[t.name] = {
			"name": t.name,
			"subject": t.subject,
			"is_milestone": int(t.is_milestone or 0),
			"start": t.exp_start_date,
			"end": t.exp_end_date,
			"deadline": t.pmo_deadline,
		}
	edges = _read_edges(project, set(by_name))
	return meta, holiday_list, by_name, active, edges


# --------------------------------------------------------------------------------------
# Diagnóstico de integridad (I.1) — entrada pública, READ-ONLY
# --------------------------------------------------------------------------------------
def analyze_schedule_integrity(project: str, status_date=None) -> dict:
	"""Diagnóstico read-only del programa (ADR-0017, I.1). NUNCA escribe. Devuelve diagnósticos + resumen
	compacto. `status_date` no se usa para mutar nada; se acepta por simetría con el resto de Project Control."""
	meta, holiday_list, by_name, active, edges_all = _load_network(project)
	calendar_available = bool(holiday_list)
	# Para dependencias: solo entre activas con fechas (las incompletas se reportan aparte).
	diag = {
		"incoherent": [],
		"multi_predecessor": [],
		"cycles": [],
		"incomplete_dates": [],
		"non_working_day": [],
		"deadline_exceeded": [],
		"natural_vs_working": [],
	}

	# 1) Fechas incompletas (gap de planeación) — tarea hoja activa sin exp_start o exp_end.
	for t in active.values():
		missing = [k for k in ("start", "end") if not t[k]]
		if missing:
			diag["incomplete_dates"].append({"task": t["name"], "subject": t["subject"], "missing": missing})

	# 2) Ciclos (estructural; sobre todas las hoja, independiente de estado/fechas).
	diag["cycles"] = [{"tasks": c} for c in _detect_cycles(list(by_name), edges_all)]

	# 3) Incoherencia temporal FS + multi-predecesora (requiere fechas completas en ambos extremos).
	preds_map: dict[str, list[str]] = {}
	for p, s in edges_all:
		if s in active and p in active:
			preds_map.setdefault(s, []).append(p)
	for s, preds in preds_map.items():
		succ = active[s]
		if not succ["start"]:
			continue
		s_start = getdate(succ["start"])
		dated_preds = [(p, getdate(active[p]["end"])) for p in preds if active[p]["end"]]
		for p, p_end in dated_preds:
			if s_start < p_end:  # FS violado: la sucesora inicia antes de terminar la predecesora
				diag["incoherent"].append(
					{
						"task": s,
						"subject": succ["subject"],
						"predecessor": p,
						"task_start": succ["start"],
						"pred_end": active[p]["end"],
					}
				)
		if len(dated_preds) >= 2:
			max_end = max(pe for _, pe in dated_preds)
			if s_start < max_end:
				diag["multi_predecessor"].append(
					{
						"task": s,
						"subject": succ["subject"],
						"predecessors": [p for p, _ in dated_preds],
						"task_start": succ["start"],
					}
				)

	# 4) pmo_deadline incumplido (forecast end > deadline). Reutiliza la semántica de ADR-0009.
	for t in active.values():
		if t["deadline"] and t["end"] and getdate(t["end"]) > getdate(t["deadline"]):
			diag["deadline_exceeded"].append(
				{
					"task": t["name"],
					"subject": t["subject"],
					"exp_end": t["end"],
					"deadline": t["deadline"],
					"slip_days": (getdate(t["end"]) - getdate(t["deadline"])).days,
				}
			)

	# 5) Chequeos dependientes del calendario (solo si hay calendario resoluble).
	if calendar_available:
		for t in active.values():
			if t["is_milestone"]:
				continue
			for which in ("start", "end"):
				if t[which] and _is_holiday(holiday_list, t[which]):
					diag["non_working_day"].append(
						{"task": t["name"], "subject": t["subject"], "which": which, "date": t[which]}
					)
			# Divergencia natural-day (cascada nativa) vs hábil: el tramo contiene días no laborables.
			if t["start"] and t["end"]:
				cal = (getdate(t["end"]) - getdate(t["start"])).days + 1
				wrk = working_days(t["start"], t["end"], holiday_list)
				if cal != wrk:
					diag["natural_vs_working"].append(
						{
							"task": t["name"],
							"subject": t["subject"],
							"calendar_days": cal,
							"working_days": wrk,
						}
					)

	# 6) Reconciliación de fines (sin sustituir ninguno). max EF solo si no hay ciclos.
	computable = {t: d for t, d in active.items() if d["start"] and d["end"]}
	fp = {} if diag["cycles"] else _forward_pass(computable, edges_all, holiday_list)
	max_ef = max((v["ef"] for v in fp.values()), default=None)
	exp_ends = [getdate(t["end"]) for t in active.values() if t["end"]]
	max_exp_end = max(exp_ends) if exp_ends else None
	proj_end = getdate(meta["expected_end_date"]) if meta.get("expected_end_date") else None
	distinct = {str(x) for x in (max_ef, max_exp_end, proj_end) if x is not None}
	ends = {
		"max_ef": str(max_ef) if max_ef else None,
		"max_exp_end": str(max_exp_end) if max_exp_end else None,
		"project_expected_end": str(proj_end) if proj_end else None,
		"diverges": len(distinct) > 1,
	}

	incoherencias = len(diag["incoherent"]) + len(diag["multi_predecessor"])
	summary = {
		"incoherencias": incoherencias,
		"deadline_excedido": len(diag["deadline_exceeded"]),
		"ciclos": len(diag["cycles"]),
		"fechas_incompletas": len(diag["incomplete_dates"]),
		"divergencia_calendario": len(diag["natural_vs_working"]),
		"sin_calendario": not calendar_available,
		"fines_divergen": ends["diverges"],
		"total": incoherencias
		+ len(diag["deadline_exceeded"])
		+ len(diag["cycles"])
		+ len(diag["incomplete_dates"]),
	}
	return {
		"calendar_available": calendar_available,
		"holiday_list": holiday_list,
		"diagnostics": diag,
		"ends": ends,
		"summary": summary,
	}


# --------------------------------------------------------------------------------------
# Slack / Float (I.2) — backward pass + holgura, READ-ONLY. CPM base sobre la red actual.
# --------------------------------------------------------------------------------------
def _working_span(a, b, holiday_list: str | None) -> int:
	"""Distancia DIRIGIDA en días hábiles de `a` a `b` (0 si a==b; negativa si b<a). Base de la holgura."""
	a, b = getdate(a), getdate(b)
	if a == b:
		return 0
	if b > a:
		return working_days(a, b, holiday_list) - 1
	return -(working_days(b, a, holiday_list) - 1)


def _backward_pass(active: dict, edges, holiday_list, fp: dict, project_finish) -> dict:
	"""LS/LF en días hábiles anclados en `project_finish` (= max EF de las sumidero). Backward sobre la red
	FS: LF(sumidero)=project_finish; LF(pred)=min(LS(sucesora) - 1 día hábil). NO escribe nada."""
	preds, succs = _adjacency(active, edges)
	topo = _topo_order(active, preds, succs)
	out: dict[str, dict] = {}
	for t in reversed(topo):  # sucesoras antes que predecesoras
		node = active[t]
		dur = _node_duration(node, holiday_list)
		child_ls = [out[s]["ls"] for s in succs.get(t, []) if s in out]
		if child_ls:
			lf = min(add_working_days(ls, -1, holiday_list) for ls in child_ls)
		else:
			lf = project_finish  # sumidero: puede terminar tan tarde como el fin de red
		ls = add_working_days(lf, -(dur - 1), holiday_list) if dur > 0 else getdate(lf)
		out[t] = {"ls": getdate(ls), "lf": getdate(lf)}
	return out


def analyze_schedule_slack(project: str, status_date=None) -> dict:
	"""Slack/Float read-only (ADR-0017, I.2). CPM base: forward + backward sobre la red FS actual, ancla =
	max EF de las sumidero. NUNCA escribe ni usa compromiso/deadline como ancla; esas son señales separadas.

	Degrada: ciclos → red no evaluable; sin tareas con fechas → no evaluable (no inventa); fechas incompletas
	→ excluidas de la red (se cuentan); sin calendario → días naturales con bandera (nunca error de pantalla)."""
	meta, holiday_list, by_name, active, edges = _load_network(project)
	calendar_available = bool(holiday_list)
	committed = meta.get("pmo_committed_end_date")

	base = {
		"evaluable": False,
		"reason": None,
		"calendar_available": calendar_available,
		"holiday_list": holiday_list,
		"project_finish": None,
		"nodes": [],
		"critical_path": [],
		"incomplete_excluded": 0,
		"margin_vs_committed": {
			"committed_end": str(committed) if committed else None,
			"network_finish": None,
			"margin_days": None,
		},
		"deadline_breach": [],
		"summary": {
			"evaluable": False,
			"sin_calendario": not calendar_available,
			"critical_count": 0,
			"min_total_slack": None,
			"committed_margin_days": None,
			"deadline_breach_count": 0,
		},
	}

	# Ciclos → la red no admite CPM (no hay orden topológico completo). Red no evaluable.
	if _detect_cycles(list(by_name), edges):
		base["reason"] = "cycles"
		return base

	# Solo nodos con fechas completas entran a la red; las incompletas se cuentan, no se inventan.
	net = {t: d for t, d in active.items() if d["start"] and d["end"]}
	base["incomplete_excluded"] = len(active) - len(net)
	if not net:
		base["reason"] = "no_dated_tasks"
		return base

	fp = _forward_pass(net, edges, holiday_list)
	project_finish = max(v["ef"] for v in fp.values())
	bp = _backward_pass(net, edges, holiday_list, fp, project_finish)

	_, succs = _adjacency(net, edges)
	nodes, critical = [], []
	min_slack = None
	for t in net:
		node = net[t]
		es, ef = fp[t]["es"], fp[t]["ef"]
		ls, lf = bp[t]["ls"], bp[t]["lf"]
		total_slack = _working_span(ef, lf, holiday_list)  # == span(ES, LS)
		# Free slack: cuánto puede deslizarse sin mover el ES más temprano de ninguna sucesora.
		child_es = [fp[s]["es"] for s in succs.get(t, []) if s in fp]
		if child_es:
			free_slack = max(0, min(_working_span(ef, ces, holiday_list) - 1 for ces in child_es))
		else:
			free_slack = total_slack  # terminal: su holgura libre es la total (contra el fin de red)
		is_critical = total_slack <= 0
		if is_critical:
			critical.append(t)
		if min_slack is None or total_slack < min_slack:
			min_slack = total_slack
		# Señal SEPARADA (no ancla): el forecast calculado (EF) frente al pmo_deadline de la tarea.
		# `deadline_margin` = distancia hábil EF → deadline (+ margen, ≤0 incumplido). Incumplido = EF > deadline.
		deadline_margin = None
		if node["deadline"]:
			dl = getdate(node["deadline"])
			deadline_margin = _working_span(ef, dl, holiday_list)
			if ef > dl:
				base["deadline_breach"].append(
					{
						"task": t,
						"subject": node["subject"],
						"ef": str(ef),
						"deadline": str(dl),
						"over_days": _working_span(dl, ef, holiday_list),
					}
				)
		nodes.append(
			{
				"task": t,
				"subject": node["subject"],
				"is_milestone": node["is_milestone"],
				"es": str(es),
				"ef": str(ef),
				"ls": str(ls),
				"lf": str(lf),
				"duration": _node_duration(node, holiday_list),
				"total_slack": total_slack,
				"free_slack": free_slack,
				"is_critical": is_critical,
				"deadline": str(node["deadline"]) if node["deadline"] else None,
				"deadline_margin": deadline_margin,
			}
		)

	nodes.sort(key=lambda n: (n["total_slack"], n["es"]))
	# Señal SEPARADA (no ancla): margen de red contra el compromiso gobernado del proyecto.
	margin_days = _working_span(project_finish, committed, holiday_list) if committed else None

	base.update(
		{
			"evaluable": True,
			"project_finish": str(project_finish),
			"nodes": nodes,
			"critical_path": critical,
			"margin_vs_committed": {
				"committed_end": str(committed) if committed else None,
				"network_finish": str(project_finish),
				"margin_days": margin_days,
			},
		}
	)
	base["summary"] = {
		"evaluable": True,
		"sin_calendario": not calendar_available,
		"critical_count": len(critical),
		"min_total_slack": min_slack,
		"committed_margin_days": margin_days,
		"deadline_breach_count": len(base["deadline_breach"]),
	}
	return base
