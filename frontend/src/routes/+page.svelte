<script lang="ts">
	import { ChevronRight } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import CameraThumb from '#lib/components/CameraThumb.svelte';
	import WeatherIcon from '#lib/components/WeatherIcon.svelte';
	import { ago, dateRange, nights, temp, wind, compass, type Units } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import type { Person } from '#lib/types.ts';

	interface Booking { id: number; kind: string; title: string; start_date: string; end_date: string; user: Person; people: Person[]; who: string }
	interface Today {
		date: string;
		at_cabin: Booking[];
		next: Booking[];
		tasks: { id: number; title: string; list: string; priority: number; assignee: Person | null; due_date: string | null }[];
		task_count: number;
		shopping_count: number;
		shopping: { id: number; text: string; qty: string | null; store: string | null }[];
		units: Units;
		weather: (Record<string, number | string | null> & { condition?: { icon: string; label: string } | null }) | null;
		starlink: { state: string | null; error: string | null; latency_ms: number | null; updated_at: string } | null;
		cameras: { id: number; name: string }[];
	}
	interface RadioStatus { enabled: boolean; active: { label: string }[]; incidents: { label: string }[] }

	let data = $state<Today | null>(null);
	let radio = $state<RadioStatus | null>(null);
	let error = $state('');

	async function load() {
		try {
			data = await api.get<Today>('/api/today');
			if (session.radioEnabled) radio = await api.get<RadioStatus>('/api/radio/status');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load.';
		}
	}
	$effect(() => {
		load();
		const t = setInterval(() => !document.hidden && load(), 60000);
		return () => clearInterval(t);
	});

	const hour = new Date().getHours();
	const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
	const w = $derived(data?.weather);
	const wc = $derived(w?.condition);
	const u = $derived(data?.units ?? 'imperial');
	const sl = $derived(data?.starlink ?? null);
	const starlinkFresh = $derived(!!sl && !sl.error && Date.now() - new Date(sl.updated_at).getTime() < 300000);
	const starlinkOk = $derived(starlinkFresh && sl?.state === 'CONNECTED');
	const shownCams = $derived(data?.cameras.slice(0, 4) ?? []);
</script>

