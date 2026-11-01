<script lang="ts">
	import { page } from '$app/state';
	import { Download, Headphones, Pause, Play, Star, Trash2 } from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import { ago, dayTime, duration, time } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	interface Status {
		enabled: boolean;
		active: { channel_id: number | null; label: string; group: string | null; freq_mhz: number | null; since: string }[];
		live: { device_id: number; name: string; mode: string; url: string }[];
		last_recording_at: string | null;
		incidents: { id: number; label: string; started_at: string; tx_count: number }[];
		tune: { freq_mhz: number; modulation: 'nfm' | 'am'; by: string | null; until: string | null } | null;
		scan_channels: number;
	}
	interface Channel { id: number; group: string; label: string; freq_mhz: number; incident: boolean }
	interface Rec { id: number; channel_id: number | null; group: string | null; label: string; freq_mhz: number | null; started_at: string; duration_s: number; keep: boolean; parts: number; url: string }

	let status = $state<Status | null>(null);
	let channels = $state<Channel[]>([]);
	let recs = $state<Rec[]>([]);
	let group = $state<string | null>(null);
	let channel = $state<number | null>(Number(page.url.searchParams.get('channel')) || null);
	let keptOnly = $state(false);
	let more = $state(true);
	let current = $state<Rec | null>(null);
	let audio: HTMLAudioElement | undefined = $state();
	let paused = $state(true);
	let liveUrl = $state<string | null>(null);

	const groups = $derived([...new Set(channels.map((c) => c.group))]);
	const freq = (f: number | null) => (f ? `${f.toFixed(4)} MHz` : '');

	async function loadStatus() {
		status = await api.get<Status>('/api/radio/status').catch(() => status);
	}
	async function loadRecs(append = false) {
		const before = append && recs.length ? recs[recs.length - 1].started_at : undefined;
		try {
			const rows = await api.get<Rec[]>(`/api/radio/recordings${qs({ group: group ?? undefined, channel_id: channel ?? undefined, keep: keptOnly || undefined, before, limit: 60 })}`);
			recs = append ? [...recs, ...rows] : rows;
			more = rows.length === 60;
		} catch (e) {
			toast.error(e);
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
		loadRecs();
		const t = setInterval(() => !document.hidden && !current && loadRecs(), 20000);
		return () => clearInterval(t);
	});

	function play(r: Rec) {
		liveUrl = null;
		if (current?.id === r.id && audio) {
			if (audio.paused) audio.play();
			else audio.pause();
			return;
		}
		current = r;
		queueMicrotask(() => audio?.play().catch(() => {}));
	}
	function listenLive(url: string) {
		current = null;
		liveUrl = liveUrl === url ? null : url;
	}
	async function keep(r: Rec) {
		try {
			r.keep = (await api.put<{ keep: boolean }>(`/api/radio/recordings/${r.id}/keep`, { keep: !r.keep })).keep;
			toast.show(r.keep ? 'Kept — it won’t be cleaned up.' : 'No longer kept.');
		} catch (e) {
			toast.error(e);
		}
	}
	async function remove(r: Rec) {
		if (!confirm(`Delete this ${r.label} call from ${dayTime(r.started_at)}?${r.keep ? ' It’s marked to keep.' : ''}`)) return;
		try {
			await api.del(`/api/radio/recordings/${r.id}`);
			if (current?.id === r.id) current = null;
			recs = recs.filter((x) => x.id !== r.id);
			toast.show('Call deleted.');
		} catch (e) {
			toast.error(e);
		}
	}
	// --- Tuning: scan the channel list, or sit on one frequency ---
	const canTune = $derived(session.can('edit'));
	let manualOpen = $state(false);
	let tuneForm = $state({ freq: '', modulation: 'nfm' as 'nfm' | 'am', minutes: 60 });
	let tuning = $state(false);
	const tuned = $derived(!!status?.tune);
	// Show the current frequency in the form when the page opens while tuned.
	$effect(() => {
		const t = status?.tune;
		if (t && !tuneForm.freq) tuneForm = { freq: t.freq_mhz.toFixed(4), modulation: t.modulation, minutes: tuneForm.minutes };
	});
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
		<section class="card stack">
			<div class="spread">
				{#if status.active.length}
					<span class="chip live pulse">Active</span>
				{:else}
					<span class="chip">{tuned ? 'Tuned' : 'Scanning'}</span>
				{/if}
				<span class="small muted">Last call {ago(status.last_recording_at)}</span>
			</div>
			{#if status.active.length}
				{#each status.active as a (a.label + a.since)}
					<div class="spread"><strong>{a.label} is active.</strong><span class="data">{freq(a.freq_mhz)}</span></div>
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
						<button class="btn {liveUrl === l.url ? '' : 'secondary'}" onclick={() => listenLive(l.url)}>
							<Headphones size={18} strokeWidth={1.75} />{liveUrl === l.url ? 'Stop listening' : `Listen live${status.live.length > 1 ? ` · ${l.name}` : ''}`}
						</button>
					{/each}
				</div>
				{#if liveUrl}<audio src={liveUrl} controls autoplay style="width:100%"></audio>{/if}
			{/if}
		</section>

		<section class="card stack tuning">
			<div class="spread wrap">
				<h2 class="h3">Tuning</h2>
				{#if canTune}
					<div class="pill-tabs" role="group" aria-label="Tuning">
						<button class:on={!tuned && !manualOpen} disabled={tuning} onclick={() => (tuned ? backToScan() : (manualOpen = false))}>Scan channels</button>
						<button class:on={tuned || manualOpen} disabled={tuning} onclick={openManual}>One frequency</button>
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
			{#if canTune && (manualOpen || tuned)}
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

		<div class="row wrap">
			<button class="btn secondary" class:sel={!group && !channel} onclick={() => ((group = null), (channel = null))}>All</button>
			{#each groups as g (g)}
				<button class="btn secondary" class:sel={group === g} onclick={() => ((group = g), (channel = null))}>{g}</button>
			{/each}
			<button class="btn secondary" class:sel={keptOnly} onclick={() => (keptOnly = !keptOnly)}><Star size={16} strokeWidth={1.75} />Kept</button>
		</div>

		<section class="card">
			{#if recs.length}
				<ul class="list">
					{#each recs as r (r.id)}
						<li class:now={current?.id === r.id}>
							<button class="btn icon secondary" aria-label={`Play ${r.label}`} onclick={() => play(r)}>
								{#if current?.id === r.id && !paused}<Pause size={18} strokeWidth={1.75} />{:else}<Play size={18} strokeWidth={1.75} />{/if}
							</button>
							<div class="grow">
								<div class:hot={r.channel_id !== null && activeIds.has(r.channel_id)}>{r.label}</div>
								<div class="small muted"><span class="data">{dayTime(r.started_at)}</span> · {duration(r.duration_s)}{r.parts > 1 ? ` · ${r.parts} transmissions` : ''}{r.freq_mhz ? ` · ${freq(r.freq_mhz)}` : ''}</div>
							</div>
							{#if session.can('edit')}
								<button class="btn icon" aria-label={r.keep ? 'Stop keeping' : 'Keep'} aria-pressed={r.keep} onclick={() => keep(r)}>
									<Star size={18} strokeWidth={1.75} fill={r.keep ? 'currentColor' : 'none'} />
								</button>
							{:else if r.keep}<Star size={18} strokeWidth={1.75} fill="currentColor" />{/if}
							<a class="btn icon" href={`${r.url}?download=1`} aria-label="Download"><Download size={18} strokeWidth={1.75} /></a>
							{#if session.can('admin')}
								<button class="btn icon" aria-label="Delete this call" onclick={() => remove(r)}><Trash2 size={18} strokeWidth={1.75} /></button>
							{/if}
						</li>
					{/each}
				</ul>
				{#if more}<button class="btn text" onclick={() => loadRecs(true)}>Older calls</button>{/if}
			{:else}
				<p class="muted">No calls recorded{group ? ` for ${group}` : ''} yet.</p>
			{/if}
		</section>
	{/if}
</div>

{#if current}
	<div class="player">
		<div class="small"><strong>{current.label}</strong> · <span class="data">{dayTime(current.started_at)}</span></div>
		<audio bind:this={audio} bind:paused src={current.url} controls style="width:100%"></audio>
	</div>
{/if}

<style>
	.h3 {
		font: 600 17px/24px var(--font-display);
	}
	.tune-form {
		display: grid;
		gap: var(--space-3);
		align-items: end;
	}
	@media (min-width: 700px) {
		.tune-form {
			grid-template-columns: 1fr 1.2fr 1.2fr auto;
		}
	}
	.btn.sel {
		border-color: var(--accent);
		color: var(--accent);
	}
	li.now {
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.hot {
		color: var(--danger);
		font-weight: 600;
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
	}
	@media (min-width: 900px) {
		.player {
			bottom: var(--space-4);
		}
	}
</style>
