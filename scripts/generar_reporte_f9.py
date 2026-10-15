#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F9 (StuffV2 post-release) a partir de los
artefactos verificados del experimento, sin dependencias externas más allá de
pandas/numpy del entorno.

Uso: .venv/bin/python scripts/generar_reporte_f9.py [experiment_id]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from postrelease.stuff_v2 import DERIVED, Z_FEATURES
F9 = ROOT / 'artifacts' / 'modeling' / (sys.argv[1] if len(sys.argv) > 1 else 'f9-stuff-v2') / 'F9'
OUT = ROOT / 'docs' / 'reporte_f9'

MODEL_COLOR = {'B0': '#64748b', 'B1': '#2563eb', 'Stuff': '#94a3b8', 'StuffV2': '#c2410c'}
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


# ----------------------- log loss por modelo y partición 2025
def chart_metricas(metrics):
    v_min, v_max = 1.40, 1.56
    left, right, top, bottom = 200, 660, 110, 440
    row_h = (bottom - top) / 9

    def X(v):
        return left + (v - v_min) / (v_max - v_min) * (right - left)

    body = text(30, 34, 'Log loss por partición 2025 · cohorte común F0',
                20, weight='bold')
    body += text(30, 56, 'Menor es mejor · B1 ve el conteo (balls/strikes); '
                         'Stuff y StuffV2 solo ven físicas', 12, '#475569')
    for tick in (1.40, 1.45, 1.50, 1.55):
        body += (f'<path d="M {X(tick):.1f} {top} V {bottom}" stroke="#e2e8f0"/>\n')
        body += text(X(tick), bottom + 18, f'{tick:.2f}', 11, '#475569', 'middle')
    i = 0
    for part in PART_ORDER:
        rows = [r for r in metrics['metrics'] if r['partition'] == part]
        body += text(30, top + i * row_h + 14, PART_LABEL[part], 13, weight='bold')
        for r in rows:
            v = r['multiclass_log_loss']
            y = top + i * row_h
            body += text(left - 8, y + 11, r['model'], 11, MODEL_COLOR[r['model']],
                         'end', 'bold')
            body += (f'<rect x="{left}" y="{y}" width="{X(v) - left:.1f}" '
                     f'height="14" fill="{MODEL_COLOR[r["model"]]}"/>\n')
            body += text(X(v) + 5, y + 11, f'{v:.4f}', 9, '#475569')
            i += 1
    ny = bottom + 42
    body += text(30, ny,
                 esc('StuffV2 (1.5154) es indistinguible del Stuff original '
                     '(1.5152) y queda muy por encima de B1 (1.4635) en las '
                     'tres particiones.'), 11, '#475569')
    body += text(30, ny + 18,
                 esc('La ventaja de B1 es estructural: conoce el conteo. Ninguna '
                     'derivada física cierra esa brecha.'), 11, '#475569')
    (OUT / 'metricas_particiones.svg').write_text(svg(760, ny + 45, body))


# ----------------------- comparaciones pareadas en phase_review
def chart_comparaciones(comparisons):
    x_min, x_max = -0.06, 0.06
    left, right, top, row_h = 230, 640, 115, 62

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Comparaciones pareadas en phase_review · Δ log loss '
                        '(StuffV2 − referencia)', 20, weight='bold')
    body += text(30, 56, 'Bootstrap pareado por partido, 500 remuestreos · '
                         'misma regla de promoción que F2 (≥1% e IC95% < 0)',
                12, '#475569')
    for tick in (-0.04, -0.02, 0.0, 0.02, 0.04):
        body += (f'<path d="M {X(tick):.1f} {top - 12} V {top + 3 * row_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 20, f'{tick:+.2f}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 12} V {top + 3 * row_h}" '
             f'stroke="#94a3b8" stroke-width="2"/>\n')
    labels = {'StuffV2_vs_B0': 'StuffV2 − B0', 'StuffV2_vs_B1': 'StuffV2 − B1',
              'StuffV2_vs_Stuff': 'StuffV2 − Stuff (F2)'}
    colors = {'StuffV2_vs_B0': '#64748b', 'StuffV2_vs_B1': '#2563eb',
              'StuffV2_vs_Stuff': '#94a3b8'}
    for i, (key, label) in enumerate(labels.items()):
        r = comparisons[key]
        cy = top + i * row_h + 22
        lo, hi, d = r['ci_low'], r['ci_high'], r['delta_candidate_minus_reference']
        body += text(left - 14, cy + 4, label, 13, '#0f172a', 'end', 'bold')
        body += (f'<path d="M {X(lo):.1f} {cy} H {X(hi):.1f}" stroke="{colors[key]}" '
                 f'stroke-width="3" stroke-opacity="0.55"/>\n')
        for xv in (X(lo), X(hi)):
            body += (f'<path d="M {xv:.1f} {cy - 7} V {cy + 7}" stroke="{colors[key]}" '
                     f'stroke-width="2"/>\n')
        body += f'<circle cx="{X(d):.1f}" cy="{cy}" r="6" fill="{colors[key]}"/>\n'
        body += text(max(X(hi) + 10, right + 8), cy + 4, f'{d:+.4f}', 11, '#334155')
    ny = top + 3 * row_h + 30
    body += text(30, ny,
                 esc('StuffV2 sí supera a B0 (−1.0% relativo, IC bajo cero) pero es '
                     'significativamente peor que B1 (+0.052): decisión '
                     'retain_reference.'), 11, '#475569')
    body += text(30, ny + 18,
                 esc('Contra el Stuff original el delta es +0.0002 con IC que '
                     'incluye cero: las 10 derivadas no agregaron señal.'),
                 11, '#475569')
    (OUT / 'comparaciones_f9.svg').write_text(svg(800, ny + 42, body))


# ----------------------- importancia por permutación (matriz derivada)
def chart_importancia(importance):
    rows = importance[:14]
    v_max = max(r['mean_log_loss_increase'] for r in rows) * 1.15
    left, width_px, top, row_h = 210, 420, 105, 34

    def X(v):
        return left + v / v_max * width_px

    body = text(30, 34, 'Importancia por permutación sobre la matriz derivada · '
                        'development 2025', 20, weight='bold')
    body += text(30, 56, 'Aumento medio de log loss al permutar cada feature ya '
                         'transformada · 3 repeticiones', 12, '#475569')
    derived = set(DERIVED + Z_FEATURES)
    for i, r in enumerate(rows):
        y = top + i * row_h
        is_new = r['feature'] in derived
        color = '#c2410c' if is_new else '#64748b'
        body += text(left - 10, y + 14, r['feature'], 11, color, 'end',
                     'bold' if is_new else None)
        body += (f'<rect x="{left}" y="{y}" width="{max(X(r["mean_log_loss_increase"]) - left, 1):.1f}" '
                 f'height="18" fill="{color}"/>\n')
        body += text(X(r['mean_log_loss_increase']) + 6, y + 14,
                     f"+{r['mean_log_loss_increase']:.4f}", 10, '#475569')
    ny = top + len(rows) * row_h + 24
    body += text(30, ny,
                 esc('Naranja = features nuevas de F9. z_rel_speed es la única '
                     'derivada con señal clara; la señal total sigue dominada '
                     'por el tipo de pitch.'), 11, '#475569')
    (OUT / 'importancia_permutacion.svg').write_text(svg(720, ny + 25, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((F9 / 'metrics.json').read_text())
    importance = json.loads((F9 / 'permutation_importance.json').read_text())
    chart_metricas(metrics)
    chart_comparaciones(metrics['comparisons'])
    chart_importancia(importance)
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
