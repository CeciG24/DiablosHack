#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F3 (Location y Pitching sin ambiente,
protocolos A y B) a partir de los artefactos verificados, sin dependencias."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'modeling'
OUT = ROOT / 'docs' / 'reporte_f3'
F3 = ART / 'f3-full-check' / 'F3'

MODEL_COLOR = {'B1': '#2563eb', 'Stuff': '#7c3aed', 'Location': '#0d9488',
               'Pitching': '#16a34a'}
PART_LABEL = {
    'development': 'development', 'calibration': 'calibration',
    'phase_review': 'phase review',
}
PROTO_TITLE = {
    'A': 'Protocolo A · temporal (fit 2024 → eval 2025)',
    'B': 'Protocolo B · pitchers separados (review = pitchers no vistos)',
}


def svg(width, height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">\n'
            f'<rect width="{width}" height="{height}" fill="white"/>\n'
            f'<g font-family="Arial,sans-serif" fill="#0f172a">\n{body}</g>\n</svg>\n')


def text(x, y, s, size=12, fill='#0f172a', anchor='start', weight=None):
    w = f' font-weight="{weight}"' if weight else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"{w}>{s}</text>\n'


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ---------------------------------------------------------------- log loss
def chart_logloss(metrics, pid):
    parts = ['development', 'calibration', 'phase_review']
    models = ['B1', 'Stuff', 'Location', 'Pitching']
    data = {(m['model'], m['partition']): m['multiclass_log_loss']
            for m in metrics['metrics']}
    y_min, y_max = 1.00, 1.56
    top, bottom, left = 110, 560, 70
    group_w, bar_w, gap = 235, 38, 7

    def Y(v):
        return bottom - (v - y_min) / (y_max - y_min) * (bottom - top)

    body = text(30, 34, f'Log loss multicase · 4 modelos · {PROTO_TITLE[pid]}', 20,
                weight='bold')
    body += text(30, 56, 'Menor es mejor · eje Y truncado en 1.00 para resaltar diferencias · '
                         'mismos IDs para los cuatro modelos', 12, '#475569')
    for i, m in enumerate(models):
        x = 425 + i * 90
        body += f'<rect x="{x}" y="22" width="14" height="14" fill="{MODEL_COLOR[m]}"/>\n'
        body += text(x + 19, 34, m, 12, MODEL_COLOR[m])
    for tick in (1.00, 1.10, 1.20, 1.30, 1.40, 1.50):
        body += f'<path d="M {left} {Y(tick):.1f} H {left + 3 * group_w}" stroke="#e2e8f0"/>\n'
        body += text(left - 8, Y(tick) + 4, f'{tick:.2f}', 11, '#475569', 'end')
    body += (f'<text x="24" y="{(top + bottom) / 2}" font-size="12" fill="#475569" '
             f'text-anchor="middle" transform="rotate(-90 24 {(top + bottom) / 2})">log loss</text>\n')
    for gi, p in enumerate(parts):
        gx = left + gi * group_w + 25
        for mi, m in enumerate(models):
            v = data[(m, p)]
            x = gx + mi * (bar_w + gap)
            body += (f'<rect x="{x}" y="{Y(v):.1f}" width="{bar_w}" '
                     f'height="{bottom - Y(v):.1f}" fill="{MODEL_COLOR[m]}"/>\n')
            body += text(x + bar_w / 2, Y(v) - 6, f'{v:.4f}', 9, '#334155', 'middle')
        n = next(m2['n_pitches'] for m2 in metrics['metrics']
                 if m2['model'] == 'B1' and m2['partition'] == p)
        cx = gx + (4 * bar_w + 3 * gap) / 2
        body += text(cx, bottom + 22, PART_LABEL[p], 12, '#0f172a', 'middle', 'bold')
        body += text(cx, bottom + 39, f'n = {n:,}', 10, '#475569', 'middle')
    body += f'<path d="M {left} {bottom} H {left + 3 * group_w}" stroke="#94a3b8"/>\n'
    (OUT / f'logloss_protocolo_{pid.lower()}.svg').write_text(svg(800, 620, body))


