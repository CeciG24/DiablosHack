#!/usr/bin/env python3
"""Genera las gráficas SVG del reporte F10 (Stuff v3, features relativas) a partir de los
artefactos verificados del experimento.

Uso: .venv/bin/python scripts/generar_reporte_f10.py [experiment_id]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F10 = ROOT / 'artifacts' / 'modeling' / (sys.argv[1] if len(sys.argv) > 1 else 'f10-stuff-v3') / 'F10'
OUT = ROOT / 'docs' / 'reporte_f10'
COLORS = {'base': '#94a3b8', 'refA': '#c2410c', 'refB': '#2563eb'}
HEADS = {'whiff_given_swing': 'whiff | swing', 'groundball_bip': 'groundball | BIP', 'hard_contact_bip': 'hard contact | BIP'}


def svg(width, height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
            f'<rect width="{width}" height="{height}" fill="white"/>\n'
            f'<g font-family="Arial,sans-serif" fill="#0f172a">\n{body}</g>\n</svg>\n')


def text(x, y, s, size=12, fill='#0f172a', anchor='start', weight=None):
    w = f' font-weight="{weight}"' if weight else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"{w}>{s}</text>\n'


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def chart_heads(metrics):
    rows = {(r['head'], r['model']): r for r in metrics['metrics'] if r['task'] == 'head' and r['partition'] == 'phase_review'}
    left, right, top, group_h = 190, 640, 100, 100
    v_max = 5.0

    def X(v):
        return left + v / v_max * (right - left)

    body = text(30, 34, 'Mejora vs prevalencia por cabeza · phase_review 2025', 20, weight='bold')
    body += text(30, 56, 'Reducción relativa de log loss (%) · mayor es mejor · refB evaluado con referencia del año previo', 12, '#475569')
    for tick in range(0, 6):
        body += f'<path d="M {X(tick):.1f} {top - 10} V {top + 3 * group_h - 20}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 16, f'{tick}%', 11, '#475569', 'middle')
    for i, (head, label) in enumerate(HEADS.items()):
        base = rows[(head, 'prevalence')]['log_loss']
        y0 = top + i * group_h
        body += text(30, y0 + 28, label, 13, weight='bold')
        for j, variant in enumerate(('base', 'refA', 'refB')):
            r = rows[(head, variant)]
            rel = (1 - r['log_loss'] / base) * 100
            y = y0 + j * 22
            body += text(left - 8, y + 13, variant, 11, COLORS[variant], 'end', 'bold')
            body += f'<rect x="{left}" y="{y}" width="{max(X(rel) - left, 0):.1f}" height="16" fill="{COLORS[variant]}"/>\n'
            body += text(X(rel) + 6, y + 12, f'{rel:.2f}%  ·  AUC {r["auc"]:.3f}', 10, '#475569')
    ny = top + 3 * group_h + 6
    body += text(30, ny, esc('refA (misma temporada, transductiva) gana en las tres cabezas salvo hard contact; refB pierde cobertura (52%) '
                             'y su NaN no se aprende en entrenamiento.'), 11, '#475569')
    (OUT / 'cabezas_vs_prevalencia.svg').write_text(svg(800, ny + 28, body))


def chart_ablacion(metrics):
    comps = metrics['comparisons']
    keys = [('whiff_given_swing:refA_vs_base', 'whiff|swing · refA − base'),
            ('whiff_given_swing:refB_vs_base', 'whiff|swing · refB − base'),
            ('whiff_given_swing:refB_vs_base_with_reference_only', 'whiff|swing · refB − base (solo con referencia)'),
            ('groundball_bip:refB_vs_base', 'groundball · refB − base'),
            ('hard_contact_bip:refB_vs_base', 'hard contact · refB − base'),
            ('event:refA_vs_stuff_count', 'evento · refA − Stuff+conteo'),
            ('event:refB_vs_stuff_count', 'evento · refB − Stuff+conteo'),
            ('event:stuff_count_vs_B1', 'evento · Stuff+conteo − B1')]
    x_min, x_max = -0.02, 0.01
    left, right, top, row_h = 330, 680, 100, 40

    def X(v):
        return left + (v - x_min) / (x_max - x_min) * (right - left)

    body = text(30, 34, 'Ablación pareada · Δ log loss (candidato − referencia)', 20, weight='bold')
    body += text(30, 56, 'Bootstrap pareado por partido, 500 remuestreos, IC95% · menor que cero = mejora', 12, '#475569')
    for tick in (-0.015, -0.01, -0.005, 0, 0.005):
        body += f'<path d="M {X(tick):.1f} {top - 12} V {top + len(keys) * row_h}" stroke="#e2e8f0"/>\n'
        body += text(X(tick), top - 18, f'{tick:+.3f}', 10, '#475569', 'middle')
    body += f'<path d="M {X(0):.1f} {top - 12} V {top + len(keys) * row_h}" stroke="#94a3b8" stroke-width="2"/>\n'
    for i, (key, label) in enumerate(keys):
        r = comps[key]
        cy = top + i * row_h + 14
        good = r['ci_high'] < 0
        color = '#16a34a' if good else '#dc2626' if r['ci_low'] > 0 else '#64748b'
        body += text(left - 12, cy + 4, esc(label), 12, '#0f172a', 'end')
        body += f'<path d="M {X(r["ci_low"]):.1f} {cy} H {X(r["ci_high"]):.1f}" stroke="{color}" stroke-width="3" stroke-opacity="0.6"/>\n'
        body += f'<circle cx="{X(r["delta_candidate_minus_reference"]):.1f}" cy="{cy}" r="5" fill="{color}"/>\n'
        body += text(right + 14, cy + 4, f'{r["delta_candidate_minus_reference"]:+.4f}', 11, '#334155')
    ny = top + len(keys) * row_h + 24
    body += text(30, ny, 'Verde: IC bajo cero · rojo: IC sobre cero · gris: incluye cero.', 11, '#475569')
    (OUT / 'ablacion_pareada.svg').write_text(svg(800, ny + 24, body))


def chart_indice(metrics):
    scores = metrics['index_diagnostics']['scores']
    items = [('Stuff_S0', 'Stuff F2 · S0 (publicado)', '#94a3b8'), ('StuffV2_S0', 'StuffV2 F9 · S0', '#cbd5e1'),
             ('v3_raw', 'V3 · P(whiff|swing)', '#2563eb'), ('v3_index_within_type', 'V3 · índice por tipo', '#c2410c')]
    left, right, top, row_h = 230, 640, 110, 38

    def panel(y0, title, key, v_max, fmt):
        out = text(30, y0 - 16, title, 14, weight='bold')
        for i, (name, label, color) in enumerate(items):
            v = scores[name][key]
            y = y0 + i * row_h
            out += text(left - 8, y + 13, label, 11, '#0f172a', 'end')
            out += f'<rect x="{left}" y="{y}" width="{v / v_max * (right - left):.1f}" height="18" fill="{color}"/>\n'
            out += text(left + v / v_max * (right - left) + 6, y + 13, fmt(v), 10, '#475569')
        return out

    body = text(30, 34, 'Índice Stuff+: dependencia del tipo de pitch · phase_review 2025', 20, weight='bold')
    body += text(30, 56, 'Menos varianza explicada por el tipo = índice más informativo dentro de cada pitch type', 12, '#475569')
    body += panel(top, 'Varianza del score explicada solo por el tipo de pitch', 'type_variance_share', 0.7, lambda v: f'{v * 100:.1f}%')
    y2 = top + 4 * row_h + 50
    body += panel(y2, 'Correlación intra-tipo con whiff | swing', 'within_type_corr_with_whiff_given_swing', 0.16, lambda v: f'{v:.3f}')
    ny = y2 + 4 * row_h + 20
    body += text(30, ny, esc('La señal intra-tipo sube ~35-40% frente al S0 publicado y la dependencia del tipo desaparece en la versión por tipo.'),
                 11, '#475569')
    (OUT / 'indice_tipo.svg').write_text(svg(800, ny + 24, body))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    saved = json.loads((F10 / 'metrics.json').read_text(encoding='utf-8'))
    chart_heads(saved)
    chart_ablacion(saved)
    chart_indice(saved)
    print('Gráficas escritas en', OUT)
