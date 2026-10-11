"""Explicit development-only pitcher holdout; never relabel seasons to fit a model."""
from modeling.datasets import game_bucket, require_unique


def assign_pitcher_partitions(frame, seed):
    require_unique(frame)
    if frame.empty or not frame.year.isin([2024, 2025]).all():
        raise PermissionError('Protocol B is restricted to 2024/2025')
    if frame[['pitcher_anon_id', 'game_anon_id', 'pitcher_split']].isna().any().any():
        raise ValueError('Protocol B requires pitcher and game identities')
    if (not frame.pitcher_split.isin(['train', 'validation', 'test']).all()
            or frame.groupby('pitcher_anon_id').pitcher_split.nunique().gt(1).any()):
        raise ValueError('Invalid or inconsistent pitcher groups')
    result = frame.copy()
    result['partition'] = result.pitcher_split.map({'train': 'train', 'test': 'phase_review', 'validation': 'development'})
    buckets = {game: game_bucket(game, seed) for game in result.game_anon_id.unique()}
    result.loc[result.pitcher_split.eq('validation') & result.game_anon_id.map(buckets).ge(5000), 'partition'] = 'calibration'
    return result.sort_values('pitch_uid').reset_index(drop=True)


def validate_fit_partition(frame, partition, protocol):
    require_unique(frame)
    if frame.empty or not frame.partition.eq(partition).all():
        raise PermissionError(f'Requires nonempty {partition} partition')
    if protocol == 'A':
        if not frame.year.eq(2024 if partition == 'train' else 2025).all():
            raise PermissionError('Protocol A requires train 2024 / development 2025')
    elif protocol == 'B':
        expected = 'train' if partition == 'train' else 'validation'
        if not frame.year.isin([2024, 2025]).all() or not frame.pitcher_split.eq(expected).all():
            raise PermissionError('Protocol B requires authorized years and pitcher groups')
        if frame.pitcher_anon_id.isna().any():
            raise ValueError('Missing pitcher identity')
    else:
        raise ValueError('Unknown protocol')
