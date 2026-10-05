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
común. I.2 añade el **backward pass** + **holgura** (total/libre). I.3 **interpreta** ese CPM como
**ruta crítica** (secuencias legibles + detalle), sin motor ni semántica nueva.
"""

import frappe
from frappe.utils import add_days, getdate

# Estados fuera de la red activa (no se programan ni diagnostican como pendientes).
_INACTIVE = ("Completed", "Cancelled", "Template")

# ------------------------------------------------------------------------------------------------
# Clasificación — FUENTE ÚNICA DE VERDAD (SSOT). Toda decisión "esto es crítico/incumplido/malo" vive
# AQUÍ, no en los templates. Los HTML solo mapean el token de severidad a una clase CSS; nunca aplican
# umbrales (`<= 0`, etc.). Tokens semánticos:
SEV_OK = "ok"  # correcto / dentro de margen
SEV_WARN = "warn"  # atención (informativo, no necesariamente problema)
SEV_BAD = "bad"  # problema / fuera de margen


def _sev_count(n: int) -> str:
	"""Contador de problemas: 0 → ok; >0 → bad."""
	return SEV_BAD if n else SEV_OK


def _sev_margin(days) -> str | None:
	"""Margen en días (compromiso o deadline): negativo (sin margen) → bad; 0 o + → ok. None → None."""
	if days is None:
		return None
	return SEV_BAD if days < 0 else SEV_OK


def _sev_min_slack(x) -> str:
	"""Holgura mínima de la red: NEGATIVA → bad (sobre-restringida). 0 es NORMAL (hay ruta crítica) → ok."""
	return SEV_BAD if (x is not None and x < 0) else SEV_OK


def _sev_critical_count(n: int) -> str:
	"""Nº de tareas en ruta crítica: informativo → warn si hay alguna (atención), ok si ninguna."""
	return SEV_WARN if n else SEV_OK


def _sev_flag(flag: bool) -> str:
	"""Bandera booleana → warn si está activa (atención), ok si no."""
	return SEV_WARN if flag else SEV_OK


def _days_label(days) -> str | None:
	"""Label de días con signo, LISTO para presentar: `+121 d`, `0 d`, `-5 d`. None → None. El template
	no deriva el signo (eso es lógica); recibe el texto final."""
	if days is None:
		return None
	return f"+{days} d" if days > 0 else f"{days} d"


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
	total = (
		incoherencias + len(diag["deadline_exceeded"]) + len(diag["cycles"]) + len(diag["incomplete_dates"])
	)
	summary = {
		"incoherencias": incoherencias,
		"deadline_excedido": len(diag["deadline_exceeded"]),
		"ciclos": len(diag["cycles"]),
		"fechas_incompletas": len(diag["incomplete_dates"]),
		"divergencia_calendario": len(diag["natural_vs_working"]),
		"sin_calendario": not calendar_available,
		"fines_divergen": ends["diverges"],
		"total": total,
		# Banderas de visibilidad (SSOT): el template NO evalúa `if count`; recibe el show ya resuelto.
		"show_ciclos": len(diag["cycles"]) > 0,
		# Severidad por métrica (SSOT): el template solo mapea token→clase, no evalúa umbrales.
		"sev": {
			"total": _sev_count(total),
			"incoherencias": _sev_count(incoherencias),
			"deadline_excedido": _sev_count(len(diag["deadline_exceeded"])),
			"fechas_incompletas": _sev_count(len(diag["incomplete_dates"])),
			"ciclos": _sev_count(len(diag["cycles"])),
		},
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
				# Severidad decidida en el dominio (SSOT): el template solo la mapea a color.
				"slack_sev": SEV_BAD if is_critical else SEV_OK,
				"deadline_sev": _sev_margin(deadline_margin),
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
				"severity": _sev_margin(margin_days),
			},
		}
	)
	base["summary"] = {
		"evaluable": True,
		"sin_calendario": not calendar_available,
		"critical_count": len(critical),
		"min_total_slack": min_slack,
		"min_total_slack_label": (f"{min_slack} d" if min_slack is not None else "—"),  # texto listo
		"committed_margin_days": margin_days,
		"committed_margin_label": _days_label(margin_days),  # texto listo: "+121 d" / "0 d" / "-5 d"
		"deadline_breach_count": len(base["deadline_breach"]),
		# Banderas de visibilidad (SSOT): el template NO evalúa `is not none` / `if count`.
		"show_committed_margin": margin_days is not None,
		"show_deadline_breach": len(base["deadline_breach"]) > 0,
		# Severidad por métrica (SSOT): el template solo mapea token→clase, no evalúa umbrales.
		"sev": {
			"critical_count": _sev_critical_count(len(critical)),
			"min_total_slack": _sev_min_slack(min_slack),
			"committed_margin": _sev_margin(margin_days),
			"deadline_breach": _sev_count(len(base["deadline_breach"])),
		},
	}
	return base


# --------------------------------------------------------------------------------------
# Ruta crítica (I.3) — INTERPRETACIÓN/visualización del CPM ya calculado en I.2. READ-ONLY.
# No es un motor nuevo ni añade semántica: compone sobre `analyze_schedule_slack`.
# --------------------------------------------------------------------------------------
_CRITICAL_BRANCH_CAP = 50  # cota anti-explosión de enumeración (se señala si trunca; nunca silencioso)


def _critical_branches(cset: set, cedges: list, nodes_by: dict):
	"""Enumera las rutas críticas (fuente→sumidero) dentro del SUBGRAFO crítico (slack ≤ 0). Varias ramas con
	slack 0 → varias rutas; NO se inventa una sola cadena. Nodo crítico aislado → rama de una tarea."""
	adj = {t: [] for t in cset}
	indeg = {t: 0 for t in cset}
	for p, s in cedges:
		adj[p].append(s)
		indeg[s] += 1
	outdeg = {t: len(adj[t]) for t in cset}
	paths, truncated = [], False

	def dfs(u, path):
		nonlocal truncated
		if len(paths) >= _CRITICAL_BRANCH_CAP:
			truncated = True
			return
		if outdeg[u] == 0:  # sumidero del subgrafo crítico
			paths.append(path)
			return
		for v in sorted(adj[u], key=lambda x: (nodes_by[x]["es"], x)):
			dfs(v, [*path, v])

	for src in sorted((t for t in cset if indeg[t] == 0), key=lambda x: (nodes_by[x]["es"], x)):
		dfs(src, [src])
	return paths, truncated


def analyze_critical_path(project: str, status_date=None) -> dict:
	"""Ruta crítica (ADR-0017, I.3). READ-ONLY: compone sobre `analyze_schedule_slack` (I.2) — NO recalcula
	CPM ni añade semántica. Devuelve las tareas críticas (ES/EF/LS/LF, slack 0), las rutas/ramas críticas
	legibles (sin inventar una cadena única) y los totales (ventana y duración hábil de la ruta)."""
	slack = analyze_schedule_slack(project, status_date)
	cal = slack["calendar_available"]
	base = {
		"evaluable": False,
		"reason": slack.get("reason"),
		"calendar_available": cal,
		"critical_tasks": [],
		"task_names": [],
		"branches": [],
		"branches_truncated": False,
		"summary": {
			"evaluable": False,
			"sin_calendario": not cal,
			"critical_count": 0,
			"branch_count": 0,
			"multi_branch": False,
			"start": None,
			"end": None,
			"duration_working_days": None,
			# Visibilidad + severidad resueltas en el dominio (SSOT): sin ruta → no se muestra el bloque.
			"show": False,
			"sev": {"multi_branch": SEV_OK},
		},
	}
	if not slack["evaluable"]:
		return base

	nodes_by = {n["task"]: n for n in slack["nodes"]}
	critical = [t for t in nodes_by if nodes_by[t]["is_critical"]]
	base["evaluable"] = True
	base["summary"]["evaluable"] = True
	if not critical:
		return base  # evaluable pero sin tareas críticas (red sin ruta determinante)

	_, holiday_list, _by, _active, edges = _load_network(project)
	cset = set(critical)
	cedges = [(p, s) for p, s in edges if p in cset and s in cset]
	paths, truncated = _critical_branches(cset, cedges, nodes_by)

	branches = []
	for path in paths:
		start = nodes_by[path[0]]["es"]
		end = nodes_by[path[-1]]["ef"]
		branches.append(
			{
				"sequence": [{"task": t, "subject": nodes_by[t]["subject"]} for t in path],
				"start": start,
				"end": end,
				"duration_working_days": working_days(start, end, holiday_list),
			}
		)

	crit_tasks = sorted(
		(
			{
				"task": n["task"],
				"subject": n["subject"],
				"is_milestone": n["is_milestone"],
				"es": n["es"],
				"ef": n["ef"],
				"ls": n["ls"],
				"lf": n["lf"],
				"total_slack": n["total_slack"],
			}
			for n in (nodes_by[t] for t in critical)
		),
		key=lambda n: (n["es"], n["ef"]),
	)
	start = min(n["es"] for n in crit_tasks)
	end = max(n["ef"] for n in crit_tasks)
	base.update(
		{
			"critical_tasks": crit_tasks,
			"task_names": sorted(cset),
			"branches": branches,
			"branches_truncated": truncated,
		}
	)
	multi_branch = len(branches) > 1
	base["summary"] = {
		"evaluable": True,
		"sin_calendario": not cal,
		"critical_count": len(critical),
		"branch_count": len(branches),
		"multi_branch": multi_branch,
		"start": start,
		"end": end,
		"duration_working_days": working_days(start, end, holiday_list),
		# Visibilidad + severidad resueltas en el dominio (SSOT).
		"show": True,  # hay ruta crítica → el Resumen muestra el bloque compacto
		"sev": {"multi_branch": _sev_flag(multi_branch)},
	}
	return base


# --------------------------------------------------------------------------------------
# Calendario del cronograma (Schedule Readiness) — ¿es confiable el cálculo en días hábiles?
# READ-ONLY. Precedencia EXPLÍCITA: Project.holiday_list PREVALECE; si existe pero NO cubre el periodo
# del proyecto, NO hay fallback silencioso a Company (se señala cobertura insuficiente). ADR-0017.
# --------------------------------------------------------------------------------------
_CAL_READY = "ready"
_CAL_MISSING = "missing"
_CAL_INSUFFICIENT = "insufficient_coverage"

# Variante corta para la tarjeta compacta del Resumen (SSOT; el template no la deriva).
_CAL_SHORT = {
	_CAL_READY: "Días hábiles",
	_CAL_MISSING: "Días naturales (sin calendario)",
	_CAL_INSUFFICIENT: "Cobertura insuficiente",
}
_CAL_SEV = {_CAL_READY: SEV_OK, _CAL_MISSING: SEV_WARN, _CAL_INSUFFICIENT: SEV_BAD}


def schedule_readiness(project: str) -> dict:
	"""¿El calendario laboral hace confiable el cálculo del cronograma? READ-ONLY, sin escribir. Precedencia
	EXPLÍCITA Project→Company, pero si el Project tiene lista propia y NO cubre el periodo, prevalece (sin
	fallback a Company) y se marca cobertura insuficiente. Estados: ready / missing / insufficient_coverage."""
	meta = frappe.db.get_value("Project", project, ["holiday_list", "company"], as_dict=True) or {}
	hl, source = meta.get("holiday_list"), None
	if hl:
		source = "project"
	elif meta.get("company"):
		hl = frappe.db.get_value("Company", meta["company"], "default_holiday_list") or None
		source = "company" if hl else None

	# Rango de fechas del proyecto = min(exp_start)..max(exp_end) de las tareas hoja ACTIVAS con fechas.
	tasks = _read_tasks(project)
	starts = [getdate(t.exp_start_date) for t in tasks if t.status not in _INACTIVE and t.exp_start_date]
	ends = [getdate(t.exp_end_date) for t in tasks if t.status not in _INACTIVE and t.exp_end_date]
	span_start = min(starts) if starts else None
	span_end = max(ends) if ends else None

	hl_from = hl_to = None
	covers_range = True  # sin lista o sin rango que cubrir → no hay cobertura que evaluar
	if hl and span_start and span_end:
		rng = frappe.db.get_value("Holiday List", hl, ["from_date", "to_date"], as_dict=True) or {}
		hl_from = getdate(rng.from_date) if rng.get("from_date") else None
		hl_to = getdate(rng.to_date) if rng.get("to_date") else None
		covers_range = bool(hl_from and hl_to and hl_from <= span_start and hl_to >= span_end)

	if not hl:
		state = _CAL_MISSING
	elif not covers_range:
		state = _CAL_INSUFFICIENT
	else:
		state = _CAL_READY

	# Frase de usuario COMPUESTA en el dominio (SSOT): integra el nombre del calendario; sin "origen" aparte.
	hint = None
	if state == _CAL_READY:
		origen = " (de la compañía)" if source == "company" else ""
		label = f"Calendario «{hl}»{origen} — los cálculos descuentan fines de semana y feriados."
	elif state == _CAL_MISSING:
		label = "Sin calendario laboral — los cálculos usan días naturales."
		hint = "Configura la Lista de feriados en el Proyecto, o la Lista de feriados por defecto en la Compañía."
	else:  # insufficient_coverage
		label = f"El calendario «{hl}» no cubre todo el periodo del proyecto."
		hint = (
			f"Amplía el rango de la lista de feriados «{hl}» "
			f"({hl_from} a {hl_to}) para cubrir el periodo del proyecto ({span_start} a {span_end})."
		)

	return {
		"state": state,
		"ready": state == _CAL_READY,
		"source": source,  # "project" | "company" | None
		"holiday_list": hl,
		"covers_range": covers_range,
		"span_start": str(span_start) if span_start else None,
		"span_end": str(span_end) if span_end else None,
		"hl_from": str(hl_from) if hl_from else None,
		"hl_to": str(hl_to) if hl_to else None,
		"label": label,  # frase de usuario lista (SSOT; incluye el nombre del calendario)
		# Resumen compacto: si hay calendario usable, muestra su NOMBRE; si no, el estado.
		"short": hl if state == _CAL_READY else _CAL_SHORT[state],
		"sev": _CAL_SEV[state],  # severidad decidida en el dominio
		"hint": hint,  # dónde/ cómo configurarlo (None si ready)
	}
