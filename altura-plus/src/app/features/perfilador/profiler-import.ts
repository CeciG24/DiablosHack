import { ALTITUDE_FROM_API, PITCH_TYPE_FROM_API } from '../../core/api/api-mappers';
import { ALTITUDE_CATEGORIES, ALTITUDE_LABELS, PITCH_TYPE_NAMES, PITCH_TYPES } from '../../core/models/domain.types';
import { Candidate, CandidateMode, CandidateRow, Hand, PhysicalKey } from '../../core/models/profiler.types';

export type ImportKey = PhysicalKey | 'type' | 'category' | 'usage' | 'n' | 'hand' | 'year';
export const IMPORT_FIELDS: { key: ImportKey; label: string; aliases: string[] }[] = [
  { key: 'type', label: 'Tipo de pitch', aliases: ['auto_pitch_type', 'AutoPitchType', 'pitch_type'] },
  { key: 'veloMph', label: 'Velocidad', aliases: ['rel_speed', 'RelSpeed', 'velocity'] },
  { key: 'spinRpm', label: 'Spin', aliases: ['spin_rate', 'SpinRate', 'spin'] },
  { key: 'ivbIn', label: 'IVB', aliases: ['induced_vert_break', 'InducedVertBreak', 'ivb'] },
  { key: 'hbIn', label: 'HB', aliases: ['horz_break', 'HorzBreak', 'hb'] },
  { key: 'extensionFt', label: 'Extensión', aliases: ['extension', 'Extension'] },
  { key: 'releaseHeightFt', label: 'Altura de liberación', aliases: ['rel_height', 'RelHeight'] },
  { key: 'releaseSideFt', label: 'Liberación lateral', aliases: ['rel_side', 'RelSide'] },
  { key: 'axisDeg', label: 'Eje (grados)', aliases: ['spin_axis', 'SpinAxis', 'axis'] },
  { key: 'category', label: 'Categoría origen', aliases: ['altitude_category', 'altitude'] },
  { key: 'usage', label: 'Uso (%)', aliases: ['usage_pct', 'usagePct', 'usage_percent'] },
  { key: 'n', label: 'Cantidad observada', aliases: ['count', 'pitches', 'sample_n'] },
  { key: 'hand', label: 'Mano', aliases: ['pitcher_throws', 'throws'] },
  { key: 'year', label: 'Temporada', aliases: ['season', 'Year'] },
];
export interface ImportTable { headers: string[]; records: Record<string, unknown>[]; name?: string; mode?: CandidateMode; sourceName?: string }
export interface ImportOptions {
  mode: CandidateMode; hand: Hand; category: CandidateRow['category'];
  speed: 'mph' | 'kmh'; movement: 'in' | 'cm'; release: 'ft' | 'm';
}
const normalize = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');

