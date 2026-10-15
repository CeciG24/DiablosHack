#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F0+F1 a partir de los artefactos
verificados (sin dependencias externas, mismo estilo que modeling/)."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'modeling'
OUT = ROOT / 'docs' / 'reporte_f0_f1'
F0 = ART / 'f0-full-reproduction' / 'F0'
F1 = ART / 'f1-full-reproduction' / 'F1'

MODEL_COLOR = {'B0': '#475569', 'B1': '#2563eb', 'B2': '#c2410c'}
CLASS_COLOR = {
    'ball': '#16a34a', 'called_strike': '#2563eb', 'whiff': '#7c3aed',
    'foul': '#d97706', 'in_play': '#dc2626', 'hit_by_pitch': '#64748b',
}
CLASS_LABEL = {
    'ball': 'ball', 'called_strike': 'called strike', 'whiff': 'whiff',
    'foul': 'foul', 'in_play': 'in play', 'hit_by_pitch': 'HBP',
}
PART_LABEL = {
    'train': 'train 2024', 'development': 'development 2025',
    'calibration': 'calibration 2025', 'phase_review': 'phase review 2025',
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
    models = ['B0', 'B1', 'B2']
    data = {(m['model'], m['partition']): m['multiclass_log_loss'] for m in metrics['metrics']}
    y_min, y_max = 1.40, 1.56
    top, bottom, left = 110, 560, 80
    group_w, bar_w, gap = 260, 56, 8

    def Y(v):
        return bottom - (v - y_min) / (y_max - y_min) * (bottom - top)

    body = text(30, 34, 'Log loss multicase por modelo y partición (2025)', 20, weight='bold')
    body += text(30, 56, 'Menor es mejor · eje Y truncado en 1.40 para resaltar diferencias', 12, '#475569')
    for i, m in enumerate(models):
        x = 640 + i * 110
        body += f'<rect x="{x}" y="22" width="14" height="14" fill="{MODEL_COLOR[m]}"/>\n'
        body += text(x + 20, 34, m, 13, MODEL_COLOR[m])
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
            body += text(x + bar_w / 2, Y(v) - 6, f'{v:.4f}', 11, '#334155', 'middle')
        n = next(m2['n_pitches'] for m2 in metrics['metrics']
                 if m2['model'] == 'B0' and m2['partition'] == p)
        body += text(gx + (3 * bar_w + 2 * gap) / 2, bottom + 22, PART_LABEL[p], 13,
                     '#0f172a', 'middle', 'bold')
        body += text(gx + (3 * bar_w + 2 * gap) / 2, bottom + 40, f'n = {n:,}', 11,
                     '#475569', 'middle')
    body += f'<path d="M {left} {bottom} H {left + 3 * group_w}" stroke="#94a3b8"/>\n'
    (OUT / 'logloss_por_modelo.svg').write_text(svg(960, 620, body))


# ------------------------------------------------------------- bootstrap IC
def chart_bootstrap(metrics):
    comps = metrics['comparisons']
    rows = [('B1_vs_B0', 'B1 vs B0'), ('B2_vs_B0', 'B2 vs B0'), ('B2_vs_B1', 'B2 vs B1')]
    x_min, x_max = -0.09, 0.01
    left, right, top, row_h = 160, 620, 120, 110

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Comparaciones bootstrap pareadas por juego · phase review 2025', 20,
                weight='bold')
    body += text(30, 56, 'Δ log loss (candidato − referencia) con IC 95% · 500 remuestreos · '
                         'valores negativos favorecen al candidato', 12, '#475569')
    for tick in (-0.08, -0.06, -0.04, -0.02, 0.0):
        body += f'<path d="M {X(tick):.1f} {top - 20} V {top + 3 * row_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 28, f'{tick:.2f}', 11, '#475569', 'middle')
    body += f'<path d="M {X(0):.1f} {top - 20} V {top + 3 * row_h}" stroke="#94a3b8" stroke-width="2"/>\n'
    for i, (key, label) in enumerate(rows):
        c = comps[key]
        cy = top + i * row_h + 30
        color = '#16a34a' if c['decision'] == 'promote' else '#d97706'
        body += text(left - 12, cy + 4, label, 14, '#0f172a', 'end', 'bold')
        body += (f'<path d="M {X(c["ci_low"]):.1f} {cy} H {X(c["ci_high"]):.1f}" '
                 f'stroke="{color}" stroke-width="3"/>\n')
        for cx in (c['ci_low'], c['ci_high']):
            body += f'<path d="M {X(cx):.1f} {cy - 8} V {cy + 8}" stroke="{color}" stroke-width="3"/>\n'
        body += f'<circle cx="{X(c["delta_candidate_minus_reference"]):.1f}" cy="{cy}" r="6" fill="{color}"/>\n'
        rel = c['relative_log_loss_reduction'] * 100
        body += text(right + 16, cy - 4, f'Δ = {c["delta_candidate_minus_reference"]:+.4f}', 12)
        body += text(right + 16, cy + 14, f'reducción relativa {rel:.2f}%', 12, '#475569')
        body += text(right + 16, cy + 32, f'decisión: {c["decision"]}', 12, color, weight='bold')
    body += text(left, top + 3 * row_h + 30,
                 esc('Umbral de promoción: reducción relativa ≥ 1% y límite superior del IC < 0.'), 11,
                 '#475569')
    (OUT / 'bootstrap_comparaciones.svg').write_text(svg(960, 500, body))


