<script lang="ts">
	import { Settings2 } from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import ObstructionMap from '#lib/components/ObstructionMap.svelte';
	import TimeChart, { type TPoint } from '#lib/components/TimeChart.svelte';
	import { ago, compass } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';

	type Num = number | null | undefined;
	interface Status {
		id?: string; state?: string; uptime_s?: Num; hardware_version?: string; software_version?: string;
		latency_ms?: Num; drop_rate?: Num; down_bps?: Num; up_bps?: Num; seconds_to_first_slot?: Num; snr_ok?: boolean;
		fraction_obstructed?: Num; currently_obstructed?: boolean; obstruction_duration_s?: Num; obstruction_interval_s?: Num;
		obstruction_valid_s?: Num; azimuth?: Num; elevation?: Num; gps_ready?: boolean; gps_enabled?: boolean; gps_sats?: Num;
		error?: string;
	}
	interface Stats {
		samples?: number; total_ping_drop?: Num; full_drop_s?: Num; obstructed_s?: Num; unscheduled_s?: Num;
		latency_mean?: Num; latency_deciles?: number[] | null; latency_stdev?: Num;
		loaded_samples?: number[] | null; loaded_median?: (number | null)[] | null;
		outage_runs_s?: number[] | null; power_latest?: Num; power_mean?: Num; power_min?: Num; power_max?: Num;
	}
	interface Avail { connected_pct: number | null; outage_s: number; measured_s: number }
	interface Dish {
		enabled: boolean; reachable: boolean; online: boolean; state_label: string; error: string | null; updated_at: string | null;
		status: Status | null; alerts: { key: string; label: string; level: 'bad' | 'warn' | 'info' }[]; stats: Stats | null;
		sleep: { enabled: boolean; start_local: string; duration_min: number } | null;
		availability: { day: Avail; week: Avail };
	}
	interface Live { step_s: number; points: { t: string; latency_ms: Num; drop: number; down_bps: number; up_bps: number; power_w: Num; obstructed: boolean }[] }
	interface Hist {
		bucket_s: number;
		series: { t: string; latency_ms: Num; drop_pct: number; down_bps: number; up_bps: number; down_peak_bps: number; up_peak_bps: number; power_w: Num; outage_s: number; obstructed_s: number; measured_s: number }[];
	}
	interface SkyMap { rows: number; cols: number; data: string; updated_at: string }

	const RANGES = [[24, 'Last 24 hours'], [168, '7 days'], [720, '30 days']] as const;
	let hours = $state<number>(24);
	let dish = $state<Dish | null>(null);
	let live = $state<Live | null>(null);
	let hist = $state<Hist | null>(null);
	let sky = $state<SkyMap | null>(null);
	let now = $state(Date.now());

	async function loadNow() {
		[dish, live] = await Promise.all([api.get<Dish>('/api/starlink'), api.get<Live>('/api/starlink/live')]);
		now = Date.now();
		sky = await api.get<SkyMap>('/api/starlink/map').catch(() => null);
	}
	$effect(() => {
		loadNow().catch(() => {});
		const t = setInterval(() => !document.hidden && loadNow().catch(() => {}), 60_000);
		return () => clearInterval(t);
	});
	$effect(() => {
		const h = hours;
		api.get<Hist>(`/api/starlink/history${qs({ hours: h })}`)
			.then((r) => {
				if (h === hours) hist = r; // a slow answer for a range you've left isn't drawn
			})
			.catch(() => {});
	});

	const st = $derived(dish?.status ?? null);
	const stats = $derived(dish?.stats ?? null);

	// --- formatting ---
	const mbps = (bps: Num) => (bps == null ? null : bps / 1e6);
	const fmtMbps = (v: number) => (v >= 10 ? `${Math.round(v)}` : v >= 1 ? v.toFixed(1) : v.toFixed(2));
	const speed = (bps: Num) => (bps == null ? '—' : `${fmtMbps(bps / 1e6)} Mbps`);
	const ms = (v: Num) => (v == null ? '—' : `${Math.round(v)} ms`);
	const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${v.toFixed(digits)}%`);
	function span(s: Num): string {
		if (s == null) return '—';
		const d = Math.floor(s / 86400);
		const h = Math.floor((s % 86400) / 3600);
		const m = Math.floor((s % 3600) / 60);
		if (d) return `${d} day${d === 1 ? '' : 's'} ${h} hr`;
		if (h) return `${h} hr ${m} min`;
		if (m) return `${m} min`;
		return `${Math.round(s)} sec`;
	}
	function availability(a: Avail | undefined): string {
		if (!a || a.connected_pct == null) return '—';
		const p = a.connected_pct;
		return `${p >= 99.9 ? p.toFixed(2) : p.toFixed(1)}%`;
	}
	// Load buckets from the dish: under 1 Mbps, then doubling (1–2, 2–4, …).
	const bucketLabel = (i: number) => (i === 0 ? 'Under 1 Mbps' : `${2 ** (i - 1)}–${2 ** i} Mbps`);
	const loaded = $derived.by(() => {
		const n = stats?.loaded_samples ?? [];
		const med = stats?.loaded_median ?? [];
		return n.map((count, i) => ({ i, count, median: med[i] ?? null })).filter((b) => b.count > 0 && b.median != null);
	});
	const loadedMax = $derived(Math.max(1, ...loaded.map((b) => b.median ?? 0)));
	const outages = $derived.by(() => {
		const runs = stats?.outage_runs_s ?? [];
		let count = 0;
		let total = 0;
		let longest = 0;
		runs.forEach((secs, i) => {
			if (!secs) return;
			count += secs / (i + 1);
			total += secs;
			longest = i + 1;
		});
		return { count: Math.round(count), total, longest };
	});
	const deciles = $derived(stats?.latency_deciles ?? null);

	// --- charts ---
	const liveStart = $derived(live?.points.length ? live.points[0].t : undefined);
	const liveEnd = $derived(live?.points.length ? new Date(new Date(live.points[live.points.length - 1].t).getTime() + 5000).toISOString() : undefined);
	const lp = $derived(live?.points ?? []);
	const liveLatency = $derived<TPoint[]>(lp.map((p) => ({ t: p.t, v: p.latency_ms ?? null })));
	const liveDown = $derived<TPoint[]>(lp.map((p) => ({ t: p.t, v: mbps(p.down_bps) })));
	const liveUp = $derived<TPoint[]>(lp.map((p) => ({ t: p.t, v: mbps(p.up_bps) })));
	const livePower = $derived<TPoint[]>(lp.filter((p) => p.power_w != null).map((p) => ({ t: p.t, v: p.power_w ?? null })));

	const hs = $derived(hist?.series ?? []);
	const histStart = $derived(new Date(now - hours * 3600_000).toISOString());
	const histEnd = $derived(new Date(now).toISOString());
	const hLatency = $derived<TPoint[]>(hs.map((p) => ({ t: p.t, v: p.latency_ms ?? null })));
	const hOffline = $derived<TPoint[]>(hs.map((p) => ({ t: p.t, v: p.outage_s / 60 })));
	const hDown = $derived<TPoint[]>(hs.map((p) => ({ t: p.t, v: mbps(p.down_bps), lo: mbps(p.down_bps), hi: mbps(p.down_peak_bps) })));
	const hUp = $derived<TPoint[]>(hs.map((p) => ({ t: p.t, v: mbps(p.up_bps), lo: mbps(p.up_bps), hi: mbps(p.up_peak_bps) })));
	const hPower = $derived<TPoint[]>(hs.map((p) => ({ t: p.t, v: p.power_w ?? null })));
	const offlineTotal = $derived(hs.reduce((a, p) => a + p.outage_s, 0));
	const bucketWord = $derived(hist?.bucket_s === 300 ? '5 minutes' : hist?.bucket_s === 3600 ? 'hour' : '6 hours');

	const tone = $derived(!dish?.reachable ? 'bad' : dish.online ? 'ok' : 'warn');
	const levelClass = { bad: 'danger', warn: 'warn', info: '' } as const;
</script>

<div class="stack">
	<div class="spread wrap">
		<h1>Starlink</h1>
		{#if session.can('admin')}
			<a class="btn secondary" href="/admin/starlink"><Settings2 size={18} strokeWidth={1.75} />Dish controls</a>
		{/if}
	</div>

	{#if dish && !dish.enabled}
		<div class="card empty"><p>Starlink is turned off.</p><p>An admin can turn it on in Admin → Starlink.</p></div>
	{:else if dish && !st}
		<div class="card empty"><p>No word from the dish yet.</p><p>It reports within a minute once the laptop can reach it.</p></div>
	{/if}

	{#if dish?.enabled && st}
		<section class="card hero {tone}">
			<div class="state">
				<span class="lamp" aria-hidden="true"></span>
				<div>
					<div class="word">{dish.state_label}</div>
					<div class="small muted">
						{#if dish.reachable}Up {span(st.uptime_s)} · checked {ago(dish.updated_at)}{:else}{dish.error ? `${dish.error}. ` : ''}Last heard from {ago(dish.updated_at)}. Everything below is from before then.{/if}
					</div>
				</div>
			</div>
			{#if dish.reachable}
				<dl class="now">
					<div><dt>Latency</dt><dd class="data">{ms(st.latency_ms)}</dd></div>
					<div><dt>Download now</dt><dd class="data">{speed(st.down_bps)}</dd></div>
					<div><dt>Upload now</dt><dd class="data">{speed(st.up_bps)}</dd></div>
					<div><dt>Dropped pings</dt><dd class="data">{pct((st.drop_rate ?? 0) * 100)}</dd></div>
				</dl>
			{/if}
		</section>

		{#if dish.reachable && dish.alerts.length}
			<div class="stack alerts">
				{#each dish.alerts as a (a.key)}<p class="notice {levelClass[a.level]}">{a.label}</p>{/each}
			</div>
		{/if}

		{#if dish.reachable && lp.length > 1}
			<div class="spread wrap"><h2>Last 15 minutes</h2><span class="small muted">From the dish, every 5 seconds</span></div>
			<div class="charts">
				<section class="card"><h3 class="ch">Latency</h3>
					<TimeChart points={liveLatency} label="Latency (ms)" unit="ms" format={(v) => `${Math.round(v)}`} start={liveStart} end={liveEnd} bucketS={5} height={160} zero />
				</section>
				<section class="card"><h3 class="ch">Download</h3>
					<TimeChart points={liveDown} label="Download (Mbps)" unit="Mbps" format={fmtMbps} start={liveStart} end={liveEnd} bucketS={5} height={160} zero />
				</section>
				<section class="card"><h3 class="ch">Upload</h3>
					<TimeChart points={liveUp} label="Upload (Mbps)" unit="Mbps" format={fmtMbps} start={liveStart} end={liveEnd} bucketS={5} height={160} zero />
				</section>
				{#if livePower.length}
					<section class="card"><h3 class="ch">Power</h3>
						<TimeChart points={livePower} label="Power (W)" unit="W" format={(v) => `${Math.round(v)}`} start={liveStart} end={liveEnd} bucketS={5} height={160} />
					</section>
				{/if}
			</div>
		{/if}

		<div class="pair">
			<section class="card">
				<div class="ch spread"><h2 class="h3">Sky view</h2>{#if sky}<span class="small muted">map from {ago(sky.updated_at)}</span>{/if}</div>
				<div class="sky">
					{#if sky}
						<ObstructionMap rows={sky.rows} cols={sky.cols} data={sky.data} size={240} />
					{:else}
						<p class="muted map-empty">The dish hasn’t shared its sky map yet.</p>
					{/if}
					<div class="stack facts">
						<p><span class="data big">{pct((st.fraction_obstructed ?? 0) * 100)}</span><br /><span class="small muted">of the sky the dish uses is blocked</span></p>
						{#if st.obstruction_duration_s && st.obstruction_interval_s}
							<p class="small">Blockages last about <span class="data">{st.obstruction_duration_s.toFixed(1)} s</span>, roughly every <span class="data">{span(st.obstruction_interval_s)}</span>.</p>
						{/if}
						{#if st.currently_obstructed}<p class="small warn-text">Blocked right now.</p>{/if}
						{#if st.azimuth != null && st.elevation != null}
							<p class="small muted">Dish faces {compass(((st.azimuth % 360) + 360) % 360)} (<span class="data">{Math.round(((st.azimuth % 360) + 360) % 360)}°</span>), tilted <span class="data">{Math.round(st.elevation)}°</span> up.</p>
						{/if}
						<p class="small muted">Light dots are clear sky; red dots are where trees or the roof got in the way. Centre is straight up, the edge is the horizon.</p>
					</div>
				</div>
			</section>

			<section class="card stack">
				<h2 class="h3">How reliable it’s been</h2>
				<div class="avail">
					<div><span class="data big">{availability(dish.availability.day)}</span><span class="small muted">connected, last 24 hours{dish.availability.day.outage_s ? ` · ${span(dish.availability.day.outage_s)} offline` : ''}</span></div>
					<div><span class="data big">{availability(dish.availability.week)}</span><span class="small muted">connected, last 7 days{dish.availability.week.outage_s ? ` · ${span(dish.availability.week.outage_s)} offline` : ''}</span></div>
				</div>
				<p class="small muted">Counted from the dish’s own second-by-second record while this laptop was on. Offline means every ping failed for that second.</p>

				{#if deciles?.length === 11}
					<div>
						<h3 class="sub">Latency, last 15 minutes</h3>
						<p>Usually <span class="data">{ms(deciles[5])}</span>. Nine times in ten under <span class="data">{ms(deciles[9])}</span>; worst <span class="data">{ms(deciles[10])}</span>.</p>
					</div>
				{/if}
				{#if loaded.length}
					<div>
						<h3 class="sub">Latency when the connection is busy</h3>
						<ul class="bars">
							{#each loaded as b (b.i)}
								<li>
									<span class="bl small">{bucketLabel(b.i)}</span>
									<span class="track"><i style="width:{((b.median ?? 0) / loadedMax) * 100}%"></i></span>
									<span class="data small">{ms(b.median)}</span>
								</li>
							{/each}
						</ul>
						<p class="small muted">Typical latency at each level of use. A big jump at higher speeds means heavy use slows everything else down.</p>
					</div>
				{/if}
				{#if stats?.outage_runs_s}
					<p class="small">{outages.count ? `${outages.count} short ${outages.count === 1 ? 'dropout' : 'dropouts'} in the last 15 minutes, the longest ${outages.longest} s.` : 'No dropouts in the last 15 minutes.'}</p>
				{/if}
			</section>
		</div>

		<div class="spread wrap history-head">
			<h2>History</h2>
			<div class="pill-tabs" role="group" aria-label="Period">
				{#each RANGES as [h, label] (h)}
					<button class:on={hours === h} aria-pressed={hours === h} onclick={() => (hours = h)}>{label}</button>
				{/each}
			</div>
		</div>
		{#if hist}
			{#if hs.length}
				<div class="charts">
					<section class="card"><div class="ch spread"><h3>Latency</h3><span class="small muted">typical for each {bucketWord}</span></div>
						<TimeChart points={hLatency} label="Latency (ms)" unit="ms" format={(v) => `${Math.round(v)}`} start={histStart} end={histEnd} bucketS={hist.bucket_s} zero />
					</section>
					<section class="card"><div class="ch spread"><h3>Time offline</h3><span class="small muted"><span class="data">{span(offlineTotal)}</span> total</span></div>
						{#if offlineTotal > 0}
							<TimeChart points={hOffline} kind="bars" label="Minutes offline" unit="min" format={(v) => (v >= 10 ? `${Math.round(v)}` : v.toFixed(1))} start={histStart} end={histEnd} bucketS={hist.bucket_s} />
						{:else}
							<p class="calm muted">No outages in this period.</p>
						{/if}
					</section>
					<section class="card"><div class="ch spread"><h3>Download</h3><span class="small muted">line = average, shading up to peak</span></div>
						<TimeChart points={hDown} label="Download (Mbps)" unit="Mbps" format={fmtMbps} start={histStart} end={histEnd} bucketS={hist.bucket_s} zero />
					</section>
					<section class="card"><div class="ch spread"><h3>Upload</h3><span class="small muted">line = average, shading up to peak</span></div>
						<TimeChart points={hUp} label="Upload (Mbps)" unit="Mbps" format={fmtMbps} start={histStart} end={histEnd} bucketS={hist.bucket_s} zero />
					</section>
					{#if hPower.some((p) => p.v != null)}
						<section class="card"><h3 class="ch">Power</h3>
							<TimeChart points={hPower} label="Power (W)" unit="W" format={(v) => `${Math.round(v)}`} start={histStart} end={histEnd} bucketS={hist.bucket_s} />
						</section>
					{/if}
				</div>
				<p class="small muted">Speeds are what the cabin actually used, not the most it could do. The dish doesn’t share the usage Starlink bills by, so there’s no data counter here.</p>
			{:else}
				<div class="card empty"><p>No history yet.</p><p>It builds up minute by minute while the laptop is on.</p></div>
			{/if}
		{/if}

		<section class="card">
			<h2 class="h3 head">The dish</h2>
			<dl class="details">
				<div><dt>Hardware</dt><dd class="data">{st.hardware_version ?? '—'}</dd></div>
				<div><dt>Software</dt><dd class="data">{st.software_version ?? '—'}</dd></div>
				<div><dt>Running for</dt><dd>{span(st.uptime_s)}</dd></div>
				<div><dt>GPS</dt><dd>{st.gps_ready ? `Locked, ${st.gps_sats ?? '?'} satellites` : st.gps_enabled === false ? 'Off' : 'Searching'}</dd></div>
				{#if stats?.power_mean != null}
					<div><dt>Power</dt><dd><span class="data">{Math.round(stats.power_latest ?? stats.power_mean)} W</span> now, <span class="data">{Math.round(stats.power_mean)} W</span> average, up to <span class="data">{Math.round(stats.power_max ?? 0)} W</span></dd></div>
				{/if}
				<div><dt>Signal</dt><dd>{st.snr_ok === false ? 'Below the noise floor' : 'Good'}</dd></div>
				<div><dt>Night sleep</dt><dd>{dish.sleep?.enabled ? `From ${dish.sleep.start_local} for ${span(dish.sleep.duration_min * 60)}` : 'Off'}</dd></div>
				{#if st.id}<div><dt>Dish ID</dt><dd class="data small id">{st.id}</dd></div>{/if}
			</dl>
		</section>
	{/if}
</div>

<style>
	.hero {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-4) var(--space-6);
		border-left: 4px solid var(--line);
	}
	.hero.ok {
		border-left-color: var(--ok);
	}
	.hero.warn {
		border-left-color: var(--warn);
	}
	.hero.bad {
		border-left-color: var(--warn);
	}
	.state {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}
	.lamp {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--text-muted);
	}
	.ok .lamp {
		background: var(--ok);
	}
	.warn .lamp {
		background: var(--warn);
	}
	.bad .lamp {
		background: var(--warn);
	}
	.word {
		font: 800 28px/34px var(--font-display);
	}
	.now {
		display: grid;
		grid-template-columns: repeat(2, minmax(110px, auto));
		gap: var(--space-3) var(--space-6);
		margin: 0;
	}
	@media (min-width: 700px) {
		.now {
			grid-template-columns: repeat(4, auto);
		}
	}
	.now dt,
	.details dt {
		font-size: 13px;
		line-height: 18px;
		color: var(--text-muted);
	}
	.now dd {
		margin: 0;
		font-size: 22px;
		line-height: 30px;
	}
	.alerts {
		gap: var(--space-2);
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
		margin-bottom: var(--space-2);
		align-items: baseline;
	}
	h3.ch,
	.ch h3 {
		font: 600 17px/24px var(--font-display);
	}
	.h3 {
		font: 600 17px/24px var(--font-display);
	}
	.head {
		margin-bottom: var(--space-3);
	}
	.sub {
		font: 600 15px/20px var(--font-ui);
		margin-bottom: var(--space-1);
	}
	.big {
		font-size: 24px;
		line-height: 32px;
	}

	.pair {
		display: grid;
		gap: var(--space-4);
		align-items: start;
	}
	.pair > * {
		min-width: 0;
	}
	@media (min-width: 1000px) {
		.pair {
			grid-template-columns: 1fr 1fr;
		}
	}
	.sky {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-5);
		align-items: flex-start;
	}
	.sky .facts {
		flex: 1 1 200px;
		gap: var(--space-3);
	}
	.map-empty {
		width: 240px;
		height: 240px;
		display: grid;
		place-items: center;
		text-align: center;
		border: 1px dashed var(--line);
		border-radius: 50%;
		padding: var(--space-5);
	}
	.warn-text {
		color: var(--warn);
		font-weight: 500;
	}
	.avail {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-4);
	}
	.avail > div {
		display: flex;
		flex-direction: column;
	}
	.bars {
		list-style: none;
		margin: var(--space-2) 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.bars li {
		display: grid;
		grid-template-columns: 110px 1fr 56px;
		align-items: center;
		gap: var(--space-3);
	}
	.track {
		height: 10px;
		border-radius: var(--radius-pill);
		background: var(--bg);
		overflow: hidden;
	}
	.track i {
		display: block;
		height: 100%;
		background: var(--accent);
		border-radius: var(--radius-pill);
	}
	.bars .data {
		text-align: right;
	}
	.calm {
		display: grid;
		place-items: center;
		min-height: 120px;
		border: 1px dashed var(--line);
		border-radius: var(--radius-md);
	}
	.history-head {
		margin-top: var(--space-4);
	}
	.details {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: var(--space-4);
		margin: 0;
	}
	.details dd {
		margin: 0;
	}
	.id {
		word-break: break-all;
	}
</style>
