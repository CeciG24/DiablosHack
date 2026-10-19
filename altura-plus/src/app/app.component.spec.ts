import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AppComponent } from './app.component';
import { signal } from '@angular/core';
import { DataService } from './core/data-access/data.service';

describe('AppComponent', () => {
  it('should create', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([]), {
        provide: DataService,
        useValue: {
          status: signal('ready'), source: signal('synthetic'), bundles: signal([]),
          errorMessage: signal(null), reload: jasmine.createSpy('reload'),
        },
      }],
    }).compileComponents();
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
    fixture.detectChanges();
    const links = fixture.nativeElement.querySelectorAll('.sidebar__list a') as NodeListOf<HTMLAnchorElement>;
    expect(links.length).toBe(4);
    expect(Array.from(links).map((link) => link.getAttribute('href'))).toEqual([
      '/dashboard', '/lanzamientos', '/lanzadores', '/simulador',
    ]);
  });
});
