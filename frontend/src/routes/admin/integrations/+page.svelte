<script lang="ts">
	import { Copy, Plus } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import LoginPhoto from '#lib/components/admin/LoginPhoto.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { ago } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	type Values = Record<string, unknown>;
	let s = $state<Record<string, Values> | null>(null);
	let tempestSeen = $state<Record<string, string>>({});

	interface Cam {
		id: number; name: string; host: string; port: number | null; username: string; password_set: boolean;
		channel: number; enabled: boolean; sort: number; cooldown_s: number; model: string | null; firmware: string | null;
		capabilities: Record<string, unknown>; last_ok_at: string | null; last_error: string | null;
	}
	let cams = $state<Cam[]>([]);
	let camOpen = $state(false);
	let cform = $state({ id: 0, name: '', host: '', port: '', username: '', password: '', channel: 0, enabled: true, sort: 0, cooldown_s: 300 });
	let testResult = $state<{ ok: boolean; model?: string; firmware?: string; error?: string } | null>(null);
	let testTo = $state(session.me?.email ?? '');

	async function load() {
		try {
			s = await api.get('/api/admin/settings');
			cams = await api.get('/api/admin/cameras');
			tempestSeen = await api.get('/api/admin/tempest/devices');
		} catch (e) {
			toast.error(e);
		}
	}
	$effect(() => {
		if (session.can('admin')) load();
	});

	function editCam(c?: Cam) {
		testResult = null;
		cform = c
			? { id: c.id, name: c.name, host: c.host, port: c.port ? String(c.port) : '', username: c.username, password: '', channel: c.channel, enabled: c.enabled, sort: c.sort, cooldown_s: c.cooldown_s }
			: { id: 0, name: '', host: '', port: '', username: 'admin', password: '', channel: 0, enabled: true, sort: cams.length, cooldown_s: 300 };
		camOpen = true;
	}
	const camBody = () => ({ ...cform, port: cform.port ? Number(cform.port) : null, password: cform.password || null });
	async function testCam() {
		testResult = { ok: false, error: 'Testing…' };
		try {
			testResult = await api.post('/api/admin/cameras/test', { ...camBody(), camera_id: cform.id || null });
		} catch (e) {
			testResult = { ok: false, error: e instanceof Error ? e.message : 'Failed' };
		}
	}
	async function saveCam(e: SubmitEvent) {
		e.preventDefault();
		try {
			if (cform.id) await api.put(`/api/admin/cameras/${cform.id}`, camBody());
			else await api.post('/api/admin/cameras', camBody());
			camOpen = false;
			toast.show('Camera saved. Connecting…');
			setTimeout(load, 4000);
			load();
		} catch (err) {
			toast.error(err);
		}
	}
	async function deleteCam() {
		if (!confirm(`Remove the ${cform.name} camera from the app? Its motion history goes too.`)) return;
		await api.del(`/api/admin/cameras/${cform.id}`);
		camOpen = false;
		load();
	}
	async function testEmail() {
		try {
			await api.post('/api/admin/settings/email/test', { to: testTo });
			toast.show(`Test email sent to ${testTo}.`);
		} catch (e) {
			toast.error(e);
		}
	}
	async function backupNow() {
		try {
			const r = await api.post<{ detail: string }>('/api/admin/backup');
			toast.show(r.detail);
		} catch (e) {
			toast.error(e);
		}
	}
	function copy(t: string) {
		navigator.clipboard?.writeText(t).then(() => toast.show('Copied.'));
	}

	const F: Record<string, Field[]> = {
		general: [
			{ key: 'site_name', label: 'App name' },
			{ key: 'public_url', label: 'Public address', type: 'url', placeholder: 'https://hawksroost.live', help: 'Used in invite links, emails and Google sign-in.' },
			{ key: 'units', label: 'Units', type: 'select', options: [['imperial', '°F, mph, inches'], ['metric', '°C, km/h, mm']] }
		],
		tempest: [
			{ key: 'enabled', label: 'Listen for the Tempest hub', type: 'checkbox' },
			{ key: 'serial', label: 'Station serial (optional)', placeholder: 'ST-00012345', help: 'Only needed if a neighbour’s Tempest shows up on your network.' },
			{ key: 'station_id', label: 'Station ID (for the forecast, optional)', placeholder: '12345' },
			{ key: 'api_token', label: 'Personal access token (for the forecast, optional)', type: 'password', help: 'tempestwx.com → Settings → Data Authorizations → Create Token.' }
		],
		starlink: [
			{ key: 'enabled', label: 'Watch the Starlink dish', type: 'checkbox' },
			{ key: 'address', label: 'Dish address', placeholder: '192.168.100.1:9200' },
			{ key: 'billing_day', label: 'Billing cycle starts on day', type: 'number' }
		],
		email: [
			{ key: 'enabled', label: 'Send email', type: 'checkbox' },
			{ key: 'host', label: 'SMTP server', placeholder: 'smtp-relay.brevo.com' },
			{ key: 'port', label: 'Port', type: 'number' },
			{ key: 'username', label: 'SMTP login', help: 'Brevo: SMTP & API → SMTP tab → Login.' },
			{ key: 'password', label: 'SMTP key', type: 'password', help: 'Brevo: SMTP & API → SMTP tab → Generate a new SMTP key.' },
			{ key: 'from_email', label: 'From address', type: 'email', help: 'Must be a sender or domain verified in Brevo.' },
			{ key: 'from_name', label: 'From name' }
		],
		google: [
			{ key: 'enabled', label: 'Allow “Continue with Google”', type: 'checkbox' },
			{ key: 'client_id', label: 'Client ID' },
			{ key: 'client_secret', label: 'Client secret', type: 'password' }
		],
		alerts: [{ key: 'default_cooldown_s', label: 'Default seconds between alerts from one camera', type: 'number' }],
		backup: [
			{ key: 'enabled', label: 'Back up the database every night', type: 'checkbox' },
			{ key: 'hour', label: 'Hour to run (0–23, cabin time)', type: 'number' },
			{ key: 'keep_days', label: 'Days of backups to keep on the laptop', type: 'number' }
		]
	};
