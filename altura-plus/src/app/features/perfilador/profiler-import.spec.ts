import { autoMapping, importCandidate, ImportOptions, readImport, templateCsv } from './profiler-import';
import { issues, payloadFor, shapeGroups } from './profiler-model';

describe('Perfilador: importación y contrato físico', () => {
  const options: ImportOptions = { mode: 'profiles', hand: 'Right', category: 'No Altitude', speed: 'mph', movement: 'in', release: 'ft' };
  it('importa ambos modos sin inventar contexto, IDs ni historia de arsenal', () => {
    for (const mode of ['profiles', 'pitches'] as const) {
      const table = readImport(templateCsv(mode));
      const candidate = importCandidate(table, autoMapping(table.headers), { ...options, mode });
      expect(issues(candidate)).toEqual([]);
      const payload = payloadFor(candidate, 'Extreme');
      expect(payload.entries.length).toBe(2);
      expect(payload.entries[0].pitch['pitcher_anon_id']).toBeUndefined();
      expect(payload.entries[0].pitch['balls']).toBeUndefined();
      expect(payload.entries[0].weight).toBe(mode === 'profiles' ? 60 : 1);
      expect(payload.entries[0].observed_n).toBe(mode === 'profiles' ? 100 : 1);
    }
  });
  it('interpreta CSV citado, BOM y saltos dentro de una celda', () => {
    const table = readImport('\uFEFFauto_pitch_type,notes,rel_speed\n"Four-Seam","texto, con\nsalto",93');
    expect(table.records.length).toBe(1);
    expect(table.records[0]['notes']).toBe('texto, con\nsalto');
    expect(() => readImport('a,b\n"sin cerrar,2')).toThrowError(/comillas/);
    expect(() => readImport('a,a\n1,2')).toThrowError(/encabezados/);
  });
  it('convierte unidades declaradas y mantiene vacíos los atributos no mapeados', () => {
    const table = readImport('[{"pitch_type":"FB","velocity":160.9344,"ivb":25.4,"hb":-12.7,"extension":1.8288,"usage":100}]');
    const candidate = importCandidate(table, autoMapping(table.headers), { ...options, speed: 'kmh', movement: 'cm', release: 'm' });
    const row = candidate.rows[0];
    expect(row.veloMph).toBeCloseTo(100);
    expect(row.ivbIn).toBeCloseTo(10);
    expect(row.hbIn).toBeCloseTo(-5);
    expect(row.extensionFt).toBeCloseTo(6);
    expect(row.spinRpm).toBeNull();
    expect(issues(candidate).length).toBeGreaterThan(0);
    expect(() => payloadFor(candidate, 'Extreme')).toThrow();
  });
  it('rechaza manos mezcladas, números ambiguos y tipos desconocidos', () => {
    for (const record of [
      { auto_pitch_type: 'unknown' }, { auto_pitch_type: 'FB', pitcher_throws: 'Left' },
      { auto_pitch_type: 'FB', rel_speed: '2,300' }, { auto_pitch_type: 'FB', rel_speed: true },
    ]) {
      const table = readImport(JSON.stringify([record]));
      expect(() => importCandidate(table, autoMapping(table.headers), options)).toThrow();
    }
  });
  it('promedia el eje circularmente y separa tipos con distintos orígenes', () => {
    const table = readImport(templateCsv('profiles'));
    const candidate = importCandidate(table, autoMapping(table.headers), options);
    candidate.rows = [{ ...candidate.rows[0], key: 'a', axisDeg: 359, usage: 50 },
      { ...candidate.rows[0], key: 'b', axisDeg: 1, usage: 50 }];
    expect(shapeGroups(candidate)[0].axisDeg).toBeCloseTo(0, 6);
    candidate.rows[1].category = 'Extreme';
    expect(shapeGroups(candidate).length).toBe(2);
  });
  it('rechaza pesos incompletos y duplicados antes de consultar el modelo', () => {
    const table = readImport(templateCsv('profiles'));
    const candidate = importCandidate(table, autoMapping(table.headers), options);
    candidate.rows[0].usage = 30;
    expect(issues(candidate).join(' ')).toContain('100%');
    candidate.rows[1].key = candidate.rows[0].key;
    expect(issues(candidate).join(' ')).toContain('repetidas');
  });
});
