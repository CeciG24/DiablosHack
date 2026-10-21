import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../core/api/api.service';
import { PITCH_TYPE_FROM_API, PITCH_TYPE_TO_API } from '../../core/api/api-mappers';
import { DataService } from '../../core/data-access/data.service';
import { ALTITUDE_CATEGORIES, ALTITUDE_LABELS, PITCH_TYPE_NAMES, PITCH_TYPES, PitchScore } from '../../core/models/domain.types';
import { Candidate, CandidateRow, EvaluationSnapshot, PhysicalKey, ProfilerReference, ReferenceSeason } from '../../core/models/profiler.types';
import { metric } from '../../core/models/pitch-analysis';
import { MovementChartComponent, PITCH_COLORS } from '../../shared/ui/movement-chart.component';
import { IMPORT_FIELDS, ImportKey, ImportOptions, ImportTable, autoMapping, importCandidate, readImport, templateCsv } from './profiler-import';
import { PHYSICAL_FIELDS, emptyCandidate, emptyRow, fromBundle, issues, payloadFor, rowWeight, shapeGroups, toMapPitch } from './profiler-model';

interface SavedCase {
  version: 1; id: string; savedAt: string; candidate: Candidate; original: Candidate;
  target: CandidateRow['category']; referenceYears: ReferenceSeason; decision: string; notes: string;
  evaluation: EvaluationSnapshot | null;
}
const STORAGE_KEY = 'mictlan.profiler.cases.v1';
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));

@Component({
  selector: 'app-perfilador-page',
  imports: [FormsModule, MovementChartComponent],
  templateUrl: './perfilador.page.html',
  styleUrl: './perfilador.page.scss',
})
export class PerfiladorPage {
  readonly data = inject(DataService);
  private readonly api = inject(ApiService);
  private readonly destroy = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  readonly names = PITCH_TYPE_NAMES;
  readonly types = PITCH_TYPES;
  readonly categories = ALTITUDE_CATEGORIES;
  readonly labels = ALTITUDE_LABELS;
  readonly fields = PHYSICAL_FIELDS;
  readonly colors = PITCH_COLORS;
  readonly metric = metric;
  readonly candidate = signal<Candidate>(emptyCandidate());
  readonly original = signal<Candidate>(copy(this.candidate()));
  readonly hand = computed(() => this.candidate().hand);
  readonly selectedKey = signal(this.candidate().rows[0].key);
  readonly selected = computed<CandidateRow | undefined>(() => this.candidate().rows.find((r) => r.key === this.selectedKey()) ?? this.candidate().rows[0]);
  readonly target = signal<CandidateRow['category']>('Extreme');
  readonly referenceYears = signal<ReferenceSeason>('2025-2026');
  readonly reference = signal<ProfilerReference | null>(null);
  readonly referenceStatus = signal<'loading' | 'ready' | 'error'>('loading');
  readonly showReference = signal(true);
  readonly referenceAttempt = signal(0);
  readonly problems = computed(() => issues(this.candidate()));
  readonly usageTotal = computed(() => this.candidate().rows.reduce((n, r) => n+(r.usage ?? 0), 0));
  readonly shapes = computed(() => shapeGroups(this.candidate()));
  readonly busy = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly snapshot = signal<EvaluationSnapshot | null>(null);
  readonly fingerprint = computed(() => JSON.stringify([this.candidate(), this.target()]));
  readonly stale = computed(() => this.snapshot() !== null && this.snapshot()!.fingerprint !== this.fingerprint());
  readonly fresh = computed(() => !!this.snapshot() && !this.stale());
  readonly pins = signal<EvaluationSnapshot[]>([]);
  readonly picker = signal('');
  readonly pickerSeason = signal<'2025' | '2026' | 'both'>('both');
  readonly decision = signal('Mantener en observación');
  readonly notes = signal('');
  readonly saved = signal<SavedCase[]>([]);
  readonly importFields = IMPORT_FIELDS;
  readonly importTable = signal<ImportTable | null>(null);
  readonly mapping = signal<Record<ImportKey, string>>(autoMapping([]));
  readonly importOptions = signal<ImportOptions>({ mode: 'pitches', hand: 'Right', category: 'No Altitude', speed: 'mph', movement: 'in', release: 'ft' });
  private sequence = 0;
  private active = true;
  private autoLoaded = false;

