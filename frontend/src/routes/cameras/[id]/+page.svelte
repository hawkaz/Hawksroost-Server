<script lang="ts">
	import { page } from '$app/state';
	import {
		ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Bell, Download, ZoomIn, ZoomOut
	} from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import LivePlayer from '#lib/components/LivePlayer.svelte';
	import { ago, cabinToday, dayTime, duration } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';
	import type { CameraInfo } from '#lib/types.ts';

	const id = Number(page.params.id);
	let cam = $state<CameraInfo | null>(null);
	let lens = $state<'sub' | 'main' | 'tele'>('sub');
	let tab = $state<'live' | 'recordings' | 'events'>('live');

	interface Rec { name: string; start: string; end: string; start_id: string; end_id: string; duration_s: number; triggers: string[] }
	let day = $state(cabinToday());
	let recs = $state<{ days_with_recordings: string[]; files: Rec[] } | null>(null);
	let recBusy = $state(false);
	let playing = $state<Rec | null>(null);
	let events = $state<{ id: number; type: string; at: string; snapshot: string | null }[]>([]);

	async function load() {
		try {
			const all = await api.get<CameraInfo[]>('/api/cameras');
			cam = all.find((c) => c.id === id) ?? null;
		} catch (e) {
			toast.error(e);
		}
	}
	$effect(() => {
		load();
	});

	async function loadRecs() {
		recBusy = true;
		recs = null;
		try {
			recs = await api.get(`/api/cameras/${id}/recordings${qs({ day })}`);
		} catch (e) {
			toast.error(e);
		} finally {
			recBusy = false;
		}
	}
	$effect(() => {
		if (tab === 'recordings') {
			void day;
			loadRecs();
		}
		if (tab === 'events') api.get<typeof events>(`/api/cameras/${id}/events`).then((e) => (events = e)).catch(toast.error.bind(toast));
	});

	const fileUrl = (r: Rec, stream: 'sub' | 'main', download = false) =>
		`/api/cameras/${id}/recordings/file${qs({ name: r.name, start_id: r.start_id, end_id: r.end_id, stream, download: download ? 1 : undefined })}`;

	// Press and hold to move; release to stop.
	let moving = false;
	async function ptz(command: string) {
		moving = command !== 'Stop';
		try {
			await api.post(`/api/cameras/${id}/ptz`, { command });
		} catch (e) {
			toast.error(e);
		}
	}
	function release() {
		if (moving) ptz('Stop');
	}
	async function preset(pid: number) {
		try {
			await api.post(`/api/cameras/${id}/preset`, { id: pid });
		} catch (e) {
			toast.error(e);
		}
	}
	async function setTrack(enabled: boolean) {
		try {
			const r = await api.put<{ auto_track: boolean }>(`/api/cameras/${id}/autotrack`, { enabled });
			if (cam) cam.auto_track = r.auto_track;
			toast.show(`Auto-tracking ${enabled ? 'on' : 'off'}.`);
		} catch (e) {
			toast.error(e);
		}
	}
	const streamName = $derived(cam?.streams[lens] ?? cam?.streams.sub ?? '');
	const PAD = [
		{ cmd: 'Up', Icon: ArrowUp, cls: 'up' },
		{ cmd: 'Left', Icon: ArrowLeft, cls: 'left' },
		{ cmd: 'Right', Icon: ArrowRight, cls: 'right' },
		{ cmd: 'Down', Icon: ArrowDown, cls: 'down' }
	];
	const LENS = { sub: 'Wide', main: 'Wide · full quality', tele: 'Zoom lens' } as const;
	const time = (s: string) => new Date(s).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).toLowerCase();
</script>

