<script lang="ts">
	import { page } from '$app/state';
	import {
		ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Bell, Camera, Download, Play, Scissors, Siren, ZoomIn, ZoomOut
	} from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import LivePlayer from '#lib/components/LivePlayer.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import Switch from '#lib/components/Switch.svelte';
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

	async function load(quiet = false) {
		try {
			const all = await api.get<CameraInfo[]>('/api/cameras');
			cam = all.find((c) => c.id === id) ?? null;
		} catch (e) {
			if (!quiet) toast.error(e);
		}
	}
	$effect(() => {
		load();
		// Keep online state and presets current while the page is open.
		const t = setInterval(() => !document.hidden && load(true), 60_000);
		return () => clearInterval(t);
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
	async function preset(pid: string) {
		try {
			await api.post(`/api/cameras/${id}/preset`, { id: pid });
		} catch (e) {
			toast.error(e);
		}
	}
	let switching = $state(false);
	async function setTrack(enabled: boolean) {
		if (!cam) return;
		const was = cam.auto_track;
		cam.auto_track = enabled; // show it straight away; put it back if the camera says no
		switching = true;
		try {
			const r = await api.put<{ auto_track: boolean }>(`/api/cameras/${id}/autotrack`, { enabled });
			cam.auto_track = r.auto_track;
			toast.show(`Auto-tracking ${enabled ? 'on' : 'off'}.`);
		} catch (e) {
			cam.auto_track = was;
			toast.error(e);
		} finally {
			switching = false;
		}
	}
	// Siren: first tap arms it, second tap within a few seconds sounds it.
	let sirenArmed = $state(false);
	let sirenTimer: ReturnType<typeof setTimeout> | undefined;
	async function siren() {
		if (!sirenArmed) {
			sirenArmed = true;
			clearTimeout(sirenTimer);
			sirenTimer = setTimeout(() => (sirenArmed = false), 4000);
			return;
		}
		sirenArmed = false;
		clearTimeout(sirenTimer);
		try {
			await api.post(`/api/cameras/${id}/siren`, { on: true });
			toast.show('Siren sounded.');
		} catch (e) {
			toast.error(e);
		}
	}
	async function light(on: boolean) {
		if (!cam) return;
		const was = cam.light_on;
		cam.light_on = on;
		switching = true;
		try {
			const r = await api.post<{ light_on: boolean }>(`/api/cameras/${id}/light`, { on });
			cam.light_on = r.light_on;
			toast.show(`Light ${r.light_on ? 'on' : 'off'}.`);
		} catch (e) {
			cam.light_on = was;
			toast.error(e);
		} finally {
			switching = false;
		}
	}
	$effect(() => () => clearTimeout(sirenTimer));

	const streamName = $derived(cam?.streams[lens] ?? cam?.streams.sub ?? '');
	const zoomHint = $derived.by(() => {
		const sharper = cam?.streams.tele
			? ` For a sharper close-up, use the zoom lens${cam.streams.main ? ' or full quality' : ''}.`
			: cam?.streams.main
				? ' For a sharper close-up, use full quality.'
				: '';
		const cost = cam?.streams.main ? " Full quality uses more of the cabin's internet." : '';
		return `Pinch, Ctrl + scroll or + to zoom the picture; drag to look around.${sharper}${cost}`;
	});
	const tabs = $derived([
		{ id: 'live', label: 'Live' },
		...(cam?.recordings ? [{ id: 'recordings', label: 'Recordings' }] : []),
		...(cam?.events ? [{ id: 'events', label: 'Motion' }] : [])
	] as { id: typeof tab; label: string }[]);
	const canMove = $derived(!!cam?.online && !!cam.ptz && session.can('camera_control'));
	// Light: members and up. Auto-tracking and siren: admins only.
	const showLight = $derived(!!cam?.online && cam.light && session.can('camera_control'));
	const showTrack = $derived(!!cam?.online && cam.auto_track !== null && session.can('admin'));
	const showSiren = $derived(!!cam?.online && cam.siren && session.can('admin'));
	const hasExtras = $derived(showLight || showTrack || showSiren);
	const PAD = [
		{ cmd: 'Up', Icon: ArrowUp, cls: 'up' },
		{ cmd: 'Left', Icon: ArrowLeft, cls: 'left' },
		{ cmd: 'Right', Icon: ArrowRight, cls: 'right' },
		{ cmd: 'Down', Icon: ArrowDown, cls: 'down' }
	];
	const LENS = { sub: 'Standard', main: 'Full quality', tele: 'Zoom lens' } as const;
	// Recording times come from the camera's clock (cabin time) without a zone: read them as-is.
	const hms = (s: string) => s.slice(11, 19);
	const secs = (t: string) => {
		const [h, m, x] = t.split(':').map(Number);
		return h * 3600 + m * 60 + (x || 0);
	};
	function time(s: string) {
		const [h, m] = s.slice(11, 16).split(':').map(Number);
		return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
	}

	// --- Clips ---
	interface ClipJob { id: string; status: 'fetching' | 'cutting' | 'ready' | 'failed'; error: string | null; progress: number; size: number; url?: string }
	let clipOpen = $state(false);
	let clipRec = $state<Rec | null>(null);
	let clipForm = $state({ start: '', length: 60, stream: 'sub' as 'sub' | 'main' });
	let job = $state<ClipJob | null>(null);
	let poll: ReturnType<typeof setInterval> | undefined;

	function openClip(r: Rec) {
		clipRec = r;
		clipForm = { start: hms(r.start), length: 60, stream: 'sub' };
		job = null;
		clearInterval(poll);
		clipOpen = true;
	}
	async function makeClip(e: SubmitEvent) {
		e.preventDefault();
		if (!clipRec) return;
		let offset = secs(clipForm.start) - secs(hms(clipRec.start));
		if (offset < 0) offset += 86400;
		offset = Math.min(Math.max(0, offset), Math.max(0, clipRec.duration_s - 5));
		try {
			job = await api.post<ClipJob>(`/api/cameras/${id}/clips`, {
				name: clipRec.name, start_id: clipRec.start_id, end_id: clipRec.end_id, stream: clipForm.stream,
				offset_s: offset, length_s: clipForm.length, label: `${day}-${clipForm.start.replaceAll(':', '')}`
			});
			clearInterval(poll);
			poll = setInterval(async () => {
				if (!job || job.status === 'ready' || job.status === 'failed') return clearInterval(poll);
				try {
					job = await api.get<ClipJob>(`/api/cameras/clips/${job.id}/status`);
				} catch (err) {
					clearInterval(poll);
					toast.error(err);
				}
			}, 2000);
		} catch (err) {
			toast.error(err);
		}
	}
	$effect(() => () => clearInterval(poll));
	const mb = (n: number) => `${(n / 1e6).toFixed(1)} MB`;
</script>

<div class="stack">
	<div class="spread">
		<div>
			<a href="/cameras" class="small muted">← Cameras</a>
			<h1>{cam?.name ?? 'Camera'}</h1>
		</div>
		{#if cam?.events}
			<a href="/settings#alerts" class="btn secondary"><Bell size={18} strokeWidth={1.75} />Alerts</a>
		{/if}
	</div>

	{#if tabs.length > 1}
		<div class="pill-tabs">
			{#each tabs as t (t.id)}
				<button class:on={tab === t.id} onclick={() => (tab = t.id)}>{t.label}</button>
			{/each}
		</div>
	{/if}

	{#if cam && tab === 'live'}
		{#if !cam.online}
			<p class="notice warn">{cam.name} camera is offline{cam.last_ok_at ? ` since ${dayTime(cam.last_ok_at)}` : ''}.</p>
		{:else}
			<div class="live" class:solo={!canMove && !hasExtras}>
				<div class="stack">
					{#if streamName}
						{#key streamName}<LivePlayer stream={streamName} name={`${cam.name} · ${LENS[lens]}`} />{/key}
					{:else}
						<p class="notice warn">{cam.name} camera is connected, but its live video isn't available. The laptop's video service may be down; an admin can check Admin → System.</p>
					{/if}
					<div class="row wrap">
						{#if Object.keys(cam.streams).length > 1}
							<div class="pill-tabs" role="group" aria-label="Picture">
								{#each Object.keys(cam.streams) as k (k)}
									<button class:on={lens === k} onclick={() => (lens = k as typeof lens)}>{LENS[k as keyof typeof LENS]}</button>
								{/each}
							</div>
						{/if}
						<a class="btn secondary" href={`/api/cameras/${id}/snapshot?full=1&download=1`} download><Camera size={18} strokeWidth={1.75} />Save picture</a>
					</div>
					<p class="small muted">{zoomHint}</p>
				</div>

				<div class="controls">
					{#if canMove}
						<section class="card">
							<h2 class="h3">Move the camera</h2>
							<div class="ptz-wrap">
								<div class="pad" role="group" aria-label="Pan and tilt">
									{#each PAD as { cmd, Icon, cls } (cmd)}
										<button
											class={`btn secondary ${cls}`}
											aria-label={`Move ${cmd.toLowerCase()}`}
											onpointerdown={() => ptz(cmd)}
											onpointerup={release}
											onpointerleave={release}
											onpointercancel={release}
											oncontextmenu={(e) => e.preventDefault()}
										><Icon size={22} strokeWidth={1.75} /></button>
									{/each}
								</div>
								{#if cam.zoom}
									<div class="zoom">
										<button class="btn secondary" aria-label="Camera zoom in" title="Camera zoom in" onpointerdown={() => ptz('ZoomInc')} onpointerup={release} onpointerleave={release}><ZoomIn size={20} strokeWidth={1.75} /></button>
										<button class="btn secondary" aria-label="Camera zoom out" title="Camera zoom out" onpointerdown={() => ptz('ZoomDec')} onpointerup={release} onpointerleave={release}><ZoomOut size={20} strokeWidth={1.75} /></button>
									</div>
								{/if}
							</div>
							<p class="small muted hint">Press and hold to move.</p>
							{#if cam.presets.length}
								<h3 class="sub">Go to</h3>
								<div class="row wrap">
									{#each cam.presets as p (p.id)}<button class="btn secondary" onclick={() => preset(p.id)}>{p.name}</button>{/each}
								</div>
							{/if}
						</section>
					{/if}

					{#if hasExtras}
						<section class="card toggles">
							{#if showLight}
								<div class="toggle">
									<div class="grow"><h2 class="h3">Light</h2><div class="small muted">{cam.light_on ? 'On' : 'Off'}</div></div>
									<Switch checked={!!cam.light_on} label="Camera light" disabled={switching} onchange={light} />
								</div>
							{/if}
							{#if showTrack}
								<div class="toggle">
									<div class="grow"><h2 class="h3">Auto-tracking</h2><div class="small muted">Follows people, vehicles and animals on its own.</div></div>
									<Switch checked={!!cam.auto_track} label="Auto-tracking" disabled={switching} onchange={setTrack} />
								</div>
							{/if}
							{#if showSiren}
								<div class="toggle siren-row">
									<div class="grow"><h2 class="h3">Siren</h2><div class="small muted">Loud. Anyone near the camera will hear it.</div></div>
									<button class="btn" class:danger={sirenArmed} class:secondary={!sirenArmed} onclick={siren} aria-live="polite">
										<Siren size={18} strokeWidth={1.75} />{sirenArmed ? 'Tap again' : 'Sound'}
									</button>
								</div>
							{/if}
						</section>
					{/if}
				</div>
			</div>
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
								<div class="grow">
									<span class="data">{time(r.start)}–{time(r.end)}</span>
									<span class="small muted"> · {duration(r.duration_s)}{r.triggers.length ? ` · ${r.triggers.join(', ')}` : ''}</span>
								</div>
								<button class="btn icon" aria-label="Play" onclick={() => (playing = r)}><Play size={18} strokeWidth={1.75} /></button>
								<button class="btn secondary" onclick={() => openClip(r)}><Scissors size={16} strokeWidth={1.75} />Clip</button>
							</li>
						{/each}
					</ul>
				</section>
			{:else}
				<div class="card empty"><p>No recordings that day.</p><p>The camera keeps as much as fits, then records over the oldest.</p></div>
			{/if}
			<p class="small muted">Recordings are long files. Use <strong>Clip</strong> to watch or save just the minutes you want; it's much faster over the cabin's internet than downloading a whole file.</p>
		{/if}
	{/if}

	{#if tab === 'events'}
		{#if events.length}
			<div class="grid grid-3">
				{#each events as e (e.id)}
					<div>
						{#if e.snapshot}<img src={e.snapshot} alt={`${e.type} at ${dayTime(e.at)}`} class="snap" loading="lazy" />{/if}
						<div class="spread small">
							<span><span class="chip">{e.type}</span> <span class="muted">{dayTime(e.at)} · {ago(e.at)}</span></span>
							{#if e.snapshot}<a class="btn icon" href={`${e.snapshot}?download=1`} download aria-label="Save picture"><Download size={18} strokeWidth={1.75} /></a>{/if}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="card empty"><p>No motion recorded.</p><p>Quiet out there.</p></div>
		{/if}
	{/if}
</div>

<Sheet bind:open={clipOpen} title="Make a clip">
	{#if clipRec}
		{#if !job || job.status === 'failed'}
			<form class="stack" onsubmit={makeClip}>
				<p class="small muted">From the recording {time(clipRec.start)}–{time(clipRec.end)} on {day}.</p>
				<div class="grid grid-2">
					<label class="field"><span>Start at</span><input type="time" step="1" required bind:value={clipForm.start} min={hms(clipRec.start)} max={hms(clipRec.end)} /></label>
					<label class="field"><span>Length</span>
						<select bind:value={clipForm.length}>
							<option value={30}>30 seconds</option><option value={60}>1 minute</option><option value={120}>2 minutes</option>
							<option value={300}>5 minutes</option><option value={600}>10 minutes</option>
						</select>
					</label>
				</div>
				<div class="pill-tabs">
					<button type="button" class:on={clipForm.stream === 'sub'} onclick={() => (clipForm.stream = 'sub')}>Small</button>
					<button type="button" class:on={clipForm.stream === 'main'} onclick={() => (clipForm.stream = 'main')}>Full quality</button>
				</div>
				{#if job?.status === 'failed'}<p class="notice danger">{job.error}</p>{/if}
				<button class="btn">Make clip</button>
			</form>
		{:else if job.status === 'ready' && job.url}
			<!-- svelte-ignore a11y_media_has_caption -->
			<video src={job.url} controls autoplay playsinline style="width:100%;border-radius:6px;background:#000"></video>
			<div class="spread">
				<span class="small muted">{mb(job.size)}</span>
				<a class="btn" href={`${job.url}?download=1`} download><Download size={18} strokeWidth={1.75} />Save clip</a>
			</div>
			<p class="small muted">Clips are kept on the cabin laptop for 2 hours.</p>
		{:else}
			<p>{job.status === 'fetching' ? `Getting the recording from the camera… ${Math.round(job.progress * 100)}%` : 'Cutting the clip…'}</p>
			<div class="meter"><i style="width:{job.status === 'cutting' ? 100 : Math.round(job.progress * 100)}%"></i></div>
			<p class="small muted">The camera is on a slow connection, so a long or full-quality recording can take a few minutes. You can leave this open.</p>
		{/if}
	{/if}
</Sheet>

<style>
	.meter {
		height: 6px;
		background: var(--line);
		border-radius: 999px;
		overflow: hidden;
	}
	.meter i {
		display: block;
		height: 100%;
		background: var(--accent);
		transition: width 0.4s;
	}
	/* Video beside its controls on tablets and computers; stacked on phones. */
	.live {
		display: grid;
		gap: var(--space-4);
	}
	.live > * {
		min-width: 0;
	}
	.controls {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.controls:empty {
		display: none;
	}
	@media (min-width: 1000px) {
		.live:not(.solo) {
			grid-template-columns: minmax(0, 1fr) 300px;
			align-items: start;
		}
	}
	.h3 {
		font: 600 17px/24px var(--font-display);
		margin: 0 0 var(--space-3);
	}
	.sub {
		font: 600 15px/20px var(--font-ui);
		margin: var(--space-4) 0 var(--space-2);
	}
	.hint {
		margin-top: var(--space-3);
		text-align: center;
	}
	.toggles {
		display: flex;
		flex-direction: column;
	}
	.toggle {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-3) 0;
		border-top: 1px solid var(--line);
	}
	.toggle:first-child {
		border-top: 0;
		padding-top: 0;
	}
	.toggle:last-child {
		padding-bottom: 0;
	}
	.toggle .h3 {
		margin: 0;
	}
	.ptz-wrap {
		display: flex;
		gap: var(--space-5);
		align-items: center;
		justify-content: center;
	}
	.zoom {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
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