  constructor() {
    this.destroy.onDestroy(() => { this.active = false; this.sequence++; });
    effect((cleanup) => {
      const hand = this.hand(), years = this.referenceYears();
      this.referenceAttempt();
      let active = true;
      cleanup(() => { active = false; });
      this.reference.set(null);
      this.referenceStatus.set('loading');
      void this.api.profilerReference(years, hand).then((ref) => {
        if (!active) return;
        this.reference.set(ref); this.referenceStatus.set('ready');
      }).catch(() => { if (active) this.referenceStatus.set('error'); });
    });
    effect(() => {
      const id = this.route.snapshot.queryParamMap.get('pitcher');
      const bundle = id ? this.data.bundleOf(id) : null;
      if (bundle && this.data.source() === 'api' && !this.autoLoaded) {
        this.autoLoaded = true; this.picker.set(id!); this.setCandidate(fromBundle(bundle, 'both'));
      }
    });
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
      if (Array.isArray(saved)) this.saved.set(saved.filter((item) => this.validCase(item)));
    } catch { this.message.set('No se pudo leer el archivo local de fichas. Puedes seguir trabajando y exportar JSON.'); }
  }

  readonly relations = computed(() => this.shapes().map((row) => {
    const base = this.shapes().find((r) => r.type === 'FB' && r.category === row.category) ??
      this.shapes().find((r) => r.type === 'SI' && r.category === row.category);
    const difference = (key: PhysicalKey) => row[key] !== null && base?.[key] != null ? row[key]!-base[key]! : null;
    const dz = difference('releaseHeightFt'), dx = difference('releaseSideFt');
    return { ...row, base: base?.type, deltaVelo: difference('veloMph'), deltaIvb: difference('ivbIn'), deltaHb: difference('hbIn'),
      releaseDistance: dz !== null && dx !== null ? Math.hypot(dz, dx) : null };
  }));
  readonly referencePitches = computed<PitchScore[]>(() => !this.showReference() ? [] : (this.reference()?.points ?? []).flatMap((p, i) => {
    const type = PITCH_TYPE_FROM_API[p.auto_pitch_type];
    if (!type) return [];
    return [{ id: `ref-${i}`, pitcherId: 'reference', pitchType: type, season: p.year,
      category: 'No Altitude' as const, veloMph: p.velo, spinRpm: 0, hbIn: p.hb, ivbIn: p.ivb,
      plateXIn: 0, plateZIn: 0, stuffPlus: null, locationPlus: null, pitchingPlus: null }];
  }));
  readonly mapPitches = computed<PitchScore[]>(() => [...this.referencePitches(), ...this.shapes().flatMap((r) => {
    const point = toMapPitch(r);
    if (!point) return [];
    if (this.fresh()) {
      const rows = this.candidate().rows.filter((row) => row.type === r.type && row.category === r.category);
      const scores = rows.flatMap((row) => {
        const result = this.snapshot()!.result.records.find((p) => p.key === row.key);
        return result?.source_score != null ? [{ score: result.source_score, weight: rowWeight(this.candidate(), row) }] : [];
      });
      const weight = scores.reduce((n, p) => n+p.weight, 0);
      point.stuffPlus = weight ? scores.reduce((n, p) => n+p.score*p.weight, 0)/weight : null;
    }
    return [{ ...point, pitcherId: 'candidate' }];
  })]);
  readonly mapHighlight = computed(() => {
    const row = this.selected();
    return this.mapPitches().findIndex((p) => p.pitcherId === 'candidate' && p.pitchType === row?.type && p.category === row?.category);
  });
  readonly connections = computed(() => this.mapPitches().flatMap((point, i, points) => {
    if (point.pitcherId !== 'candidate') return [];
    const base = points.findIndex((p) => p.pitcherId === 'candidate' && p.pitchType === 'FB' && p.category === point.category);
    return base >= 0 && base !== i ? [{ from: base, to: i }] : [];
  }));
  readonly projections = computed(() => !this.fresh() ? [] : this.mapPitches().flatMap((point, index) => {
    if (point.pitcherId !== 'candidate') return [];
    const rows = this.candidate().rows.filter((r) => r.type === point.pitchType && r.category === point.category && rowWeight(this.candidate(), r) > 0);
    const results = rows.map((r) => this.snapshot()!.result.records.find((p) => p.key === r.key));
    if (!rows.length || results.some((r) => r?.target_hb == null || r?.target_ivb == null)) return [];
    const total = rows.reduce((n, r) => n+rowWeight(this.candidate(), r), 0);
    return [{ index, hbIn: results.reduce((n, r, i) => n+r!.target_hb!*rowWeight(this.candidate(), rows[i]), 0)/total,
      ivbIn: results.reduce((n, r, i) => n+r!.target_ivb!*rowWeight(this.candidate(), rows[i]), 0)/total }];
  }));
  readonly physicalComparison = computed(() => {
    const row = this.shapes().find((r) => r.type === this.selected()?.type && r.category === this.selected()?.category);
    const ref = this.reference()?.groups.find((r) => r.auto_pitch_type === PITCH_TYPE_TO_API[this.selected()?.type ?? 'FB']);
    const apiKeys: Record<string, string> = { veloMph: 'rel_speed', spinRpm: 'spin_rate', hbIn: 'horz_break', ivbIn: 'induced_vert_break', extensionFt: 'extension' };
    return this.fields.filter((f) => f.key in apiKeys).map((f) => ({
      ...f, value: row?.[f.key] ?? null, reference: ref?.quantiles[apiKeys[f.key]], n: ref?.n ?? 0,
    }));
  });
  readonly scoreDistribution = computed(() => {
    const s = this.snapshot();
    if (!s || s.result.representative) return null;
    const scores = s.result.records.map((r) => r.source_score).filter((n): n is number => n !== null && Number.isFinite(n)).sort((a, b) => a-b);
    if (!scores.length) return null;
    const q = (fraction: number) => {
      const position = (scores.length-1)*fraction, low = Math.floor(position), high = Math.ceil(position);
      return scores[low]+(scores[high]-scores[low])*(position-low);
    };
    return { n: scores.length, p10: q(.1), median: q(.5), p90: q(.9) };
  });

  setCandidate(candidate: Candidate): void {
    this.sequence++; this.busy.set(false);
    this.candidate.set(copy(candidate)); this.original.set(copy(candidate));
    this.selectedKey.set(candidate.rows[0]?.key ?? ''); this.snapshot.set(null);
    this.error.set(''); this.message.set(''); this.notes.set(''); this.decision.set('Mantener en observación');
  }
  newCandidate(): void { this.setCandidate(emptyCandidate()); }
  retryReference(): void { this.referenceAttempt.update((n) => n+1); }
  setHeader<K extends 'name' | 'hand'>(key: K, value: Candidate[K]): void {
    this.candidate.update((c) => ({ ...c, [key]: value }));
  }
  updateRow(key: string, field: keyof CandidateRow, value: unknown): void {
    const numeric = ['usage', 'n', ...this.fields.map((f) => f.key)].includes(field);
    this.candidate.update((c) => ({ ...c, rows: c.rows.map((r) =>
      r.key === key ? { ...r, [field]: numeric ? typeof value === 'number' ? value : null : value } as CandidateRow : r) }));
  }
  addRow(): void {
    const row = { ...emptyRow(), usage: this.candidate().rows.length ? 0 : 100 };
    this.candidate.update((c) => ({ ...c, rows: [...c.rows, row] })); this.selectedKey.set(row.key);
  }
  removeRow(key: string): void {
    this.candidate.update((c) => ({ ...c, rows: c.rows.filter((r) => r.key !== key) }));
  }
  normalizeUsage(): void {
    const rows = this.candidate().rows;
    if (!rows.length || rows.some((r) => r.n === null || !Number.isInteger(r.n) || r.n < 1)) { this.error.set('Completa n en todas las filas para distribuir el uso por cantidad.'); return; }
    const total = rows.reduce((n, r) => n+r.n!, 0);
    this.candidate.update((c) => ({ ...c, rows: rows.map((r) => ({ ...r, usage: r.n!/total*100 })) }));
  }
  createScenario(): void {
    this.candidate.update((c) => ({ ...c, mode: 'profiles', rows: this.shapes().map((r) => ({ ...r, key: crypto.randomUUID() })),
      provenance: 'Escenario de perfiles promedio; no conserva la variabilidad de los lanzamientos originales' }));
  }
  restoreOriginal(): void { this.candidate.set(copy(this.original())); this.message.set('Se restauró la entrada original. Vuelve a evaluar si cambió el escenario.'); }
  captureOriginal(): void { this.original.set(copy(this.candidate())); this.message.set('Se conservó esta captura como entrada original para restaurarla después.'); }
  loadPitcher(): void {
    const bundle = this.data.bundleOf(this.picker());
    if (!bundle || this.data.source() !== 'api') return;
    const candidate = fromBundle(bundle, this.pickerSeason());
    if (!candidate.rows.length) { this.error.set('Este lanzador no tiene pitches cargados en la temporada seleccionada.'); return; }
    this.setCandidate(candidate);
  }
  selectMap(key: string): void {
    const point = this.mapPitches().find((p) => p.id === key && p.pitcherId === 'candidate');
    const shape = this.shapes().find((r) => r.key === key);
    const row = this.candidate().rows.find((r) => r.type === (point?.pitchType ?? shape?.type) && r.category === (point?.category ?? shape?.category));
    if (row) this.selectedKey.set(row.key);
  }
  async evaluate(): Promise<void> {
    if (this.problems().length || this.busy()) return;
    const candidate = copy(this.candidate()), target = this.target(), fingerprint = this.fingerprint();
    const referenceYears = this.referenceYears(), seq = ++this.sequence;
    this.busy.set(true); this.error.set(''); this.message.set('');
    try {
      const result = await this.api.evaluateCandidate(payloadFor(candidate, target));
      if (!this.active || seq !== this.sequence) return;
      if (fingerprint !== this.fingerprint()) { this.message.set('El arsenal cambió durante el cálculo. Evalúa los ajustes actuales.'); return; }
      this.snapshot.set({ candidate, target, fingerprint, result, referenceYears, evaluatedAt: new Date().toISOString() });
    } catch { if (this.active && seq === this.sequence) this.error.set('No se pudo evaluar el arsenal. Revisa el backend y vuelve a intentar; no se fabrican scores.'); }
    finally { if (this.active && seq === this.sequence) this.busy.set(false); }
  }

  async readFile(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement, file = input.files?.[0];
    if (!file) return;
    this.error.set('');
    try {
      if (file.size > 2_000_000) throw new Error('El límite de importación es 2 MB.');
      const text = await file.text();
      if (text.trim().startsWith('{')) {
        const data: unknown = JSON.parse(text);
        if (this.validCase(data)) { this.loadCase(data); this.importTable.set(null); return; }
      }
      const table = readImport(text);
      table.sourceName = file.name;
      this.importTable.set(table); this.mapping.set(autoMapping(table.headers));
      this.importOptions.update((o) => ({ ...o, mode: table.mode ?? o.mode, hand: this.hand() }));
    } catch (error) { this.error.set(error instanceof Error ? error.message : 'No se pudo leer el archivo.'); }
    finally { input.value = ''; }
  }
  mapField(key: ImportKey, column: string): void { this.mapping.update((m) => ({ ...m, [key]: column })); }
  setImportOption<K extends keyof ImportOptions>(key: K, value: ImportOptions[K]): void {
    this.importOptions.update((o) => ({ ...o, [key]: value }));
  }
  applyImport(): void {
    const table = this.importTable();
    if (!table) return;
    try {
      const used = Object.values(this.mapping()).filter(Boolean);
      if (new Set(used).size !== used.length) throw new Error('Cada columna solo puede mapearse a un atributo.');
      this.setCandidate(importCandidate(table, this.mapping(), this.importOptions()));
      this.importTable.set(null);
      this.message.set('Archivo importado. Revisa el arsenal y los datos faltantes antes de evaluar.');
    } catch (error) { this.error.set(error instanceof Error ? error.message : 'No se pudo importar.'); }
  }
  downloadTemplate(): void {
    this.download(templateCsv(this.importOptions().mode), 'ejemplo-sintetico-perfilador.csv', 'text/csv');
  }
  private download(text: string, name: string, type: string): void {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = document.createElement('a');
    link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  pin(): void {
    if (!this.fresh() || !this.snapshot()) return;
    if (this.pins().length >= 2) { this.message.set('Retira una de las dos fichas fijadas para comparar otra.'); return; }
    this.pins.update((pins) => [...pins, copy(this.snapshot()!)]);
  }
  unpin(index: number): void { this.pins.update((pins) => pins.filter((_, i) => i !== index)); }
  private caseFile(): SavedCase {
    return { version: 1, id: crypto.randomUUID(), savedAt: new Date().toISOString(),
      candidate: copy(this.candidate()), original: copy(this.original()), target: this.target(),
      referenceYears: this.referenceYears(), decision: this.decision(), notes: this.notes(),
      evaluation: this.fresh() ? copy(this.snapshot()) : null };
  }
  saveCase(): void {
    try {
      if (this.saved().length >= 8) throw new Error('El archivo local tiene 8 fichas. Exporta esta evaluación como JSON.');
      const next = [...this.saved(), this.caseFile()];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      this.saved.set(next); this.message.set('Ficha guardada en este navegador. No se envió a un servidor.');
    } catch (error) { this.error.set(error instanceof Error ? error.message : 'No se pudo guardar; exporta la ficha como JSON.'); }
  }
  exportCase(): void { this.download(JSON.stringify(this.caseFile(), null, 2), 'mictlan-ficha-candidato.json', 'application/json'); }
  loadCase(file: SavedCase): void {
    this.setCandidate(file.candidate); this.original.set(copy(file.original));
    this.target.set(file.target); this.referenceYears.set(file.referenceYears);
    this.notes.set(file.notes); this.decision.set(file.decision);
    this.message.set('Ficha restaurada. Recalcula para obtener una evaluación vigente; no se reutilizan scores guardados.');
  }
  private validCase(value: unknown): value is SavedCase {
    if (!value || typeof value !== 'object') return false;
    const file = value as SavedCase;
    const validCandidate = (c: Candidate) => c && typeof c.name === 'string' && ['Right', 'Left'].includes(c.hand) &&
      ['pitches', 'profiles'].includes(c.mode) && Array.isArray(c.rows) && c.rows.length <= 1000 &&
      c.rows.every((r) => r && typeof r.key === 'string' && this.types.includes(r.type) && this.categories.includes(r.category) &&
        this.fields.every((f) => r[f.key] === null || typeof r[f.key] === 'number' && Number.isFinite(r[f.key])));
    return file.version === 1 && typeof file.id === 'string' && validCandidate(file.candidate) && validCandidate(file.original) &&
      this.categories.includes(file.target) && ['2025', '2026', '2025-2026'].includes(file.referenceYears) &&
      typeof file.notes === 'string' && typeof file.decision === 'string';
  }
}
