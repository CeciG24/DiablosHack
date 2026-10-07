"""Check the modeling specification without loading pitch rows or training models."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    cfg = json.loads((ROOT / 'config/modeling_contract.json').read_text(encoding='utf-8'))
    document = (ROOT / cfg['document']).read_text(encoding='utf-8')
    current = (ROOT / 'data/CURRENT').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r'[0-9a-f]{16}', current), 'Invalid data pointer'
    assert current == cfg['expected_data_run'], 'Data version changed; review the modeling contract'
    run = ROOT / 'data/runs' / current
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'validated'
    data_cfg = json.loads((ROOT / cfg['data_contract']).read_text(encoding='utf-8'))
    protocol = cfg['protocol_A']
    assert [protocol['fit_year'], protocol['development_year'], protocol['final_test_year']] == [data_cfg['train_year'], data_cfg['validation_year'], data_cfg['test_year']]
    ranges = [protocol[k] for k in ['development_bucket', 'calibration_bucket', 'phase_review_bucket']]
    assert [n for lo, hi in ranges for n in range(lo, hi+1)] == list(range(10000))
    seen = set()
    for phase in cfg['phases']:
        assert phase['id'] not in seen
        assert set(phase['depends_on']).issubset(seen), 'Invalid phase dependency order'
        assert re.search(r'^### ' + phase['id'] + r' ', document, re.M)
        seen.add(phase['id'])
    assert seen == {'F'+str(i) for i in range(9)}
    assert len(cfg['event_class_order']) == len(set(cfg['event_class_order'])) == 6
    assert set(cfg['score']['default_weights']) == set(cfg['event_class_order'])
    assert cfg['score']['represents_expected_runs'] is False
    assert protocol['final_test_year'] not in cfg['protocol_B']['development_years_only']
    assert max(cfg['protocol_C']['reference_years_fixed']) < protocol['development_year']
    assert cfg['protocol_C']['existing_2026_arsenal_features_allowed'] is False
    assert (run / 'feature_sets.json').exists()
    print('PASS: contrato y configuracion coherentes; 9 fases; datos '+current)
    print('No se cargaron etiquetas, no se entrenaron modelos y no se evaluo 2026.')


if __name__ == '__main__':
    main()
