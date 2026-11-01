<script lang="ts">
	import { Copy, Plus } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import Avatar from '#lib/components/Avatar.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { ago, dayTime } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';
	import type { Me } from '#lib/types.ts';

	interface Invite { id: number; name: string | null; email: string | null; role: string; expires_at: string; url?: string | null; emailed?: boolean }
	interface AccessRequest { id: number; name: string; email: string; message: string | null; created_at: string }
	let people = $state<Me[]>([]);
	let requests = $state<AccessRequest[]>([]);
	let invites = $state<Invite[]>([]);
	let emailOn = $state(false);
	let inviteOpen = $state(false);
	let inv = $state({ name: '', email: '', role: 'member', days: 7, send_email: true, request_id: null as number | null });
	let created = $state<Invite | null>(null);
	let editing = $state<Me | null>(null);
	let editOpen = $state(false);
	let link = $state('');

	const ROLES = [
		['viewer', 'Viewer — can look at everything, can’t change anything'],
		['member', 'Member — can book, edit lists, move cameras, turn the camera light on and off'],
		['admin', 'Admin — everything, including auto-tracking, the siren, settings and people']
	];

	async function load() {
		try {
			[people, invites, requests] = await Promise.all([
				api.get<Me[]>('/api/admin/users'),
				api.get<Invite[]>('/api/admin/invites'),
				api.get<AccessRequest[]>('/api/admin/access-requests')
			]);
			emailOn = (await api.get<{ email: boolean }>('/api/auth/config')).email;
		} catch (e) {
			toast.error(e);
		}
	}
	$effect(() => {
		if (session.can('admin')) load();
	});

	async function createInvite(e: SubmitEvent) {
		e.preventDefault();
		try {
			created = await api.post<Invite>('/api/admin/invites', { ...inv, email: inv.email || null, name: inv.name || null, send_email: inv.send_email && !!inv.email });
			if (inv.request_id) requests = requests.filter((x) => x.id !== inv.request_id);
			load();
		} catch (err) {
			toast.error(err);
		}
	}
	function copy(text: string) {
		navigator.clipboard?.writeText(text).then(() => toast.show('Link copied.'), () => {});
	}
	async function share(url: string) {
		if (navigator.share) await navigator.share({ title: 'Cabin app invite', text: 'Set up your account for the cabin app:', url }).catch(() => {});
		else copy(url);
	}
	async function update(u: Me, patch: Record<string, unknown>) {
		try {
			Object.assign(u, await api.patch(`/api/admin/users/${u.id}`, patch));
			toast.show(`${u.name} updated.`);
		} catch (e) {
			toast.error(e);
		}
	}
	async function resetLink(u: Me) {
		try {
			link = (await api.post<{ url: string }>(`/api/admin/users/${u.id}/reset-link`)).url;
		} catch (e) {
			toast.error(e);
		}
	}
	async function signOutEverywhere(u: Me) {
		if (!confirm(`Sign ${u.name} out on every phone, tablet and computer? They can sign in again with their password or Google.`)) return;
		try {
			await api.post(`/api/admin/users/${u.id}/sign-out`);
			toast.show(`${u.name} is signed out everywhere.`);
		} catch (e) {
			toast.error(e);
		}
	}
	async function remove(u: Me) {
		if (!confirm(`Remove ${u.name}'s account? Their bookings go too. To keep history, turn the account off instead.`)) return;
		try {
			await api.del(`/api/admin/users/${u.id}`);
			editOpen = false;
			load();
		} catch (e) {
			toast.error(e);
		}
	}
	async function revoke(i: Invite) {
		await api.del(`/api/admin/invites/${i.id}`);
		load();
	}
	function openInvite(r?: AccessRequest) {
		inv = { name: r?.name ?? '', email: r?.email ?? '', role: r ? 'viewer' : 'member', days: 7, send_email: true, request_id: r?.id ?? null };
		created = null;
		inviteOpen = true;
	}
	async function dismiss(r: AccessRequest) {
		try {
			await api.post(`/api/admin/access-requests/${r.id}/dismiss`);
			requests = requests.filter((x) => x.id !== r.id);
			toast.show(`Dismissed ${r.name}'s request.`);
		} catch (e) {
			toast.error(e);
		}
	}
</script>

