import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard.page').then((m) => m.DashboardPage),
  },
  {
    path: 'lanzamientos',
    loadComponent: () =>
      import('./features/lanzamientos/lanzamientos.page').then((m) => m.LanzamientosPage),
  },
  {
    path: 'lanzadores',
    loadComponent: () =>
      import('./features/lanzadores/lanzadores.page').then((m) => m.LanzadoresPage),
  },
  {
    path: 'simulador',
    loadComponent: () =>
      import('./features/simulador/simulador.page').then((m) => m.SimuladorPage),
  },
  { path: 'home', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'pitcher', redirectTo: 'lanzadores', pathMatch: 'full' },
  { path: 'comparador', redirectTo: 'lanzadores', pathMatch: 'full' },
  { path: 'scouting', redirectTo: 'simulador', pathMatch: 'full' },
  { path: 'metodo', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: '**', redirectTo: 'dashboard' },
];
