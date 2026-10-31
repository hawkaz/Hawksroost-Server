<script lang="ts">
	import { CloudLightning, Droplets, Gauge, Sun, Thermometer, Wind } from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import BarChart from '#lib/components/BarChart.svelte';
	import LineChart from '#lib/components/LineChart.svelte';
	import {
		ago, bytes, compass, distance, pressure, rain, rainValue, temp, tempValue, wind, windValue, type Units
	} from '#lib/format.ts';

	interface Weather {
		enabled: boolean;
		units: Units;
		now: Record<string, number | string | null> | null;
		updated_at: string | null;
		wind: { speed: number; dir: number; ts: string } | null;
		rain_today_mm: number;
		lightning: { count_3h: number; nearest_km: number | null; last: string | null };
		forecast: { days: { date: string; conditions: string; high_c: number; low_c: number; precip_pct: number }[]; conditions: string } | null;
	}
	interface History {
		series: { t: string; temp_c: number; humidity: number; pressure_mb: number; wind_avg: number; wind_gust: number; rain_mm: number }[];
		daily_rain: { date: string; rain_mm: number }[];
		strikes: { t: string; distance_km: number }[];
	}
	interface Starlink {
		enabled: boolean;
		online: boolean;
		status: Record<string, unknown> | null;
		updated_at: string | null;
		usage: { today: { down_bytes: number; up_bytes: number }; cycle: { down_bytes: number; up_bytes: number; covered_s: number }; cycle_start: string };
		series: { t: string; latency_ms: number | null; down_bytes: number; up_bytes: number }[];
	}

	let w = $state<Weather | null>(null);
	let h = $state<History | null>(null);
	let s = $state<Starlink | null>(null);
	let hours = $state(24);

	async function load() {
		[w, h, s] = await Promise.all([
			api.get<Weather>('/api/weather'),
			api.get<History>(`/api/weather/history${qs({ hours })}`),
			api.get<Starlink>('/api/starlink')
		]);
	}
	$effect(() => {
		void hours;
		load().catch(() => {});
		const t = setInterval(() => !document.hidden && load().catch(() => {}), 60000);
		return () => clearInterval(t);
	});

	const u = $derived<Units>(w?.units ?? 'imperial');
	const n = $derived(w?.now);
	const live = $derived(w?.wind);
	const tUnit = $derived(u === 'imperial' ? '°F' : '°C');
	const wUnit = $derived(u === 'imperial' ? ' mph' : ' km/h');
	const dayLabel = (d: string) => new Date(d + 'T12:00').toLocaleDateString('en-US', { weekday: 'short' });
	const st = $derived(s?.status as Record<string, number | string | boolean | string[] | null> | null);
</script>

