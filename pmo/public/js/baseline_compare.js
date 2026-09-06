// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// ADR-0005 D11: render modesto del comparator Baseline ↔ Baseline. Diálogo con secciones
// added / removed / changed. Es una diferencia ENTRE baselines (puede consolidar varios Change Requests),
// no una atribución por CR. Se incluye globalmente (app_include_js) para reutilizarlo desde el form del
// Change Request y del PMO Project Baseline.

(function () {
	function esc(v) {
		if (v === null || v === undefined || v === "") return "—";
		return frappe.utils.escape_html(String(v));
	}

	function fromTo(change) {
		return `<span class="text-muted">${esc(change.from)}</span> → <strong>${esc(
			change.to
		)}</strong>`;
	}

	function taskRow(t) {
		return `<tr><td><code>${esc(t.name)}</code></td><td>${esc(t.subject)}</td>
			<td>${esc(t.exp_start_date)} → ${esc(t.exp_end_date)}</td>
			<td>${esc(t.expected_time)}</td><td>${esc(t.status)}</td></tr>`;
	}

	function section(title, bodyHtml, count) {
		return `<h5 style="margin-top:1rem">${title} <span class="badge">${count}</span></h5>${bodyHtml}`;
	}

	function fieldChangesHtml(fields) {
		const keys = Object.keys(fields || {});
		if (!keys.length) return "";
		const rows = keys.map((k) => `<li><b>${esc(k)}</b>: ${fromTo(fields[k])}</li>`).join("");
		return `<ul style="margin:.25rem 0">${rows}</ul>`;
	}

	function assignmentsHtml(a) {
		if (!a) return "";
		const parts = [];
		(a.added || []).forEach((x) =>
			parts.push(
				`<li>+ ${esc(x.user)} <span class="text-muted">(${esc(
					x.effective_hours
				)} h)</span></li>`
			)
		);
		(a.removed || []).forEach((x) => parts.push(`<li>− ${esc(x.user)}</li>`));
		(a.changed || []).forEach((x) => {
			const ch = Object.keys(x.changes || {})
				.map((k) => `${esc(k)}: ${fromTo(x.changes[k])}`)
				.join("; ");
			parts.push(`<li>~ ${esc(x.user)} — ${ch}</li>`);
		});
		if (!parts.length) return "";
		return `<div class="text-muted small">${__(
			"Asignaciones"
		)}:</div><ul style="margin:.25rem 0">${parts.join("")}</ul>`;
	}

	function format(diff) {
		if (!diff.has_changes) {
			return `<p>${__("Sin diferencias entre ambas baselines.")}</p>`;
		}
		let html = `<p class="text-muted">${__(
			"Diferencia entre baselines (puede consolidar varios Change Requests)."
		)}</p>`;

		const pc = diff.project_changes || {};
		if (Object.keys(pc).length) {
			html += section(__("Proyecto"), fieldChangesHtml(pc), Object.keys(pc).length);
		}

		const tblHead = `<table class="table table-bordered table-sm"><thead><tr>
			<th>${__("Task")}</th><th>${__("Asunto")}</th><th>${__("Fechas")}</th>
			<th>${__("Horas")}</th><th>${__("Estado")}</th></tr></thead><tbody>`;

		if ((diff.tasks_added || []).length) {
			html += section(
				__("Tasks añadidas"),
				tblHead + diff.tasks_added.map(taskRow).join("") + "</tbody></table>",
				diff.tasks_added.length
			);
		}
		if ((diff.tasks_removed || []).length) {
			html += section(
				__("Tasks eliminadas"),
				tblHead + diff.tasks_removed.map(taskRow).join("") + "</tbody></table>",
				diff.tasks_removed.length
			);
		}
		if ((diff.tasks_changed || []).length) {
			const body = diff.tasks_changed
				.map(
					(t) =>
						`<div style="padding:.4rem 0;border-bottom:1px solid #eee">
							<div><code>${esc(t.name)}</code> ${esc(t.subject)}</div>
							${fieldChangesHtml(t.fields)}${assignmentsHtml(t.assignments)}</div>`
				)
				.join("");
			html += section(__("Tasks modificadas"), body, diff.tasks_changed.length);
		}
		return html;
	}

	window.pmo_show_baseline_diff = function (before_name, after_name, title) {
		frappe
			.call({
				method: "pmo.compare.compare_baselines",
				args: { baseline_before: before_name, baseline_after: after_name },
				freeze: true,
				freeze_message: __("Comparando baselines…"),
			})
			.then((r) => {
				if (r.exc || !r.message) return;
				const m = r.message.meta || {};
				const dlg = new frappe.ui.Dialog({
					title: title || __("Cambios entre baselines"),
					size: "large",
					fields: [{ fieldtype: "HTML", fieldname: "diff" }],
				});
				const header =
					m.before && m.after
						? `<p><b>${esc(m.before.revision || m.before.name)}</b> (${esc(
								m.before.effective_date
						  )}) → <b>${esc(m.after.revision || m.after.name)}</b> (${esc(
								m.after.effective_date
						  )})</p>`
						: "";
				dlg.fields_dict.diff.$wrapper.html(header + format(r.message));
				dlg.show();
			});
	};
})();
