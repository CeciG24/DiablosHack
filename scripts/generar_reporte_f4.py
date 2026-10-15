#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F4 (calibración por temperatura y cabezas
de contacto, protocolo A) a partir de los artefactos verificados, sin
dependencias externas."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'modeling'
OUT = ROOT / 'docs' / 'reporte_f4'
F4 = ART / 'f4-full-check' / 'F4'

FAMILIES = ['stuff', 'location', 'pitching']
HEADS = ['contact', 'groundball', 'chase']
FAM_COLOR = {'stuff': '#7c3aed', 'location': '#0d9488', 'pitching': '#16a34a'}
FAM_LABEL = {'stuff': 'Stuff', 'location': 'Location', 'pitching': 'Pitching'}
HEAD_COLOR = {'contact': '#ea580c', 'groundball': '#16a34a', 'chase': '#2563eb'}
PART_LABEL = {'train': 'train 2024', 'development': 'development',
              'calibration': 'calibration', 'phase_review': 'phase review'}


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


# --------------------------------------------- bootstrap de las 9 cabezas
def chart_bootstrap_cabezas(metrics):
    x_min, x_max = -0.21, 0.02
    left, right, top, row_h, group_gap = 190, 510, 120, 38, 22

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    n_rows = 9
    total_h = n_rows * row_h + 2 * group_gap
    body = text(30, 34, 'Cabezas auxiliares vs prevalencia de entrenamiento · phase review',
                20, weight='bold')
    body += text(30, 56, 'Δ log loss (modelo − prevalencia) con IC 95% · 500 remuestreos '
                         'pareados por juego · negativo favorece al modelo · poblaciones '
                         'condicionales por cabeza', 12, '#475569')
    for tick in (-0.20, -0.15, -0.10, -0.05, 0.0):
        body += f'<path d="M {X(tick):.1f} {top - 20} V {top + total_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 28, f'{tick:.2f}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 20} V {top + total_h}" stroke="#94a3b8" '
             f'stroke-width="2"/>\n')
    y = top
    for head in HEADS:
        body += text(30, y + 14, head, 14, HEAD_COLOR[head], weight='bold')
        for fam in FAMILIES:
            h = metrics['families'][fam]['heads'][head]
            c = h['comparison']
            cy = y + 20
            validated = h['status'] == 'validated'
            color = FAM_COLOR[fam]
            body += text(left - 12, cy + 4, FAM_LABEL[fam], 12, color, 'end', 'bold')
            body += (f'<path d="M {X(c["ci_low"]):.1f} {cy} H {X(c["ci_high"]):.1f}" '
                     f'stroke="{color}" stroke-width="3"/>\n')
            for cx in (c['ci_low'], c['ci_high']):
                body += (f'<path d="M {X(cx):.1f} {cy - 8} V {cy + 8}" stroke="{color}" '
                         f'stroke-width="3"/>\n')
            body += (f'<circle cx="{X(c["delta_candidate_minus_reference"]):.1f}" cy="{cy}" '
                     f'r="5.5" fill="{color}"/>\n')
            rel = c['relative_log_loss_reduction'] * 100
            st_color = '#16a34a' if validated else '#d97706'
            body += text(right + 14, cy - 5,
                         f'Δ = {c["delta_candidate_minus_reference"]:+.4f}  ({rel:+.2f}%)',
                         11)
            body += text(right + 14, cy + 12, f'{h["status"]}', 10, st_color, weight='bold')
            y += row_h
        y += group_gap
    body += text(left, top + total_h + 30,
                 esc('Las dos cabezas experimental son de Stuff: mejoran pero no llegan al 1% '
                     'exigido → la salida pública conserva la prevalencia suavizada.'), 11,
                 '#475569')
    (OUT / 'bootstrap_cabezas.svg').write_text(svg(860, top + total_h + 60, body))


