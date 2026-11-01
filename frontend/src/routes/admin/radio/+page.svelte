<script lang="ts">
	import { Plus } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	interface Device { id: number; name: string; serial: string | null; index: number; gain: number; correction: number; mode: string; centerfreq: number | null; live_stream: boolean; enabled: boolean }
	interface Channel { id: number; device_id: number | null; group: string; label: string; freq_mhz: number; modulation: string; squelch_snr: number | null; ctcss: number | null; incident: boolean; enabled: boolean; sort: number }
	interface Plan { changed?: boolean; errors: string[]; devices: { id: number; name: string; mode: string; centerfreq: number | null; channels: number; mount: string | null }[] }

	let settings = $state<Record<string, unknown> | null>(null);
	let devices = $state<Device[]>([]);
	let channels = $state<Channel[]>([]);
	let plan = $state<Plan | null>(null);

	let devOpen = $state(false);
	let dform = $state<Device>({ id: 0, name: '', serial: '', index: 0, gain: 32, correction: 0, mode: 'auto', centerfreq: null, live_stream: true, enabled: true });
	let chOpen = $state(false);
	let cform = $state<Channel>({ id: 0, device_id: null, group: '', label: '', freq_mhz: 154, modulation: 'nfm', squelch_snr: null, ctcss: null, incident: false, enabled: true, sort: 0 });

	async function load() {
		try {
			const all = await api.get<Record<string, Record<string, unknown>>>('/api/admin/settings');
			settings = all.radio;
			const r = await api.get<{ devices: Device[]; channels: Channel[]; plan: Plan | null }>('/api/admin/radio');
			devices = r.devices;
			channels = r.channels;
			plan = r.plan;
		} catch (e) {
			toast.error(e);
		}
	}
	$effect(() => {
		if (session.can('admin')) load();
	});

	function editDevice(d?: Device) {
		dform = d ? { ...d, serial: d.serial ?? '' } : { id: 0, name: `Dongle ${devices.length + 1}`, serial: '', index: devices.length, gain: 32, correction: 0, mode: 'auto', centerfreq: null, live_stream: true, enabled: true };
		devOpen = true;
	}
	async function saveDevice(e: SubmitEvent) {
		e.preventDefault();
		const body = { ...dform, serial: dform.serial || null, centerfreq: dform.centerfreq || null };
		try {
			if (dform.id) await api.put(`/api/admin/radio/devices/${dform.id}`, body);
			else await api.post('/api/admin/radio/devices', body);
			devOpen = false;
			load();
		} catch (err) {
			toast.error(err);
		}
	}
	async function deleteDevice() {
		if (!confirm('Remove this dongle? Its channels stay but become unassigned.')) return;
		try {
			await api.del(`/api/admin/radio/devices/${dform.id}`);
			devOpen = false;
			load();
		} catch (e) {
			toast.error(e);
		}
	}
	function editChannel(c?: Channel) {
		cform = c ? { ...c } : { id: 0, device_id: devices[0]?.id ?? null, group: channels[0]?.group ?? 'Fire/EMS', label: '', freq_mhz: 154, modulation: 'nfm', squelch_snr: null, ctcss: null, incident: false, enabled: true, sort: channels.length };
		chOpen = true;
	}
	async function saveChannel(e: SubmitEvent) {
		e.preventDefault();
		const num = (v: unknown) => (v === null || v === '' || v === undefined ? null : Number(v));
		const body = { ...cform, ctcss: num(cform.ctcss), freq_mhz: Number(cform.freq_mhz), squelch_snr: cform.squelch_snr === null || (cform.squelch_snr as unknown) === '' ? null : Number(cform.squelch_snr), device_id: cform.device_id ? Number(cform.device_id) : null };
		try {
			if (cform.id) await api.put(`/api/admin/radio/channels/${cform.id}`, body);
			else await api.post('/api/admin/radio/channels', body);
			chOpen = false;
			load();
		} catch (err) {
			toast.error(err);
		}
	}
	async function quickToggle(c: Channel, enabled: boolean) {
		try {
			await api.put(`/api/admin/radio/channels/${c.id}`, { ...c, enabled });
			c.enabled = enabled;
		} catch (e) {
			toast.error(e);
		}
	}
	async function deleteChannel() {
		if (!confirm(`Delete ${cform.label}?`)) return;
		try {
			await api.del(`/api/admin/radio/channels/${cform.id}`);
			chOpen = false;
			load();
		} catch (e) {
			toast.error(e);
		}
	}
	async function seed() {
		try {
			const r = await api.post<{ added: number }>('/api/admin/radio/seed');
			toast.show(`Added ${r.added} channels. The core set is on; press Apply when ready.`);
			load();
		} catch (e) {
			toast.error(e);
		}
	}
	async function apply() {
		try {
			plan = await api.post<Plan>('/api/admin/radio/apply');
			toast.show(plan.errors.length ? 'Saved, with problems — see below.' : 'Saved. The recorder restarts in a few seconds.');
			session.refreshFeatures();
		} catch (e) {
			toast.error(e);
		}
	}

	const F: Field[] = [
		{ key: 'enabled', label: 'Radio scanner on', type: 'checkbox' },
		{ key: 'join_gap_s', label: 'Join replies within this many seconds into one call', type: 'number', help: 'A transmission that follows the last one on the same channel within this time is added to the same recording, so a back-and-forth is one call. 0 saves every transmission on its own.' },
		{ key: 'min_call_s', label: 'Don’t save calls shorter than (seconds)', type: 'number', help: 'Counts the whole call after joining. Gets rid of key-ups and static bursts. 0 keeps everything.' },
		{ key: 'max_storage_gb', label: 'Storage limit for calls (GB)', type: 'number', help: 'Oldest calls are removed first. Kept calls are never removed.' },
		{ key: 'max_age_days', label: 'Keep calls for (days)', type: 'number' },
		{ key: 'incident_tx_count', label: 'Busy alert: this many calls…', type: 'number' },
		{ key: 'incident_window_min', label: '…within this many minutes', type: 'number' },
		{ key: 'incident_cooldown_min', label: 'Busy ends after this many quiet minutes', type: 'number' }
	];
	const devName = (id: number | null) => devices.find((d) => d.id === id)?.name ?? 'No dongle';
