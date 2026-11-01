<script lang="ts">
	import { Plus } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { ago } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	type Kind = 'reolink' | 'onvif' | 'stream';
	interface Options { main_url: string; sub_url: string; snapshot_url: string }
	interface Cam {
		id: number; name: string; kind: Kind; host: string; port: number | null; username: string; password_set: boolean;
		channel: number; options: Partial<Options>; enabled: boolean; sort: number; cooldown_s: number;
		model: string | null; firmware: string | null; capabilities: Record<string, unknown> | null;
		last_ok_at: string | null; last_error: string | null;
	}
	interface TestResult {
		ok: boolean; model?: string | null; firmware?: string | null; error?: string;
		caps?: Record<string, unknown>; streams?: string[]; channels?: number[]; nvr?: boolean;
	}

	// What each kind of camera needs, in plain words. No brand models: anything the driver supports works.
	const KINDS: { id: Kind; label: string; help: string }[] = [
		{ id: 'reolink', label: 'Reolink', help: 'Reolink cameras, NVRs and home hubs. Live view, recordings, pan/tilt, presets, auto-tracking, detections, siren and light — whatever the camera has.' },
		{ id: 'onvif', label: 'ONVIF', help: 'Most other IP cameras. Live view, pictures, pan/tilt, presets and motion alerts when the camera offers them. Turn on ONVIF in the camera’s own settings first.' },
		{ id: 'stream', label: 'Video address', help: 'Anything with an RTSP or HTTP video address. View only: no controls, recordings or alerts.' }
	];

	let s = $state<Record<string, Record<string, unknown>> | null>(null);
	let cams = $state<Cam[]>([]);
	let open = $state(false);
	let busy = $state(false);
	let f = $state(blank());
	let test = $state<TestResult | null>(null);

	function blank() {
		return {
			id: 0, name: '', kind: 'reolink' as Kind, host: '', port: '', username: '', password: '', password_set: false,
			channel: 0, main_url: '', sub_url: '', snapshot_url: '', enabled: true, sort: 0, cooldown_s: 300
		};
	}

	async function load() {
		try {
			[s, cams] = await Promise.all([api.get<typeof s>('/api/admin/settings'), api.get<Cam[]>('/api/admin/cameras')]);
		} catch (e) {
			toast.error(e);
		}
	}
	$effect(() => {
		if (session.can('admin')) load();
	});

	function edit(c?: Cam) {
		test = null;
		f = c
			? {
					id: c.id, name: c.name, kind: c.kind, host: c.kind === 'stream' ? '' : c.host, port: c.port ? String(c.port) : '',
					username: c.username, password: '', password_set: c.password_set, channel: c.channel,
					main_url: c.options.main_url ?? '', sub_url: c.options.sub_url ?? '', snapshot_url: c.options.snapshot_url ?? '',
					enabled: c.enabled, sort: c.sort, cooldown_s: c.cooldown_s
				}
			: { ...blank(), sort: cams.length };
		open = true;
	}

	const body = () => ({
		name: f.name, kind: f.kind, host: f.kind === 'stream' ? '' : f.host, port: f.port ? Number(f.port) : null,
		username: f.username, password: f.password || null, channel: Number(f.channel) || 0,
		options: f.kind === 'stream' ? { main_url: f.main_url, sub_url: f.sub_url, snapshot_url: f.snapshot_url } : {},
		enabled: f.enabled, sort: Number(f.sort) || 0, cooldown_s: Number(f.cooldown_s) || 300
	});

	async function runTest() {
		busy = true;
		test = null;
		try {
			test = await api.post<TestResult>('/api/admin/cameras/test', { ...body(), camera_id: f.id || null });
		} catch (e) {
			test = { ok: false, error: e instanceof Error ? e.message : 'That didn’t work.' };
		} finally {
			busy = false;
		}
	}
	async function save(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		try {
			if (f.id) await api.put(`/api/admin/cameras/${f.id}`, body());
			else await api.post('/api/admin/cameras', body());
			open = false;
			toast.show(`${f.name} saved. Connecting…`);
			load();
			setTimeout(load, 5000);
		} catch (err) {
			toast.error(err);
		} finally {
			busy = false;
		}
	}
	async function remove() {
		if (!confirm(`Remove the ${f.name} camera from the app? Its motion history goes too. Recordings on the camera stay.`)) return;
		try {
			await api.del(`/api/admin/cameras/${f.id}`);
			open = false;
			load();
		} catch (e) {
			toast.error(e);
		}
	}

	const CAP_WORDS: Record<string, string> = {
		ptz: 'pan/tilt', zoom: 'zoom', presets: 'presets', auto_track: 'auto-tracking', recordings: 'recordings',
		events: 'motion alerts', siren: 'siren', light: 'light'
	};
	const capList = (caps: Record<string, unknown> | null | undefined) =>
		Object.entries(CAP_WORDS).filter(([k]) => caps?.[k]).map(([, w]) => w);
	const kindLabel = (k: Kind) => KINDS.find((x) => x.id === k)?.label ?? k;
	const kindHelp = $derived(KINDS.find((k) => k.id === f.kind)?.help ?? '');
	const defaultPort = $derived(f.kind === 'onvif' ? '80 (some cameras use 8000 or 2020)' : 'automatic');

	const ALERT_FIELDS: Field[] = [
		{ key: 'default_cooldown_s', label: 'Seconds between alerts from one camera (default for new cameras)', type: 'number' }
	];
