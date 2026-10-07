import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from modeling.datasets import (ROOT, FEATURES, FLAGS, LOCATION, PITCHING, STUFF,
                               ModelingDataset, assign_partitions, game_bucket,
                               ids_hash, join_pitches, pd, sample_games, select_family)

CONFIG = json.loads((ROOT / 'config/modeling_contract.json').read_text(encoding='utf-8'))


def fixture():
    rows = []
    for i in range(100):
        rows.append({'pitch_uid': f'id-{i:03}', 'year': 2024 if i < 20 else 2025,
                     'game_anon_id': f'game-{i // 2}', 'pitcher_anon_id': 'pitcher',
                     'pitcher_split': 'train', 'game_cv_fold': i % 5,
                     **{c: 1 for c in PITCHING},
                     **{c: True for c in sum(FLAGS.values(), [])}, 'y_event': 'ball'})
    return assign_partitions(pd.DataFrame(rows), CONFIG)


class InfrastructureTests(unittest.TestCase):
    def test_hash_formula_and_boundaries(self):
        import hashlib
        seed = CONFIG['protocol_A']['validation_hash_seed']
        self.assertEqual(game_bucket('game', seed), int(hashlib.sha256((seed + '|game').encode()).hexdigest()[:16], 16) % 10000)
        frame = fixture().iloc[20:26].copy()
        frame['game_anon_id'] = [f'g{i}' for i in range(6)]
        with patch('modeling.datasets.game_bucket', side_effect=[0, 4999, 5000, 7499, 7500, 9999]):
            result = assign_partitions(frame, CONFIG)
        self.assertEqual(result.partition.tolist(), ['development'] * 2 + ['calibration'] * 2 + ['phase_review'] * 2)

    def test_shuffle_partitions_and_sample(self):
        a = fixture()
        b = assign_partitions(a.sample(frac=1, random_state=8), CONFIG)
        pd.testing.assert_frame_equal(a, b)
        self.assertTrue(a.groupby('game_anon_id').partition.nunique().eq(1).all())
        x = sample_games(a, 31, CONFIG['seed'])
        y = sample_games(b.sample(frac=1, random_state=4), 31, CONFIG['seed'])
        pd.testing.assert_frame_equal(x, y)
        self.assertLessEqual(len(x), 31)
        self.assertTrue(x.groupby('game_anon_id').size().eq(2).all())
        self.assertEqual(ids_hash(x.pitch_uid.tolist()), ids_hash(y.pitch_uid.tolist()[::-1]))

    def test_duplicate_null_and_missing_game_rejected(self):
        frame = fixture()
        for column, value in [('pitch_uid', None), ('pitch_uid', frame.pitch_uid.iloc[1]), ('game_anon_id', None)]:
            bad = frame.copy(); bad.loc[0, column] = value
            with self.assertRaises(ValueError):
                assign_partitions(bad, CONFIG)

    def test_no_final_year_or_cross_season_game(self):
        bad = fixture(); bad.loc[0, 'year'] = 2026
        with self.assertRaises(PermissionError):
            assign_partitions(bad, CONFIG)
        bad = fixture(); bad.loc[0, 'year'] = 2025
        with self.assertRaises(ValueError):
            assign_partitions(bad, CONFIG)

    def test_join_uses_ids_not_dataframe_index(self):
        left = pd.DataFrame({'pitch_uid': ['a', 'b'], 'feature': [10, 20]})
        right = pd.DataFrame({'pitch_uid': ['b', 'a'], 'label': [0, 1]})
        self.assertEqual(join_pitches(left, right).label.tolist(), [1, 0])
        with self.assertRaises(ValueError):
            join_pitches(left, pd.concat([right, right]))

    def test_exact_features_and_exclusion_accounting(self):
        self.assertEqual(len(STUFF), 11)
        self.assertEqual(LOCATION, ['auto_pitch_type', 'pitcher_throws', 'plate_loc_height', 'plate_loc_side', 'balls', 'strikes', 'batter_side'])
        self.assertEqual(PITCHING, STUFF + LOCATION[2:])
        self.assertFalse(set(STUFF) & {'balls', 'strikes', 'batter_side', 'altitude_category', 'plate_loc_height', 'plate_loc_side'})
        frame = fixture()
        frame.loc[0, 'eligible_stuff_default'] = False
        frame.loc[1, 'y_event'] = None
        frame.loc[2, 'rel_speed'] = float('nan')
        selected, counts = select_family(frame, 'stuff', 'y_event')
        self.assertEqual(len(selected), 97)
        self.assertEqual([counts[k] for k in ['quality_filter', 'null_target_after_quality', 'missing_features_after_quality_and_target']], [1, 1, 1])
        self.assertEqual(sum(v for k, v in counts.items() if k != 'input_rows'), counts['input_rows'])

    def test_test_guard_precedes_any_io(self):
        dataset = ModelingDataset.__new__(ModelingDataset)
        for phase in ('F0', 'F8'):
            with self.assertRaises(PermissionError):
                dataset.load(partitions=['test'], phase=phase)

    def test_matrices_keep_context_separate(self):
        rows, _ = select_family(fixture(), 'stuff', 'y_event')
        cohort = {'aligned': {'stuff': rows}}
        X, y, meta = ModelingDataset.matrices(cohort, 'stuff')
        changed = rows.copy()
        changed['balls'] = 3
        changed['pitcher_anon_id'] = 'another-pitcher'
        changed['altitude_category'] = 'Extreme Altitude'
        other, _, _ = ModelingDataset.matrices({'aligned': {'stuff': changed}}, 'stuff')
        pd.testing.assert_frame_equal(X, other)
        self.assertEqual(X.columns.tolist(), STUFF)
        self.assertNotIn('pitch_uid', X)

    def test_conditional_null_targets_stay_excluded(self):
        frame = fixture()
        frame['y_hard_contact_bip'] = float('nan')
        frame.loc[0, 'y_hard_contact_bip'] = 0
        selected, counts = select_family(frame, 'stuff', 'y_hard_contact_bip')
        self.assertEqual(len(selected), 1)
        self.assertEqual(counts['null_target_after_quality'], 99)

    def test_changed_version_manifest_and_config_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = ModelingDataset.__new__(ModelingDataset)
            dataset.root = Path(directory)
            (dataset.root / 'data').mkdir()
            pointer = dataset.root / 'data/CURRENT'; pointer.write_text('version-a')
            dataset.run_id = 'version-a'
            dataset.manifest_path = dataset.root / 'manifest.json'; dataset.manifest_path.write_text('{}')
            dataset.config_path = dataset.root / 'config.json'; dataset.config_path.write_text('{}')
            from modeling.datasets import sha256_file
            dataset.manifest_hash = sha256_file(dataset.manifest_path)
            dataset.config_hash = sha256_file(dataset.config_path)
            dataset.assert_unchanged()
            for path in (pointer, dataset.manifest_path, dataset.config_path):
                original = path.read_text(); path.write_text('changed')
                with self.assertRaises(RuntimeError):
                    dataset.assert_unchanged()
                path.write_text(original)


if __name__ == '__main__':
    unittest.main()