# ------------------------------------------------------------- bootstrap IC
def chart_bootstrap(metrics, pid):
    comps = metrics['comparisons']
    rows = [('Location_vs_B1', 'Location vs B1'),
            ('Pitching_vs_B1', 'Pitching vs B1'),
            ('Pitching_vs_Location', 'Pitching vs Location'),
            ('Stuff_vs_B1', 'Stuff vs B1')]
    x_min, x_max = -0.47, 0.08
    left, right, top, row_h = 210, 500, 120, 82

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, f'Comparaciones bootstrap · {PROTO_TITLE[pid]}', 20, weight='bold')
    body += text(30, 56, 'Δ log loss (candidato − referencia) con IC 95% · 500 remuestreos '
                         'pareados por juego · phase review · negativo favorece al candidato',
                 12, '#475569')
    for tick in (-0.4, -0.3, -0.2, -0.1, 0.0, 0.05):
        body += f'<path d="M {X(tick):.1f} {top - 20} V {top + 4 * row_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 28, f'{tick:.2f}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 20} V {top + 4 * row_h}" stroke="#94a3b8" '
             f'stroke-width="2"/>\n')
    for i, (key, label) in enumerate(rows):
        c = comps[key]
        cy = top + i * row_h + 24
        promotes = c['decision'] == 'promote'
        color = '#16a34a' if promotes else '#d97706'
        body += text(left - 12, cy + 4, label, 13, '#0f172a', 'end', 'bold')
        body += (f'<path d="M {X(c["ci_low"]):.1f} {cy} H {X(c["ci_high"]):.1f}" '
                 f'stroke="{color}" stroke-width="3"/>\n')
        for cx in (c['ci_low'], c['ci_high']):
            body += (f'<path d="M {X(cx):.1f} {cy - 8} V {cy + 8}" stroke="{color}" '
                     f'stroke-width="3"/>\n')
        body += (f'<circle cx="{X(c["delta_candidate_minus_reference"]):.1f}" cy="{cy}" '
                 f'r="6" fill="{color}"/>\n')
        rel = c['relative_log_loss_reduction'] * 100
        body += text(right + 16, cy - 10,
                     f'Δ = {c["delta_candidate_minus_reference"]:+.4f}', 11)
        body += text(right + 16, cy + 6, f'reducción rel. {rel:+.2f}%', 11, '#475569')
        body += text(right + 16, cy + 22, f'decisión: {c["decision"]}', 11, color,
                     weight='bold')
    note = ('Pitching promueve contra B1 y además contra Location: la física suma sobre '
            'ubicación/contexto.' if pid == 'A' else
            'Mismo veredicto con pitchers de review nunca vistos en fit ni selección.')
    body += text(left, top + 4 * row_h + 36, esc(note), 11, '#475569')
    body += text(left, top + 4 * row_h + 54,
                 'Stuff sigue sin superar a B1: retain_reference en ambos protocolos.', 11,
                 '#475569')
    (OUT / f'bootstrap_protocolo_{pid.lower()}.svg').write_text(svg(800, 500, body))


# ------------------------------------------------------ selección candidatos
def chart_seleccion(selection, pid):
    fams = [f for f in ('stuff', 'location', 'pitching')
            if isinstance(selection.get(f), dict) and 'trials' in selection[f]]
    left, max_w, top, row_h, block_h = 300, 300, 118, 40, 150

    body = text(30, 34, f'Selección de configuración LightGBM · {PROTO_TITLE[pid]}', 20,
                weight='bold')
    body += text(30, 56, 'Selección solo en development (review nunca selecciona) · early '
                         'stopping 30 · eje truncado por familia', 12, '#475569')
    y = top
    if pid == 'A':
        body += text(left - 12, y - 6, 'stuff: modelo congelado de F2 '
                                       '(sin búsqueda nueva)', 11, '#7c3aed', 'end')
    for fam in fams:
        sel = selection[fam]
        trials = sel['trials']
        vals = [t['development_log_loss'] for t in trials]
        lo, hi = min(vals), max(vals)
        pad = max((hi - lo) * 0.3, 5e-4)
        x_min, x_max = lo - pad, hi + pad

        def X(v):
            return left + (v - x_min) / (x_max - x_min) * max_w

        color = MODEL_COLOR[fam.capitalize()]
        body += text(left - 12, y + 4, fam.capitalize(), 14, color, 'end', 'bold')
        for i, t in enumerate(trials):
            cy = y + 14 + i * row_h
            is_sel = t['candidate_id'] == sel['selected']['candidate_id']
            p = t['parameters']
            body += text(left - 12, cy + 12, t['candidate_id'], 12,
                         '#0f172a' if is_sel else '#64748b', 'end',
                         'bold' if is_sel else None)
            body += text(left - 12, cy + 27,
                         f"leaves {p['num_leaves']} · min_data {p['min_data_in_leaf']} · "
                         f"L2 {p['lambda_l2']:.0f} · iter {t['best_iteration']}", 9,
                         '#64748b', 'end')
            w = max(X(t['development_log_loss']) - left, 2)
            body += (f'<rect x="{left}" y="{cy}" width="{w:.1f}" height="26" '
                     f'fill="{color}" fill-opacity="{1.0 if is_sel else 0.35}"/>\n')
            body += text(left + w + 8, cy + 17,
                         f"{t['development_log_loss']:.5f}", 11, '#334155')
            if is_sel:
                body += text(left + w + 92, cy + 17, '← seleccionado', 10, color,
                             weight='bold')
        y += block_h
    (OUT / f'seleccion_protocolo_{pid.lower()}.svg').write_text(
        svg(860, y + 30, body))


