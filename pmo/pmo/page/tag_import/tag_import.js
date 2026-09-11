// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — Importador de Tags nativos desde CSV.
// UI mínima: subir CSV → Dry Run (sin escribir) → Aplicar (idempotente).
// Toda la lógica vive en el servidor (pmo.tag_import). Esta página solo lee el
// archivo, llama a los métodos y muestra el resumen.

frappe.pages["tag_import"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Import Tags"),
		single_column: true,
	});

	const $body = $(page.body);
	$body.html(`
		<div class="tag-import-tool" style="max-width: 720px;">
			<p class="text-muted">
				${__("Upload a CSV with columns")} <code>doctype,document,tags</code>.
				${__("Multiple Tags per document separated by commas.")}
			</p>
			<pre class="small text-muted" style="background:var(--control-bg);padding:8px;border-radius:6px;">doctype,document,tags
Task,TASK-0001,"CIERRE,CLIENTE,GO-NO-GO"
Task,TASK-0002,"DATOS,COMPARTIDA"</pre>
			<input type="file" class="tag-import-file form-control" accept=".csv,text/csv" style="margin:12px 0;">
			<div class="tag-import-summary" style="margin-top:16px;"></div>
		</div>
	`);

	const $file = $body.find(".tag-import-file");
	const $summary = $body.find(".tag-import-summary");

	// Lee el CSV seleccionado como texto (sin subirlo a File / sin fixtures).
	function read_csv() {
		return new Promise((resolve, reject) => {
			const f = $file[0].files[0];
			if (!f) {
				reject(__("Select a CSV file first."));
				return;
			}
			const reader = new FileReader();
			reader.onload = (e) => resolve(e.target.result);
			reader.onerror = () => reject(__("Could not read the file."));
			reader.readAsText(f);
		});
	}

	function run(method, freeze_message) {
		read_csv()
			.then((csv_content) =>
				frappe.call({
					method: `pmo.tag_import.${method}`,
					args: { csv_content },
					freeze: true,
					freeze_message,
				})
			)
			.then((r) => render_summary(r.message))
			.catch((err) =>
				frappe.msgprint({ title: __("Import Tags"), message: err, indicator: "orange" })
			);
	}

	function render_summary(s) {
		if (!s) {
			$summary.empty();
			return;
		}
		const mode = s.mode === "apply" ? __("Apply") : __("Dry Run");
		const rows = [
			[__("Documents read"), s.documentos_leidos],
			[__("Valid documents"), s.documentos_validos],
			[__("Associations requested"), s.asociaciones_solicitadas],
			[
				s.mode === "apply"
					? __("Associations applied")
					: __("Associations that would be applied"),
				s.asociaciones_aplicadas,
			],
			[__("Nonexistent documents"), (s.documentos_inexistentes || []).length],
			[__("Errors"), (s.errores || []).length],
		];
		const indicator = s.ok ? "green" : "red";
		let html = `<h5>${mode} — <span class="indicator ${indicator}">${
			s.ok ? __("valid") : __("with errors")
		}</span></h5><table class="table table-bordered small">`;
		rows.forEach(([k, v]) => {
			html += `<tr><td>${k}</td><td><b>${v}</b></td></tr>`;
		});
		html += `</table>`;

		// Aviso inequívoco: con errores es TODO-O-NADA → Aplicar NO escribe ningún tag.
		if (!s.ok) {
			const n = (s.errores || []).length;
			const msg =
				s.mode === "apply"
					? __(
							"Nothing was applied. With {0} error(s), NO tag was written (all or nothing).",
							[n]
					  )
					: __(
							"Apply will NOT write ANY tag while there are errors ({0}). It is all or nothing: fix the CSV and retry.",
							[n]
					  );
			html += `<div class="alert alert-warning" style="margin-top:8px;"><b>⚠️ ${msg}</b></div>`;
		}

		// Desglose por documento (guard visual): errores primero, luego el resto.
		// Contenedor con scroll para tolerar cientos de filas sin estirar la página.
		const detalle = (s.detalle || []).slice().sort((a, b) => rank(a) - rank(b));
		if (detalle.length) {
			const applied = s.mode === "apply" && s.ok;
			html += `<h6>${__("Detail by document")}</h6>`;
			html += `<div style="max-height:360px;overflow:auto;border:1px solid var(--border-color);border-radius:6px;">`;
			html += `<table class="table table-bordered small" style="margin:0;">
				<thead><tr>
					<th>${__("Type")}</th><th>${__("Document")}</th>
					<th>${applied ? __("Tags added") : __("Tags to add")}</th>
					<th>${__("Status")}</th>
				</tr></thead><tbody>`;
			detalle.forEach((d) => {
				html += `<tr>
					<td>${frappe.utils.escape_html(d.tipo || "")}</td>
					<td>${frappe.utils.escape_html(d.documento || "")}</td>
					<td>${
						(d.tags || [])
							.map(
								(t) =>
									`<span class="indicator-pill blue">${frappe.utils.escape_html(
										t
									)}</span>`
							)
							.join(" ") || "—"
					}</td>
					<td>${estado_label(d, applied, !s.ok)}</td>
				</tr>`;
			});
			html += `</tbody></table></div>`;
		}
		$summary.html(html);
	}

	// Orden del detalle: errores arriba, luego "se agregarán", luego "sin cambios".
	function rank(d) {
		return d.estado === "error" ? 0 : d.estado === "se_agregaran" ? 1 : 2;
	}

	function estado_label(d, applied, blocked) {
		if (d.estado === "error") {
			return `<span class="text-danger">${frappe.utils.escape_html(
				d.error || __("error")
			)}</span>`;
		}
		// Si la importación está bloqueada por errores, esta fila válida NO se aplicará.
		if (blocked) {
			return `<span class="text-warning">${__(
				"will not be applied (there are errors in the CSV)"
			)}</span>`;
		}
		if (d.estado === "sin_cambios") {
			return `<span class="text-muted">${__("no changes (already has the tags)")}</span>`;
		}
		return `<span class="${applied ? "text-success" : ""}">${
			applied ? __("added") : __("will be added")
		}</span>`;
	}

	page.set_primary_action(
		__("Apply"),
		() => run("tag_import_apply", __("Applying Tags...")),
		"play"
	);
	page.set_secondary_action(__("Dry Run"), () => run("tag_import_dry_run", __("Validating...")));
};