</script>

<div class="stack">
	<AdminNav />
	{#if s}
		<section class="card">
			<div class="card-head"><h2>Cameras</h2><button class="btn" onclick={() => editCam()}><Plus size={18} strokeWidth={1.75} />Add</button></div>
			{#if cams.length}
				<ul class="list">
					{#each cams as c (c.id)}
						<li>
							<div class="grow">
								<div>{c.name}{#if !c.enabled}<span class="chip" style="margin-left:8px">Off</span>{/if}</div>
								<div class="small muted">{c.host} · {c.model ?? 'not connected yet'}{c.firmware ? ` · ${c.firmware}` : ''}</div>
								{#if c.last_error}<div class="small" style="color:var(--danger)">{c.last_error}</div>{:else if c.last_ok_at}<div class="small muted">Online {ago(c.last_ok_at)}</div>{/if}
							</div>
							<button class="btn text" onclick={() => editCam(c)}>Edit</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="muted">No cameras yet. Add the TrackMix by its address on the cabin network.</p>
			{/if}
			<p class="small muted" style="margin-top:12px">
				Tips: give the camera a fixed address on your router; make a separate camera user for the app in the Reolink app; set the camera's video to H.264 so every browser can play it.
			</p>
		</section>

		<SettingsForm section="general" title="General" fields={F.general} bind:values={s.general} />

		<LoginPhoto />

		<SettingsForm section="tempest" title="Tempest weather" fields={F.tempest} bind:values={s.tempest}>
			{#snippet intro()}
				<p class="small muted">Live readings come straight from the hub on the cabin network — nothing to fill in. {#if Object.keys(tempestSeen).length}Heard on the network: <span class="data">{Object.keys(tempestSeen).join(', ')}</span>{:else}No Tempest heard yet.{/if}</p>
			{/snippet}
		</SettingsForm>

		<SettingsForm section="starlink" title="Starlink" fields={F.starlink} bind:values={s.starlink} />

		<SettingsForm section="email" title="Email (Brevo)" fields={F.email} bind:values={s.email}>
			{#snippet intro()}<p class="small muted">Used for invites and “forgot password”. Without it, you share links yourself.</p>{/snippet}
			{#snippet actions()}
				<input type="email" bind:value={testTo} style="max-width:240px" aria-label="Send test to" />
				<button type="button" class="btn secondary" onclick={testEmail}>Send test</button>
			{/snippet}
		</SettingsForm>

		<SettingsForm section="google" title="Google sign-in" fields={F.google} bind:values={s.google}>
			{#snippet intro()}
				<div class="small muted stack" style="gap:8px">
					<p>In Google Cloud Console: APIs &amp; Services → Credentials → Create credentials → OAuth client ID → Web application. Add this as an authorised redirect URI:</p>
					<div class="row"><input readonly value={s!.google.redirect_uri as string} /><button type="button" class="btn icon secondary" aria-label="Copy" onclick={() => copy(s!.google.redirect_uri as string)}><Copy size={18} strokeWidth={1.75} /></button></div>
					<p>OAuth consent screen: External, publishing status “In production” (only the basic email/profile scopes are used, so no Google review is needed).</p>
				</div>
			{/snippet}
		</SettingsForm>

		<SettingsForm section="alerts" title="Camera alerts" fields={F.alerts} bind:values={s.alerts} />

		<SettingsForm section="backup" title="Backups" fields={F.backup} bind:values={s.backup}>
			{#snippet intro()}<p class="small muted">Copies go to the laptop's data/backups folder.</p>{/snippet}
			{#snippet actions()}<button type="button" class="btn secondary" onclick={backupNow}>Back up now</button>{/snippet}
		</SettingsForm>
	{/if}
</div>

<Sheet bind:open={camOpen} title={cform.id ? `Edit ${cform.name}` : 'Add a camera'}>
	<form class="stack" onsubmit={saveCam}>
		<label class="field"><span>Name</span><input required maxlength="80" bind:value={cform.name} placeholder="Porch" /></label>
		<div class="grid grid-2">
			<label class="field"><span>Address on the cabin network</span><input required bind:value={cform.host} placeholder="192.168.1.50" /></label>
			<label class="field"><span>Port (blank = automatic)</span><input inputmode="numeric" bind:value={cform.port} /></label>
			<label class="field"><span>Camera username</span><input required bind:value={cform.username} autocomplete="off" /></label>
			<label class="field"><span>Camera password</span><input type="password" bind:value={cform.password} autocomplete="new-password" placeholder={cform.id ? 'Saved — leave blank to keep' : ''} /></label>
			<label class="field"><span>Seconds between alerts</span><input type="number" min="30" bind:value={cform.cooldown_s} /></label>
			<label class="field"><span>Order</span><input type="number" bind:value={cform.sort} /></label>
		</div>
		<label class="spread"><span>Turned on</span><input type="checkbox" bind:checked={cform.enabled} /></label>
		{#if testResult}
			<p class="notice {testResult.ok ? '' : 'danger'}">{testResult.ok ? `Connected: ${testResult.model} (${testResult.firmware})` : testResult.error}</p>
		{/if}
		<div class="spread wrap">
			{#if cform.id}<button type="button" class="btn text" style="color:var(--danger)" onclick={deleteCam}>Remove</button>{:else}<span></span>{/if}
			<div class="row"><button type="button" class="btn secondary" onclick={testCam}>Test</button><button class="btn">Save</button></div>
		</div>
	</form>
</Sheet>
