"""Pinned, read-only development cohorts; the final test remains sealed."""
import hashlib
import json
from pathlib import Path

from diablos_data import ROOT, duckdb, pd

STUFF = ['auto_pitch_type', 'pitcher_throws', 'rel_speed', 'spin_rate',
         'spin_axis_sin', 'spin_axis_cos', 'rel_height', 'rel_side',
         'extension', 'induced_vert_break', 'horz_break']
LOCATION = ['auto_pitch_type', 'pitcher_throws', 'plate_loc_height',
            'plate_loc_side', 'balls', 'strikes', 'batter_side']
PITCHING = STUFF + LOCATION[2:]
FEATURES = {'stuff': STUFF, 'location': LOCATION, 'pitching': PITCHING}
FLAGS = {
    'stuff': ['eligible_stuff_default'],
    'location': ['eligible_event', 'eligible_location'],
    'pitching': ['eligible_pitching_default'],
}
META = ['pitch_uid', 'year', 'game_anon_id', 'pitcher_anon_id',
        'pitcher_split', 'game_cv_fold', 'partition']
PARTITIONS = ('train', 'development', 'calibration', 'phase_review')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ids_hash(values):
    """Order-independent, unambiguous encoding of a collection of IDs."""
    return hashlib.sha256(json.dumps(sorted(values), ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def require_unique(frame):
    if frame.pitch_uid.isna().any() or frame.pitch_uid.duplicated().any():
        raise ValueError('pitch_uid must be non-null and unique')


def join_pitches(left, right):
    require_unique(left)
    require_unique(right)
    return left.merge(right, on='pitch_uid', how='inner', validate='one_to_one')


def game_bucket(game_id, seed):
    return int(hashlib.sha256(f'{seed}|{game_id}'.encode()).hexdigest()[:16], 16) % 10000


def assign_partitions(frame, config):
    require_unique(frame)
    result = frame.copy()
    protocol = config['protocol_A']
    if result.game_anon_id.isna().any():
        raise ValueError('Missing game_anon_id prevents grouped partitioning')
    if not result.year.isin([protocol['fit_year'], protocol['development_year']]).all():
        raise PermissionError('Only 2024/2025 development data are authorized before F8')
    if result.groupby('game_anon_id').year.nunique().gt(1).any():
        raise ValueError('A game crosses seasons')
    groups = result.game_anon_id.unique()
    buckets = {g: game_bucket(g, protocol['validation_hash_seed']) for g in groups}
    result['partition'] = 'train'
    dev = result.year.eq(protocol['development_year'])
    b = result.game_anon_id.map(buckets)
    for name in PARTITIONS[1:]:
        lo, hi = protocol[name + '_bucket']
        result.loc[dev & b.between(lo, hi), 'partition'] = name
    return result.sort_values('pitch_uid').reset_index(drop=True)


def sample_games(frame, maximum, seed):
    """Keep whole games in hash order, stop before exceeding the pitch budget."""
    if maximum is None:
        return frame.sort_values('pitch_uid').reset_index(drop=True)
    if maximum <= 0:
        raise ValueError('maximum must be positive')
    sizes = frame.groupby('game_anon_id').size()
    ordered = sorted(sizes.index, key=lambda g: (
        hashlib.sha256(f'{seed}|{g}'.encode()).hexdigest(), g))
    selected, count = [], 0
    for game in ordered:
        if count + int(sizes[game]) > maximum:
            break
        selected.append(game)
        count += int(sizes[game])
    return frame.loc[frame.game_anon_id.isin(selected)].sort_values('pitch_uid').reset_index(drop=True)


def select_family(frame, family, target):
    columns = FEATURES[family]
    quality = frame[FLAGS[family]].fillna(False).all(axis=1)
    known_target = frame[target].notna()
    complete = frame[columns].notna().all(axis=1)
    keep = quality & known_target & complete
    # Sequential, disjoint reasons: counts add up to the denominator.
    excluded = {
        'input_rows': len(frame),
        'quality_filter': int((~quality).sum()),
        'null_target_after_quality': int((quality & ~known_target).sum()),
        'missing_features_after_quality_and_target': int((quality & known_target & ~complete).sum()),
        'eligible_rows': int(keep.sum()),
    }
    return frame.loc[keep, META + columns + [target]].reset_index(drop=True), excluded


class ModelingDataset:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.config_path = self.root / 'config/modeling_contract.json'
        self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        self.config_hash = sha256_file(self.config_path)
        self.run_id = self.config['expected_data_run']
        self.run = self.root / 'data/runs' / self.run_id
        self.manifest_path = self.run / 'manifest.json'
        self.manifest_hash = sha256_file(self.manifest_path)
        self.manifest = json.loads(self.manifest_path.read_text(encoding='utf-8'))
        if self.manifest['status'] != 'validated' or self.manifest['run_id'] != self.run_id:
            raise ValueError('Data run is not validated or identity does not match')
        self.assert_unchanged()
        for name in ('diablos.duckdb', 'feature_sets.json'):
            if sha256_file(self.run / name) != self.manifest['outputs'][name]['sha256']:
                raise ValueError(f'Data integrity failure: {name}')
        self.file_signatures = {name: self._signature(self.run / name)
                                for name in ('diablos.duckdb', 'feature_sets.json')}
        source_features = json.loads((self.run / 'feature_sets.json').read_text(encoding='utf-8'))
        if source_features['stuff'] != STUFF or source_features['location'] != LOCATION or source_features['pitching'] != PITCHING + ['altitude_category']:
            raise ValueError('Feature allowlists diverge from the data contract')
        protocol = self.config['protocol_A']
        data_config = json.loads((self.root / self.config['data_contract']).read_text(encoding='utf-8'))
        if [protocol[k] for k in ('fit_year', 'development_year', 'final_test_year')] != [data_config[k] for k in ('train_year', 'validation_year', 'test_year')]:
            raise ValueError('Modeling and data years diverge')
        ranges = [protocol[name + '_bucket'] for name in PARTITIONS[1:]]
        if ranges != [[0, 4999], [5000, 7499], [7500, 9999]]:
            raise ValueError('Partition ranges diverge from the system contract')

    @staticmethod
    def _signature(path):
        info = path.stat()
        return (info.st_size, info.st_mtime_ns)

    def assert_unchanged(self):
        current = (self.root / 'data/CURRENT').read_text(encoding='utf-8').strip()
        if current != self.run_id:
            raise RuntimeError('Data version changed; reconcile the contract before continuing')
        if sha256_file(self.manifest_path) != self.manifest_hash:
            raise RuntimeError('Pinned data manifest changed')
        if sha256_file(self.config_path) != self.config_hash:
            raise RuntimeError('Modeling configuration changed during the experiment')
        for name, signature in getattr(self, 'file_signatures', {}).items():
            if self._signature(self.run / name) != signature:
                raise RuntimeError(f'Pinned data file changed: {name}')

    def load(self, target='y_event', partitions=PARTITIONS, maximum=None, phase='F0'):
        if isinstance(partitions, str):
            partitions = (partitions,)
        if 'test' in partitions or '2026' in partitions:
            if phase != 'F8':
                raise PermissionError('Final test is sealed; F8 with a frozen release is required')
            raise PermissionError('F8 release authorization is not implemented in F0; test remains sealed')
        if not partitions or not set(partitions).issubset(PARTITIONS):
            raise ValueError('Unknown development partition')
        self.assert_unchanged()
        with duckdb.connect(str(self.run / 'diablos.duckdb'), read_only=True) as db:
            targets = {r[1] for r in db.execute("PRAGMA table_info('targets')").fetchall() if r[1].startswith('y_')}
            if target not in targets:
                raise ValueError(f'Unknown target: {target}')
            columns = list(dict.fromkeys(META[:-1] + PITCHING +
                                        sum(FLAGS.values(), []) + [target]))
            selected = ', '.join('"' + c + '"' for c in columns)
            # No target from 2026 is returned or used. No call to the unrestricted legacy loader.
            frame = db.execute(f'SELECT {selected} FROM model_base WHERE year IN (?, ?)',
                               [self.config['protocol_A']['fit_year'],
                                self.config['protocol_A']['development_year']]).df()
        self.assert_unchanged()
        assignments = assign_partitions(frame[META[:-1]], self.config)
        frame = join_pitches(frame, assignments[['pitch_uid', 'partition']])
        frame = frame.loc[frame.partition.isin(partitions)]
        assignments = assignments.loc[assignments.partition.isin(partitions)].reset_index(drop=True)
        sampled = sample_games(frame, maximum, self.config['seed'])
        families, exclusions = {}, {}
        for family in FEATURES:
            families[family], exclusions[family] = select_family(sampled, family, target)
            exclusions[family]['by_partition'] = {
                name: select_family(group, family, target)[1]
                for name, group in sampled.groupby('partition')}
        common = families['stuff'][['pitch_uid']]
        for family in ('location', 'pitching'):
            common = join_pitches(common, families[family][['pitch_uid']])
        common = common.sort_values('pitch_uid').reset_index(drop=True)
        for family in families:
            exclusions[family]['outside_common_cohort'] = len(families[family]) - len(common)
        aligned = {family: join_pitches(common, rows) for family, rows in families.items()}
        # Baseline context is aligned by ID and stays outside the physical matrix.
        context = join_pitches(common, sampled[['pitch_uid', 'balls', 'strikes']])
        self.assert_unchanged()
        return {'assignments': assignments, 'sampled_ids': sampled[['pitch_uid']],
                'families': families, 'aligned': aligned, 'context': context,
                'exclusions': exclusions, 'common_ids': common}

    @staticmethod
    def matrices(cohort, family, target='y_event', common=True):
        rows = cohort['aligned' if common else 'families'][family]
        return rows[FEATURES[family]].copy(), rows[target].copy(), rows[META].copy()