# ---------------------------------------------------- calibración diagnóstica
def chart_calibracion(csv_path, pid):
    pts = {}
    with csv_path.open() as fh:
        for r in csv.DictReader(fh):
            if r['partition'] != 'phase_review' or int(r['n']) == 0:
                continue
            pts.setdefault(r['model'], []).append(
                (float(r['mean_probability']), float(r['observed_frequency']),
                 int(r['n'])))
    left, right, top, bottom = 90, 560, 95, 545

    def X(v):
        return left + v * (right - left)

    def Y(v):
        return bottom - v * (bottom - top)

    body = text(30, 34, f'Calibración diagnóstica · {PROTO_TITLE[pid]}', 20,
                weight='bold')
    body += text(30, 56, 'Phase review · 6 clases × 10 bins agrupados · ideal = diagonal · '
                         'sin calibradores ajustados', 12, '#475569')
    for i, m in enumerate(('B1', 'Stuff', 'Location', 'Pitching')):
        x = 590 + (i % 2) * 105
        y = 22 + (i // 2) * 20
        body += f'<rect x="{x}" y="{y - 10}" width="14" height="14" fill="{MODEL_COLOR[m]}"/>\n'
        body += text(x + 19, y + 2, m, 12, MODEL_COLOR[m])
    for tick in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        body += f'<path d="M {X(tick):.1f} {top} V {bottom}" stroke="#e2e8f0"/>\n'
        body += f'<path d="M {left} {Y(tick):.1f} H {right}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), bottom + 18, f'{tick:.1f}', 11, '#475569', 'middle')
        body += text(left - 8, Y(tick) + 4, f'{tick:.1f}', 11, '#475569', 'end')
    body += text((left + right) / 2, bottom + 38, 'probabilidad media predicha', 12,
                 '#475569', 'middle')
    body += (f'<text x="30" y="{(top + bottom) / 2}" font-size="12" fill="#475569" '
             f'text-anchor="middle" transform="rotate(-90 30 {(top + bottom) / 2})">'
             f'frecuencia observada</text>\n')
    body += (f'<path d="M {X(0):.1f} {Y(0):.1f} L {X(1):.1f} {Y(1):.1f}" stroke="#94a3b8" '
             f'stroke-width="2" stroke-dasharray="6,4"/>\n')
    for m, rows in pts.items():
        for mp, of, n in rows:
            r = max(2.5, min(9.0, (n / 400) ** 0.5))
            body += (f'<circle cx="{X(mp):.1f}" cy="{Y(of):.1f}" r="{r:.1f}" '
                     f'fill="{MODEL_COLOR[m]}" fill-opacity="0.55"/>\n')
    (OUT / f'calibracion_protocolo_{pid.lower()}.svg').write_text(svg(800, 600, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for pid in ('A', 'B'):
        metrics = json.loads((F3 / pid / 'metrics.json').read_text())
        selection = json.loads((F3 / pid / 'selection.json').read_text())
        chart_logloss(metrics, pid)
        chart_bootstrap(metrics, pid)
        chart_seleccion(selection, pid)
        chart_calibracion(F3 / pid / 'calibration.csv', pid)
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