/** RFC-style quoted fields, including delimiters and newlines inside quotes. */
function cells(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i+1] === '"') { cell += '"'; i++; } else quoted = !quoted;
    } else if (!quoted && c === delimiter) { row.push(cell.trim()); cell = ''; }
    else if (!quoted && (c === '\n' || c === '\r')) {
      if (c === '\r' && text[i+1] === '\n') i++;
      row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = '';
    } else cell += c;
  }
  if (quoted) throw new Error('Hay comillas sin cerrar en el archivo.');
  row.push(cell.trim()); if (row.some(Boolean)) rows.push(row);
  return rows;
}
export function readImport(text: string): ImportTable {
  text = text.replace(/^\uFEFF/, '').trim();
  if (!text) throw new Error('El archivo está vacío.');
  let records: Record<string, unknown>[], name: string | undefined, mode: CandidateMode | undefined;
  if (text.startsWith('[') || text.startsWith('{')) {
    const data = JSON.parse(text);
    const list = Array.isArray(data) ? data : data.rows ?? data.records;
    if (!Array.isArray(list) || list.some((r) => !r || typeof r !== 'object' || Array.isArray(r))) throw new Error('JSON: usa un arreglo de objetos o un objeto con rows/records.');
    records = list;
    if (!Array.isArray(data)) {
      name = typeof data.name === 'string' ? data.name.slice(0, 100) : undefined;
      mode = data.mode === 'pitches' || data.mode === 'profiles' ? data.mode : undefined;
    }
  } else {
    const first = text.split(/\r?\n/)[0];
    const delimiter = first.includes('\t') ? '\t' : first.split(';').length > first.split(',').length ? ';' : ',';
    const [headers, ...values] = cells(text, delimiter);
    if (!headers || new Set(headers).size !== headers.length || headers.some((h) => !h)) throw new Error('Los encabezados deben ser únicos y no estar vacíos.');
    records = values.map((row, i) => {
      if (row.length !== headers.length) throw new Error(`Fila ${i+2}: número de columnas distinto al encabezado.`);
      return Object.fromEntries(headers.map((h, j) => [h, row[j]]));
    });
  }
  if (!records.length || records.length > 1000) throw new Error('Importa entre 1 y 1000 registros por candidato.');
  return { headers: [...new Set(records.flatMap((r) => Object.keys(r)))], records, name, mode };
}
export function autoMapping(headers: string[]): Record<ImportKey, string> {
  return Object.fromEntries(IMPORT_FIELDS.map((f) => [f.key,
    headers.find((h) => [f.key, ...f.aliases].some((alias) => normalize(h) === normalize(alias))) ?? ''])) as Record<ImportKey, string>;
}
function number(value: unknown, field: string, row: number): number | null {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value === 'boolean' || !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(String(value).trim()) || !Number.isFinite(Number(value))) throw new Error(`Fila ${row}: ${field} debe ser numérico; usa punto decimal.`);
  return Number(value);
}
export function importCandidate(table: ImportTable, mapping: Record<ImportKey, string>, options: ImportOptions): Candidate {
  const rows = table.records.map((record, i) => {
    const get = (key: ImportKey) => mapping[key] ? record[mapping[key]] : undefined;
    const typeValue = String(get('type') ?? '');
    const apiType = Object.keys(PITCH_TYPE_FROM_API).find((t) => normalize(t) === normalize(typeValue));
    const type = apiType ? PITCH_TYPE_FROM_API[apiType] : PITCH_TYPES.find((t) =>
      normalize(t) === normalize(typeValue) || normalize(PITCH_TYPE_NAMES[t]) === normalize(typeValue));
    if (!type) throw new Error(`Fila ${i+1}: tipo de pitch no reconocido (${typeValue}). Usa FB, SI, CT, SL, CB, CH, SP o SW.`);
    const handValue = get('hand');
    const hand = !handValue ? options.hand : ['right', 'r', 'derecho', 'derecha'].includes(normalize(String(handValue))) ? 'Right' :
      ['left', 'l', 'zurdo', 'zurda'].includes(normalize(String(handValue))) ? 'Left' : null;
    if (hand !== options.hand) throw new Error(`Fila ${i+1}: la mano no coincide con la seleccionada. Separa los candidatos por mano.`);
    const catValue = get('category');
    const category = !catValue ? options.category : ALTITUDE_FROM_API[String(catValue)] ??
      ALTITUDE_CATEGORIES.find((c) => normalize(c) === normalize(String(catValue)) || normalize(ALTITUDE_LABELS[c]) === normalize(String(catValue)));
    if (!category) throw new Error(`Fila ${i+1}: categoría de altitud no reconocida.`);
    const physical = Object.fromEntries(IMPORT_FIELDS.filter((f) =>
      !['type', 'category', 'usage', 'n', 'hand', 'year'].includes(f.key)).map((f) => [f.key, number(get(f.key), f.label, i+1)]));
    const factor = (key: string, f: number) => { if (physical[key] !== null) physical[key] = physical[key]!*f; };
    if (options.speed === 'kmh') factor('veloMph', 1/1.609344);
    if (options.movement === 'cm') { factor('ivbIn', 1/2.54); factor('hbIn', 1/2.54); }
    if (options.release === 'm') ['extensionFt', 'releaseHeightFt', 'releaseSideFt'].forEach((key) => factor(key, 1/.3048));
    const year = number(get('year'), 'Temporada', i+1);
    if (year !== null && (!Number.isInteger(year) || year < 1900 || year > 2026)) throw new Error(`Fila ${i+1}: temporada inválida.`);
    return { ...physical, key: crypto.randomUUID(), type, category,
      usage: options.mode === 'pitches' ? null : number(get('usage'), 'Uso', i+1),
      n: options.mode === 'pitches' ? 1 : number(get('n'), 'Cantidad', i+1),
      ...(year !== null ? { year } : {}) } as CandidateRow;
  });
  return { name: table.name ?? 'Candidato importado', hand: options.hand, mode: options.mode,
    rows, provenance: normalize(table.sourceName ?? '').includes('ejemplosintetico')
      ? 'Plantilla sintética; no es evidencia de un candidato real'
      : 'Archivo local importado; datos declarados por el evaluador' };
}

export function templateCsv(mode: CandidateMode): string {
  const header = 'auto_pitch_type,pitcher_throws,altitude_category,rel_speed,spin_rate,induced_vert_break,horz_break,extension,rel_height,rel_side,spin_axis,usage,n,year';
  const rows = mode === 'profiles'
    ? ['Four-Seam,Right,No Altitude,93,2350,15,8,6.2,6,1.8,150,60,100,2025', 'Slider,Right,No Altitude,84,2500,2,-5,6.1,5.9,1.8,80,40,80,2025']
    : ['Four-Seam,Right,No Altitude,93,2350,15,8,6.2,6,1.8,150,,,2025', 'Slider,Right,No Altitude,84,2500,2,-5,6.1,5.9,1.8,80,,,2026'];
  return [header, ...rows].join('\n');
}
