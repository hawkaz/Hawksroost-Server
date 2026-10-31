<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { BellOff, Shield } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import { dayTime } from '#lib/format.ts';
	import { currentSubscription, disablePush, enablePush, isIOS, isStandalone, pushSupported } from '#lib/push.ts';
	import { session } from '#lib/session.svelte.ts';
	import { theme, type ThemePref } from '#lib/theme.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	const COLORS = ['copper', 'pine', 'navy', 'gold', 'lake', 'bark', 'sage', 'plum'];
	const welcome = page.url.searchParams.has('welcome');

	let name = $state(session.me?.name ?? '');
	let pushOn = $state(false);
	let pushBusy = $state(false);
	let canPush = $state(false);
	let devices = $state<{ id: number; device_label: string | null; last_ok_at: string | null }[]>([]);
	interface AlertCam { camera_id: number; camera_name: string; enabled: boolean; types: string[]; mute_until: string | null }
	let alerts = $state<{ types: string[]; cameras: AlertCam[]; mute_until: string | null } | null>(null);
	let pw = $state({ current: '', new: '' });

	const muted = $derived(!!session.me?.mute_until && new Date(session.me.mute_until) > new Date());
	const TYPE_LABEL: Record<string, string> = { person: 'People', vehicle: 'Vehicles', animal: 'Animals', motion: 'Any motion' };

	$effect(() => {
		canPush = pushSupported();
		currentSubscription().then((s) => (pushOn = !!s)).catch(() => {});
		loadDevices();
		api.get<typeof alerts>('/api/me/alerts').then((a) => (alerts = a)).catch(() => {});
	});
	async function loadDevices() {
		devices = await api.get<typeof devices>('/api/me/push').catch(() => []);
	}

	async function saveProfile(patch: Record<string, unknown>) {
		try {
			session.me = { ...session.me!, ...(await api.patch('/api/me', patch)) };
		} catch (e) {
			toast.error(e);
		}
	}
	async function togglePush() {
		pushBusy = true;
		try {
			if (pushOn) {
				await disablePush();
				pushOn = false;
				toast.show('Notifications off for this device.');
			} else {
				const key = session.me?.push_public_key ?? (await session.load())?.push_public_key ?? '';
				await enablePush(key);
				pushOn = true;
				toast.show('Notifications on for this device.');
			}
			await loadDevices();
		} catch (e) {
			toast.error(e);
		} finally {
			pushBusy = false;
		}
	}
	async function testPush() {
		try {
			const r = await api.post<{ sent: number }>('/api/me/push/test');
			toast.show(`Sent to ${r.sent} device${r.sent === 1 ? '' : 's'}.`);
		} catch (e) {
			toast.error(e);
		}
	}
	async function mute(minutes: number) {
		try {
			const r = await api.post<{ mute_until: string | null }>('/api/me/mute', { minutes });
			session.me = { ...session.me!, mute_until: r.mute_until };
			toast.show(minutes ? `Notifications muted until ${dayTime(r.mute_until)}.` : 'Notifications back on.');
		} catch (e) {
			toast.error(e);
		}
	}
	async function setAlert(c: AlertCam, patch: Partial<{ enabled: boolean; types: string[]; mute_minutes: number }>) {
		try {
			const r = await api.put<{ enabled: boolean; types: string[]; mute_until: string | null }>(`/api/me/alerts/${c.camera_id}`, patch);
			Object.assign(c, r);
		} catch (e) {
			toast.error(e);
		}
	}
	function toggleType(c: AlertCam, t: string) {
		const types = c.types.includes(t) ? c.types.filter((x) => x !== t) : [...c.types, t];
		setAlert(c, { types });
	}
	async function changePassword(e: SubmitEvent) {
		e.preventDefault();
		try {
			await api.post('/api/me/password', pw);
			pw = { current: '', new: '' };
			toast.show('Password saved.');
			session.load();
		} catch (err) {
			toast.error(err);
		}
	}
	async function signOut() {
		await session.logout();
		goto('/login');
	}
</script>