<div class="stack">
	<div class="spread">
		<div><a href="/cameras" class="small muted">← Cameras</a><h1>{cam?.name ?? 'Camera'}</h1></div>
		<a href="/settings#alerts" class="btn secondary"><Bell size={18} strokeWidth={1.75} />Alerts</a>
	</div>

	<div class="pill-tabs">
		<button class:on={tab === 'live'} onclick={() => (tab = 'live')}>Live</button>
		<button class:on={tab === 'recordings'} onclick={() => (tab = 'recordings')}>Recordings</button>
		<button class:on={tab === 'events'} onclick={() => (tab = 'events')}>Motion</button>
	</div>

	{#if cam && tab === 'live'}
		{#if !cam.online}
			<p class="notice warn">{cam.name} camera is offline{cam.last_ok_at ? ` since ${dayTime(cam.last_ok_at)}` : ''}.</p>
		{:else if streamName}
			{#key streamName}<LivePlayer stream={streamName} name={`${cam.name} · ${LENS[lens]}`} />{/key}
			<div class="row wrap">
				{#each Object.keys(cam.streams) as k (k)}
					<button class="btn secondary" class:sel={lens === k} onclick={() => (lens = k as typeof lens)}>{LENS[k as keyof typeof LENS]}</button>
				{/each}
			</div>
			<p class="small muted">Full quality uses more of the cabin's internet. Use it only when you need detail.</p>
		{/if}

		{#if cam.online && cam.ptz && session.can('camera_control')}
			<section class="card">
				<div class="card-head"><span class="label">Move the camera</span></div>
				<div class="ptz-wrap">
					<div class="pad" role="group" aria-label="Pan and tilt">
						{#each PAD as { cmd, Icon, cls } (cmd)}
							<button
								class={`btn secondary ${cls}`}
								aria-label={`Move ${cmd}`}
								onpointerdown={() => ptz(cmd)}
								onpointerup={release}
								onpointerleave={release}
								onpointercancel={release}
								oncontextmenu={(e) => e.preventDefault()}
							><Icon size={22} strokeWidth={1.75} /></button>
						{/each}
					</div>
					{#if cam.zoom}
						<div class="stack" style="gap:8px">
							<button class="btn secondary" aria-label="Zoom in" onpointerdown={() => ptz('ZoomInc')} onpointerup={release} onpointerleave={release}><ZoomIn size={20} strokeWidth={1.75} /></button>
							<button class="btn secondary" aria-label="Zoom out" onpointerdown={() => ptz('ZoomDec')} onpointerup={release} onpointerleave={release}><ZoomOut size={20} strokeWidth={1.75} /></button>
						</div>
					{/if}
				</div>
				{#if cam.presets.length}
					<div class="label" style="margin-top:16px">Presets</div>
					<div class="row wrap" style="margin-top:8px">
						{#each cam.presets as p (p.id)}<button class="btn secondary" onclick={() => preset(p.id)}>{p.name}</button>{/each}
					</div>
				{/if}
			</section>
		{/if}

		{#if cam.online && cam.auto_track !== null}
			<section class="card spread">
				<div><div>Auto-tracking</div><div class="small muted">The camera follows people, vehicles and animals on its own.</div></div>
				{#if session.can('admin')}
					<input type="checkbox" checked={cam.auto_track} onchange={(e) => setTrack((e.target as HTMLInputElement).checked)} aria-label="Auto-tracking" />
				{:else}
					<span class="chip">{cam.auto_track ? 'On' : 'Off'}</span>
				{/if}
			</section>
		{/if}
	{/if}

	{#if tab === 'recordings'}
		<div class="row">
			<label class="field"><span>Day</span><input type="date" bind:value={day} max={cabinToday()} /></label>
		</div>
		{#if playing}
			<section class="card stack">
				<!-- svelte-ignore a11y_media_has_caption -->
				<video src={fileUrl(playing, 'sub')} controls autoplay playsinline style="width:100%;border-radius:6px;background:#000"></video>
				<div class="spread wrap">
					<span class="data">{time(playing.start)} · {duration(playing.duration_s)}</span>
					<div class="row">
						<a class="btn secondary" href={fileUrl(playing, 'sub', true)} download><Download size={18} strokeWidth={1.75} />Small</a>
						<a class="btn secondary" href={fileUrl(playing, 'main', true)} download><Download size={18} strokeWidth={1.75} />Full quality</a>
					</div>
				</div>
			</section>
		{/if}
		{#if recBusy}
			<p class="muted">Asking the camera for its recordings…</p>
		{:else if recs}
			{#if recs.files.length}
				<section class="card">
					<ul class="list">
						{#each recs.files as r (r.name)}
							<li>
								<button class="grow plain" onclick={() => (playing = r)}>
									<span class="data">{time(r.start)}</span>
									<span class="small muted"> · {duration(r.duration_s)}{r.triggers.length ? ` · ${r.triggers.join(', ')}` : ''}</span>
								</button>
								<a class="btn icon" href={fileUrl(r, 'main', true)} download aria-label="Download"><Download size={18} strokeWidth={1.75} /></a>
							</li>
						{/each}
					</ul>
				</section>
			{:else}
				<div class="card empty"><p>No recordings that day.</p><p>The camera's memory card keeps about a week or two.</p></div>
			{/if}
		{/if}
	{/if}

	{#if tab === 'events'}
		{#if events.length}
			<div class="grid grid-3">
				{#each events as e (e.id)}
					<div>
						{#if e.snapshot}<img src={e.snapshot} alt={`${e.type} at ${dayTime(e.at)}`} class="snap" loading="lazy" />{/if}
						<div class="small"><span class="chip">{e.type}</span> <span class="muted">{dayTime(e.at)} · {ago(e.at)}</span></div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="card empty"><p>No motion recorded.</p><p>Quiet out there.</p></div>
		{/if}
	{/if}
</div>

<style>
	.btn.sel {
		border-color: var(--accent);
		color: var(--accent);
	}
	.ptz-wrap {
		display: flex;
		gap: var(--space-5);
		align-items: center;
		justify-content: center;
	}
	.pad {
		display: grid;
		grid-template-columns: repeat(3, 56px);
		grid-template-rows: repeat(3, 56px);
		gap: var(--space-2);
		touch-action: none;
		user-select: none;
		-webkit-user-select: none;
	}
	.pad .btn {
		height: 56px;
		padding: 0;
	}
	.up {
		grid-area: 1 / 2;
	}
	.left {
		grid-area: 2 / 1;
	}
	.right {
		grid-area: 2 / 3;
	}
	.down {
		grid-area: 3 / 2;
	}
	.plain {
		background: none;
		border: 0;
		padding: 0;
		text-align: left;
		color: inherit;
		font: inherit;
		cursor: pointer;
		min-height: var(--tap);
	}
	.snap {
		width: 100%;
		aspect-ratio: 16/9;
		object-fit: cover;
		border-radius: var(--radius-md);
		display: block;
		margin-bottom: var(--space-2);
		background: #000;
	}
</style>
