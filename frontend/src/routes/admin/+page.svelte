<script lang="ts">
	import { ChevronRight } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import { ADMIN_SECTIONS } from '#lib/components/admin/sections.ts';
	import { session } from '#lib/session.svelte.ts';

	interface Item { name: string; ok: boolean; detail: string }
	let items = $state<Item[]>([]);
	let people = $state<number | null>(null);
	let asking = $state(0);

	$effect(() => {
		if (!session.can('admin')) return;
		api.get<{ items: Item[] }>('/api/admin/health').then((h) => (items = h.items)).catch(() => {});
		api.get<unknown[]>('/api/admin/users').then((u) => (people = u.length)).catch(() => {});
		api.get<unknown[]>('/api/admin/access-requests').then((r) => (asking = r.length)).catch(() => {});
	});

	const find = (name: string) => items.find((i) => i.name === name);
	type Status = { text: string; tone: 'ok' | 'warn' | 'note' | '' };

	// One line per section: what's going on there right now.
	const status = $derived.by((): Record<string, Status> => {
		const out: Record<string, Status> = {};
		out['/admin/people'] = asking
			? { text: `${asking} asking to join`, tone: 'note' }
			: { text: people === null ? '' : `${people} ${people === 1 ? 'person' : 'people'}`, tone: '' };

		const cams = items.filter((i) => i.name.startsWith('Camera · '));
		const up = cams.filter((c) => c.ok).length;
		out['/admin/cameras'] = cams.length
			? { text: up === cams.length ? `${cams.length} online` : `${cams.length - up} of ${cams.length} offline`, tone: up === cams.length ? 'ok' : 'warn' }
			: { text: items.length ? 'None added yet' : '', tone: '' };

		const fromItem = (name: string, off: string): Status => {
			const i = find(name);
			return i ? { text: i.detail, tone: i.ok ? 'ok' : 'warn' } : { text: items.length ? off : '', tone: '' };
		};
		out['/admin/weather'] = fromItem('Tempest', 'Turned off');
		out['/admin/starlink'] = fromItem('Starlink', 'Turned off');
		out['/admin/radio'] = fromItem('Radio recorder', 'Turned off');

		const email = find('Email');
		const google = find('Google sign-in');
		const emailWord = !email ? '' : email.ok ? 'Email on' : email.detail.startsWith('Not set up') ? 'No email' : 'Email is failing';
		out['/admin/sign-in'] = email
			? { text: [emailWord, google?.ok ? 'Google on' : ''].filter(Boolean).join(' · '), tone: emailWord === 'Email is failing' ? 'warn' : '' }
			: { text: '', tone: '' };

		const sys = ['Disk', 'Collector', 'Video server', 'Backup'].map(find).filter(Boolean) as Item[];
		const bad = sys.filter((i) => !i.ok);
		out['/admin/system'] = sys.length
			? { text: bad.length ? `${bad.map((b) => b.name).join(', ')} need${bad.length === 1 ? 's' : ''} a look` : 'All good', tone: bad.length ? 'warn' : 'ok' }
			: { text: '', tone: '' };
		out['/admin/site'] = { text: '', tone: '' };
		return out;
	});
</script>

<div class="stack">
	<AdminNav />
	{#if session.can('admin')}
		<div class="sections">
			{#each ADMIN_SECTIONS as s (s.href)}
				{@const st = status[s.href]}
				<a class="section" href={s.href}>
					<span class="icon"><s.icon size={22} strokeWidth={1.75} /></span>
					<span class="grow">
						<span class="name">{s.label}</span>
						<span class="blurb">{s.blurb}</span>
						{#if st?.text}<span class="status {st.tone}">{st.text}</span>{/if}
					</span>
					<ChevronRight size={18} strokeWidth={1.75} class="chev" />
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.sections {
		display: grid;
		gap: var(--space-3);
	}
	@media (min-width: 700px) {
		.sections {
			grid-template-columns: 1fr 1fr;
		}
	}
	@media (min-width: 1200px) {
		.sections {
			grid-template-columns: repeat(3, 1fr);
		}
	}
	.section {
		display: flex;
		align-items: flex-start;
		gap: var(--space-3);
		padding: var(--space-4);
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius-md);
		text-decoration: none;
		color: inherit;
		min-height: 96px;
	}
	.section:hover {
		border-color: var(--accent);
	}
	.icon {
		flex: none;
		display: grid;
		place-items: center;
		width: 40px;
		height: 40px;
		border-radius: var(--radius-md);
		background: var(--bg);
		color: var(--primary);
	}
	.grow {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.name {
		font: 600 17px/24px var(--font-display);
	}
	.blurb {
		font-size: 14px;
		line-height: 20px;
		color: var(--text-muted);
	}
	.status {
		margin-top: var(--space-1);
		font-size: 13px;
		line-height: 18px;
		font-weight: 500;
		color: var(--text-muted);
	}
	.status.ok {
		color: var(--ok);
	}
	.status.warn {
		color: var(--warn);
	}
	.status.note {
		color: var(--accent);
	}
	.section :global(.chev) {
		flex: none;
		align-self: center;
		color: var(--text-muted);
	}
</style>
