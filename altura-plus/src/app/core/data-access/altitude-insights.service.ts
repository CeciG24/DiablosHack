import { Injectable, effect, inject, signal } from '@angular/core';
import { ApiProfile, ApiService } from '../api/api.service';
import { DataService } from './data.service';

@Injectable({ providedIn: 'root' })
export class AltitudeInsightsService {
  private readonly api = inject(ApiService);
  private readonly data = inject(DataService);
  readonly profile = signal<ApiProfile | null>(null);
  readonly status = signal<'idle' | 'loading' | 'ready' | 'error'>('idle');
  private request = 0;

  constructor() {
    effect(() => {
      if (this.data.source() === 'api') void this.reload();
      else {
        this.request++;
        this.profile.set(null);
        this.status.set('idle');
      }
    });
  }

  async reload(): Promise<void> {
    const request = ++this.request;
    this.profile.set(null);
    this.status.set('loading');
    try {
      const profile = await this.api.profile();
      if (request !== this.request) return;
      this.profile.set(profile);
      this.status.set('ready');
    } catch {
      if (request !== this.request) return;
      this.status.set('error');
    }
  }
}
