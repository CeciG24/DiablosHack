#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F6 (ambiente y simulación de
asociaciones, protocolo A) a partir de los artefactos verificados, sin
dependencias externas."""
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'modeling'
OUT = ROOT / 'docs' / 'reporte_f6'
F6 = ART / 'f6-full-check' / 'F6'

PART_ORDER = ['train', 'development', 'calibration', 'phase_review']
PART_LABEL = {'train': 'train 2024', 'development': 'development',
              'calibration': 'calibration', 'phase_review': 'phase review'}
CAT_ORDER = ['No Altitude', 'Medium Altitude', 'Extreme Altitude']
CAT_COLOR = {'No Altitude': '#94a3b8', 'Medium Altitude': '#f59e0b',
             'Extreme Altitude': '#c2410c'}
CAT_SHORT = {'No Altitude': 'sin altura', 'Medium Altitude': 'altura media',
             'Extreme Altitude': 'altura extrema'}
CLASSES = ['ball', 'called_strike', 'whiff', 'foul', 'in_play', 'hit_by_pitch']


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


# ----------------------- cobertura por categoría ambiental y partición
def chart_cobertura():
    rows = list(csv.DictReader((F6 / 'environment_coverage.csv').open()))
    data = {(r['partition'], r['altitude_category']): int(r['n_pitches'])
            for r in rows}
    y_max, top, bottom, left = 250000, 110, 470, 80
    group_w, bar_w = 155, 70

    def Y(v):
        return bottom - v / y_max * (bottom - top)

    body = text(30, 34, 'Pitches por categoría ambiental y partición', 20,
                weight='bold')
    body += text(30, 56, 'Categoría disponible en toda la cohorte común · '
                         'las particiones 2025 se asignan por hash de juego',
                12, '#475569')
    lx = 480
    for i, c in enumerate(['Extreme Altitude', 'Medium Altitude', 'No Altitude']):
        body += f'<rect x="{lx}" y="{20 + i * 20}" width="14" height="14" fill="{CAT_COLOR[c]}"/>\n'
        body += text(lx + 19, 32 + i * 20, c, 12)
    for tick in (0, 50000, 100000, 150000, 200000, 250000):
        body += (f'<path d="M {left} {Y(tick):.1f} H {left + 4 * group_w}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(left - 8, Y(tick) + 4, f'{tick // 1000}k', 11, '#475569', 'end')
    for gi, p in enumerate(PART_ORDER):
        x = left + gi * group_w + (group_w - bar_w) / 2
        total = sum(data[(p, c)] for c in CAT_ORDER)
        acc = 0
        for c in CAT_ORDER:
            v = data[(p, c)]
            y0, y1 = Y(acc), Y(acc + v)
            body += (f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bar_w}" '
                     f'height="{y0 - y1:.1f}" fill="{CAT_COLOR[c]}"/>\n')
            if v > 22000:
                body += text(x + bar_w / 2, (y0 + y1) / 2 + 4,
                             f'{v / 1000:.1f}k', 10, 'white', 'middle', 'bold')
            acc += v
        body += text(x + bar_w / 2, Y(total) - 8,
                     f'{total:,}'.replace(',', ' '), 10, '#334155', 'middle')
        body += text(x + bar_w / 2, bottom + 18, PART_LABEL[p], 12,
                     '#0f172a', 'middle', 'bold')
    body += f'<path d="M {left} {bottom} H {left + 4 * group_w}" stroke="#94a3b8"/>\n'
    body += text(left, bottom + 48,
                 esc('Las tres categorías están representadas en las cuatro '
                     'particiones; train 2024 concentra la mayoría sin altura.'),
                11, '#475569')
    body += text(left, bottom + 66,
                 esc('Las categorías no se convierten a metros ni se '
                     'interpretan como estadios concretos.'), 11, '#475569')
    (OUT / 'cobertura_ambiente.svg').write_text(svg(760, bottom + 90, body))


# ----------------------- comparación bootstrap pareada global
def chart_bootstrap(metrics):
    c = metrics['comparison']
    x_min, x_max = -0.0005, 0.0009
    left, right, top = 300, 640, 130

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Aporte de la categoría ambiental · bootstrap pareado '
                        'por juego', 20, weight='bold')
    body += text(30, 56, 'Δ log loss (candidato − control) con IC 95% · 500 '
                         'remuestreos ponderados por pitch · negativo favorece '
                         'al ambiente', 12, '#475569')
    for tick in (-0.0004, -0.0002, 0.0, 0.0002, 0.0004, 0.0006, 0.0008):
        body += (f'<path d="M {X(tick):.1f} {top - 20} V {top + 90}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 28, f'{tick:.4f}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 20} V {top + 90}" stroke="#94a3b8" '
             f'stroke-width="2"/>\n')
    rel = c['relative_log_loss_reduction'] * 100
    body += text(30, top + 8, 'Ambiente vs control · phase review', 13,
                 weight='bold')
    body += text(30, top + 26,
                 f"{c['n_pitches']:,} pitches · {c['n_games']} juegos · "
                 f'reducción relativa {rel:+.4f}%'.replace(',', ' '), 11,
                 '#475569')
    cy = top + 44
    color = '#c2410c'
    body += (f'<path d="M {X(c["ci_low"]):.1f} {cy} H {X(c["ci_high"]):.1f}" '
             f'stroke="{color}" stroke-width="3"/>\n')
    for cx in (c['ci_low'], c['ci_high']):
        body += (f'<path d="M {X(cx):.1f} {cy - 9} V {cy + 9}" '
                 f'stroke="{color}" stroke-width="3"/>\n')
    body += (f'<circle cx="{X(c["delta_candidate_minus_reference"]):.1f}" '
             f'cy="{cy}" r="6" fill="{color}"/>\n')
    body += text(X(c['ci_high']) + 12, cy - 2,
                 f'Δ = {c["delta_candidate_minus_reference"]:+.5f}', 11)
    body += text(X(c['ci_high']) + 12, cy + 15,
                 f'decisión: {metrics["scientific_decision"]}', 10, '#d97706',
                 weight='bold')
    note_y = top + 110
    body += text(30, note_y,
                 esc('El IC contiene cero y el punto cae del lado que perjudica '
                     'al candidato: no hay'), 11, '#475569')
    body += text(30, note_y + 18,
                 esc('evidencia de mejora → retain_reference. Se conserva el '
                     'Pitching sin ambiente de F4.'), 11, '#475569')
    (OUT / 'comparacion_bootstrap.svg').write_text(svg(860, note_y + 45, body))


# ----------------------- mejora relativa por categoría en revisión
def chart_subgrupos(subgroups):
    rows = [g for g in subgroups
            if g['status'] == 'evaluated' and g['group_by'] == ['altitude_category']]
    rows.sort(key=lambda g: CAT_ORDER.index(g['values'][0]), reverse=True)
    x_min, x_max = -0.10, 0.10
    left, right, top, row_h = 300, 640, 130, 62

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Cambio relativo de log loss por categoría · revisión',
                20, weight='bold')
    body += text(30, 56, 'Positivo favorece al candidato ambiental · '
                         'diagnóstico sin corrección por comparaciones múltiples',
                12, '#475569')
    for tick in (-0.10, -0.05, 0.0, 0.05, 0.10):
        body += (f'<path d="M {X(tick):.1f} {top - 14} V {top + len(rows) * row_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 22, f'{tick:+.2f}%', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 14} V {top + len(rows) * row_h}" '
             f'stroke="#94a3b8" stroke-width="2"/>\n')
    y = top
    for g in rows:
        cat = g['values'][0]
        rel = g['comparison']['relative_log_loss_reduction'] * 100
        n = g['review_support']['eligible_rows']
        x0, x1 = X(min(0, rel)), X(max(0, rel))
        body += text(left - 12, y + 26, cat, 12, '#0f172a', 'end')
        body += (f'<rect x="{x0:.1f}" y="{y + 12}" width="{max(x1 - x0, 1.5):.1f}" '
                 f'height="22" fill="{CAT_COLOR[cat]}" rx="3"/>\n')
        side = x1 + 8 if rel >= 0 else x0 - 8
        anchor = 'start' if rel >= 0 else 'end'
        body += text(side, y + 28, f'{rel:+.4f}% · {n:,} pitches'.replace(',', ' '),
                     11, '#0f172a', anchor)
        y += row_h
    body += text(left, y + 18,
                 esc('Ninguna categoría muestra mejora consistente; el efecto se '
                     'concentra en altura media'), 11, '#475569')
    body += text(left, y + 36,
                 esc('(+0.07%) y se invierte sin altura (−0.08%). Solo 12 de 61 '
                     'grupos tuvieron muestra suficiente.'), 11, '#475569')
    (OUT / 'mejoras_subgrupos.svg').write_text(svg(860, y + 60, body))


# ----------------------- deltas del simulador por clase y destino
def chart_deltas(intervals):
    x_min, x_max = -0.30, 0.25
    left, right = 300, 660
    top, row_h, group_h = 110, 30, 210

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Deltas medios del simulador por destino · puntos '
                        'porcentuales', 20, weight='bold')
    body += text(30, 56, 'P(evento | destino) − P(evento | origen) · media de '
                         'cohorte con IC 95% · asociación a forma fija, no '
                         'causal ni recomendación', 12, '#475569')
    for tick in (-0.30, -0.20, -0.10, 0.0, 0.10, 0.20):
        body += (f'<path d="M {X(tick):.1f} {top - 14} V {top + 3 * group_h - 40}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 22, f'{tick:+.1f}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 14} V {top + 3 * group_h - 40}" '
             f'stroke="#94a3b8" stroke-width="2"/>\n')
    y = top
    for block in intervals:
        target = block['target_environment']
        color = CAT_COLOR[target]
        body += text(30, y, f"→ {target} · {block['n_pitches']:,} pitches "
                            f"({block['n_excluded']} fuera de soporte)".replace(',', ' '),
                     13, color, weight='bold')
        y += 14
        for cls in CLASSES:
            d = block['classes'][cls]
            mean, lo, hi = (d['mean_delta'] * 100, d['ci_low'] * 100,
                            d['ci_high'] * 100)
            cy = y + 10
            body += text(left - 12, cy + 4, cls, 11, '#0f172a', 'end')
            body += (f'<path d="M {X(lo):.1f} {cy} H {X(hi):.1f}" '
                     f'stroke="{color}" stroke-width="2.5"/>\n')
            for cx in (lo, hi):
                body += (f'<path d="M {X(cx):.1f} {cy - 6} V {cy + 6}" '
                         f'stroke="{color}" stroke-width="2.5"/>\n')
            body += (f'<circle cx="{X(mean):.1f}" cy="{cy}" r="4.5" '
                     f'fill="{color}"/>\n')
            body += text(X(hi) + 8, cy + 4, f'{mean:+.4f}', 10, '#475569')
            y += row_h
        y += group_h - 6 * row_h - 14
    note_y = top + 3 * group_h - 20
    body += text(30, note_y,
                 esc('Los seis deltas de cada destino suman ~0. Cada fila compara '
                     'el destino fijo con la categoría'), 11, '#475569')
    body += text(30, note_y + 18,
                 esc('original de sus pitches elegibles; las poblaciones difieren '
                     'entre destinos → no es comparación pareada.'), 11, '#475569')
    (OUT / 'deltas_simulacion.svg').write_text(svg(860, note_y + 45, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((F6 / 'metrics.json').read_text())
    subgroups = json.loads((F6 / 'subgroup_metrics.json').read_text())
    intervals = json.loads((F6 / 'simulation_intervals.json').read_text())
    chart_cobertura()
    chart_bootstrap(metrics)
    chart_subgrupos(subgroups)
    chart_deltas(intervals)
    for m, name in (('control', 'control'), ('environment', 'ambiente')):
        shutil.copy2(F6 / m / 'calibration_phase_review.svg',
                     OUT / f'calibracion_{name}.svg')
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
