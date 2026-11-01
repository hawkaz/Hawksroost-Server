<script lang="ts">
	import { ArrowDown, ArrowUp, CloudLightning, Droplets, Gauge, Minus, Sun, Umbrella } from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import TimeChart, { type TPoint } from '#lib/components/TimeChart.svelte';
	import WindDial from '#lib/components/WindDial.svelte';
	import WeatherIcon from '#lib/components/WeatherIcon.svelte';
	import WindRose from '#lib/components/WindRose.svelte';
	import {
		ago, distance, pressure, rain, rainValue, temp, tempValue, time, wind, windValue, type Units
	} from '#lib/format.ts';

	type Num = number | null;
	interface Weather {
		enabled: boolean;
		units: Units;
		now: Record<string, number | string | null> | null;
		derived: {
			dew_point_c?: Num; feels_like_c?: Num; pressure_mb?: Num; pressure_kind?: string; rain_rate_mm_h?: Num;
			pressure_trend?: { delta_mb: number; word: 'rising' | 'falling' | 'steady' };
		};
		updated_at: string | null;
		wind: { speed: number; dir: number; ts: string } | null;
		today: { high_c: Num; high_at: string | null; low_c: Num; low_at: string | null; gust_max_ms: Num; gust_at: string | null };
		rain: { today_mm: number; yesterday_mm: number; last_24h_mm: number; last_7d_mm: number };
		lightning: { count_3h: number; nearest_km: Num; last: string | null; count_24h: number };
		forecast: { days: { date: string; conditions: string; icon: string | null; high_c: number; low_c: number; precip_pct: number }[]; conditions: string } | null;
		condition: { icon: string; label: string; source: 'station' | 'forecast' } | null;
	}
	interface Point {
		t: string; temp_c: Num; temp_min_c: Num; temp_max_c: Num; humidity: Num; pressure_mb: Num;
		wind_avg: Num; wind_lull: Num; wind_gust: Num; wind_dir: Num; rain_mm: number; solar: Num; uv: Num;
	}
	interface Day { date: string; high_c: Num; low_c: Num; rain_mm: number; gust_ms: Num }
	interface History {
		range: string; bucket_s: number; since: string; series: Point[]; pressure_kind: string; days: Day[];
		wind_rose: { classes_ms: number[]; sectors: number[][]; calm: number; total: number };
		strikes: { t: string; distance_km: number }[];
	}

	const RANGES = [['day', 'Last 24 hours'], ['week', '7 days'], ['month', '30 days']] as const;
	let range = $state<'day' | 'week' | 'month'>('day');
	let w = $state<Weather | null>(null);
	let h = $state<History | null>(null);
	let now = $state(Date.now());

	async function loadNow() {
		w = await api.get<Weather>('/api/weather');
		now = Date.now();
	}
	async function loadHistory() {
		h = await api.get<History>(`/api/weather/history${qs({ range })}`);
	}
	$effect(() => {
		loadNow().catch(() => {});
		const t = setInterval(() => !document.hidden && loadNow().catch(() => {}), 60_000);
		return () => clearInterval(t);
	});
	$effect(() => {
		void range;
		loadHistory().catch(() => {});
		const t = setInterval(() => !document.hidden && loadHistory().catch(() => {}), 5 * 60_000);
		return () => clearInterval(t);
	});

	const u = $derived<Units>(w?.units ?? 'imperial');
	const imp = $derived(u === 'imperial');
	const n = $derived(w?.now);
	const d = $derived(w?.derived ?? {});
	const stale = $derived(!!w?.updated_at && now - new Date(w.updated_at).getTime() > 10 * 60_000);
	const live = $derived(w?.wind);
	const windNow = $derived(live?.speed ?? (n?.wind_avg as Num));
	const windDir = $derived(live?.dir ?? (n?.wind_dir as Num));

	// --- formatting for charts ---
	const tU = $derived(imp ? '°F' : '°C');
	const wU = $derived(imp ? 'mph' : 'km/h');
	const rU = $derived(imp ? 'in' : 'mm');
	const pU = $derived(imp ? 'inHg' : 'mb');
	const T = (c: Num) => (c == null ? null : tempValue(c, u));
	const W = (ms: Num) => (ms == null ? null : windValue(ms, u));
	const P = (mb: Num) => (mb == null ? null : imp ? mb * 0.02953 : mb);
	const fmtT = (v: number) => `${Math.round(v)}°`;
	const fmtW = (v: number) => `${Math.round(v)}`;
	const fmtR = $derived((v: number) => (imp ? v.toFixed(2) : v.toFixed(1)));
	const fmtP = $derived((v: number) => (imp ? v.toFixed(2) : `${Math.round(v)}`));
	const showBand = $derived(range !== 'day');

	const end = $derived(new Date(now).toISOString());
	const s = $derived(h?.series ?? []);
	const tempPts = $derived<TPoint[]>(s.map((p) => ({ t: p.t, v: T(p.temp_c), lo: showBand ? T(p.temp_min_c) : null, hi: showBand ? T(p.temp_max_c) : null })));
	const windPts = $derived<TPoint[]>(s.map((p) => ({ t: p.t, v: W(p.wind_avg), lo: W(p.wind_lull), hi: W(p.wind_gust) })));
	const humPts = $derived<TPoint[]>(s.map((p) => ({ t: p.t, v: p.humidity })));
	const presPts = $derived<TPoint[]>(s.map((p) => ({ t: p.t, v: P(p.pressure_mb) })));
	const sunPts = $derived<TPoint[]>(s.map((p) => ({ t: p.t, v: p.solar })));
	// Midnight in Arizona (UTC−7 all year) for a YYYY-MM-DD date.
	const dayStart = (date: string) => `${date}T07:00:00Z`;
	// Rain: per 15 minutes over a day; per cabin day over a week or month.
	const rainPts = $derived<TPoint[]>(
		range === 'day'
			? s.map((p) => ({ t: p.t, v: rainValue(p.rain_mm, u) }))
			: (h?.days ?? []).map((x) => ({ t: dayStart(x.date), v: rainValue(x.rain_mm, u) }))
	);
	const rainBucket = $derived(range === 'day' ? (h?.bucket_s ?? 900) : 86400);
	const rainStart = $derived(range === 'day' || !h?.days.length ? h?.since : dayStart(h.days[0].date));
	const rainTotal = $derived(s.reduce((a, p) => a + (p.rain_mm || 0), 0));

	const roseLabels = $derived.by(() => {
		const c = (h?.wind_rose.classes_ms ?? [3, 6, 10]).map((ms) => Math.round(windValue(ms, u)));
		return [`Under ${c[0]} ${wU}`, `${c[0]}–${c[1]} ${wU}`, `${c[1]}–${c[2]} ${wU}`, `Over ${c[2]} ${wU}`];
	});
	const strikeNearest = $derived(h?.strikes.length ? Math.min(...h.strikes.map((x) => x.distance_km)) : null);

	const dayName = (date: string, i: number) =>
		i === 0 ? 'Today' : new Date(date + 'T12:00').toLocaleDateString('en-US', { weekday: 'short' });
	const shortDate = (date: string) =>
		new Date(date + 'T12:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
	const trendIcon = $derived(d.pressure_trend?.word === 'rising' ? ArrowUp : d.pressure_trend?.word === 'falling' ? ArrowDown : Minus);
	const uvWord = (uv: number) => (uv < 3 ? 'low' : uv < 6 ? 'moderate' : uv < 8 ? 'high' : uv < 11 ? 'very high' : 'extreme');
</script>

<div class="stack">
	<h1>Weather</h1>

	{#if w && !w.enabled}
		<div class="card empty"><p>Weather is turned off.</p><p>An admin can turn it on in Admin → Weather.</p></div>
	{:else if w && !n}
		<div class="card empty"><p>No weather yet.</p><p>Once the Tempest hub is on the cabin network, readings show up within a minute.</p></div>
	{/if}

	{#if n}
		{#if stale}<p class="notice warn">No new readings from the weather station since {time(w?.updated_at)}. These are the last ones it sent.</p>{/if}

		<section class="card hero">
			<div class="now">
				<div class="temp">
					{#if w?.condition}<WeatherIcon icon={w.condition.icon} label={w.condition.label} size={56} />{/if}
					<span>{temp(n.temp_c as number, u)}</span>
				</div>
				<div class="cond">
					{#if w?.condition?.label}<div class="h3">{w.condition.label}</div>{:else if w?.forecast?.conditions}<div class="h3">{w.forecast.conditions}</div>{/if}
					<div>Feels like <span class="data">{temp(d.feels_like_c, u)}</span></div>
					<div class="muted">Dew point <span class="data">{temp(d.dew_point_c, u)}</span> · humidity <span class="data">{Math.round(n.humidity as number)}%</span></div>
				</div>
				<dl class="today">
					<div><dt>High</dt><dd><span class="data">{temp(w?.today.high_c, u)}</span> <span class="small muted">{time(w?.today.high_at)}</span></dd></div>
					<div><dt>Low</dt><dd><span class="data">{temp(w?.today.low_c, u)}</span> <span class="small muted">{time(w?.today.low_at)}</span></dd></div>
					<div><dt>Top gust</dt><dd><span class="data">{wind(w?.today.gust_max_ms, u)}</span> <span class="small muted">{time(w?.today.gust_at)}</span></dd></div>
				</dl>
			</div>
			<div class="dial">
				<WindDial dir={windNow ? windDir : null} speed={wind(windNow, u)} gust={wind(n.wind_gust as number, u)} />
			</div>
		</section>

		<div class="facts">
			<section class="card fact">
				<h2 class="fh"><Droplets size={18} strokeWidth={1.75} />Rain</h2>
				<div class="data big">{rain(w?.rain.today_mm, u)}</div>
				<div class="small muted">today{(d.rain_rate_mm_h ?? 0) > 0 ? `, falling at ${rain(d.rain_rate_mm_h, u)}/hr` : ''}</div>
				<div class="small muted">Yesterday {rain(w?.rain.yesterday_mm, u)} · 7 days {rain(w?.rain.last_7d_mm, u)}</div>
			</section>
			<section class="card fact">
				<h2 class="fh"><Gauge size={18} strokeWidth={1.75} />Pressure</h2>
				<div class="data big">{pressure(d.pressure_mb, u)}</div>
				<div class="small muted trend">
					{#if d.pressure_trend}{@const Icon = trendIcon}<Icon size={14} strokeWidth={2} />{d.pressure_trend.word} over 3 hours{:else}{d.pressure_kind ?? 'station'} pressure{/if}
				</div>
			</section>
			<section class="card fact">
				<h2 class="fh"><Sun size={18} strokeWidth={1.75} />Sun</h2>
				<div class="data big">UV {n.uv ?? '—'}</div>
				<div class="small muted">{n.uv != null ? uvWord(n.uv as number) : ''} · <span class="data">{Math.round((n.solar as number) ?? 0)}</span> W/m²</div>
			</section>
			<section class="card fact" class:alert={!!w?.lightning.count_3h}>
				<h2 class="fh"><CloudLightning size={18} strokeWidth={1.75} />Lightning</h2>
				{#if w?.lightning.count_3h}
					<div class="data big">{w.lightning.count_3h} {w.lightning.count_3h === 1 ? 'strike' : 'strikes'}</div>
					<div class="small muted">in 3 hours · nearest {distance(w.lightning.nearest_km, u)}, last {ago(w.lightning.last)}</div>
				{:else}
					<div class="data big">None</div>
					<div class="small muted">in 3 hours{w?.lightning.count_24h ? ` · ${w.lightning.count_24h} in 24 hours` : ''}</div>
				{/if}
			</section>
		</div>
	{/if}

	{#if w?.forecast?.days.length}
		<section class="card">
			<h2 class="h3 head">Next few days</h2>
			<ol class="forecast">
				{#each w.forecast.days as f, i (f.date)}
					<li>
						<span class="fd">{dayName(f.date, i)}</span>
						<WeatherIcon icon={f.icon} label={f.conditions} size={28} />
						<span class="data">{temp(f.high_c, u)}<span class="muted"> / {temp(f.low_c, u)}</span></span>
						<span class="small muted">{f.conditions}</span>
						{#if f.precip_pct}<span class="small precip"><Umbrella size={13} strokeWidth={1.75} />{f.precip_pct}%</span>{/if}
					</li>
				{/each}
			</ol>
		</section>
	{/if}

	{#if n || h?.series.length}
		<div class="spread wrap history-head">
			<h2>History</h2>
			<div class="pill-tabs" role="group" aria-label="Period">
				{#each RANGES as [id, label] (id)}
					<button class:on={range === id} onclick={() => (range = id)}>{label}</button>
				{/each}
			</div>
		</div>

		{#if h}
			<div class="charts">
				<section class="card">
					<div class="ch"><h3>Temperature</h3>{#if showBand}<span class="small muted">line = average, shading = low to high</span>{/if}</div>
					<TimeChart points={tempPts} label={`Temperature (${tU})`} unit={tU} format={fmtT} start={h.since} {end} bucketS={h.bucket_s} />
				</section>
				<section class="card">
					<div class="ch"><h3>Wind</h3><span class="small muted">line = average, shading = lull to gust</span></div>
					<TimeChart points={windPts} label={`Wind (${wU})`} unit={wU} format={fmtW} zero start={h.since} {end} bucketS={h.bucket_s} />
				</section>
				<section class="card">
					<div class="ch"><h3>Rain</h3><span class="small muted"><span class="data">{rain(rainTotal, u)}</span> {range === 'day' ? 'in 24 hours' : 'total'}</span></div>
					{#if rainTotal > 0}
						<TimeChart points={rainPts} kind="bars" label={`Rain (${rU})`} unit={rU} format={fmtR} start={rainStart} {end} bucketS={rainBucket} />
					{:else}
						<p class="dry muted">Dry. No rain {range === 'day' ? 'in the last 24 hours' : 'in this period'}.</p>
					{/if}
				</section>
				<section class="card">
					<div class="ch"><h3>Pressure</h3><span class="small muted">{h.pressure_kind}</span></div>
					<TimeChart points={presPts} label={`Pressure (${pU})`} unit={pU} format={fmtP} start={h.since} {end} bucketS={h.bucket_s} />
				</section>
				<section class="card">
					<div class="ch"><h3>Humidity</h3></div>
					<TimeChart points={humPts} label="Humidity (%)" unit="%" format={(v) => `${Math.round(v)}`} start={h.since} {end} bucketS={h.bucket_s} />
				</section>
				<section class="card">
					<div class="ch"><h3>Sunlight</h3></div>
					<TimeChart points={sunPts} label="Sunlight (W/m²)" unit="W/m²" format={(v) => `${Math.round(v)}`} zero start={h.since} {end} bucketS={h.bucket_s} />
				</section>
				<section class="card">
					<div class="ch"><h3>Where the wind came from</h3></div>
					<WindRose sectors={h.wind_rose.sectors} calm={h.wind_rose.calm} total={h.wind_rose.total} classLabels={roseLabels} />
				</section>
				<section class="card">
					<div class="ch"><h3>Lightning</h3></div>
					{#if h.strikes.length}
						<p><span class="data big">{h.strikes.length}</span> {h.strikes.length === 1 ? 'strike' : 'strikes'} detected, nearest <span class="data">{distance(strikeNearest, u)}</span>.</p>
						<ul class="list strikes">
							{#each h.strikes.slice(0, 6) as x (x.t)}
								<li><span class="data">{distance(x.distance_km, u)}</span><span class="small muted">{shortDate(new Date(x.t).toLocaleDateString('en-CA', { timeZone: 'America/Phoenix' }))}, {time(x.t)}</span></li>
							{/each}
						</ul>
					{:else}
						<p class="muted">No lightning detected in this period. The station hears strikes up to about 25 miles away.</p>
					{/if}
				</section>
			</div>

			{#if range !== 'day' && h.days.length}
				<section class="card">
					<h3 class="head">Day by day</h3>
					<div class="tbl">
						<table>
							<thead><tr><th>Day</th><th>High</th><th>Low</th><th>Rain</th><th>Top gust</th></tr></thead>
							<tbody>
								{#each [...h.days].reverse() as x (x.date)}
									<tr>
										<td>{shortDate(x.date)}</td>
										<td class="data">{temp(x.high_c, u)}</td>
										<td class="data">{temp(x.low_c, u)}</td>
										<td class="data" class:muted={!x.rain_mm}>{x.rain_mm ? rain(x.rain_mm, u) : '—'}</td>
										<td class="data">{wind(x.gust_ms, u)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</section>
			{/if}
		{/if}

		{#if n}
			<p class="small muted">Tempest station · updated {ago(w?.updated_at)} · battery <span class="data">{n.battery ?? '—'} V</span></p>
		{/if}
	{/if}
</div>

<style>
	/* The one big moment: today's temperature beside the wind. */
	.hero {
		display: grid;
		gap: var(--space-4);
		align-items: center;
	}
	@media (min-width: 700px) {
		.hero {
			grid-template-columns: 1fr auto;
		}
	}
	.now {
		display: grid;
		gap: var(--space-3) var(--space-5);
		grid-template-columns: auto 1fr;
		align-items: center;
	}
	.temp {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		font: 400 76px/1 var(--font-data);
		letter-spacing: -0.04em;
		font-variant-numeric: tabular-nums;
	}
	.cond {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.h3 {
		font: 600 19px/26px var(--font-display);
	}
	.today {
		grid-column: 1 / -1;
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2) var(--space-5);
		margin: 0;
		padding-top: var(--space-3);
		border-top: 1px solid var(--line);
	}
	.today dt {
		font-size: 13px;
		line-height: 18px;
		color: var(--text-muted);
	}
	.today dd {
		margin: 0;
	}
	.dial {
		display: flex;
		justify-content: center;
	}

	.facts {
		display: grid;
		gap: var(--space-3);
		grid-template-columns: 1fr 1fr;
	}
	@media (min-width: 1000px) {
		.facts {
			grid-template-columns: repeat(4, 1fr);
		}
	}
	.fact {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.fact.alert {
		border-color: var(--danger);
	}
	.fh {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: 600 15px/20px var(--font-ui);
		color: var(--text-muted);
		margin-bottom: var(--space-1);
	}
	.big {
		font-size: 22px;
		line-height: 30px;
	}
	.trend {
		display: flex;
		align-items: center;
		gap: 4px;
	}

	.head {
		margin-bottom: var(--space-3);
	}
	.forecast {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		gap: var(--space-4);
	}
	.forecast li {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.fd {
		font-weight: 600;
	}
	.precip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		color: var(--info);
	}

	.history-head {
		margin-top: var(--space-4);
	}
	.charts {
		display: grid;
		gap: var(--space-4);
	}
	.charts > * {
		min-width: 0;
	}
	@media (min-width: 1000px) {
		.charts {
			grid-template-columns: 1fr 1fr;
		}
	}
	.ch {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--space-1) var(--space-3);
		margin-bottom: var(--space-2);
	}
	.dry {
		display: grid;
		place-items: center;
		min-height: 120px;
		border: 1px dashed var(--line);
		border-radius: var(--radius-md);
	}
	.strikes li {
		min-height: 36px;
		justify-content: space-between;
	}
	.tbl {
		overflow: auto;
		max-height: 460px;
	}
	thead th {
		position: sticky;
		top: 0;
		background: var(--surface);
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 14px;
	}
	th {
		text-align: left;
		font-weight: 500;
		color: var(--text-muted);
		padding: var(--space-2) var(--space-3) var(--space-2) 0;
		border-bottom: 1px solid var(--line);
	}
	td {
		padding: var(--space-2) var(--space-3) var(--space-2) 0;
		border-bottom: 1px solid var(--line);
		white-space: nowrap;
	}
</style>
