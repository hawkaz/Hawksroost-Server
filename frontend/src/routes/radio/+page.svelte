<script lang="ts">
	import { page } from '$app/state';
	import { Download, Headphones, Pause, Play, Square, Star, Trash2, X } from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import { ago, dayTime, duration, time } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	interface Live { device_id: number; name: string; mode: string; url: string }
	interface Status {
		enabled: boolean;
		active: { channel_id: number | null; label: string; group: string | null; freq_mhz: number | null; since: string }[];
		live: Live[];
		last_recording_at: string | null;
		incidents: { id: number; label: string; started_at: string; tx_count: number }[];
		tune: { freq_mhz: number; modulation: 'nfm' | 'am'; by: string | null; until: string | null } | null;
		scan_channels: number;
	}
	interface Channel { id: number; group: string; label: string; freq_mhz: number; incident: boolean }
	interface Rec { id: number; channel_id: number | null; group: string | null; label: string; freq_mhz: number | null; started_at: string; duration_s: number; keep: boolean; parts: number; url: string }

	const PAGE = 60;
	let status = $state<Status | null>(null);
	let channels = $state<Channel[]>([]);
	let recs = $state<Rec[]>([]);
	let loaded = $state(false);
	let group = $state<string | null>(null);
	let channel = $state<number | null>(Number(page.url.searchParams.get('channel')) || null);
	let keptOnly = $state(false);
	let more = $state(false);
	let loadingMore = $state(false);
	let seq = 0; // goes up when the filters change; answers for older filters are dropped

	const groups = $derived([...new Set(channels.map((c) => c.group))]);
	const channelName = $derived(channels.find((c) => c.id === channel)?.label ?? 'One channel');
	const freq = (f: number | null) => (f ? `${f.toFixed(4)} MHz` : '');
	const canEdit = $derived(session.can('edit'));

	async function loadStatus() {
		const s = await api.get<Status>('/api/radio/status').catch(() => null);
		if (!s) return;
		if (!status && s.tune) tuneForm.freq = s.tune.freq_mhz.toFixed(4); // fill the form once, when the page opens
		status = s;
	}

	const listUrl = (before?: string) =>
		`/api/radio/recordings${qs({ group: group ?? undefined, channel_id: channel ?? undefined, keep: keptOnly || undefined, before, limit: PAGE })}`;

	// Newest calls. Older pages already loaded stay put (and so does the call that's playing).
	async function refresh() {
		const mine = seq;
		try {
			const rows = await api.get<Rec[]>(listUrl());
			if (mine !== seq) return;
			const ids = new Set(rows.map((r) => r.id));
			const oldest = rows.at(-1)?.started_at;
			const older = rows.length === PAGE && oldest ? recs.filter((r) => !ids.has(r.id) && r.started_at < oldest) : [];
			recs = [...rows, ...older];
			if (!older.length) more = rows.length === PAGE;
		} catch (e) {
			if (mine === seq && !loaded) toast.error(e);
		} finally {
			if (mine === seq) loaded = true;
		}
	}
	async function loadOlder() {
		if (loadingMore || !recs.length) return;
		const mine = seq;
		loadingMore = true;
		try {
			const rows = await api.get<Rec[]>(listUrl(recs[recs.length - 1].started_at));
			if (mine !== seq) return;
			const have = new Set(recs.map((r) => r.id));
			recs = [...recs, ...rows.filter((r) => !have.has(r.id))];
			more = rows.length === PAGE;
		} catch (e) {
			toast.error(e);
		} finally {
			loadingMore = false;
		}
	}

	$effect(() => {
		api.get<Channel[]>('/api/radio/channels').then((c) => (channels = c)).catch(() => {});
		loadStatus();
		const t = setInterval(() => !document.hidden && loadStatus(), 3000);
		return () => clearInterval(t);
	});
	$effect(() => {
		void group, channel, keptOnly;
		seq++;
		recs = [];
		more = false;
		loaded = false;
		refresh();
		const t = setInterval(() => !document.hidden && refresh(), 20000);
		return () => clearInterval(t);
	});

	// --- Listening: one audio element for calls and live, always on the page, started
	// from the tap itself (iPhones won't start sound later than that) ---
	type Playing = { kind: 'call'; rec: Rec } | { kind: 'live'; live: Live };
	let audio: HTMLAudioElement | undefined = $state();
	let playing = $state<Playing | null>(null);
	let paused = $state(true);
	let note = $state('');
	let waiting = $state(false);
	let retries = 0;
	let stallTimer: ReturnType<typeof setTimeout> | undefined;

	const isPlaying = (r: Rec) => playing?.kind === 'call' && playing.rec.id === r.id;

	function start(src: string) {
		if (!audio) return;
		note = '';
		waiting = true;
		audio.src = src;
		audio.play().catch((e: DOMException) => {
			if (e.name !== 'NotAllowedError') return; // a newer tap or Stop took over
			if (playing?.kind === 'live') {
				stop();
				toast.show('Tap Listen live to hear it again.');
			} else note = 'Tap play to listen.';
		});
	}
	function playCall(r: Rec) {
		if (isPlaying(r) && audio) {
			if (audio.paused) audio.play().catch(() => {});
			else audio.pause();
			return;
		}
		playing = { kind: 'call', rec: r };
		start(r.url);
	}
	function listenLive(l: Live) {
		if (playing?.kind === 'live' && playing.live.url === l.url) return stop();
		retries = 0;
		playing = { kind: 'live', live: l };
		start(l.url);
	}
	function stop() {
		clearTimeout(stallTimer);
		waiting = false;
		if (audio) {
			audio.pause();
			audio.removeAttribute('src');
			audio.load(); // hangs up the live stream
		}
		playing = null;
		note = '';
	}
	// Live sound stops whenever the recorder restarts (a retune, a settings change): reconnect.
	function liveDropped() {
		if (playing?.kind !== 'live') return;
		if (retries >= 8) {
			stop();
			toast.show('Live listening stopped. Tap Listen live to try again.');
			return;
		}
		retries++;
		note = 'Reconnecting…';
		const url = playing.live.url;
		setTimeout(() => {
			if (playing?.kind === 'live' && playing.live.url === url) start(url);
		}, 3000);
	}
	function onPlaying() {
		clearTimeout(stallTimer);
		retries = 0;
		note = '';
		waiting = false;
	}
	function onWaiting() {
		waiting = true;
		clearTimeout(stallTimer);
		// A live stream that stops sending without hanging up: reconnect after 15 s.
		if (playing?.kind === 'live') stallTimer = setTimeout(liveDropped, 15000);
	}
	function onError() {
		if (playing?.kind === 'live') liveDropped();
		else if (playing) note = 'That call couldn’t be played. It may have been cleaned up.';
	}

	async function keep(r: Rec) {
		try {
			r.keep = (await api.put<{ keep: boolean }>(`/api/radio/recordings/${r.id}/keep`, { keep: !r.keep })).keep;
			toast.show(r.keep ? 'Kept. It won’t be cleaned up.' : 'No longer kept.');
		} catch (e) {
			toast.error(e);
		}
	}
	async function remove(r: Rec) {
		if (!confirm(`Delete this ${r.label} call from ${dayTime(r.started_at)}?${r.keep ? ' It’s marked to keep.' : ''}`)) return;
		try {
			await api.del(`/api/radio/recordings/${r.id}`);
			if (isPlaying(r)) stop();
			recs = recs.filter((x) => x.id !== r.id);
			toast.show('Call deleted.');
		} catch (e) {
			toast.error(e);
		}
	}

	// --- Tuning: scan the channel list, or sit on one frequency ---
	let manualOpen = $state(false);
	let tuneForm = $state({ freq: '', modulation: 'nfm' as 'nfm' | 'am', minutes: 60 });
	let tuning = $state(false);
	const tuned = $derived(!!status?.tune);
	function openManual() {
		if (status?.tune) tuneForm = { freq: status.tune.freq_mhz.toFixed(4), modulation: status.tune.modulation, minutes: tuneForm.minutes };
		manualOpen = true;
	}
	async function setTune(body: Record<string, unknown>, done: string) {
		tuning = true;
		try {
			const r = await api.put<{ errors: string[] }>('/api/radio/tune', body);
			if (r.errors.length) toast.error(new Error(r.errors.join(' ')));
			else toast.show(done);
			await loadStatus();
		} catch (e) {
			toast.error(e);
		} finally {
			tuning = false;
		}
	}
	function tuneTo(e: SubmitEvent) {
		e.preventDefault();
		const f = Number(tuneForm.freq.replace(',', '.'));
		if (!f) return toast.error(new Error('Enter a frequency in MHz, like 155.160.'));
		setTune({ mode: 'manual', freq_mhz: f, modulation: tuneForm.modulation, minutes: Number(tuneForm.minutes) },
			`Tuned to ${f.toFixed(4)} MHz. The recorder restarts in a few seconds.`);
	}
	function backToScan() {
		manualOpen = false;
		setTune({ mode: 'scan' }, 'Back to scanning.');
	}
	const activeIds = $derived(new Set(status?.active.map((a) => a.channel_id)));
