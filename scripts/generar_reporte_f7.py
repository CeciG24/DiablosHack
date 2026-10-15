#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F7 (índices provisionales y agregación,
protocolo A) a partir de los artefactos verificados, sin dependencias externas
más allá de pandas/numpy del entorno."""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'modeling'
OUT = ROOT / 'docs' / 'reporte_f7'
F7 = ART / 'f7-full-check' / 'F7'

FAMILY_COLOR = {'stuff': '#0d9488', 'location': '#2563eb', 'pitching': '#ea580c'}
FAMILY_LABEL = {'stuff': 'Stuff+', 'location': 'Location+', 'pitching': 'Pitching+'}
PART_ORDER = ['development', 'calibration', 'phase_review']
PART_LABEL = {'development': 'development', 'calibration': 'calibration',
              'phase_review': 'phase review'}


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


# ----------------------- cobertura: registros vs score válido por partición
def chart_cobertura(scores, population):
    y_max, top, bottom, left = 150000, 105, 470, 80
    group_w, bar_w = 190, 70

    def Y(v):
        return bottom - v / y_max * (bottom - top)

    body = text(30, 34, 'Cobertura del score S0 por partición · idéntica en las '
                        'tres familias', 20, weight='bold')
    body += text(30, 56, 'Denominador = todos los registros 2025 de model_base en '
                         'los partidos seleccionados · los nulos conservan motivo',
                12, '#475569')
    body += f'<rect x="480" y="20" width="14" height="14" fill="#0d9488"/>\n'
    body += text(499, 32, 'score válido', 12)
    body += f'<rect x="480" y="42" width="14" height="14" fill="#cbd5e1"/>\n'
    body += text(499, 54, 'sin score (motivo registrado)', 12, '#475569')
    for tick in (0, 25000, 50000, 75000, 100000, 125000, 150000):
        body += (f'<path d="M {left} {Y(tick):.1f} H {left + 3 * group_w}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(left - 8, Y(tick) + 4, f'{tick // 1000}k', 11, '#475569', 'end')
    fam = scores.loc[scores.family == 'pitching']
    for gi, p in enumerate(PART_ORDER):
        total = int((population.partition == p).sum())
        valid = int(((fam.partition == p) & fam.score.notna()).sum())
        cov = valid / total
        x = left + gi * group_w + (group_w - bar_w) / 2
        body += (f'<rect x="{x}" y="{Y(valid):.1f}" width="{bar_w}" '
                 f'height="{bottom - Y(valid):.1f}" fill="#0d9488"/>\n')
        body += (f'<rect x="{x}" y="{Y(total):.1f}" width="{bar_w}" '
                 f'height="{Y(valid) - Y(total):.1f}" fill="#cbd5e1"/>\n')
        body += text(x + bar_w / 2, Y(total) - 8,
                     f'{total:,}'.replace(',', ' '), 10, '#334155', 'middle')
        body += text(x + bar_w / 2, Y(valid) + 18, f'{valid / 1000:.1f}k', 11,
                     'white', 'middle', 'bold')
        body += text(x + bar_w / 2, bottom + 18, PART_LABEL[p], 12, '#0f172a',
                     'middle', 'bold')
        body += text(x + bar_w / 2, bottom + 36, f'{cov * 100:.2f}% válido', 10,
                     '#475569', 'middle')
    body += f'<path d="M {left} {bottom} H {left + 3 * group_w}" stroke="#94a3b8"/>\n'
    body += text(left, bottom + 62,
                 esc('Cobertura global 98.37% por familia: 251,969 scores válidos '
                     'de 256,144 registros por familia.'), 11, '#475569')
    body += text(left, bottom + 80,
                 esc('Las tres familias comparten denominador por diseño (cohorte '
                     'común); la cobertura describe disponibilidad, no exactitud.'),
                11, '#475569')
    (OUT / 'cobertura_scores.svg').write_text(svg(720, bottom + 100, body))


# ----------------------- distribución de índices por familia
def chart_distribucion(scores):
    left, width_px, top, panel_h = 120, 560, 100, 120
    bins = np.arange(35, 165, 5)

    body = text(30, 34, 'Distribución de los índices S0 (100 = media de '
                        'calibración 2025)', 20, weight='bold')
    body += text(30, 56, 'Misma utilidad, escalas distintas: la σ pequeña de '
                         'Stuff estira su índice — no comparar entre familias',
                12, '#475569')
    for tick in (40, 60, 80, 100, 120, 140, 160):
        x = left + (tick - 35) / 125 * width_px
        body += (f'<path d="M {x:.1f} {top - 10} V {top + 3 * panel_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(x, top - 18, str(tick), 11, '#475569', 'middle')
    x100 = left + (100 - 35) / 125 * width_px
    body += (f'<path d="M {x100:.1f} {top - 10} V {top + 3 * panel_h}" '
             f'stroke="#94a3b8" stroke-width="2" stroke-dasharray="4 3"/>\n')
    for i, fam in enumerate(('stuff', 'location', 'pitching')):
        s = scores.loc[(scores.family == fam) & scores.score.notna(), 'score']
        hist, edges = np.histogram(s, bins=bins)
        h_max = hist.max()
        py = top + i * panel_h
        body += text(30, py + 20, FAMILY_LABEL[fam], 14, FAMILY_COLOR[fam],
                     weight='bold')
        body += text(30, py + 36,
                     f'n={len(s):,} · rango {s.min():.0f}–{s.max():.0f}'.replace(',', ' '),
                     10, '#475569')
        bw = width_px / (len(bins) - 1)
        for j, h in enumerate(hist):
            if h == 0:
                continue
            bh = h / h_max * (panel_h - 35)
            x = left + (edges[j] - 35) / 125 * width_px
            body += (f'<rect x="{x:.1f}" y="{py + panel_h - 15 - bh:.1f}" '
                     f'width="{bw - 1:.1f}" height="{bh:.1f}" '
                     f'fill="{FAMILY_COLOR[fam]}"/>\n')
        body += (f'<path d="M {left} {py + panel_h - 15} H {left + width_px}" '
                 f'stroke="#94a3b8"/>\n')
    note_y = top + 3 * panel_h + 24
    body += text(30, note_y,
                 esc('Location y Pitching se concentran en 80–115; Stuff llega a '
                     '~158 porque su σ de utilidad es ~9× menor.'), 11, '#475569')
    body += text(30, note_y + 18,
                 esc('Cada familia describe un componente distinto: los índices '
                     'no se suman ni se comparan como una sola magnitud.'),
                11, '#475569')
    (OUT / 'distribucion_scores.svg').write_text(svg(760, note_y + 45, body))


# ----------------------- sensibilidad de S1 ante ±25% en pesos
def chart_sensibilidad(variants):
    x_min, x_max = 0.9960, 1.0005
    y_min, y_max = 0.0, 0.9
    left, right, top, bottom = 90, 660, 110, 430

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    def Y(v):
        return bottom - (v - y_min) / (y_max - y_min) * (bottom - top)

    body = text(30, 34, 'Sensibilidad de S1 (contacto) a perturbaciones de '
                        '±25% en pesos', 20, weight='bold')
    body += text(30, 56, '24 variantes en development · correlación de rangos '
                         'vs S1 base · no valida los pesos ni equivale a carreras',
                12, '#475569')
    for tick in (0.996, 0.997, 0.998, 0.999, 1.0):
        body += (f'<path d="M {X(tick):.1f} {top} V {bottom}" stroke="#e2e8f0"/>\n')
        body += text(X(tick), bottom + 18, f'{tick:.3f}', 11, '#475569', 'middle')
    for tick in (0.0, 0.2, 0.4, 0.6, 0.8):
        body += (f'<path d="M {left} {Y(tick):.1f} H {right}" stroke="#e2e8f0"/>\n')
        body += text(left - 8, Y(tick) + 4, f'{tick:.1f}', 11, '#475569', 'end')
    body += text(left - 60, (top + bottom) / 2,
                 'cambio absoluto medio (puntos de índice)', 11, '#475569')
    body += text((left + right) / 2, bottom + 40,
                 'correlación de rangos con S1 base (Spearman)', 11, '#475569',
                 'middle')
    body += f'<rect x="480" y="70" width="14" height="14" fill="#2563eb"/>\n'
    body += text(499, 82, 'Location', 12)
    body += f'<rect x="575" y="70" width="14" height="14" fill="#ea580c"/>\n'
    body += text(594, 82, 'Pitching', 12)
    for v in variants:
        color = FAMILY_COLOR[v['family']]
        body += (f'<circle cx="{X(v["spearman_correlation"]):.1f}" '
                 f'cy="{Y(v["mean_absolute_score_change"]):.1f}" r="6" '
                 f'fill="{color}" fill-opacity="0.75"/>\n')
    body += text(30, bottom + 62,
                 esc('Todos los puntos quedan con correlación ≥ 0.9966: el '
                     'ordenamiento es estable ante perturbaciones, pero el mayor '
                     'cambio absoluto medio llega a 0.83 puntos.'), 11, '#475569')
    (OUT / 'sensibilidad_s1.svg').write_text(svg(720, bottom + 85, body))


# ----------------------- deltas de score del experimento ambiental
def chart_deltas_ambiente(env):
    stats = env.groupby('target_environment').delta_score.agg(
        ['mean', 'std', 'min', 'max'])
    order = ['Extreme Altitude', 'Medium Altitude', 'No Altitude']
    color = {'Extreme Altitude': '#c2410c', 'Medium Altitude': '#f59e0b',
             'No Altitude': '#94a3b8'}
    x_min, x_max = -5.5, 4.0
    left, right, top, row_h = 300, 660, 130, 80

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Cambio de índice S0 al mover la categoría ambiental '
                        '(experimental)', 20, weight='bold')
    body += text(30, 56, 'Δ score por pitch en revisión con el normalizador fijo '
                         'de Pitching · dispersión = min–max y ±1σ · asociación, '
                         'no causal', 12, '#475569')
    for tick in (-4, -2, 0, 2, 4):
        body += (f'<path d="M {X(tick):.1f} {top - 14} V {top + len(order) * row_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 22, f'{tick:+d}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 14} V {top + len(order) * row_h}" '
             f'stroke="#94a3b8" stroke-width="2"/>\n')
    y = top
    for target in order:
        r = stats.loc[target]
        cy = y + 30
        body += text(30, cy + 4, target, 13, color[target], weight='bold')
        body += text(30, cy + 20, '58,182 escenarios', 10, '#475569')
        body += (f'<path d="M {X(r["min"]):.1f} {cy} H {X(r["max"]):.1f}" '
                 f'stroke="{color[target]}" stroke-width="1.5" '
                 f'stroke-opacity="0.35"/>\n')
        body += (f'<path d="M {X(r["mean"] - r["std"]):.1f} {cy - 8} '
                 f'H {X(r["mean"] + r["std"]):.1f} V {cy + 8} '
                 f'H {X(r["mean"] - r["std"]):.1f} Z" fill="{color[target]}" '
                 f'fill-opacity="0.25"/>\n')
        body += (f'<circle cx="{X(r["mean"]):.1f}" cy="{cy}" r="5" '
                 f'fill="{color[target]}"/>\n')
        body += text(X(r['max']) + 8, cy + 4,
                     f'media {r["mean"]:+.3f} pts', 11, '#475569')
        y += row_h
    body += text(left, y + 14,
                 esc('Las medias son prácticamente cero (−0.04 a +0.06 puntos): '
                     'el índice apenas se mueve al cambiar de categoría.'),
                11, '#475569')
    body += text(left, y + 32,
                 esc('Pertenece al candidato ambiental no promovido de F6; no '
                     'sustituye los índices de la política aprobada.'), 11,
                 '#475569')
    (OUT / 'deltas_ambiente_score.svg').write_text(svg(860, y + 55, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    scores = pd.read_parquet(F7 / 'scores.parquet')
    population = pd.read_parquet(F7 / 'population.parquet')
    env = pd.read_parquet(F7 / 'environment_score_deltas.parquet')
    variants = json.loads((F7 / 'contact_sensitivity.json').read_text())
    chart_cobertura(scores, population)
    chart_distribucion(scores)
    chart_sensibilidad(variants)
    chart_deltas_ambiente(env)
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
