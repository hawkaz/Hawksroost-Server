<script lang="ts">
	import { ChevronRight } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import CameraThumb from '#lib/components/CameraThumb.svelte';
	import { ago, dateRange, nights, temp, wind, compass, type Units } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import type { Person } from '#lib/types.ts';

	interface Booking { id: number; kind: string; title: string; start_date: string; end_date: string; user: Person }
	interface Today {
		date: string;
		at_cabin: Booking[];
		next: Booking[];
		tasks: { id: number; title: string; list: string; priority: number; assignee: Person | null; due_date: string | null }[];
		task_count: number;
		shopping_count: number;
		units: Units;
		weather: Record<string, number | string | null> | null;
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
	const u = $derived(data?.units ?? 'imperial');
	const starlinkOk = $derived(!!data?.starlink && !data.starlink.error && (Date.now() - new Date(data.starlink.updated_at).getTime()) < 300000);
</script>

<div class="stack">
	<h1>{greeting}, {session.me?.name}</h1>
	{#if error}<p class="notice danger">{error}</p>{/if}

	{#if data}
		<div class="grid grid-2">
			<section class="card">
				<div class="card-head"><span class="label">At the cabin</span><a class="btn text" href="/calendar">Calendar</a></div>
				{#if data.at_cabin.length}
					<ul class="list">
						{#each data.at_cabin as b (b.id)}
							<li><Avatar person={b.user} /><div class="grow"><div>{b.user.name} · {b.title}</div><div class="small muted data">{dateRange(b.start_date, b.end_date)}</div></div></li>
						{/each}
					</ul>
				{:else}
					<p class="muted">Nobody's booked in tonight.</p>
				{/if}
				{#if data.next.length}
					<div class="label" style="margin-top:16px">Coming up</div>
					<ul class="list">
						{#each data.next as b (b.id)}
							<li>
								<Avatar person={b.user} />
								<div class="grow">
									<div>{b.kind === 'stay' ? `${b.user.name} · ${b.title}` : b.title}</div>
									<div class="small muted data">{dateRange(b.start_date, b.end_date)}{b.kind === 'stay' ? ` · ${nights(b.start_date, b.end_date)} nights` : ''}</div>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			</section>

			<a class="card weather" href="/weather">
				<div class="card-head"><span class="label">Weather at the lake</span><ChevronRight size={20} strokeWidth={1.75} /></div>
				{#if w}
					<div class="row">
						<span class="big">{temp(w.temp_c as number, u)}</span>
						<div class="data small">
							<div>Wind {wind(w.wind_avg as number, u)} {compass(w.wind_dir as number)}, gusts {wind(w.wind_gust as number, u)}</div>
							<div>Humidity {Math.round(w.humidity as number)}%</div>
							<div class="muted">Updated {ago(w.ts as string)}</div>
						</div>
					</div>
				{:else}
					<p class="muted">No weather yet. An admin can check Settings → Tempest.</p>
				{/if}
				<div class="row small starlink">
					<span class="dot" style="background:{starlinkOk ? 'var(--ok)' : 'var(--warn)'}"></span>
					{#if starlinkOk}Starlink online · <span class="data">{Math.round(data.starlink?.latency_ms ?? 0)} ms</span>{:else}Starlink {data.starlink?.error ? 'unreachable' : 'no data'}{/if}
				</div>
			</a>

			{#if data.cameras.length}
				<a class="card cam" href={`/cameras/${data.cameras[0].id}`}>
					<div class="card-head"><span class="label">Cameras</span><ChevronRight size={20} strokeWidth={1.75} /></div>
					<CameraThumb id={data.cameras[0].id} name={data.cameras[0].name} />
				</a>
			{/if}

			<section class="card">
				<div class="card-head"><span class="label">To-do · {data.task_count} open</span><a class="btn text" href="/lists?tab=todo">All lists</a></div>
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
				<a class="row shop" href="/lists?tab=shopping">
					<span class="grow">Shopping list</span><span class="data">{data.shopping_count} items</span><ChevronRight size={18} strokeWidth={1.75} />
				</a>
			</section>

			{#if radio?.enabled}
				<a class="card" href="/radio">
					<div class="card-head"><span class="label">Radio</span><ChevronRight size={20} strokeWidth={1.75} /></div>
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
	.starlink {
		margin-top: var(--space-4);
		gap: var(--space-2);
	}
	.dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		display: inline-block;
	}
	.shop {
		margin-top: var(--space-3);
		padding-top: var(--space-3);
		border-top: 1px solid var(--line);
		text-decoration: none;
		min-height: var(--tap);
	}
</style>
