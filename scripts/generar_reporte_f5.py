#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F5 (arsenal con historia real,
protocolo C) a partir de los artefactos verificados, sin dependencias
externas."""
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'modeling'
OUT = ROOT / 'docs' / 'reporte_f5'
F5 = ART / 'f5-full-check' / 'F5'

MODELS = ['fallback', 'control', 'arsenal']
MODEL_COLOR = {'fallback': '#64748b', 'control': '#2563eb', 'arsenal': '#ea580c',
               'full_base': '#94a3b8', 'candidate_policy': '#ea580c',
               'control_policy': '#2563eb', 'selected_policy': '#16a34a'}
MODEL_LABEL = {'full_base': 'full_base (referencia descriptiva)',
               'control_policy': 'control_policy',
               'candidate_policy': 'candidate_policy',
               'selected_policy': 'selected_policy (= control)'}
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


# --------------------------------- cobertura de historia fija 2024 por partición
def chart_cobertura():
    rows = {r['partition']: r for r in
            csv.DictReader((F5 / 'coverage_partition.csv').open())}
    y_max = 150000
    top, bottom, left = 105, 470, 90
    group_w, bar_w = 170, 80

    def Y(v):
        return bottom - v / y_max * (bottom - top)

    body = text(30, 34, 'Cobertura de la referencia 2024 por partición · 2025',
                20, weight='bold')
    body += text(30, 56, 'Con referencia = pitcher con al menos 30 fastballs completos en 2024 '
                         '(Four-Seam o Sinker) · el resto va por la rama fallback', 12, '#475569')
    body += f'<rect x="480" y="20" width="14" height="14" fill="#0d9488"/>\n'
    body += text(499, 32, 'con referencia 2024', 12, '#0f172a')
    body += f'<rect x="480" y="42" width="14" height="14" fill="#cbd5e1"/>\n'
    body += text(499, 54, 'historia insuficiente → fallback', 12, '#475569')
    for tick in (0, 25000, 50000, 75000, 100000, 125000, 150000):
        body += f'<path d="M {left} {Y(tick):.1f} H {left + 3 * group_w}" stroke="#e2e8f0"/>\n'
        body += text(left - 8, Y(tick) + 4, f'{tick // 1000}k', 11, '#475569', 'end')
    for gi, p in enumerate(PART_ORDER):
        r = rows[p]
        total = int(r['n_pitches'])
        with_ref = int(r['n_with_reference'])
        cov = float(r['coverage'])
        x = left + gi * group_w + (group_w - bar_w) / 2
        body += (f'<rect x="{x}" y="{Y(with_ref):.1f}" width="{bar_w}" '
                 f'height="{bottom - Y(with_ref):.1f}" fill="#0d9488"/>\n')
        body += (f'<rect x="{x}" y="{Y(total):.1f}" width="{bar_w}" '
                 f'height="{Y(with_ref) - Y(total):.1f}" fill="#cbd5e1"/>\n')
        body += text(x + bar_w / 2, Y(total) - 8, f'{total:,}'.replace(',', ' '), 10,
                     '#334155', 'middle')
        body += text(x + bar_w / 2, Y(with_ref) + 18, f'{with_ref / 1000:.1f}k', 11,
                     'white', 'middle', 'bold')
        body += text(x + bar_w / 2, bottom + 18, PART_LABEL[p], 12, '#0f172a',
                     'middle', 'bold')
        body += text(x + bar_w / 2, bottom + 36, f'{cov * 100:.2f}% con referencia',
                     10, '#475569', 'middle')
    body += f'<path d="M {left} {bottom} H {left + 3 * group_w}" stroke="#94a3b8"/>\n'
    body += text(left, bottom + 62,
                 'Casi la mitad de los pitches de 2025 no tiene historia utilizable: '
                 'es la limitación principal', 11, '#475569')
    body += text(left, bottom + 80,
                 esc('de cualquier lectura del experimento. Las particiones se asignan por '
                     'hash de juego, no por cronología.'), 11, '#475569')
    (OUT / 'cobertura_historia.svg').write_text(svg(720, bottom + 100, body))


# --------------------------------- comparaciones bootstrap pareadas
def chart_bootstrap(metrics):
    x_min, x_max = -0.0040, 0.0005
    left, right, top, row_h = 300, 640, 130, 90

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    comps = [
        ('Arsenal vs control · rama con historia',
         f"{metrics['paired_arsenal']['n_pitches']:,} pitches · "
         f"{metrics['paired_arsenal']['n_games']} juegos".replace(',', ' '),
         metrics['paired_arsenal']),
        ('Políticas completas (candidata vs control) · incluye fallback',
         f"{metrics['full_policy_comparison']['n_pitches']:,} pitches · "
         f"{metrics['full_policy_comparison']['n_games']} juegos".replace(',', ' '),
         metrics['full_policy_comparison']),
    ]
    body = text(30, 34, 'Aporte del arsenal · bootstrap pareado por juego', 20,
                weight='bold')
    body += text(30, 56, 'Δ log loss (candidato − control) con IC 95% · 500 remuestreos '
                         'ponderados por pitch · negativo favorece al arsenal', 12, '#475569')
    for tick in (-0.004, -0.003, -0.002, -0.001, 0.0):
        body += (f'<path d="M {X(tick):.1f} {top - 20} V {top + len(comps) * row_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 28, f'{tick:.3f}', 11, '#475569', 'middle')
    body += (f'<path d="M {X(0):.1f} {top - 20} V {top + len(comps) * row_h}" '
             f'stroke="#94a3b8" stroke-width="2"/>\n')
    y = top
    for title, sub, c in comps:
        rel = c['relative_log_loss_reduction'] * 100
        body += text(30, y + 8, title, 13, weight='bold')
        body += text(30, y + 26, sub + f' · reducción relativa {rel:+.3f}%', 11, '#475569')
        cy = y + 44
        color = '#ea580c'
        body += (f'<path d="M {X(c["ci_low"]):.1f} {cy} H {X(c["ci_high"]):.1f}" '
                 f'stroke="{color}" stroke-width="3"/>\n')
        for cx in (c['ci_low'], c['ci_high']):
            body += (f'<path d="M {X(cx):.1f} {cy - 9} V {cy + 9}" stroke="{color}" '
                     f'stroke-width="3"/>\n')
        body += (f'<circle cx="{X(c["delta_candidate_minus_reference"]):.1f}" cy="{cy}" '
                 f'r="6" fill="{color}"/>\n')
        body += text(X(c['ci_high']) + 12, cy - 2,
                     f'Δ = {c["delta_candidate_minus_reference"]:+.5f}', 11)
        body += text(X(c['ci_high']) + 12, cy + 15, f'decisión: {c["decision"]}', 10,
                     '#d97706', weight='bold')
        y += row_h
    note_y = top + len(comps) * row_h + 30
    body += text(30, note_y,
                 esc('El IC queda completo bajo cero (mejora con evidencia) pero la reducción '
                     'relativa es ~0.17%:'), 11, '#475569')
    body += text(30, note_y + 18,
                 esc('la regla de promoción exige ≥1% → inconclusive → retain_reference. '
                     'La rama con historia conserva el control.'), 11, '#475569')
    (OUT / 'comparaciones_bootstrap.svg').write_text(svg(860, note_y + 45, body))


# --------------------------------- log loss de las políticas en revisión
def chart_logloss(metrics):
    review = {m['model']: m for m in metrics['metrics'] if m['partition'] == 'phase_review'}
    order = ['full_base', 'control_policy', 'candidate_policy', 'selected_policy']
    x_min, x_max = 1.025, 1.035
    left, right, top, row_h = 260, 660, 120, 46

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Log loss multiclase en phase review · políticas F5', 20,
                weight='bold')
    body += text(30, 56, 'full_base se ajustó con más pitches: comparación descriptiva, '
                         'no aísla el aporte del arsenal', 12, '#475569')
    for tick in (1.025, 1.030, 1.035):
        body += (f'<path d="M {X(tick):.1f} {top - 14} V {top + len(order) * row_h}" '
                 f'stroke="#e2e8f0"/>\n')
        body += text(X(tick), top - 22, f'{tick:.3f}', 11, '#475569', 'middle')
    y = top
    for m in order:
        ll = review[m]['multiclass_log_loss']
        color = MODEL_COLOR[m]
        body += text(left - 12, y + 20, MODEL_LABEL[m], 12, '#0f172a', 'end')
        body += (f'<rect x="{X(x_min)}" y="{y + 6}" width="{X(ll) - X(x_min):.1f}" '
                 f'height="22" fill="{color}" rx="3"/>\n')
        body += text(X(ll) + 8, y + 22, f'{ll:.5f}', 11, '#0f172a')
        y += row_h
    body += text(left, top + len(order) * row_h + 24,
                 esc('selected_policy = control_policy: se conserva el control en la rama '
                     'con historia y fallback sin historia.'), 11, '#475569')
    (OUT / 'logloss_politicas.svg').write_text(svg(860, top + len(order) * row_h + 50, body))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((F5 / 'metrics.json').read_text())
    chart_cobertura()
    chart_bootstrap(metrics)
    chart_logloss(metrics)
    for m in MODELS:
        shutil.copy2(F5 / m / 'calibration_phase_review.svg',
                     OUT / f'calibracion_{m}.svg')
    print(f'OK -> {OUT}')


if __name__ == '__main__':
    main()