</script>

<div class="stack">
	<AdminNav title="Cameras" />
	{#if s}
		<section class="card">
			<div class="card-head"><h2>Cameras</h2><button class="btn" onclick={() => edit()}><Plus size={18} strokeWidth={1.75} />Add camera</button></div>
			{#if cams.length}
				<ul class="list">
					{#each cams as c (c.id)}
						{@const caps = capList(c.capabilities)}
						<li>
							<span class="dot" class:ok={!c.last_error && !!c.last_ok_at && c.enabled} class:bad={!!c.last_error && c.enabled} aria-hidden="true"></span>
							<div class="grow">
								<div>{c.name}{#if !c.enabled}<span class="chip" style="margin-left:8px">Off</span>{/if}</div>
								<div class="small muted">{kindLabel(c.kind)} · {c.host || 'no address'}{c.model ? ` · ${c.model}` : ''}</div>
								{#if c.last_error && c.enabled}
									<div class="small err">{c.last_error}</div>
								{:else if c.last_ok_at}
									<div class="small muted">Online {ago(c.last_ok_at)}{caps.length ? ` · ${caps.join(', ')}` : ' · view only'}</div>
								{/if}
							</div>
							<button class="btn text" onclick={() => edit(c)}>Edit</button>
						</li>
					{/each}
				</ul>
			{:else}
				<div class="empty"><p>No cameras yet.</p><p>Add one by its address on the cabin network.</p></div>
			{/if}
		</section>

		<section class="card tips">
			<h2>Before you add a camera</h2>
			<ul>
				<li>Give it a fixed address on the router so it doesn’t move.</li>
				<li>Make a separate camera login for the app in the camera’s own app, so nobody shares the main password.</li>
				<li>Set its video to H.264. Every browser can play it; H.265 only plays on some.</li>
			</ul>
		</section>

		<SettingsForm section="alerts" title="Motion alerts" fields={ALERT_FIELDS} bind:values={s.alerts}>
			{#snippet intro()}<p class="small muted">Each person picks which cameras alert them in their own Settings.</p>{/snippet}
		</SettingsForm>
	{/if}
</div>

<Sheet bind:open title={f.id ? `Edit ${f.name}` : 'Add a camera'}>
	<form class="stack" onsubmit={save}>
		<label class="field"><span>Name</span><input required maxlength="80" bind:value={f.name} placeholder="Porch" /></label>

		<fieldset class="kinds">
			<legend>Type</legend>
			<div class="pill-tabs" role="radiogroup">
				{#each KINDS as k (k.id)}
					<button type="button" role="radio" aria-checked={f.kind === k.id} class:on={f.kind === k.id} onclick={() => ((f.kind = k.id), (test = null))}>{k.label}</button>
				{/each}
			</div>
			<p class="small muted">{kindHelp}</p>
		</fieldset>

		{#if f.kind === 'stream'}
			<label class="field">
				<span>Video address</span>
				<input required bind:value={f.main_url} placeholder="rtsp://192.168.67.50:554/stream1" autocomplete="off" />
				<span class="small muted">The camera’s manual lists it. Put the login below, not in the address.</span>
			</label>
			<label class="field"><span>Smaller video address (optional)</span><input bind:value={f.sub_url} placeholder="rtsp://192.168.67.50:554/stream2" autocomplete="off" /><span class="small muted">Used for tiles and phones to save the cabin’s internet.</span></label>
			<label class="field"><span>Picture address (optional)</span><input bind:value={f.snapshot_url} placeholder="http://192.168.67.50/snapshot.jpg" autocomplete="off" /></label>
		{:else}
			<div class="grid grid-2">
				<label class="field"><span>Address on the cabin network</span><input required bind:value={f.host} placeholder="192.168.67.50" autocomplete="off" /></label>
				<label class="field"><span>Port</span><input inputmode="numeric" bind:value={f.port} placeholder={defaultPort} /></label>
			</div>
		{/if}

		<div class="grid grid-2">
			<label class="field"><span>Camera username{f.kind === 'stream' ? ' (if it has one)' : ''}</span><input required={f.kind !== 'stream'} bind:value={f.username} autocomplete="off" /></label>
			<label class="field">
				<span>Camera password</span>
				<input type="password" bind:value={f.password} autocomplete="new-password" placeholder={f.password_set ? 'Saved — leave blank to keep' : ''} />
			</label>
		</div>

		<details>
			<summary>More options</summary>
			<div class="grid grid-2" style="margin-top:12px">
				{#if f.kind === 'reolink'}
					<label class="field"><span>Channel (recorders and hubs)</span><input type="number" min="0" max="63" bind:value={f.channel} /><span class="small muted">0 for a camera on its own.</span></label>
				{/if}
				<label class="field"><span>Seconds between alerts</span><input type="number" min="30" bind:value={f.cooldown_s} /></label>
				<label class="field"><span>Order in the list</span><input type="number" bind:value={f.sort} /></label>
			</div>
		</details>

		<label class="spread"><span>Turned on</span><input type="checkbox" bind:checked={f.enabled} /></label>

		{#if test}
			{#if test.ok}
				<div class="notice">
					<div>Connected{test.model ? ` to ${test.model}` : ''}{test.firmware ? ` (${test.firmware})` : ''}.</div>
					{#if f.kind !== 'stream'}
						<div class="small muted">Can do: {capList(test.caps).join(', ') || 'live view only'}.</div>
					{/if}
					{#if test.nvr && test.channels?.length}<div class="small muted">This is a recorder with channels {test.channels.join(', ')}.</div>{/if}
				</div>
			{:else}
				<p class="notice danger">{test.error}</p>
			{/if}
		{/if}

		<div class="spread wrap">
			{#if f.id}<button type="button" class="btn text" style="color:var(--danger)" onclick={remove}>Remove</button>{:else}<span></span>{/if}
			<div class="row">
				<button type="button" class="btn secondary" onclick={runTest} disabled={busy}>{busy && !test ? 'Testing…' : 'Test'}</button>
				<button class="btn" disabled={busy}>Save</button>
			</div>
		</div>
	</form>
</Sheet>

<style>
	.dot {
		flex: none;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--line);
	}
	.dot.ok {
		background: var(--ok);
	}
	.dot.bad {
		background: var(--warn);
	}
	.err {
		color: var(--danger);
	}
	.tips ul {
		margin: var(--space-2) 0 0;
		padding-left: var(--space-5);
		color: var(--text-muted);
	}
	.tips li + li {
		margin-top: var(--space-1);
	}
	.kinds {
		border: 0;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.kinds legend {
		font-size: 13px;
		line-height: 18px;
		color: var(--text-muted);
		padding: 0;
		margin-bottom: var(--space-1);
	}
	details summary {
		cursor: pointer;
		min-height: var(--tap);
		display: flex;
		align-items: center;
		color: var(--accent);
		font-weight: 500;
	}
</style>