<div class="stack">
	<h1>Weather</h1>

	{#if w && !w.now}
		<div class="card empty"><p>No weather yet.</p><p>Once the Tempest hub is on the cabin network, readings show up within a minute.</p></div>
	{/if}

	{#if n}
		<section class="card">
			<div class="spread wrap">
				<div class="row">
					<span class="big">{temp(n.temp_c as number, u)}</span>
					<div>
						<div>{w?.forecast?.conditions ?? ''}</div>
						<div class="small muted">Updated {ago(n.ts as string)}</div>
					</div>
				</div>
			</div>
			<div class="facts">
				<div><Wind size={20} strokeWidth={1.75} /><span class="label">Wind</span><span class="data">{wind(live?.speed ?? (n.wind_avg as number), u)} {compass(live?.dir ?? (n.wind_dir as number))}</span><span class="small muted">gusts {wind(n.wind_gust as number, u)}</span></div>
				<div><Droplets size={20} strokeWidth={1.75} /><span class="label">Rain today</span><span class="data">{rain(w?.rain_today_mm, u)}</span><span class="small muted">humidity {Math.round(n.humidity as number)}%</span></div>
				<div><Gauge size={20} strokeWidth={1.75} /><span class="label">Pressure</span><span class="data">{pressure(n.pressure_mb as number, u)}</span><span class="small muted">at the station</span></div>
				<div><Sun size={20} strokeWidth={1.75} /><span class="label">UV</span><span class="data">{n.uv ?? '—'}</span><span class="small muted">{Math.round((n.solar as number) ?? 0)} W/m²</span></div>
				<div><CloudLightning size={20} strokeWidth={1.75} /><span class="label">Lightning</span>
					{#if w?.lightning.count_3h}
						<span class="data">{w.lightning.count_3h} {w.lightning.count_3h === 1 ? 'strike' : 'strikes'}</span><span class="small muted">nearest {distance(w.lightning.nearest_km, u)}, last {ago(w.lightning.last)}</span>
					{:else}<span class="data">None</span><span class="small muted">in the last 3 hours</span>{/if}
				</div>
				<div><Thermometer size={20} strokeWidth={1.75} /><span class="label">Battery</span><span class="data">{n.battery ?? '—'} V</span><span class="small muted">Tempest</span></div>
			</div>
		</section>
	{/if}

	{#if w?.forecast?.days.length}
		<section class="card">
			<div class="card-head"><span class="label">Forecast</span></div>
			<div class="forecast">
				{#each w.forecast.days as d (d.date)}
					<div><div class="label">{dayLabel(d.date)}</div><div class="data">{temp(d.high_c, u)} / {temp(d.low_c, u)}</div><div class="small muted">{d.conditions}{d.precip_pct ? ` · ${d.precip_pct}%` : ''}</div></div>
				{/each}
			</div>
		</section>
	{/if}

	{#if h?.series.length}
		<div class="pill-tabs">
			{#each [[24, '24 hours'], [168, '7 days'], [720, '30 days']] as [hv, l] (hv)}
				<button class:on={hours === hv} onclick={() => (hours = hv as number)}>{l}</button>
			{/each}
		</div>
		<div class="grid grid-2">
			<section class="card"><div class="card-head"><span class="label">Temperature ({tUnit})</span></div>
				<LineChart label="Temperature" points={h.series.map((p) => ({ t: p.t, v: tempValue(p.temp_c, u) }))} format={(v) => `${Math.round(v)}°`} />
			</section>
			<section class="card"><div class="card-head"><span class="label">Wind gusts ({wUnit.trim()})</span></div>
				<LineChart label="Wind gusts" zeroBased points={h.series.map((p) => ({ t: p.t, v: windValue(p.wind_gust, u) }))} format={(v) => `${Math.round(v)}`} />
			</section>
			<section class="card"><div class="card-head"><span class="label">Humidity (%)</span></div>
				<LineChart label="Humidity" points={h.series.map((p) => ({ t: p.t, v: p.humidity }))} format={(v) => `${Math.round(v)}%`} />
			</section>
			<section class="card"><div class="card-head"><span class="label">Rain per day · last 7 days</span></div>
				<BarChart label="Rain per day" bars={h.daily_rain.map((d) => ({ key: d.date, label: dayLabel(d.date), v: rainValue(d.rain_mm, u) }))} format={(v) => (u === 'imperial' ? `${v.toFixed(2)}"` : `${v.toFixed(1)}`)} />
			</section>
		</div>
	{/if}

	<h2>Starlink</h2>
	{#if s && s.status}
		<section class="card">
			<div class="row">
				<span class="chip {s.online ? 'ok' : 'warn'}">{s.online ? 'Online' : 'Offline'}</span>
				<span class="small muted">Updated {ago(s.updated_at)}</span>
			</div>
			<div class="facts">
				<div><span class="label">Latency</span><span class="data">{st?.latency_ms != null ? `${Math.round(st.latency_ms as number)} ms` : '—'}</span></div>
				<div><span class="label">Dropped pings</span><span class="data">{st?.drop_rate != null ? `${((st.drop_rate as number) * 100).toFixed(1)}%` : '—'}</span></div>
				<div><span class="label">Sky blocked</span><span class="data">{st?.fraction_obstructed != null ? `${((st.fraction_obstructed as number) * 100).toFixed(1)}%` : '—'}</span></div>
				<div><span class="label">Today</span><span class="data">{bytes(s.usage.today.down_bytes + s.usage.today.up_bytes)}</span><span class="small muted">↓ {bytes(s.usage.today.down_bytes)} ↑ {bytes(s.usage.today.up_bytes)}</span></div>
				<div><span class="label">Since {new Date(s.usage.cycle_start + 'T12:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span><span class="data">{bytes(s.usage.cycle.down_bytes + s.usage.cycle.up_bytes)}</span><span class="small muted">approximate</span></div>
			</div>
			{#if st?.error}<p class="notice warn" style="margin-top:12px">{st.error}</p>{/if}
			{#if Array.isArray(st?.alerts) && (st.alerts as string[]).length}<p class="small muted" style="margin-top:8px">Dish alerts: {(st.alerts as string[]).join(', ')}</p>{/if}
		</section>
		{#if s.series.length > 1}
			<section class="card"><div class="card-head"><span class="label">Latency · last 24 hours (ms)</span></div>
				<LineChart label="Latency" zeroBased points={s.series.map((p) => ({ t: p.t, v: p.latency_ms }))} format={(v) => `${Math.round(v)}`} />
			</section>
		{/if}
		<p class="small muted">Usage is counted by this laptop while it's on, so it won't exactly match Starlink's bill.</p>
	{:else if s}
		<div class="card empty"><p>No Starlink data yet.</p><p>An admin can check Settings → Starlink.</p></div>
	{/if}
</div>

<style>
	.big {
		font: 400 56px/60px var(--font-data);
		letter-spacing: -0.02em;
	}
	.facts {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: var(--space-4);
		margin-top: var(--space-4);
	}
	.facts > div {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.forecast {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
		gap: var(--space-4);
	}
</style>