<div class="stack">
	<h1>{greeting}, {session.me?.name}</h1>
	{#if error}<p class="notice danger">{error}</p>{/if}

	{#if data}
		<div class="grid grid-2">
			<section class="card">
				<div class="card-head"><h2>At the cabin</h2><a class="btn text" href="/calendar">Calendar</a></div>
				{#if data.at_cabin.length}
					<ul class="list">
						{#each data.at_cabin as b (b.id)}
							<li><Avatar person={b.people[0] ?? b.user} /><div class="grow"><div>{b.who} · {b.title}</div><div class="small muted data">{dateRange(b.start_date, b.end_date)}</div></div></li>
						{/each}
					</ul>
				{:else}
					<p class="muted">Nobody's booked in tonight.</p>
				{/if}
				{#if data.next.length}
					<h3 class="sub">Coming up</h3>
					<ul class="list">
						{#each data.next as b (b.id)}
							<li>
								<Avatar person={b.people[0] ?? b.user} />
								<div class="grow">
									<div>{b.kind === 'stay' ? `${b.who} · ${b.title}` : b.title}</div>
									<div class="small muted data">{dateRange(b.start_date, b.end_date)}{b.kind === 'stay' ? ` · ${nights(b.start_date, b.end_date)} nights` : ''}</div>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			</section>

			<a class="card weather" href="/weather">
				<div class="card-head"><h2>Weather</h2><ChevronRight size={20} strokeWidth={1.75} /></div>
				{#if w}
					<div class="row">
						{#if wc}<WeatherIcon icon={wc.icon} label={wc.label} size={44} />{/if}
						<span class="big">{temp(w.temp_c as number, u)}</span>
						<div class="data small">
							{#if wc?.label}<div class="cond-label">{wc.label}</div>{/if}
							<div>Wind {wind(w.wind_avg as number, u)} {compass(w.wind_dir as number)}, gusts {wind(w.wind_gust as number, u)}</div>
							<div>Humidity {Math.round(w.humidity as number)}%</div>
							<div class="muted">Updated {ago(w.ts as string)}</div>
						</div>
					</div>
				{:else}
					<p class="muted">No weather yet. An admin can check Admin → Weather.</p>
				{/if}
			</a>

			{#if shownCams.length}
				<a class="card cam" href={shownCams.length === 1 ? `/cameras/${shownCams[0].id}` : '/cameras'}>
					<div class="card-head"><h2>Cameras</h2><ChevronRight size={20} strokeWidth={1.75} /></div>
					<div class="cams" class:multi={shownCams.length > 1}>
						{#each shownCams as c (c.id)}<CameraThumb id={c.id} name={c.name} every={shownCams.length > 1 ? 60 : 30} />{/each}
					</div>
				</a>
			{/if}

			<section class="card">
				<div class="card-head"><h2>Shopping <span class="count data">{data.shopping_count} to get</span></h2><a class="btn text" href="/shopping">Open</a></div>
				{#if data.shopping.length}
					<ul class="list">
						{#each data.shopping as i (i.id)}
							<li>
								<div class="grow"><div>{i.text}</div>{#if i.store}<div class="small muted">{i.store}</div>{/if}</div>
								{#if i.qty}<span class="data">{i.qty}</span>{/if}
							</li>
						{/each}
					</ul>
					{#if data.shopping_count > data.shopping.length}<a class="small muted more-link" href="/shopping">and {data.shopping_count - data.shopping.length} more</a>{/if}
				{:else}
					<p class="muted">Nothing on the list.</p>
				{/if}
			</section>

			<section class="card">
				<div class="card-head"><h2>Lists <span class="count data">{data.task_count} open</span></h2><a class="btn text" href="/lists">Open</a></div>
				{#if data.tasks.length}
					<ul class="list">
						{#each data.tasks as t (t.id)}
							<li>
								<div class="grow">
									<div>{t.title}{#if t.priority === 2}<span class="chip warn" style="margin-left:8px">High</span>{/if}</div>
									<div class="small muted">{t.list}{t.assignee ? ` · ${t.assignee.name}` : ''}</div>
								</div>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="muted">Nothing to do. Go sit on the porch.</p>
				{/if}
			</section>

			{#if sl}
				<a class="card" href="/starlink">
					<div class="card-head"><h2>Starlink</h2><ChevronRight size={20} strokeWidth={1.75} /></div>
					<div class="row link-state">
						<span class="dot" class:ok={starlinkOk} class:warn={starlinkFresh && !starlinkOk} class:bad={!starlinkFresh}></span>
						{#if starlinkOk}
							<span>Online · <span class="data">{Math.round(sl.latency_ms ?? 0)} ms</span> latency</span>
						{:else if starlinkFresh}
							<span>Not connected right now</span>
						{:else}
							<span>Can’t reach the dish · last heard {ago(sl.updated_at)}</span>
						{/if}
					</div>
				</a>
			{/if}

			{#if radio?.enabled}
				<a class="card" href="/radio">
					<div class="card-head"><h2>Radio</h2><ChevronRight size={20} strokeWidth={1.75} /></div>
					{#if radio.incidents.length}
						<p><span class="chip live pulse">Busy</span> {radio.incidents.map((i) => i.label).join(', ')}</p>
					{:else if radio.active.length}
						<p><span class="chip live pulse">Live</span> {radio.active[0].label} is active.</p>
					{:else}
						<p class="muted">Scanner is quiet.</p>
					{/if}
				</a>
			{/if}
		</div>
	{/if}
</div>

<style>
	a.card {
		text-decoration: none;
		color: inherit;
		display: block;
	}
	.big {
		font: 400 48px/52px var(--font-data);
		letter-spacing: -0.02em;
	}
	.weather .row {
		align-items: center;
		gap: var(--space-4);
	}
	.card-head h2 {
		font-size: 19px;
		line-height: 26px;
	}
	.count {
		font-weight: 400;
		font-size: 13px;
		color: var(--text-muted);
		margin-left: var(--space-1);
	}
	.sub {
		font: 600 15px/20px var(--font-ui);
		margin: var(--space-4) 0 var(--space-1);
	}
	.cams {
		display: grid;
		gap: var(--space-2);
	}
	.cams.multi {
		grid-template-columns: 1fr 1fr;
	}
	.link-state {
		gap: var(--space-2);
	}
	.dot {
		flex: none;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		display: inline-block;
		background: var(--text-muted);
	}
	.dot.ok {
		background: var(--ok);
	}
	.dot.warn {
		background: var(--warn);
	}
	.dot.bad {
		background: var(--warn);
	}
	.cond-label {
		font: 500 15px/20px var(--font-ui);
	}
	.more-link {
		display: inline-flex;
		align-items: center;
		min-height: var(--tap);
	}
</style>
