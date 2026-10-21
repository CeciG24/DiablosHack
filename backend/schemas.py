"""Public contracts; all measurements use the existing model's units."""
from typing import Annotated, Literal
from math import isclose
from pydantic import BaseModel, ConfigDict, Field, model_validator

Family = Literal['stuff', 'location', 'pitching']
Altitude = Literal['No Altitude', 'Medium Altitude', 'Extreme Altitude']
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]

EXAMPLE = dict(auto_pitch_type='Four-Seam', pitcher_throws='Right',
    rel_speed=93.0, spin_rate=2300.0, spin_axis_sin=0.5,
    spin_axis_cos=-0.8660254037844386, rel_height=6.0, rel_side=1.8,
    extension=6.2, induced_vert_break=16.0, horz_break=-8.0,
    plate_loc_height=2.5, plate_loc_side=0.0, balls=0, strikes=0,
    batter_side='Right', altitude_category='No Altitude', pitcher_anon_id='prospecto')


class Pitch(BaseModel):
    model_config = ConfigDict(extra='forbid', json_schema_extra={'example': EXAMPLE})
    request_id: str | None = Field(None, max_length=128)
    pitch_uid: str | None = Field(None, max_length=128)
    pitcher_anon_id: str | None = Field(None, max_length=128)
    auto_pitch_type: str = Field(min_length=1, max_length=80, pattern=r'\S')
    pitcher_throws: Literal['Right', 'Left']
    rel_speed: Number | None = Field(None, ge=30, le=110, description='Velocidad, mph')
    spin_rate: Number | None = Field(None, ge=0, le=5000, description='rpm')
    spin_axis_sin: Number | None = Field(None, ge=-1, le=1)
    spin_axis_cos: Number | None = Field(None, ge=-1, le=1)
    rel_height: Number | None = Field(None, ge=0, le=10, description='Pies')
    rel_side: Number | None = Field(None, ge=-8, le=8, description='Pies')
    extension: Number | None = Field(None, ge=0, le=10, description='Pies')
    induced_vert_break: Number | None = Field(None, ge=-40, le=40, description='IVB, pulgadas')
    horz_break: Number | None = Field(None, ge=-40, le=40, description='HB, pulgadas')
    plate_loc_height: Number | None = Field(None, description='Pies')
    plate_loc_side: Number | None = Field(None, description='Pies')
    balls: Annotated[int, Field(strict=True, ge=0, le=3)] | None = None
    strikes: Annotated[int, Field(strict=True, ge=0, le=2)] | None = None
    batter_side: Literal['Right', 'Left'] | None = None
    altitude_category: Altitude | None = None

    @model_validator(mode='after')
    def axis(self):
        if self.spin_axis_sin is not None and self.spin_axis_cos is not None:
            if not isclose(self.spin_axis_sin**2+self.spin_axis_cos**2, 1, abs_tol=0.02):
                raise ValueError('spin_axis_sin y spin_axis_cos deben representar el mismo ángulo')
        return self

    def record(self):
        return self.model_dump(exclude_none=True)


class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid', json_schema_extra={'example': {'records': [EXAMPLE]}})
    records: list[Pitch] = Field(min_length=1, max_length=200)


class PredictionRequest(Batch):
    family: Family | Literal['all'] = 'all'


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', json_schema_extra={'example': {'records': [EXAMPLE], 'target': 'Extreme Altitude'}})
    records: list[Pitch] = Field(min_length=1, max_length=50)
    target: Altitude = 'Extreme Altitude'

    @model_validator(mode='after')
    def physical_inputs(self):
        required = ('rel_speed', 'spin_rate', 'spin_axis_sin', 'spin_axis_cos',
                    'rel_height', 'rel_side', 'extension', 'induced_vert_break',
                    'horz_break', 'altitude_category')
        if any(getattr(p, f) is None for p in self.records for f in required):
            raise ValueError('La simulación requiere todas las variables físicas y altitude_category de origen')
        return self


class ApproximateRunValue(BaseModel):
    reference_label: str
    league: str
    season: int
    version: str
    weights_sha256: str
    status: Literal['ok', 'missing_or_invalid_count', 'event_prediction_unavailable', 'invalid_event_probabilities', 'unavailable']
    runs_per_pitch: float | None
    runs_per_100: float | None
    baseline_runs_per_pitch: float | None
    delta_vs_count_baseline: float | None
    lower_is_better_for_pitcher: bool = True
    experimental: bool = True
    in_play_policy: str
    baseline_route: str | None = None
    event_weights: dict[str, float] | None = None
    contributions: dict[str, float] | None = None


class Prediction(BaseModel):
    # Preserve the complete provenance and conditional head diagnostics from F8.
    model_config = ConfigDict(extra='allow')
    family: Family
    status: str
    score: float | None
    stuff_plus: float | None
    location_plus: float | None
    pitching_plus: float | None
    probabilities: dict[str, float | None]
    conditional_probabilities: dict[str, float | None]
    warnings: str
    score_version: str
    provisional: bool
    xrv: ApproximateRunValue | None = None


class PredictionResponse(BaseModel):
    release_id: str
    records: list[dict[Family, Prediction]]


class FinalPrediction(BaseModel):
    xrv: ApproximateRunValue | None = None
    pitch_uid: str | None = None
    status: Literal['experimental', 'invalid_input']
    score: float | None
    probabilities: dict[str, float] | None
    model_id: str
    score_version: str
    experimental: bool = True
    represents_runs: bool = False
    history_status: str | None
    history_n: int
    warnings: str
    context_mode: str
    auxiliary_targets_in_score: bool = False


class FinalScoreResponse(BaseModel):
    records: list[FinalPrediction]


class StuffComparison(BaseModel):
    status: Literal['experimental', 'unavailable'] = 'unavailable'
    source_score: float | None = None
    target_score: float | None = None
    delta_score: float | None = None
    release_id: str | None = None
    score_version: str | None = None
    warnings: str = ''
    interval: None = None
    interval_reason: str = 'individual_uncertainty_not_estimated'
    method: str = 'F8_stuff_on_F10_projected_movement'


class Simulation(BaseModel):
    model_config = ConfigDict(extra='allow')
    pitch_uid: str | None = None
    source: str
    target: Altitude
    status: str
    reason: str | None
    delta_score: float | None
    score_version: str
    scope: str
    interval: None = None
    source_score: float | None = None
    target_score: float | None = None
    stuff_comparison: StuffComparison | None = None


class SimulationResponse(BaseModel):
    experimental: bool = True
    records: list[Simulation]


class GroupScore(BaseModel):
    pitcher_anon_id: str | None
    auto_pitch_type: str | None = None
    requested: int
    scored: int
    coverage: float
    stuff_plus: float | None
    location_plus: float | None
    pitching_plus: float | None


class SummaryResponse(BaseModel):
    release_id: str
    scope: str = 'Medias de los lanzamientos enviados; no ranking de toda la liga'
    pitchers: list[GroupScore]
    arsenal: list[GroupScore]


class MovementPoint(BaseModel):
    pitch_uid: str | None
    auto_pitch_type: str
    pitcher_anon_id: str | None
    ivb: float | None
    hb: float | None
    pitching_plus: float | None
    status: str


class MovementResponse(BaseModel):
    units: str = 'inches'
    records: list[MovementPoint]


class RecommendationResponse(BaseModel):
    experimental: bool = True
    scope: str = 'Orden de candidatos enviados por score destino F10; no óptimo global ni recomendación causal'
    supported: int
    unsupported: int
    ranked_candidates: list[dict]
