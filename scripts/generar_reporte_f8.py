#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F8 (release congelado y evaluación final
sobre 2026) a partir de los artefactos verificados del release, sin dependencias
externas más allá de pandas/numpy del entorno.

Uso: .venv/bin/python scripts/generar_reporte_f8.py [nombre_release]
"""
import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'artifacts' / 'modeling' / 'releases' / (
    sys.argv[1] if len(sys.argv) > 1 else 'f8-release-20261014')
EVAL = RELEASE / 'evaluation'
OUT = ROOT / 'docs' / 'reporte_f8'

MODEL_COLOR = {'B1': '#64748b', 'stuff': '#0d9488', 'location': '#2563eb',
               'pitching': '#ea580c', 'environment': '#7c3aed'}
MODEL_LABEL = {'B1': 'B1 (baseline)', 'stuff': 'Stuff', 'location': 'Location',
               'pitching': 'Pitching', 'environment': 'Ambiente (experimental)'}
MODEL_ORDER = ['B1', 'stuff', 'location', 'pitching', 'environment']
CLASS_LABEL = {'ball': 'ball', 'called_strike': 'called strike', 'whiff': 'whiff',
               'foul': 'foul', 'in_play': 'in play', 'hit_by_pitch': 'hit by pitch'}


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


# ----------------------- métricas globales: log loss y Brier por modelo
def chart_metricas(metrics):
    left, panel_w, top, row_h = 150, 200, 110, 44
    panels = [('multiclass_log_loss', 'Log loss multiclase', 1.6),
              ('multiclass_brier_sum_over_classes', 'Brier multiclase', 0.8)]
    values = {r['model']: r for r in metrics}

    body = text(30, 34, 'Métricas globales en el test 2026 · cohorte común '
                        '(n = 130,053)', 20, weight='bold')
    body += text(30, 56, 'Menor es mejor · las cinco filas se evalúan sobre los '
                         'mismos pitches elegibles', 12, '#475569')
    for pi, (key, title, vmax) in enumerate(panels):
        x0 = left + pi * (panel_w + 140)

        def X(v, x0=x0, vmax=vmax):
            return x0 + v / vmax * panel_w

        body += text(x0, top - 16, title, 14, weight='bold')
        for tick in (0, vmax / 2, vmax):
            body += (f'<path d="M {X(tick):.1f} {top} V {top + 5 * row_h}" '
                     f'stroke="#e2e8f0"/>\n')
            body += text(X(tick), top + 5 * row_h + 18, f'{tick:g}', 11,
                         '#475569', 'middle')
        for i, name in enumerate(MODEL_ORDER):
            v = values[name][key]
            y = top + i * row_h
            body += text(x0 - 10, y + 20, MODEL_LABEL[name], 12,
                         MODEL_COLOR[name], 'end', 'bold')
            body += (f'<rect x="{x0}" y="{y + 5}" width="{X(v) - x0:.1f}" '
                     f'height="24" fill="{MODEL_COLOR[name]}"/>\n')
            body += text(X(v) + 6, y + 22, f'{v:.4f}', 11, '#334155')
    ny = top + 5 * row_h + 44
    body += text(30, ny,
                 esc('Pitching es el mejor de la política: 1.0235 de log loss '
                     'frente a 1.0388 de Location y 1.4869 de B1.'), 11, '#475569')
    body += text(30, ny + 18,
                 esc('Stuff (1.5362) queda por debajo incluso del baseline de '
                     'eventos: mantiene su lectura diagnóstica, no predictiva.'),
                 11, '#475569')
    (OUT / 'metricas_test.svg').write_text(svg(760, ny + 45, body))


# ----------------------- comparaciones pareadas predeclaradas (delta + IC95%)
def chart_comparaciones(comparisons):
    x_min, x_max = -0.50, 0.08
    left, right, top, row_h = 250, 660, 120, 62

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Comparaciones pareadas predeclaradas · Δ log loss '
                        '(candidato − referencia)', 20, weight='bold')
    body += text(30, 56, 'Bootstrap pareado por partido, 500 remuestreos · '
                         'todas etiquetadas report_only_no_selection', 12, '#475569')
    for tick in (-0.4, -0.3, -0.2, -0.1, 0.0):
        body += (f'<path d="M {X(tick):.1f} {top - 12} V {top + 5 * row_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 20, f'{tick:+.1f}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 12} V {top + 5 * row_h}" '
             f'stroke="#94a3b8" stroke-width="2"/>\n')
    labels = {('B1', 'stuff'): 'Stuff − B1', ('B1', 'location'): 'Location − B1',
              ('B1', 'pitching'): 'Pitching − B1',
              ('location', 'pitching'): 'Pitching − Location',
              ('pitching', 'environment'): 'Ambiente − Pitching'}
    for i, r in enumerate(comparisons):
        label = labels[(r['reference'], r['candidate'])]
        cand = r['candidate']
        color = MODEL_COLOR[cand]
        cy = top + i * row_h + 22
        lo, hi, d = r['ci_low'], r['ci_high'], r['delta_candidate_minus_reference']
        body += text(left - 14, cy + 4, label, 13, color, 'end', 'bold')
        body += (f'<path d="M {X(lo):.1f} {cy} H {X(hi):.1f}" stroke="{color}" '
                 f'stroke-width="3" stroke-opacity="0.55"/>\n')
        for xv in (X(lo), X(hi)):
            body += (f'<path d="M {xv:.1f} {cy - 7} V {cy + 7}" stroke="{color}" '
                     f'stroke-width="2"/>\n')
        body += (f'<circle cx="{X(d):.1f}" cy="{cy}" r="6" fill="{color}"/>\n')
        body += text(max(X(hi) + 10, right + 8), cy + 4, f'{d:+.4f}', 11, '#334155')
    ny = top + 5 * row_h + 30
    body += text(30, ny,
                 esc('Solo Pitching supera a su referencia inmediata con IC '
                     'completo bajo cero (−0.0154, −1.48% relativo).'), 11, '#475569')
    body += text(30, ny + 18,
                 esc('El candidato ambiental es estadísticamente indistinguible '
                     'de Pitching (−0.00004): confirma la decisión de no '
                     'promoverlo. Ninguna comparación selecciona modelos.'),
                 11, '#475569')
    (OUT / 'comparaciones_pareadas.svg').write_text(svg(820, ny + 42, body))


# ----------------------- cobertura: población vs inferencia válida vs cohorte común
def chart_cobertura(coverage):
    y_max, top, bottom, left = 150000, 110, 430, 110
    group_w, bar_w, gap = 190, 42, 10

    def Y(v):
        return bottom - v / y_max * (bottom - top)

    body = text(30, 34, 'Dos poblaciones distintas en 2026: cobertura de '
                        'inferencia vs cohorte evaluativa', 20, weight='bold')
    body += text(30, 56, 'La inferencia no exige outcomes · la evaluación exige '
                         'elegibilidad común F0 y evento conocido', 12, '#475569')
    legend = [('total 2026', '#cbd5e1'), ('inferencia válida', '#94a3b8'),
              ('cohorte común', '#2563eb')]
    for i, (lab, col) in enumerate(legend):
        body += f'<rect x="{430 + i * 105}" y="22" width="13" height="13" fill="{col}"/>\n'
        body += text(430 + i * 105 + 18, 33, lab, 11, '#475569')
    for tick in (0, 50000, 100000, 150000):
        body += (f'<path d="M {left} {Y(tick):.1f} H {left + 3 * group_w}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(left - 8, Y(tick) + 4, f'{tick // 1000}k', 11, '#475569', 'end')
    for gi, fam in enumerate(('stuff', 'location', 'pitching')):
        c = coverage[fam]
        x = left + gi * group_w + (group_w - 3 * bar_w - 2 * gap) / 2
        for bi, (key, col) in enumerate((('n_total', '#cbd5e1'),
                                         ('n_inference_valid', '#94a3b8'),
                                         ('n_common_evaluation', '#2563eb'))):
            v = c[key]
            bx = x + bi * (bar_w + gap)
            body += (f'<rect x="{bx}" y="{Y(v):.1f}" width="{bar_w}" '
                     f'height="{bottom - Y(v):.1f}" fill="{col}"/>\n')
            body += text(bx + bar_w / 2, Y(v) - 7, f'{v // 1000}k', 9, '#475569',
                         'middle')
        body += text(x + (3 * bar_w + 2 * gap) / 2, bottom + 20,
                     MODEL_LABEL[fam].split(' ')[0], 13, MODEL_COLOR[fam],
                     'middle', 'bold')
        body += text(x + (3 * bar_w + 2 * gap) / 2, bottom + 38,
                     f"{c['n_inference_valid'] / c['n_total'] * 100:.2f}% inferible",
                     10, '#475569', 'middle')
    body += f'<path d="M {left} {bottom} H {left + 3 * group_w}" stroke="#94a3b8"/>\n'
    ny = bottom + 60
    body += text(30, ny,
                 esc('135,604 pitches 2026 · inferencia válida ≥ 99.1% por '
                     'familia · cohorte común evaluativa: 130,053 (95.91%).'),
                 11, '#475569')
    body += text(30, ny + 18,
                 esc('Fuera de la cohorte común el score evaluativo es nulo con '
                     'motivo; la cobertura de producto y la muestra evaluable se '
                     'reportan por separado.'), 11, '#475569')
    (OUT / 'cobertura_test.svg').write_text(svg(760, ny + 45, body))


# ----------------------- calibración de Pitching en test (6 clases)
def chart_calibracion(calibration):
    cell_w, cell_h, top0, left0 = 215, 165, 105, 70
    body = text(30, 34, 'Calibración del modelo Pitching en el test 2026 · '
                        'diez bins por clase', 20, weight='bold')
    body += text(30, 56, 'Probabilidad media predicha vs frecuencia observada '
                         '(cohorte común) · tamaño ∝ n del bin', 12, '#475569')
    rows = [r for r in calibration
            if r['model'] == 'pitching' and r['n'] and r['n'] > 0]
    classes = ['ball', 'called_strike', 'whiff', 'foul', 'in_play', 'hit_by_pitch']
    n_max = max(r['n'] for r in rows)
    for ci, cls in enumerate(classes):
        cx, cy = divmod(ci, 3)
        x0 = left0 + cx * cell_w
        y0 = top0 + cy * cell_h
        w, h = cell_w - 55, cell_h - 60
        body += text(x0, y0 - 8, CLASS_LABEL[cls], 12, weight='bold')
        body += (f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="none" '
                 f'stroke="#e2e8f0"/>\n')
        body += (f'<path d="M {x0} {y0 + h} L {x0 + w} {y0}" stroke="#94a3b8" '
                 f'stroke-width="1" stroke-dasharray="4 3"/>\n')
        sub = sorted((r for r in rows if r['class'] == cls),
                     key=lambda r: r['bin'])
        prev = None
        for r in sub:
            px = x0 + r['mean_probability'] * w
            py = y0 + h - r['observed_frequency'] * h
            if prev:
                body += (f'<path d="M {prev[0]:.1f} {prev[1]:.1f} L {px:.1f} '
                         f'{py:.1f}" stroke="#ea580c" stroke-width="1.2"/>\n')
            rad = 2 + 4 * (r['n'] / n_max) ** 0.5
            body += (f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rad:.1f}" '
                     f'fill="#ea580c" fill-opacity="0.8"/>\n')
            prev = (px, py)
        freq = sub[-1]['observed_frequency'] if sub else 0
        body += text(x0, y0 + h + 16,
                     f'freq. global {freq * 100:.1f}%', 10, '#475569')
    ny = top0 + 2 * cell_h + 10
    body += text(30, ny,
                 esc('Las clases frecuentes (ball, called_strike, whiff) caen '
                     'sobre la diagonal; las raras (hit_by_pitch) tienen bins '
                     'poblados solo en el extremo bajo.'), 11, '#475569')
    (OUT / 'calibracion_test.svg').write_text(svg(760, ny + 30, body))


# ----------------------- distribución de índices S0 en el test 2026
def chart_distribucion(scores):
    left, width_px, top, panel_h = 120, 560, 100, 120
    bins = np.arange(35, 165, 5)

    body = text(30, 34, 'Distribución de los índices S0 en el test 2026 · '
                        'la escala fija se mantiene centrada', 20, weight='bold')
    body += text(30, 56, 'Media ≈ 100 y σ ≈ 10 en las tres familias sobre '
                         '130,053 pitches de la cohorte común', 12, '#475569')
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
        body += text(30, py + 20, MODEL_LABEL[fam] + '+', 14, MODEL_COLOR[fam],
                     weight='bold')
        body += text(30, py + 36,
                     f'n={len(s):,} · rango {s.min():.0f}–{s.max():.0f}'.replace(',', ' '),
                     10, '#475569')
        bw = width_px / (len(bins) - 1)
        for j, hgt in enumerate(hist):
            if hgt == 0:
                continue
            bh = hgt / h_max * (panel_h - 35)
            x = left + (edges[j] - 35) / 125 * width_px
            body += (f'<rect x="{x:.1f}" y="{py + panel_h - 15 - bh:.1f}" '
                     f'width="{bw - 1:.1f}" height="{bh:.1f}" '
                     f'fill="{MODEL_COLOR[fam]}"/>\n')
        body += (f'<path d="M {left} {py + panel_h - 15} H {left + width_px}" '
                 f'stroke="#94a3b8"/>\n')
    note_y = top + 3 * panel_h + 24
    body += text(30, note_y,
                 esc('La escala congelada en calibración 2025 sigue centrada en '
                     '~100 sobre 2026 sin reajuste: la deriva anual no rompió '
                     'la normalización.'), 11, '#475569')
    body += text(30, note_y + 18,
                 esc('La σ de Stuff sigue siendo ~9× menor en utilidad, por eso '
                     'su índice llega a ~158: los índices no se comparan entre '
                     'familias.'), 11, '#475569')
    (OUT / 'distribucion_scores_test.svg').write_text(svg(760, note_y + 45, body))


# ----------------------- benchmark de inferencia local
def chart_benchmark(bench):
    left, width_px, top, row_h = 150, 460, 115, 70
    vmax = 0.4

    def X(v):
        return left + v / vmax * width_px

    hw = bench['hardware']
    body = text(30, 34, 'Benchmark de inferencia del release · 1,000 registros '
                        'por lote', 20, weight='bold')
    body += text(30, 56,
                 esc(f"Mediana de 3 corridas en caliente · {hw['platform']} · "
                     'incluye cabezas auxiliares, excluye carga inicial y red'),
                 12, '#475569')
    for tick in (0, 0.1, 0.2, 0.3, 0.4):
        body += (f'<path d="M {X(tick):.1f} {top - 12} V {top + 3 * row_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 20, f'{tick:.1f} s', 11, '#475569', 'middle')
    for i, r in enumerate(bench['results']):
        fam = r['family']
        y = top + i * row_h
        body += text(left - 12, y + 26, MODEL_LABEL[fam], 13, MODEL_COLOR[fam],
                     'end', 'bold')
        for rep in r['warm_seconds']:
            body += (f'<circle cx="{X(rep):.1f}" cy="{y + 20}" r="4" '
                     f'fill="{MODEL_COLOR[fam]}" fill-opacity="0.35"/>\n')
        body += (f'<rect x="{left}" y="{y + 10}" '
                 f'width="{X(r["median_seconds"]) - left:.1f}" height="20" '
                 f'fill="{MODEL_COLOR[fam]}" fill-opacity="0.85"/>\n')
        body += text(X(r['median_seconds']) + 8, y + 25,
                     f"{r['median_seconds'] * 1000:.0f} ms", 11, '#334155')
    ny = top + 3 * row_h + 26
    body += text(30, ny,
                 esc('Mediana < 0.35 s por 1,000 lanzamientos en las tres '
                     'familias: apto para uso interactivo en la interfaz local.'),
                 11, '#475569')
    (OUT / 'benchmark_inferencia.svg').write_text(svg(720, ny + 25, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((EVAL / 'metrics.json').read_text())
    coverage = json.loads((EVAL / 'coverage.json').read_text())
    calibration = json.loads((EVAL / 'calibration.json').read_text())
    bench = json.loads((RELEASE / 'benchmark.json').read_text())
    scores = pd.read_parquet(EVAL / 'scores.parquet')
    chart_metricas(metrics['metrics'])
    chart_comparaciones(metrics['comparisons'])
    chart_cobertura(coverage)
    chart_calibracion(calibration)
    chart_distribucion(scores)
    chart_benchmark(bench)
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
