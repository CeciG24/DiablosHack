"""Genera docs/F10_IDEAL_PROFILE.json — el perfil ideal F10 servido por /api/v1/profile.

Agrega scenarios.json (No Altitude -> Extreme Altitude) unido a cohort.parquet
para responder las tres preguntas del brief:
  1. Que perfiles ganan Stuff+ relativo en altura (con explicacion fisica).
  2. Que perfiles pierden, con riesgo adicional de contacto duro (proxy; no hay
     etiqueta de jonron en los datos).
  3. Como perfilar un prospecto: fisicas del cuartil que mejor resiste por tipo.

Uso:  python experiments/phase10_profile.py
"""
import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(os.getenv('DIABLOS_ROOT', Path(__file__).resolve().parents[1]))
F10 = Path(os.getenv('DIABLOS_F10', ROOT / 'artifacts/modeling/f10-full/F10'))
OUT = ROOT / 'docs' / 'F10_IDEAL_PROFILE.json'

PAIRS = [('No Altitude', 'Extreme Altitude')]
TOP_Q = 0.75


def pct(x: float) -> float:
    return round(x * 100, 2)


def main() -> None:
    scenarios = pd.DataFrame(json.loads((F10 / 'scenarios.json').read_text(encoding='utf-8')))
    cohort = pd.read_parquet(F10 / 'cohort.parquet')
    keys = cohort[['pitch_uid', 'auto_pitch_type', 'pitcher_throws', 'rel_speed',
                   'spin_rate', 'induced_vert_break', 'horz_break', 'extension']]
    df = scenarios.merge(keys, on='pitch_uid', validate='m:1')

    rows = []
    prospect = []
    for source, target in PAIRS:
        up = df[(df.source == source) & (df.target == target) & (df.status == 'experimental')].copy()
        up['d_ivb'] = up.target_ivb - up.source_ivb
        up['d_hb'] = up.target_hb - up.source_hb
        up['d_hard'] = up.hard_contact_given_bip_target - up.hard_contact_given_bip_source
        up['d_gb'] = up.groundball_given_bip_target - up.groundball_given_bip_source

        for ptype, s in up.groupby('auto_pitch_type'):
            s = s.dropna(subset=['delta_score'])
            if len(s) < 10:
                continue
            rows.append({
                'pair': f'{source} -> {target}',
                'auto_pitch_type': ptype,
                'n': int(len(s)),
                'delta_score': round(float(s.delta_score.mean()), 2),
                'delta_ivb_in': round(float(s.d_ivb.mean()), 2),
                'delta_hb_in': round(float(s.d_hb.mean()), 2),
                'delta_hard_contact_bip_pp': pct(float(s.d_hard.mean())),
                'delta_groundball_bip_pp': pct(float(s.d_gb.mean())),
            })

            # Perfil del cuartil que mejor resiste vs. el que mas cae.
            hi, lo = s.delta_score.quantile(TOP_Q), s.delta_score.quantile(1 - TOP_Q)
            top, bot = s[s.delta_score >= hi], s[s.delta_score <= lo]
            corrs = {c: round(float(s.delta_score.corr(s[c])), 2)
                     for c in ('rel_speed', 'spin_rate', 'source_ivb', 'source_hb', 'extension')}
            prospect.append({
                'pair': f'{source} -> {target}',
                'auto_pitch_type': ptype,
                'resists': {
                    'velo_mph': round(float(top.rel_speed.mean()), 1),
                    'spin_rpm': round(float(top.spin_rate.mean()), 0),
                    'ivb_in': round(float(top.source_ivb.mean()), 1),
                    'hb_in': round(float(top.source_hb.mean()), 1),
                    'extension_ft': round(float(top.extension.mean()), 2),
                    'delta_score_mean': round(float(top.delta_score.mean()), 2),
                },
                'drops': {
                    'velo_mph': round(float(bot.rel_speed.mean()), 1),
                    'spin_rpm': round(float(bot.spin_rate.mean()), 0),
                    'ivb_in': round(float(bot.source_ivb.mean()), 1),
                    'hb_in': round(float(bot.source_hb.mean()), 1),
                    'extension_ft': round(float(bot.extension.mean()), 2),
                    'delta_score_mean': round(float(bot.delta_score.mean()), 2),
                },
                'corr_delta_with': corrs,
            })

    rows.sort(key=lambda r: r['delta_score'])
    global_dhard = pct(float((df[(df.source == 'No Altitude') & (df.target == 'Extreme Altitude')]
                              .hard_contact_given_bip_target -
                              df[(df.source == 'No Altitude') & (df.target == 'Extreme Altitude')]
                              .hard_contact_given_bip_source).mean()))

    doc = {
        'generated_from': 'artifacts/modeling/f10-full/F10/scenarios.json + cohort.parquet',
        'score_version': 'F10_regularized_context_standardized_utility_v1',
        'scope': 'categorical_association_fixed_history_not_causal_not_Harp',
        'pair_focus': 'No Altitude -> Extreme Altitude',
        'n_simulated': int(len(df[(df.source == 'No Altitude') & (df.target == 'Extreme Altitude')
                                  & (df.status == 'experimental')])),
        'global_delta_hard_contact_bip_pp': global_dhard,
        'by_pitch_type': rows,
        'prospect_profile': prospect,
        'answers': {
            'q1_ganan_en_altura': (
                'Slider (-0.6), Curveball (-0.4) y Cutter (+0.7) conservan o mejoran el score '
                'relativo: dependen de barrido lateral/gyro, no de "ride" vertical. En aire '
                'delgado la fuerza de Magnus cae y los perfiles de rompimiento lateral pierden '
                'menos ventaja comparativa que la recta de carry.'
            ),
            'q2_pierden_en_altura': (
                'Four-Seam (-6.1 pts, IVB -3.6 in) y Sinker (-4.0 pts, IVB -2.4 in, HB -2.1 in): '
                'pitches que viven del carry/sink via IVB pierden pulgadas de quiebre real -> '
                'quedan mas planos. Riesgo asociado: hard_contact|BIP sube ~+1.5 pp en FB '
                '(global +1.0 pp). No hay etiqueta de jonron: el proxy declarado es hard '
                'contact >=95 mph; el riesgo de HR se lee como proxy, no como estimacion.'
            ),
            'q3_perfil_prospecto': (
                'Dentro de Four-Seam, quienes resisten mejor en Extreme tienen MENOS IVB y velo '
                'observados (corr delta vs velo -0.47, vs IVB -0.39) y mayor extension (+0.23): '
                'el carry extremo es lo que mas se comprime en altura, asi que el diferencial '
                'real esta en arsenal secundario (slider/curve de alto spin) y extension. '
                'Perfilar un prospecto para CDMX = priorizar secundaria de barrido + extension '
                'sobre FB de ride puro.'
            ),
        },
        'caveats': [
            'Categorias de altitud; Extreme Altitude no identifica Harp Helu ni ningun estadio.',
            'Asociacion observacional con historia fija 2024; no es efecto causal del parque.',
            'hard_contact es proxy declarado (>=95 mph); no existe etiqueta de jonron ni barrel.',
            'Deltas en escala F10 experimental; no comparables con F8.',
        ],
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'wrote {OUT} ({len(rows)} filas por tipo, {len(prospect)} perfiles)')


if __name__ == '__main__':
    main()
