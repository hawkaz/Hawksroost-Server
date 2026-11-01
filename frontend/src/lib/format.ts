// Dates shown in cabin time (Arizona, no DST). Units follow Settings → General.
export const CABIN_TZ = 'America/Phoenix';

const timeFmt = new Intl.DateTimeFormat('en-US', { timeZone: CABIN_TZ, hour: 'numeric', minute: '2-digit' });
const dateTimeFmt = new Intl.DateTimeFormat('en-US', {
	timeZone: CABIN_TZ,
	month: 'short',
	day: 'numeric',
	hour: 'numeric',
	minute: '2-digit'
});

export const time = (iso: string | null | undefined) => (iso ? timeFmt.format(new Date(iso)).toLowerCase() : '—');
export const dayTime = (iso: string | null | undefined) => (iso ? dateTimeFmt.format(new Date(iso)).replace(' AM', ' am').replace(' PM', ' pm') : '—');

/** Today's date in cabin time, as YYYY-MM-DD. */
export function cabinToday(): string {
	return new Intl.DateTimeFormat('en-CA', { timeZone: CABIN_TZ }).format(new Date());
}

/** 'YYYY-MM-DD' → Date at local noon (safe from timezone shifts). */
export function parseDate(s: string): Date {
	const [y, m, d] = s.split('-').map(Number);
	return new Date(y, m - 1, d, 12);
}

export function isoDate(d: Date): string {
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function addDays(s: string, n: number): string {
	const d = parseDate(s);
	d.setDate(d.getDate() + n);
	return isoDate(d);
}

export function dateRange(start: string, end: string): string {
	const a = parseDate(start);
	const b = parseDate(end);
	const sameMonth = a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear();
	const m = (d: Date) => d.toLocaleDateString('en-US', { month: 'short' });
	if (start === end) return `${m(a)} ${a.getDate()}`;
	return sameMonth ? `${m(a)} ${a.getDate()}–${b.getDate()}` : `${m(a)} ${a.getDate()} – ${m(b)} ${b.getDate()}`;
}

export function nights(start: string, end: string): number {
	return Math.round((parseDate(end).getTime() - parseDate(start).getTime()) / 86400000);
}

/** "1 night", "3 nights". */
export function nightsText(start: string, end: string): string {
	const n = nights(start, end);
	return `${n} ${n === 1 ? 'night' : 'nights'}`;
}

export function ago(iso: string | null | undefined): string {
	if (!iso) return 'never';
	const s = (Date.now() - new Date(iso).getTime()) / 1000;
	if (s < 60) return 'just now';
	if (s < 3600) return `${Math.floor(s / 60)}m ago`;
	if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
	if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`;
	return dayTime(iso);
}

// --- Units --------------------------------------------------------------------------

export type Units = 'imperial' | 'metric';

export const temp = (c: number | null | undefined, u: Units) =>
	c == null ? '—' : u === 'imperial' ? `${Math.round((c * 9) / 5 + 32)}°` : `${Math.round(c)}°`;
export const tempValue = (c: number, u: Units) => (u === 'imperial' ? (c * 9) / 5 + 32 : c);
export const wind = (ms: number | null | undefined, u: Units) =>
	ms == null ? '—' : u === 'imperial' ? `${Math.round(ms * 2.23694)} mph` : `${Math.round(ms * 3.6)} km/h`;
export const windValue = (ms: number, u: Units) => (u === 'imperial' ? ms * 2.23694 : ms * 3.6);
export const pressure = (mb: number | null | undefined, u: Units) =>
	mb == null ? '—' : u === 'imperial' ? `${(mb * 0.02953).toFixed(2)} inHg` : `${Math.round(mb)} mb`;
export const rain = (mm: number | null | undefined, u: Units) =>
	mm == null ? '—' : u === 'imperial' ? `${(mm / 25.4).toFixed(2)} in` : `${mm.toFixed(1)} mm`;
export const rainValue = (mm: number, u: Units) => (u === 'imperial' ? mm / 25.4 : mm);
export const distance = (km: number | null | undefined, u: Units) =>
	km == null ? '—' : u === 'imperial' ? `${Math.round(km * 0.621371)} mi` : `${Math.round(km)} km`;

export function compass(deg: number | null | undefined): string {
	if (deg == null) return '';
	return ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'][
		Math.round(deg / 22.5) % 16
	];
}

export function duration(s: number): string {
	const t = Math.round(s); // round first: 59.6 s is 1:00, not 0:60
	return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}
