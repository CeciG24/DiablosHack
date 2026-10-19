import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { DataService } from './core/data-access/data.service';
import { ScoutingContextService } from './core/state/scouting-context.service';

interface NavItem {
  path: string;
  label: string;
  shortLabel: string;
  icon: string;
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);

  readonly nav: NavItem[] = [
    { path: '/dashboard', label: 'Dashboard', shortLabel: 'Dashboard', icon: 'home' },
    { path: '/lanzamientos', label: 'Análisis de lanzamientos', shortLabel: 'Lanzamientos', icon: 'compare' },
    { path: '/lanzadores', label: 'Lanzadores y arsenales', shortLabel: 'Lanzadores', icon: 'pitcher' },
    { path: '/simulador', label: 'Simulador y recomendaciones', shortLabel: 'Simulador', icon: 'sliders' },
  ];

  selectPitcher(event: Event): void {
    this.ctx.selectPitcher((event.target as HTMLSelectElement).value);
  }
}
