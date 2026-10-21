import { Component, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { DataService } from './core/data-access/data.service';
import { ScoutingContextService } from './core/state/scouting-context.service';

interface NavItem {
  path: string;
  label: string;
  shortLabel: string;
  icon: string;
}

/** Rutas que leen el lanzador global (ctx.pitcherId) y necesitan el selector. */
const PITCHER_CONTEXT_ROUTES = new Set(['/lanzadores']);

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);
  private readonly router = inject(Router);

  private readonly url = signal(this.router.url);
  protected readonly showPitcherSelector = computed(() =>
    PITCHER_CONTEXT_ROUTES.has(this.url().split('?')[0]));
  protected readonly independentRoute = computed(() => this.url().split('?')[0] === '/perfilador');

  constructor() {
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => this.url.set(e.urlAfterRedirects));
  }

  readonly nav: NavItem[] = [
    { path: '/dashboard', label: 'Dashboard', shortLabel: 'Dashboard', icon: 'home' },
    { path: '/lanzamientos', label: 'Análisis de lanzamientos', shortLabel: 'Lanzamientos', icon: 'compare' },
    { path: '/lanzadores', label: 'Lanzadores y arsenales', shortLabel: 'Lanzadores', icon: 'pitcher' },
    { path: '/simulador', label: 'Simulador y recomendaciones', shortLabel: 'Simulador', icon: 'sliders' },
    { path: '/perfilador', label: 'Perfilador de candidatos', shortLabel: 'Perfilador', icon: 'clipboard' },
  ];

  selectPitcher(event: Event): void {
    this.ctx.selectPitcher((event.target as HTMLSelectElement).value);
  }
}
