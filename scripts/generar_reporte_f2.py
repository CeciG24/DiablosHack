#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F2 (modelo Stuff) a partir de los
artefactos verificados, sin dependencias externas."""
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'modeling'
OUT = ROOT / 'docs' / 'reporte_f2'
F2 = ART / 'f2-full-check' / 'F2'

MODEL_COLOR = {'B0': '#475569', 'B1': '#2563eb', 'Stuff': '#7c3aed'}
PART_LABEL = {
    'development': 'development 2025', 'calibration': 'calibration 2025',
    'phase_review': 'phase review 2025',
}
FEATURE_LABEL = {
    'auto_pitch_type': 'tipo de pitch (auto)', 'induced_vert_break': 'induced vert break',
    'rel_speed': 'velocidad (rel_speed)', 'spin_rate': 'spin rate',
    'rel_height': 'release height', 'horz_break': 'horz break',
    'spin_axis_cos': 'spin axis (cos)', 'rel_side': 'release side',
    'spin_axis_sin': 'spin axis (sin)', 'extension': 'extension',
    'pitcher_throws': 'mano del pitcher',
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
def chart_logloss(metrics):
    parts = ['development', 'calibration', 'phase_review']
    models = ['B0', 'B1', 'Stuff']
    data = {(m['model'], m['partition']): m['multiclass_log_loss'] for m in metrics['metrics']}
    y_min, y_max = 1.40, 1.56
    top, bottom, left = 110, 560, 70
    group_w, bar_w, gap = 235, 52, 8

    def Y(v):
        return bottom - (v - y_min) / (y_max - y_min) * (bottom - top)

    body = text(30, 34, 'Log loss multicase · Stuff vs baselines (2025)', 20, weight='bold')
    body += text(30, 56, 'Menor es mejor · eje Y truncado en 1.40 para resaltar diferencias', 12,
                 '#475569')
    for i, m in enumerate(models):
        x = 555 + i * 80
        body += f'<rect x="{x}" y="22" width="14" height="14" fill="{MODEL_COLOR[m]}"/>\n'
        body += text(x + 19, 34, m, 12, MODEL_COLOR[m])
    for tick in (1.40, 1.45, 1.50, 1.55):
        body += f'<path d="M {left} {Y(tick):.1f} H {left + 3 * group_w}" stroke="#e2e8f0"/>\n'
        body += text(left - 8, Y(tick) + 4, f'{tick:.2f}', 11, '#475569', 'end')
    body += (f'<text x="24" y="{(top + bottom) / 2}" font-size="12" fill="#475569" '
             f'text-anchor="middle" transform="rotate(-90 24 {(top + bottom) / 2})">log loss</text>\n')
    for gi, p in enumerate(parts):
        gx = left + gi * group_w + 30
        for mi, m in enumerate(models):
            v = data[(m, p)]
            x = gx + mi * (bar_w + gap)
            body += (f'<rect x="{x}" y="{Y(v):.1f}" width="{bar_w}" '
                     f'height="{bottom - Y(v):.1f}" fill="{MODEL_COLOR[m]}"/>\n')
            body += text(x + bar_w / 2, Y(v) - 6, f'{v:.4f}', 10, '#334155', 'middle')
        n = next(m2['n_pitches'] for m2 in metrics['metrics']
                 if m2['model'] == 'B0' and m2['partition'] == p)
        body += text(gx + (3 * bar_w + 2 * gap) / 2, bottom + 22, PART_LABEL[p], 12,
                     '#0f172a', 'middle', 'bold')
        body += text(gx + (3 * bar_w + 2 * gap) / 2, bottom + 39, f'n = {n:,}', 10,
                     '#475569', 'middle')
    body += f'<path d="M {left} {bottom} H {left + 3 * group_w}" stroke="#94a3b8"/>\n'
    (OUT / 'logloss_stuff.svg').write_text(svg(800, 620, body))


# ------------------------------------------------------------- bootstrap IC
def chart_bootstrap(metrics):
    comps = metrics['comparisons']
    rows = [('Stuff_vs_B0', 'Stuff vs B0'), ('Stuff_vs_B1', 'Stuff vs B1')]
    x_min, x_max = -0.03, 0.065
    left, right, top, row_h = 140, 470, 120, 120

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Comparaciones bootstrap pareadas por juego · phase review 2025', 20,
                weight='bold')
    body += text(30, 56, 'Δ log loss (Stuff − referencia) con IC 95% · 500 remuestreos · '
                         'valores negativos favorecen a Stuff', 12, '#475569')
    for tick in (-0.02, 0.0, 0.02, 0.04, 0.06):
        body += f'<path d="M {X(tick):.1f} {top - 20} V {top + 2 * row_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 28, f'{tick:.2f}', 11, '#475569', 'middle')
    body += f'<path d="M {X(0):.1f} {top - 20} V {top + 2 * row_h}" stroke="#94a3b8" stroke-width="2"/>\n'
    for i, (key, label) in enumerate(rows):
        c = comps[key]
        cy = top + i * row_h + 30
        promotes = c['decision'] == 'promote'
        color = '#16a34a' if promotes else '#d97706'
        body += text(left - 12, cy + 4, label, 14, '#0f172a', 'end', 'bold')
        body += (f'<path d="M {X(c["ci_low"]):.1f} {cy} H {X(c["ci_high"]):.1f}" '
                 f'stroke="{color}" stroke-width="3"/>\n')
        for cx in (c['ci_low'], c['ci_high']):
            body += f'<path d="M {X(cx):.1f} {cy - 8} V {cy + 8}" stroke="{color}" stroke-width="3"/>\n'
        body += f'<circle cx="{X(c["delta_candidate_minus_reference"]):.1f}" cy="{cy}" r="6" fill="{color}"/>\n'
        rel = c['relative_log_loss_reduction'] * 100
        body += text(right + 16, cy - 4, f'Δ = {c["delta_candidate_minus_reference"]:+.4f}', 12)
        body += text(right + 16, cy + 14, f'reducción relativa {rel:+.2f}%', 12, '#475569')
        body += text(right + 16, cy + 32, f'decisión: {c["decision"]}', 12, color, weight='bold')
    body += text(left, top + 2 * row_h + 40,
                 esc('Stuff mejora a B0 con evidencia (Δ<0), pero es peor que B1 (Δ>0, IC completo sobre cero):'),
                 11, '#475569')
    body += text(left, top + 2 * row_h + 58,
                 'las variables físicas solas no capturan la señal que ya aporta el conteo.', 11,
                 '#475569')
    (OUT / 'bootstrap_stuff.svg').write_text(svg(800, 420, body))


# ------------------------------------------------------ selección candidatos
def chart_seleccion(selection):
    trials = selection['trials']
    x_min, x_max = 1.5160, 1.5190
    left, right, top, row_h = 280, 600, 115, 95

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Selección de configuración LightGBM · development 2025', 20, weight='bold')
    body += text(30, 56, 'Fit en train 2024 · selección por log loss en development · '
                         'early stopping 30 rondas · eje X truncado en 1.516', 12, '#475569')
    for tick in (1.516, 1.517, 1.518, 1.519):
        body += f'<path d="M {X(tick):.1f} {top - 16} V {top + 3 * row_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 24, f'{tick:.3f}', 11, '#475569', 'middle')
    for i, t in enumerate(trials):
        cy = top + i * row_h
        sel = t['candidate_id'] == selection['selected']['candidate_id']
        color = '#7c3aed' if sel else '#cbd5e1'
        p = t['parameters']
        body += text(left - 12, cy + 14, t['candidate_id'], 13,
                     '#0f172a' if sel else '#64748b', 'end', 'bold' if sel else None)
        body += text(left - 12, cy + 30,
                     f"leaves {p['num_leaves']} · min_data {p['min_data_in_leaf']} · "
                     f"lr {p['learning_rate']} · L2 {p['lambda_l2']:.0f}", 10, '#64748b', 'end')
        body += text(left - 12, cy + 46,
                     f"best iter {t['best_iteration']} / {t['iterations_evaluated']} evaluadas",
                     10, '#64748b', 'end')
        w = max(X(t['development_log_loss']) - left, 2)
        body += f'<rect x="{left}" y="{cy}" width="{w:.1f}" height="34" fill="{color}"/>\n'
        body += text(left + w + 8, cy + 22, f"{t['development_log_loss']:.5f}", 12,
                     '#334155')
        if sel:
            body += text(left + w + 8, cy + 38, '← seleccionado', 11, '#7c3aed', weight='bold')
    (OUT / 'seleccion_candidatos.svg').write_text(svg(760, 430, body))


# ----------------------------------------------------- permutation importance
def chart_importancia():
    rows = list(csv.DictReader((F2 / 'permutation_importance.csv').open()))
    rows = [(r['feature'], float(r['mean_log_loss_increase']),
             float(r['std_log_loss_increase'])) for r in rows]
    rows.sort(key=lambda r: r[1], reverse=True)
    v_max = max(m + s for _, m, s in rows) * 1.15
    left, right, top, row_h = 180, 540, 105, 34

    def X(v):
        return left + v / v_max * (right - left)

    body = text(30, 34, 'Importancia por permutación · Stuff en development 2025', 20,
                weight='bold')
    body += text(30, 56, 'Incremento medio de log loss al permutar la feature · 3 repeticiones · '
                         'barras de error = ±1 desviación estándar', 12, '#475569')
    for tick in (0.002, 0.004, 0.006, 0.008):
        body += f'<path d="M {X(tick):.1f} {top - 12} V {top + len(rows) * row_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 20, f'{tick:.3f}', 11, '#475569', 'middle')
    for i, (feat, mean, std) in enumerate(rows):
        cy = top + i * row_h
        color = '#7c3aed' if i < 3 else '#a78bfa' if i < 6 else '#ddd6fe'
        body += text(left - 12, cy + 22, FEATURE_LABEL.get(feat, feat), 12, '#0f172a', 'end')
        body += f'<rect x="{left}" y="{cy + 6}" width="{X(mean) - left:.1f}" height="22" fill="{color}"/>\n'
        xs, xe = X(mean - std), X(mean + std)
        body += f'<path d="M {xs:.1f} {cy + 17} H {xe:.1f} M {xs:.1f} {cy + 12} V {cy + 22} M {xe:.1f} {cy + 12} V {cy + 22}" stroke="#334155" stroke-width="1.5"/>\n'
        body += text(X(mean + std) + 10, cy + 21, f'{mean:.5f}', 11, '#475569')
    body += text(left, top + len(rows) * row_h + 24,
                 'Modelo seleccionado: candidate_01 · calculado solo en development (no en review).',
                 11, '#475569')
    (OUT / 'permutation_importance.svg').write_text(
        svg(760, top + len(rows) * row_h + 60, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((F2 / 'metrics.json').read_text())
    selection = json.loads((F2 / 'selection.json').read_text())
    chart_logloss(metrics)
    chart_bootstrap(metrics)
    chart_seleccion(selection)
    chart_importancia()
    for name in ('calibration_development.svg', 'calibration_calibration.svg',
                 'calibration_phase_review.svg'):
        shutil.copy2(F2 / name, OUT / name)
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