# ------------------------------------------------------- clases por partición
def chart_clases(cohort):
    order = ['train', 'development', 'calibration', 'phase_review']
    classes = ['ball', 'called_strike', 'whiff', 'foul', 'in_play', 'hit_by_pitch']
    left, width, top, row_h = 170, 620, 120, 80
    body = text(30, 34, 'Distribución de clases (y_event) por partición', 20, weight='bold')
    body += text(30, 56, 'Porcentaje apilado · mismo cohorte común F0 en las tres familias', 12,
                 '#475569')
    for i, c in enumerate(classes):
        x = 170 + (i % 6) * 105
        body += f'<rect x="{x}" y="76" width="12" height="12" fill="{CLASS_COLOR[c]}"/>\n'
        body += text(x + 17, 87, CLASS_LABEL[c], 11)
    for i, p in enumerate(order):
        d = cohort['by_partition'][p]
        total = d['n_pitches']
        cy = top + i * row_h
        body += text(left - 12, cy + 26, PART_LABEL[p], 13, '#0f172a', 'end', 'bold')
        body += text(left - 12, cy + 42, f'{total:,} pitches', 10, '#475569', 'end')
        body += text(left - 12, cy + 56, f'{d["n_games"]} juegos', 10, '#475569', 'end')
        x = left
        for c in classes:
            frac = d['class_counts'][c] / total
            w = frac * width
            body += f'<rect x="{x:.1f}" y="{cy}" width="{w:.1f}" height="34" fill="{CLASS_COLOR[c]}"/>\n'
            if frac > 0.045:
                body += text(x + w / 2, cy + 21, f'{frac * 100:.1f}%', 10, 'white', 'middle')
            x += w
    body += text(left, top + 4 * row_h + 8,
                 'hit_by_pitch ≈ 0.3–0.4% (segmento estrecho gris al final de cada barra).', 11,
                 '#475569')
    (OUT / 'clases_por_particion.svg').write_text(svg(860, 480, body))


# ----------------------------------------------------------- embudo elegibilidad
def chart_embudo(cohort):
    exc = cohort['exclusions']
    rows = [
        ('pitches asignados (input)', cohort['exclusions']['pitching']['input_rows'], '#334155'),
        ('elegibles · stuff', exc['stuff']['eligible_rows'], MODEL_COLOR['B1']),
        ('elegibles · location', exc['location']['eligible_rows'], '#0e7490'),
        ('elegibles · pitching', exc['pitching']['eligible_rows'], MODEL_COLOR['B2']),
        ('cohorte común F0', cohort['common_rows'], '#16a34a'),
    ]
    x_min, x_max = 480000, 500000
    left, right, top, row_h = 200, 720, 120, 78

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Embudo de elegibilidad hacia el cohorte común F0', 20, weight='bold')
    body += text(30, 56, 'Eje X truncado en 480k · el cohorte común es la intersección de las '
                         'tres familias', 12, '#475569')
    for tick in (480000, 485000, 490000, 495000, 500000):
        body += f'<path d="M {X(tick):.1f} {top - 16} V {top + 5 * row_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 24, f'{tick / 1000:.0f}k', 11, '#475569', 'middle')
    for i, (label, v, color) in enumerate(rows):
        cy = top + i * row_h
        body += text(left - 12, cy + 24, esc(label), 13, '#0f172a', 'end')
        body += f'<rect x="{left}" y="{cy}" width="{X(v) - left:.1f}" height="34" fill="{color}"/>\n'
        body += text(X(v) + 8, cy + 22, f'{v:,}', 12, '#334155')
    notes = [
        f'stuff: −{exc["stuff"]["quality_filter"]:,} calidad · −{exc["stuff"]["outside_common_cohort"]:,} fuera del común',
        f'location: −{exc["location"]["quality_filter"]:,} calidad · −{exc["location"]["missing_features_after_quality_and_target"]:,} sin features · −{exc["location"]["outside_common_cohort"]:,} fuera del común',
        f'pitching: −{exc["pitching"]["quality_filter"]:,} calidad · familia restrictiva (define el común)',
    ]
    ny = top + 5 * row_h + 16
    for n in notes:
        body += text(left, ny, n, 11, '#475569')
        ny += 18
    (OUT / 'embudo_elegibilidad.svg').write_text(svg(860, 590, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f1_metrics = json.loads((F1 / 'metrics.json').read_text())
    f1_cohort = json.loads((F1 / 'cohort_manifest.json').read_text())
    chart_logloss(f1_metrics)
    chart_bootstrap(f1_metrics)
    chart_clases(f1_cohort)
    chart_embudo(f1_cohort)
    for name in ('calibration_development.svg', 'calibration_calibration.svg',
                 'calibration_phase_review.svg'):
        shutil.copy2(F1 / name, OUT / name)
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