# --------------------------------------- cobertura de etiquetas condicionales
def chart_cobertura(metrics):
    heads = ['contact', 'groundball', 'chase']
    parts = ['train', 'development', 'calibration', 'phase_review']
    cov = {h: {} for h in heads}
    pop_max = 0
    for h in heads:
        c = json.loads((F4 / 'pitching' / h / 'coverage.json').read_text())
        for p in parts:
            row = c[p]
            cov[h][p] = (row['eligible_rows'], row['missing_rows'],
                         row['population_rows'])
            pop_max = max(pop_max, row['population_rows'])
    y_max = pop_max * 1.12
    top, bottom, left = 105, 520, 80
    group_w, bar_w, gap = 190, 32, 8

    def Y(v):
        return bottom - v / y_max * (bottom - top)

    body = text(30, 34, 'Cobertura de etiquetas por cabeza · denominadores condicionales',
                20, weight='bold')
    body += text(30, 56, 'Barras: elegibles con etiqueta + sin etiqueta/fuera de la población '
                         'condicional (gris) · mismo subconjunto para las 3 familias', 12,
                 '#475569')
    for i, h in enumerate(heads):
        x = 385 + i * 95
        body += f'<rect x="{x}" y="20" width="14" height="14" fill="{HEAD_COLOR[h]}"/>\n'
        body += text(x + 19, 32, h, 12, HEAD_COLOR[h])
    body += f'<rect x="385" y="44" width="14" height="14" fill="#cbd5e1"/>\n'
    body += text(404, 56, 'sin etiqueta / fuera de población', 11, '#475569')
    for tick in (0, 50000, 100000, 150000, 200000, 250000):
        if tick > y_max:
            continue
        body += f'<path d="M {left} {Y(tick):.1f} H {left + 3 * group_w}" stroke="#e2e8f0"/>\n'
        body += text(left - 8, Y(tick) + 4, f'{tick // 1000}k', 11, '#475569', 'end')
    for gi, h in enumerate(heads):
        gx = left + gi * group_w + 12
        for pi, p in enumerate(parts):
            elig, missing, pop = cov[h][p]
            x = gx + pi * (bar_w + gap)
            body += (f'<rect x="{x}" y="{Y(elig):.1f}" width="{bar_w}" '
                     f'height="{bottom - Y(elig):.1f}" fill="{HEAD_COLOR[h]}"/>\n')
            body += (f'<rect x="{x}" y="{Y(pop):.1f}" width="{bar_w}" '
                     f'height="{Y(elig) - Y(pop):.1f}" fill="#cbd5e1"/>\n')
            body += text(x + bar_w / 2, Y(pop) - 6, f'{elig / 1000:.0f}k', 9, '#334155',
                         'middle')
            body += text(x + bar_w / 2, bottom + 15, PART_LABEL[p].split()[0][:4], 9,
                         '#64748b', 'middle')
        body += text(gx + (4 * bar_w + 3 * gap) / 2, bottom + 34, h, 13, HEAD_COLOR[h],
                     'middle', 'bold')
    body += f'<path d="M {left} {bottom} H {left + 3 * group_w}" stroke="#94a3b8"/>\n'
    body += text(left, bottom + 58,
                 'contact/groundball: solo batazos en juego medidos · chase: solo pitches '
                 'fuera de la zona suministrada', 11, '#475569')
    body += text(left, bottom + 76,
                 esc('los faltantes de chase incluyen pitches fuera de su población condicional '
                     '(no son mediciones perdidas)'), 11, '#475569')
    (OUT / 'cobertura_cabezas.svg').write_text(svg(720, bottom + 95, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((F4 / 'metrics.json').read_text())
    chart_bootstrap_cabezas(metrics)
    chart_cobertura(metrics)
    for fam in FAMILIES:
        shutil.copy2(F4 / fam / 'event' / 'calibration_phase_review.svg',
                     OUT / f'calibracion_evento_{fam}.svg')
    shutil.copy2(F4 / 'pitching' / 'chase' / 'calibration_phase_review.svg',
                 OUT / 'calibracion_chase_pitching.svg')
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
