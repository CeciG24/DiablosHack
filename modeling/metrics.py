"""Contract-defined multiclass metrics and paired cluster bootstrap."""
from html import escape
from pathlib import Path

from modeling.datasets import pd, join_pitches
import numpy as np


def validate_probabilities(probabilities, n_classes=6, atol=1e-6):
    p = np.asarray(probabilities, dtype=float)
    if p.ndim != 2 or p.shape[1] != n_classes or not np.isfinite(p).all():
        raise ValueError('Probability matrix has invalid shape or non-finite values')
    if (p < 0).any() or (p > 1).any() or not np.allclose(p.sum(axis=1), 1, atol=atol, rtol=0):
        raise ValueError('Probabilities must be in [0,1] and sum to one')
    return p


def per_pitch_losses(labels, probabilities, classes, epsilon=1e-12):
    p = validate_probabilities(probabilities, len(classes))
    indices = pd.Index(classes).get_indexer(labels)
    if len(indices) != len(p) or len(p) == 0 or (indices < 0).any():
        raise ValueError('Empty population or invalid/misaligned labels')
    if not 0 < epsilon < 1:
        raise ValueError('Invalid clipping epsilon')
    truth = np.eye(len(classes))[indices]
    return (-np.log(np.clip(p[np.arange(len(p)), indices], epsilon, 1)),
            np.square(p - truth).sum(axis=1))


def multiclass_metrics(labels, probabilities, classes, epsilon=1e-12):
    log_loss, brier = per_pitch_losses(labels, probabilities, classes, epsilon)
    return {'n_pitches': len(log_loss), 'multiclass_log_loss': float(log_loss.mean()),
            'multiclass_brier_sum_over_classes': float(brier.mean())}


def calibration_bins(labels, probabilities, classes, bins=10):
    p = validate_probabilities(probabilities, len(classes))
    labels = np.asarray(labels)
    if len(labels) != len(p) or not pd.Series(labels).isin(classes).all():
        raise ValueError('Invalid calibration labels')
    if bins != 10:
        raise ValueError('The contract requires 10 equal-width bins')
    rows = []
    for k, label in enumerate(classes):
        assigned = np.minimum((p[:, k] * bins).astype(int), bins - 1)
        for b in range(bins):
            selected = assigned == b
            count = int(selected.sum())
            positives = int((labels[selected] == label).sum())
            rows.append({'class': label, 'bin': b, 'lower': b / bins, 'upper': (b + 1) / bins,
                         'upper_inclusive': b == bins - 1, 'n': count, 'positives': positives,
                         'mean_probability': float(p[selected, k].mean()) if count else None,
                         'observed_frequency': positives / count if count else None})
    return rows


def paired_bootstrap(reference, candidate, repetitions, seed, confidence=0.95,
                     minimum_relative_improvement=0.01, smoke=False):
    """Resample whole games; divide sampled loss sums by sampled pitch counts."""
    if repetitions < 2 or not 0 < confidence < 1:
        raise ValueError('Invalid bootstrap settings')
    joined = join_pitches(reference, candidate)
    if joined.empty or len(joined) != len(reference) or len(joined) != len(candidate):
        raise ValueError('Paired comparisons require exactly the same nonempty pitches')
    for column in ('game_anon_id', 'y_event'):
        if joined[column + '_x'].isna().any() or not joined[column + '_x'].equals(joined[column + '_y']):
            raise ValueError('Paired game or target mismatch')
    if not np.isfinite(joined[['loss_x', 'loss_y']].to_numpy()).all():
        raise ValueError('Non-finite losses')
    joined['delta'] = joined.loss_y - joined.loss_x
    grouped = joined.groupby('game_anon_id_x', sort=True).delta.agg(['sum', 'size'])
    baseline = float(joined.loss_x.mean())
    delta = float(joined.delta.mean())
    relative = -delta / baseline if baseline > 0 else None
    result = {'n_pitches': len(joined), 'n_games': len(grouped), 'resamples': repetitions,
              'seed': seed, 'confidence': confidence, 'delta_candidate_minus_reference': delta,
              'relative_log_loss_reduction': relative, 'ci_low': None, 'ci_high': None,
              'decision': 'inconclusive', 'scientific_evidence': not smoke,
              'method': 'paired percentile bootstrap by game; pitch-weighted loss'}
    if len(grouped) < 2:
        result.update(scientific_evidence=False, reason='insufficient_games')
        return result
    rng = np.random.default_rng(seed)
    sums, counts = grouped['sum'].to_numpy(), grouped['size'].to_numpy()
    sampled = []
    for _ in range(repetitions):
        selected = rng.integers(0, len(grouped), size=len(grouped))
        sampled.append(float(sums[selected].sum() / counts[selected].sum()))
    tail = (1 - confidence) / 2
    low, high = np.quantile(sampled, [tail, 1 - tail])
    result.update(ci_low=float(low), ci_high=float(high))
    if not smoke and relative is not None and relative >= minimum_relative_improvement and high < 0:
        result['decision'] = 'promote'
    if smoke:
        result['reason'] = 'smoke_has_no_scientific_conclusion'
    return result


def write_calibration_svg(path, rows, partition, classes, colors=None, phase='F1'):
    """Standalone SVG: one panel per class, fixed [0,1] axes, counts in tooltips."""
    colors = colors or {'B0': '#475569', 'B1': '#2563eb', 'B2': '#c2410c'}
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="720" viewBox="0 0 1080 720">',
           '<rect width="1080" height="720" fill="white"/>',
           '<g font-family="Arial,sans-serif" fill="#0f172a">',
           f'<text x="30" y="30" font-size="20">Calibración {escape(phase)} · {escape(partition)}</text>',
           '<text x="30" y="54" font-size="12">X: probabilidad media · Y: frecuencia observada · 10 bins fijos · recuentos en CSV y tooltip</text>']
    for i, (model, color) in enumerate(colors.items()):
        out.append(f'<text x="{720 + i * 90}" y="30" fill="{color}">{model}</text>')
    for k, label in enumerate(classes):
        left, top, size = 55 + (k % 3) * 350, 110 + (k // 3) * 310, 220
        out.append(f'<text x="{left}" y="{top - 15}" font-size="16">{escape(label)}</text>')
        for t in (0, 0.5, 1):
            x, y = left + size * t, top + size * (1 - t)
            out.extend([f'<path d="M {x} {top} V {top+size} M {left} {y} H {left+size}" stroke="#e2e8f0" fill="none"/>',
                        f'<text x="{x}" y="{top+size+18}" font-size="11">{t:g}</text>',
                        f'<text x="{left-25}" y="{y+4}" font-size="11">{t:g}</text>'])
        out.append(f'<path d="M {left} {top+size} L {left+size} {top}" stroke="#94a3b8" stroke-dasharray="5 5"/>')
        for model, color in colors.items():
            points = [r for r in rows if r['model'] == model and r['partition'] == partition and r['class'] == label and r['n']]
            coords = [(left + size * r['mean_probability'], top + size * (1-r['observed_frequency'])) for r in points]
            poly = ' '.join(f'{x:.3f},{y:.3f}' for x, y in coords)
            out.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>')
            for (x, y), row in zip(coords, points):
                out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="4" fill="{color}"><title>{model}: n={row["n"]}; positivos={row["positives"]}; bin={row["bin"]}</title></circle>')
    out.append('<text x="30" y="705" font-size="12">Diagnóstico descriptivo; bins escasos no demuestran por sí solos mala calibración. 2026 sellado.</text></g></svg>')
    Path(path).write_text('\n'.join(out), encoding='utf-8')