</script>

<div class="stack">
	<h1>Radio</h1>
	{#if status && !status.enabled}
		<div class="card empty"><p>The scanner is off.</p><p>{session.can('admin') ? 'Set it up in Admin → Radio.' : 'An admin can turn it on.'}</p></div>
	{:else if status}
		<div class="layout">
			<div class="side">
				<section class="card stack now-card">
					<div class="spread">
						{#if status.active.length}
							<span class="chip live pulse">On the air</span>
						{:else}
							<span class="chip">{tuned ? 'Tuned' : 'Scanning'}</span>
						{/if}
						<span class="small muted">Last call {ago(status.last_recording_at)}</span>
					</div>
					{#if status.active.length}
						{#each status.active as a, i (i)}
							<div class="spread"><strong>{a.label} is talking.</strong><span class="data wide-only">{freq(a.freq_mhz)}</span></div>
						{/each}
					{:else}
						<p class="muted">Quiet right now.</p>
					{/if}
					{#each status.incidents as i (i.id)}
						<p class="notice danger">{i.label} is busy: {i.tx_count} transmissions since {dayTime(i.started_at)}.</p>
					{/each}
					{#if status.live.length}
						<div class="row wrap">
							{#each status.live as l (l.url)}
								{@const on = playing?.kind === 'live' && playing.live.url === l.url}
								<button class="btn {on ? '' : 'secondary'}" aria-pressed={on} onclick={() => listenLive(l)}>
									{#if on}<Square size={16} strokeWidth={1.75} />Stop listening{:else}<Headphones size={18} strokeWidth={1.75} />Listen live{status.live.length > 1 ? ` · ${l.name}` : ''}{/if}
								</button>
							{/each}
						</div>
					{/if}
				</section>
				<section class="card stack tuning">
					<div class="spread wrap">
						<h2 class="h3">Tuning</h2>
						{#if canEdit}
							<div class="pill-tabs" role="group" aria-label="Tuning">
								<button class:on={!tuned && !manualOpen} aria-pressed={!tuned && !manualOpen} disabled={tuning} onclick={() => (tuned ? backToScan() : (manualOpen = false))}>Scan channels</button>
								<button class:on={tuned || manualOpen} aria-pressed={tuned || manualOpen} disabled={tuning} onclick={openManual}>One frequency</button>
							</div>
						{/if}
					</div>
					{#if status.tune}
						<p>
							Listening to <span class="data">{status.tune.freq_mhz.toFixed(4)} MHz</span> ({status.tune.modulation === 'am' ? 'AM' : 'FM'})
							{status.tune.until ? `until ${time(status.tune.until)}` : 'until someone switches back'}.
							<span class="muted">Scanning is paused{status.tune.by ? `; set by ${status.tune.by}` : ''}.</span>
						</p>
					{:else}
						<p class="muted">Scanning {status.scan_channels} {status.scan_channels === 1 ? 'channel' : 'channels'} and recording any calls.</p>
					{/if}
					{#if canEdit && (manualOpen || tuned)}
						<form class="tune-form" onsubmit={tuneTo}>
							<label class="field"><span>Frequency (MHz)</span><input class="data" inputmode="decimal" required bind:value={tuneForm.freq} placeholder="155.160" /></label>
							<label class="field"><span>Type</span>
								<select bind:value={tuneForm.modulation}><option value="nfm">FM (fire, police, forest)</option><option value="am">AM (aircraft)</option></select>
							</label>
							<label class="field"><span>Back to scanning</span>
								<select bind:value={tuneForm.minutes}>
									<option value={30}>after 30 minutes</option><option value={60}>after 1 hour</option>
									<option value={240}>after 4 hours</option><option value={0}>when someone switches back</option>
								</select>
							</label>
							<button class="btn" disabled={tuning}>{tuned ? 'Retune' : 'Tune'}</button>
						</form>
						<p class="small muted">Calls on this frequency are recorded like any other. Live listening plays it too.</p>
					{/if}
				</section>
			</div>
			<div class="main">
				<div class="row wrap filters" role="group" aria-label="Show calls">
					<button class="btn secondary" class:sel={!group && !channel && !keptOnly} aria-pressed={!group && !channel && !keptOnly}
						onclick={() => ((group = null), (channel = null), (keptOnly = false))}>All</button>
					{#each groups as g (g)}
						<button class="btn secondary" class:sel={group === g} aria-pressed={group === g} onclick={() => ((group = group === g ? null : g), (channel = null))}>{g}</button>
					{/each}
					{#if channel}
						<button class="btn secondary sel" aria-pressed="true" onclick={() => (channel = null)} aria-label={`Showing ${channelName} only. Show all channels`}>
							{channelName}<X size={16} strokeWidth={1.75} />
						</button>
					{/if}
					<button class="btn secondary" class:sel={keptOnly} aria-pressed={keptOnly} onclick={() => (keptOnly = !keptOnly)}><Star size={16} strokeWidth={1.75} />Kept</button>
				</div>

				<section class="card">
					{#if recs.length}
						<ul class="list">
							{#each recs as r (r.id)}
								<li class:now={isPlaying(r)}>
									<button class="btn icon secondary" aria-label={`${isPlaying(r) && !paused ? 'Pause' : 'Play'} ${r.label}, ${dayTime(r.started_at)}`} onclick={() => playCall(r)}>
										{#if isPlaying(r) && !paused}<Pause size={18} strokeWidth={1.75} />{:else}<Play size={18} strokeWidth={1.75} />{/if}
									</button>
									<div class="grow">
										<div class="name" class:hot={r.channel_id !== null && activeIds.has(r.channel_id)}>{r.label}</div>
										<div class="small muted meta">
											<span class="data">{dayTime(r.started_at)}</span> · <span class="data">{duration(r.duration_s)}</span><span class="wide-only">{r.parts > 1 ? ` · ${r.parts} parts` : ''}{r.freq_mhz ? ` · ${freq(r.freq_mhz)}` : ''}</span>
										</div>
									</div>
									{#if canEdit}
										<button class="btn icon" aria-label={r.keep ? 'Kept. Tap to stop keeping' : 'Keep this call'} aria-pressed={r.keep} onclick={() => keep(r)}>
											<Star size={18} strokeWidth={1.75} fill={r.keep ? 'currentColor' : 'none'} />
										</button>
									{:else if r.keep}<span class="kept" title="Kept"><Star size={18} strokeWidth={1.75} fill="currentColor" /></span>{/if}
								</li>
							{/each}
						</ul>
						{#if more}<button class="btn text" disabled={loadingMore} onclick={loadOlder}>{loadingMore ? 'Loading…' : 'Older calls'}</button>{/if}
					{:else if loaded}
						<p class="muted">{keptOnly ? 'No kept calls' : 'No calls recorded'}{channel ? ` on ${channelName}` : group ? ` for ${group}` : ''} yet.</p>
					{:else}
						<p class="muted">Loading calls…</p>
					{/if}
				</section>
			</div>
		</div>
	{/if}
</div>

<!-- Always on the page (hidden until something plays) so a tap can start it straight away. -->
<div class="player" hidden={!playing}>
	{#if playing?.kind === 'call'}
		{@const r = playing.rec}
		<div class="spread">
			<div class="grow">
				<strong class="name">{r.label}</strong>
				<div class="small muted"><span class="data">{dayTime(r.started_at)}</span>{r.freq_mhz ? ` · ${freq(r.freq_mhz)}` : ''}</div>
			</div>
			<div class="row actions">
				{#if canEdit}
					<button class="btn icon" aria-label={r.keep ? 'Kept. Tap to stop keeping' : 'Keep this call'} aria-pressed={r.keep} onclick={() => keep(r)}>
						<Star size={18} strokeWidth={1.75} fill={r.keep ? 'currentColor' : 'none'} />
					</button>
				{/if}
				<a class="btn icon" href={`${r.url}?download=1`} aria-label="Download this call"><Download size={18} strokeWidth={1.75} /></a>
				{#if session.can('admin')}
					<button class="btn icon" aria-label="Delete this call" onclick={() => remove(r)}><Trash2 size={18} strokeWidth={1.75} /></button>
				{/if}
				<button class="btn icon" aria-label="Close the player" onclick={stop}><X size={18} strokeWidth={1.75} /></button>
			</div>
		</div>
	{:else if playing?.kind === 'live'}
		<div class="spread">
			<div class="grow">
				<strong>Live{status && status.live.length > 1 ? ` · ${playing.live.name}` : ''}</strong>
				<div class="small muted">{note || (waiting ? 'Connecting…' : 'You’re hearing the scanner as it happens.')}</div>
			</div>
			<button class="btn secondary" onclick={stop}><Square size={16} strokeWidth={1.75} />Stop</button>
		</div>
	{/if}
	{#if note && playing?.kind === 'call'}<p class="small muted">{note}</p>{/if}
	<audio
		bind:this={audio}
		bind:paused
		preload="none"
		controls={playing?.kind === 'call'}
		hidden={playing?.kind !== 'call'}
		onplaying={onPlaying}
		onwaiting={onWaiting}
		onended={() => playing?.kind === 'live' && liveDropped()}
		onerror={onError}
		style="width:100%"
	></audio>
</div>

<style>
	/* Phones and tablets: what's on now, the calls, then tuning. Wide screens: calls on
	   the left; listening and tuning in a column beside them. */
	.layout {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.side,
	.main {
		display: contents;
	}
	.now-card {
		order: 1;
	}
	.main > :global(*) {
		order: 2;
	}
	.tuning {
		order: 3;
	}
	@media (min-width: 1100px) {
		.layout {
			display: grid;
			grid-template-columns: minmax(0, 1fr) 340px;
			align-items: start;
		}
		.side,
		.main {
			display: flex;
			flex-direction: column;
			gap: var(--space-4);
		}
		.side {
			grid-column: 2;
			grid-row: 1;
			position: sticky;
			top: var(--space-4);
		}
		.main {
			grid-column: 1;
			grid-row: 1;
		}
	}
	.tune-form {
		display: grid;
		gap: var(--space-3);
		align-items: end;
	}
	@media (min-width: 700px) and (max-width: 1099px) {
		.tune-form {
			grid-template-columns: 1fr 1.2fr 1.2fr auto;
		}
	}
	.meta {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.btn.sel {
		border-color: var(--accent);
		color: var(--accent);
	}
	.grow {
		min-width: 0;
	}
	.name {
		display: block;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	li.now {
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.hot {
		color: var(--danger);
		font-weight: 600;
	}
	.kept {
		display: grid;
		place-items: center;
		width: var(--tap);
		color: var(--text-muted);
	}
	.wide-only {
		display: none;
	}
	@media (min-width: 700px) {
		.wide-only {
			display: inline;
		}
	}
	.player {
		position: sticky;
		bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom) + 8px);
		margin-top: var(--space-4);
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius-md);
		padding: var(--space-3);
		box-shadow: var(--shadow-overlay);
		display: grid;
		gap: var(--space-2);
	}
	.player[hidden] {
		display: none;
	}
	.actions {
		flex: none;
		gap: 0;
	}
	@media (min-width: 700px) {
		.player {
			bottom: var(--space-4);
		}
	}
</style>