</script>

<div class="stack">
	<AdminNav title="Radio" />
	{#if settings}
		<SettingsForm section="radio" title="Radio scanner" fields={F} bind:values={settings}>
			{#snippet intro()}<p class="small muted">The recorder also has to be started on the server (see the deploy guide, “Radio”). After changing dongles or channels, press <strong>Apply</strong> below.</p>{/snippet}
		</SettingsForm>

		<section class="card">
			<div class="card-head"><h2>Dongles</h2><button class="btn secondary" onclick={() => editDevice()}><Plus size={18} strokeWidth={1.75} />Add</button></div>
			{#if devices.length}
				<ul class="list">
					{#each devices as d (d.id)}
						{@const p = plan?.devices.find((x) => x.id === d.id)}
						<li>
							<div class="grow">
								<div>{d.name}{#if !d.enabled}<span class="chip" style="margin-left:8px">Off</span>{/if}</div>
								<div class="small muted">{d.serial ? `Serial ${d.serial}` : `USB #${d.index}`} · gain {d.gain} · {p ? `${p.mode}${p.centerfreq ? ` at ${p.centerfreq.toFixed(3)} MHz` : ''}` : d.mode}</div>
							</div>
							<button class="btn text" onclick={() => editDevice(d)}>Edit</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="muted">No dongles yet.</p>
			{/if}
		</section>

		<section class="card">
			<div class="card-head">
				<h2>Channels</h2>
				<div class="row">
					{#if !channels.length}<button class="btn secondary" onclick={seed}>Load Mormon Lake list</button>{/if}
					<button class="btn secondary" onclick={() => editChannel()}><Plus size={18} strokeWidth={1.75} />Add</button>
				</div>
			</div>
			{#if channels.length}
				<ul class="list">
					{#each channels as c (c.id)}
						<li>
							<input type="checkbox" checked={c.enabled} aria-label={`${c.label} on`} onchange={(e) => quickToggle(c, (e.target as HTMLInputElement).checked)} />
							<div class="grow">
								<div>{c.label}{#if c.incident}<span class="chip warn" style="margin-left:8px">Alerts</span>{/if}</div>
								<div class="small muted"><span class="data">{c.freq_mhz.toFixed(4)}</span>{c.ctcss ? ` · tone ${c.ctcss}` : ''} · {c.modulation.toUpperCase()} · {c.group} · {devName(c.device_id)}</div>
							</div>
							<button class="btn text" onclick={() => editChannel(c)}>Edit</button>
						</li>
					{/each}
				</ul>
			{/if}
			<p class="small muted" style="margin-top:12px">The Mormon Lake list was researched from RadioReference, the Forest Service communications guide and a local Broadcastify feed (sources in docs/RADIO.md). Twelve core channels start on. Sheriff channels may have gone digital: if they sound like data noise, turn them off.</p>
		</section>

		<section class="card stack">
			<div class="spread"><h2>Apply</h2><button class="btn" onclick={apply}>Apply to recorder</button></div>
			{#if plan}
				{#each plan.devices as d (d.id)}
					<div class="small">{d.name}: {d.mode === 'off' ? 'no channels on' : `${d.mode}, ${d.channels} channels${d.centerfreq ? `, centred on ${d.centerfreq.toFixed(3)} MHz` : ''}`}</div>
				{/each}
				{#each plan.errors as e, i (i)}<p class="notice danger">{e}</p>{/each}
			{/if}
		</section>
	{/if}
</div>

<Sheet bind:open={devOpen} title={dform.id ? `Edit ${dform.name}` : 'Add a dongle'}>
	<form class="stack" onsubmit={saveDevice}>
		<label class="field"><span>Name</span><input required bind:value={dform.name} /></label>
		<div class="grid grid-2">
			<label class="field"><span>Serial (needed with 2+ dongles)</span><input bind:value={dform.serial} placeholder="00000001" /></label>
			<label class="field"><span>USB index (if no serial)</span><input type="number" min="0" bind:value={dform.index} /></label>
			<label class="field"><span>Gain (dB)</span><input type="number" step="0.1" min="0" max="50" bind:value={dform.gain} /></label>
			<label class="field"><span>PPM correction</span><input type="number" bind:value={dform.correction} /></label>
			<label class="field"><span>Mode</span><select bind:value={dform.mode}><option value="auto">Automatic</option><option value="multichannel">All at once (channels within ~1.6 MHz)</option><option value="scan">Scan (hop between channels)</option></select></label>
			<label class="field"><span>Centre MHz (blank = automatic)</span><input type="number" step="0.001" bind:value={dform.centerfreq} /></label>
		</div>
		<label class="spread"><span>Live listening stream</span><input type="checkbox" bind:checked={dform.live_stream} /></label>
		<label class="spread"><span>Turned on</span><input type="checkbox" bind:checked={dform.enabled} /></label>
		<div class="spread">
			{#if dform.id}<button type="button" class="btn text" style="color:var(--danger)" onclick={deleteDevice}>Remove</button>{:else}<span></span>{/if}
			<button class="btn">Save</button>
		</div>
	</form>
</Sheet>

<Sheet bind:open={chOpen} title={cform.id ? `Edit ${cform.label}` : 'Add a channel'}>
	<form class="stack" onsubmit={saveChannel}>
		<div class="grid grid-2">
			<label class="field"><span>Name</span><input required maxlength="80" bind:value={cform.label} placeholder="Ponderosa Dispatch" /></label>
			<label class="field"><span>Group</span><input required maxlength="40" bind:value={cform.group} list="groups" /></label>
			<datalist id="groups">{#each [...new Set(channels.map((c) => c.group))] as g (g)}<option value={g}></option>{/each}</datalist>
			<label class="field"><span>Frequency (MHz)</span><input type="number" step="0.0001" required bind:value={cform.freq_mhz} /></label>
			<label class="field"><span>Modulation</span><select bind:value={cform.modulation}><option value="nfm">NFM (public safety)</option><option value="am">AM (aircraft)</option></select></label>
			<label class="field"><span>Squelch dB (blank = default 9)</span><input type="number" step="0.5" bind:value={cform.squelch_snr} /></label>
			<label class="field"><span>Tone / CTCSS Hz (blank = none)</span><input type="number" step="0.1" bind:value={cform.ctcss} placeholder="e.g. 114.8" /></label>
			<label class="field"><span>Dongle</span><select bind:value={cform.device_id}>{#each devices as d (d.id)}<option value={d.id}>{d.name}</option>{/each}</select></label>
		</div>
		<label class="spread"><span>Busy alerts (fire, incidents)</span><input type="checkbox" bind:checked={cform.incident} /></label>
		<label class="spread"><span>Turned on</span><input type="checkbox" bind:checked={cform.enabled} /></label>
		<div class="spread">
			{#if cform.id}<button type="button" class="btn text" style="color:var(--danger)" onclick={deleteChannel}>Delete</button>{:else}<span></span>{/if}
			<button class="btn">Save</button>
		</div>
	</form>
</Sheet>