<div class="stack">
	<AdminNav title="People" />
	{#if session.can('admin')}
		{#if requests.length}
			<section class="card requests">
				<div class="card-head"><h2>Asking to join</h2></div>
				<ul class="list">
					{#each requests as r (r.id)}
						<li>
							<div class="grow">
								<div>{r.name} <span class="small muted">· {r.email}</span></div>
								{#if r.message}<div class="small note">“{r.message}”</div>{/if}
								<div class="small muted">Asked {ago(r.created_at)}</div>
							</div>
							<div class="row">
								<button class="btn text" onclick={() => dismiss(r)}>Dismiss</button>
								<button class="btn" onclick={() => openInvite(r)}>Invite</button>
							</div>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<section class="card">
			<div class="card-head"><h2>Everyone</h2><button class="btn" onclick={() => openInvite()}><Plus size={18} strokeWidth={1.75} />Invite</button></div>
			<ul class="list">
				{#each people as u (u.id)}
					<li>
						<Avatar person={u} size={32} />
						<div class="grow">
							<div>{u.name}{#if !u.active}<span class="chip" style="margin-left:8px">Off</span>{/if}</div>
							<div class="small muted">{u.email} · seen {ago(u.last_seen_at)}</div>
						</div>
						<span class="chip">{u.role}</span>
						<button class="btn text" onclick={() => ((editing = u), (link = ''), (editOpen = true))}>Edit</button>
					</li>
				{/each}
			</ul>
		</section>

		{#if invites.length}
			<section class="card">
				<div class="card-head"><h2>Open invites</h2></div>
				<ul class="list">
					{#each invites as i (i.id)}
						<li>
							<div class="grow"><div>{i.name ?? i.email ?? 'Invite'}</div><div class="small muted">{i.role} · expires {dayTime(i.expires_at)}</div></div>
							<button class="btn text" onclick={() => revoke(i)}>Cancel</button>
						</li>
					{/each}
				</ul>
				<p class="small muted">Invite links are only shown once. If someone lost theirs, cancel it and send a new one.</p>
			</section>
		{/if}
	{/if}
</div>

<Sheet bind:open={inviteOpen} title="Invite someone">
	{#if created?.url}
		<p>{created.emailed ? `Emailed to ${created.email}. You can also send the link yourself:` : 'Send this link by text or email. It works once.'}</p>
		<input readonly value={created.url} onfocus={(e) => (e.target as HTMLInputElement).select()} />
		<div class="row">
			<button class="btn" onclick={() => share(created!.url!)}>Share</button>
			<button class="btn secondary" onclick={() => copy(created!.url!)}><Copy size={18} strokeWidth={1.75} />Copy</button>
		</div>
	{:else}
		<form class="stack" onsubmit={createInvite}>
			<label class="field"><span>First name (optional)</span><input bind:value={inv.name} maxlength="80" /></label>
			<label class="field"><span>Email (optional)</span><input type="email" bind:value={inv.email} /></label>
			<label class="field"><span>Role</span><select bind:value={inv.role}>{#each ROLES as [v, l] (v)}<option value={v}>{l}</option>{/each}</select></label>
			<label class="field"><span>Link works for</span><select bind:value={inv.days}><option value={2}>2 days</option><option value={7}>1 week</option><option value={30}>30 days</option></select></label>
			{#if emailOn && inv.email}<label class="spread"><span>Email the invite</span><input type="checkbox" bind:checked={inv.send_email} /></label>{/if}
			<button class="btn">Create invite</button>
		</form>
	{/if}
</Sheet>

<Sheet bind:open={editOpen} title={editing?.name ?? ''}>
	{#if editing}
		{@const u = editing}
		<label class="field"><span>Role</span>
			<select value={u.role} onchange={(e) => update(u, { role: (e.target as HTMLSelectElement).value })}>{#each ROLES as [v, l] (v)}<option value={v}>{l}</option>{/each}</select>
		</label>
		<label class="spread"><span>Account turned on</span><input type="checkbox" checked={u.active} onchange={(e) => update(u, { active: (e.target as HTMLInputElement).checked })} /></label>
		<div class="small muted">Signs in with {[u.has_google && 'Google', u.has_password && 'password'].filter(Boolean).join(' and ') || 'nothing yet'}.</div>
		<div class="row wrap">
			<button class="btn secondary" onclick={() => resetLink(u)}>Make a password reset link</button>
			<button class="btn secondary" onclick={() => signOutEverywhere(u)} disabled={u.id === session.me?.id}>Sign out on all devices</button>
		</div>
		<p class="small muted">Use “Sign out on all devices” if a phone is lost or shared by mistake.</p>
		{#if link}<input readonly value={link} onfocus={(e) => (e.target as HTMLInputElement).select()} /><p class="small muted">Send this to {u.name}. It works once, for 2 days.</p>{/if}
		<div class="spread">
			<button class="btn text" style="color:var(--danger)" onclick={() => remove(u)} disabled={u.id === session.me?.id}>Remove account</button>
			<button class="btn" onclick={() => ((editOpen = false), load())}>Done</button>
		</div>
	{/if}
</Sheet>

<style>
	.requests {
		border-left: 4px solid var(--accent);
	}
	.note {
		margin: 2px 0;
		color: var(--text);
	}
	.requests li {
		flex-wrap: wrap;
	}
</style>
