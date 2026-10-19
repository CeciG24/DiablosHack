import { Component, input, output } from '@angular/core';
import { ALTITUDE_CATEGORIES, ALTITUDE_LABELS, PITCH_TYPES, PITCH_TYPE_NAMES, Pitcher } from '../../core/models/domain.types';
import { DEFAULT_FILTERS, PitchFilters } from '../../core/models/pitch-analysis';

@Component({
  selector: 'app-pitch-filters',
  template: `
    <div class="filters" role="group" aria-label="Filtros de lanzamientos">
      @if (showPitcher()) {
        <label>Lanzador
          <select [value]="value().pitcherId" (change)="change('pitcherId', $event)">
            <option value="ALL">Todos</option>
            @for (p of pitchers(); track p.id) { <option [value]="p.id">{{ p.label }}</option> }
          </select>
        </label>
      }
      <label>Temporada
        <select [value]="value().season" (change)="change('season', $event)">
          <option value="ALL">Todas</option>
          @for (year of seasons(); track year) { <option [value]="year">{{ year }}</option> }
        </select>
      </label>
      <label>Altitud
        <select [value]="value().category" (change)="change('category', $event)">
          <option value="ALL">Todas</option>
          @for (c of categories; track c) { <option [value]="c">{{ labels[c] }}</option> }
        </select>
      </label>
      <label>Tipo de pitcheo
        <select [value]="value().pitchType" (change)="change('pitchType', $event)">
          <option value="ALL">Todos</option>
          @for (t of types; track t) { <option [value]="t">{{ names[t] }}</option> }
        </select>
      </label>
      <button type="button" class="button button--quiet" (click)="changed.emit(defaults)">Limpiar filtros</button>
    </div>
  `,
})
export class PitchFiltersComponent {
  readonly pitchers = input<readonly Pitcher[]>([]);
  readonly seasons = input<readonly number[]>([]);
  readonly value = input<PitchFilters>(DEFAULT_FILTERS);
  readonly showPitcher = input(true);
  readonly changed = output<PitchFilters>();
  protected readonly defaults = DEFAULT_FILTERS;
  protected readonly categories = ALTITUDE_CATEGORIES;
  protected readonly labels = ALTITUDE_LABELS;
  protected readonly types = PITCH_TYPES;
  protected readonly names = PITCH_TYPE_NAMES;

  change(key: keyof PitchFilters, event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.changed.emit({
      ...this.value(),
      [key]: key === 'season' && value !== 'ALL' ? Number(value) : value,
    });
  }
}