<div class="stack">
	<h1>Settings</h1>
	{#if welcome}<p class="notice">Welcome, {session.me?.name}. Two things to do: install the app on your phone, then turn on notifications.</p>{/if}

	{#if !isStandalone()}
		<section class="card">
			<div class="card-head"><span class="label">Install on your phone</span></div>
			{#if isIOS()}
				<p>In Safari, tap the Share button, then <strong>Add to Home Screen</strong>. Open the app from your home screen. iPhones only show notifications for installed apps.</p>
			{:else}
				<p>In Chrome or Edge, open the menu and choose <strong>Install app</strong> (or <strong>Add to Home screen</strong>).</p>
			{/if}
		</section>
	{/if}

	<section class="card stack">
		<span class="label">You</span>
		<form class="row" onsubmit={(e) => (e.preventDefault(), saveProfile({ name }))}>
			<label class="field grow"><span>First name</span><input bind:value={name} maxlength="80" /></label>
			<button class="btn secondary" style="align-self:flex-end" disabled={name === session.me?.name}>Save</button>
		</form>
		<div>
			<div class="small muted" style="margin-bottom:8px">Your colour on the calendar</div>
			<div class="row wrap">
				{#each COLORS as c (c)}
					<button class="swatch" class:on={session.me?.color === c} style="background:var(--fam-{c})" aria-label={c} aria-pressed={session.me?.color === c} onclick={() => saveProfile({ color: c })}></button>
				{/each}
			</div>
		</div>
		<div>
			<div class="small muted" style="margin-bottom:8px">Look</div>
			<div class="pill-tabs">
				{#each [['system', 'Match phone'], ['light', 'Light'], ['dark', 'Dark']] as [v, l] (v)}
					<button class:on={theme.pref === v} onclick={() => theme.set(v as ThemePref)}>{l}</button>
				{/each}
			</div>
		</div>
		<div class="small muted">{session.me?.email} · {session.me?.role === 'viewer' ? 'Viewer (can look, not change)' : session.me?.role === 'admin' ? 'Admin' : 'Member'}</div>
	</section>

	<section class="card stack">
		<span class="label">Notifications</span>
		{#if !canPush}
			<p class="muted">This browser can't get notifications.{isIOS() ? ' Install the app to your home screen first (see above), then open it from there.' : ''}</p>
		{:else}
			<div class="spread">
				<div><div>On this device</div><div class="small muted">{pushOn ? 'This device will get notifications.' : 'Off'}</div></div>
				<button class="btn {pushOn ? 'secondary' : ''}" disabled={pushBusy} onclick={togglePush}>{pushOn ? 'Turn off' : 'Turn on'}</button>
			</div>
		{/if}
		{#if devices.length}
			<div class="small muted">Your devices: {devices.map((d) => d.device_label ?? 'Device').join(', ')} · <button class="btn text" onclick={testPush}>Send a test</button></div>
		{/if}
		<label class="spread"><span>When someone books the cabin</span><input type="checkbox" checked={session.me?.notify_bookings} onchange={(e) => saveProfile({ notify_bookings: (e.target as HTMLInputElement).checked })} /></label>
		{#if session.radioEnabled}
			<label class="spread"><span>When the radio gets busy (fire, incidents)</span><input type="checkbox" checked={session.me?.notify_radio} onchange={(e) => saveProfile({ notify_radio: (e.target as HTMLInputElement).checked })} /></label>
		{/if}
		<div>
			<div class="row" style="margin-bottom:8px"><BellOff size={18} strokeWidth={1.75} /><span>{muted ? `Muted until ${dayTime(session.me?.mute_until)}` : 'Mute everything for a while'}</span></div>
			<div class="row wrap">
				{#if muted}<button class="btn" onclick={() => mute(0)}>Unmute</button>{/if}
				<button class="btn secondary" onclick={() => mute(60)}>1 hour</button>
				<button class="btn secondary" onclick={() => mute(480)}>8 hours</button>
				<button class="btn secondary" onclick={() => mute(1440)}>1 day</button>
				<button class="btn secondary" onclick={() => mute(10080)}>1 week</button>
			</div>
		</div>
	</section>

	{#if alerts?.cameras.length}
		<section class="card stack" id="alerts">
			<span class="label">Camera alerts</span>
			{#each alerts.cameras as c (c.camera_id)}
				<div class="stack" style="gap:8px">
					<label class="spread"><span>{c.camera_name}</span><input type="checkbox" checked={c.enabled} onchange={(e) => setAlert(c, { enabled: (e.target as HTMLInputElement).checked })} /></label>
					{#if c.enabled}
						<div class="row wrap">
							{#each alerts.types as t (t)}
								<button class="btn secondary chipbtn" class:sel={c.types.includes(t)} aria-pressed={c.types.includes(t)} onclick={() => toggleType(c, t)}>{TYPE_LABEL[t] ?? t}</button>
							{/each}
						</div>
						<div class="row wrap small">
							{#if c.mute_until && new Date(c.mute_until) > new Date()}
								<span class="muted">Muted until {dayTime(c.mute_until)}</span><button class="btn text" onclick={() => setAlert(c, { mute_minutes: 0 })}>Unmute</button>
							{:else}
								<span class="muted">Mute this camera:</span>
								<button class="btn text" onclick={() => setAlert(c, { mute_minutes: 60 })}>1 hour</button>
								<button class="btn text" onclick={() => setAlert(c, { mute_minutes: 1440 })}>1 day</button>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</section>
	{/if}

	<section class="card">
		<form class="stack" onsubmit={changePassword}>
			<span class="label">{session.me?.has_password ? 'Change password' : 'Add a password'}</span>
			{#if !session.me?.has_password}<p class="small muted">You sign in with Google. A password lets you sign in without it too.</p>{/if}
			{#if session.me?.has_password}<label class="field"><span>Current password</span><input type="password" autocomplete="current-password" bind:value={pw.current} required /></label>{/if}
			<label class="field"><span>New password (8 or more characters)</span><input type="password" autocomplete="new-password" minlength="8" bind:value={pw.new} required /></label>
			<button class="btn secondary" style="align-self:flex-start">Save password</button>
		</form>
	</section>

	<div class="row wrap">
		{#if session.can('admin')}<a class="btn secondary" href="/admin"><Shield size={18} strokeWidth={1.75} />Admin</a>{/if}
		<button class="btn secondary" onclick={signOut}>Sign out</button>
	</div>
</div>

<style>
	.swatch {
		width: var(--tap);
		height: var(--tap);
		border-radius: var(--radius-pill);
		border: 3px solid transparent;
		cursor: pointer;
	}
	.swatch.on {
		border-color: var(--text);
		box-shadow: inset 0 0 0 2px var(--surface);
	}
	label.spread {
		min-height: var(--tap);
	}
	.chipbtn {
		min-height: 36px;
	}
	.btn.sel {
		background: var(--primary);
		color: var(--on-primary);
		border-color: var(--primary);
	}
</style>
