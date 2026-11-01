<script lang="ts">
	import { CircleAlert, CircleCheck, CircleDashed } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import { ago } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	// ok: true working, false needs a look, null optional and not set up.
	interface Health { version: string; items: { name: string; ok: boolean | null; detail: string; last: string | null }[] }
	let h = $state<Health | null>(null);
	let s = $state<Record<string, Record<string, unknown>> | null>(null);

	async function loadHealth() {
		h = await api.get<Health>('/api/admin/health').catch(() => null);
	}
	$effect(() => {
		if (!session.can('admin')) return;
		loadHealth();
		api.get<typeof s>('/api/admin/settings').then((v) => (s = v)).catch(toast.error.bind(toast));
		const t = setInterval(() => !document.hidden && loadHealth(), 30000);
		return () => clearInterval(t);
	});

	async function backupNow() {
		try {
			const r = await api.post<{ detail: string }>('/api/admin/backup');
			toast.show(r.detail);
			loadHealth();
		} catch (e) {
			toast.error(e);
		}
	}

	const BACKUP: Field[] = [
		{ key: 'enabled', label: 'Back up the database every night', type: 'checkbox' },
		{ key: 'hour', label: 'Hour to run (0–23, cabin time)', type: 'number' },
		{ key: 'keep_days', label: 'Days of backups to keep on the laptop', type: 'number' }
	];
	const problems = $derived(h?.items.filter((i) => i.ok === false).length ?? 0);
</script>

<div class="stack">
	<AdminNav title="System" />
	<div class="cols">
		{#if h}
			<section class="card">
				<div class="card-head">
					<h2>Health</h2>
					<span class="small muted">{problems ? `${problems} need${problems === 1 ? 's' : ''} a look` : 'All good'}</span>
				</div>
				<ul class="list">
					{#each h.items as i, n (n)}
						<li>
							<span class:ok={i.ok === true} class:warn={i.ok === false} class="icon">
								{#if i.ok}<CircleCheck size={20} strokeWidth={1.75} />{:else if i.ok === false}<CircleAlert size={20} strokeWidth={1.75} />{:else}<CircleDashed size={20} strokeWidth={1.75} />{/if}
							</span>
							<div class="grow"><div>{i.name}</div><div class="small muted">{i.detail}</div></div>
							{#if i.last}<span class="small muted data">{ago(i.last)}</span>{/if}
						</li>
					{/each}
				</ul>
				<p class="small muted" style="margin-top:12px">Version <span class="data">{h.version}</span>. Checks again every 30 seconds.</p>
			</section>
		{/if}
		{#if s}
			<SettingsForm section="backup" title="Backups" fields={BACKUP} bind:values={s.backup}>
				{#snippet intro()}<p class="small muted">Copies of the database go to the laptop’s data/backups folder. Camera recordings stay on the camera.</p>{/snippet}
				{#snippet actions()}<button type="button" class="btn secondary" onclick={backupNow}>Back up now</button>{/snippet}
			</SettingsForm>
		{/if}
	</div>
</div>

<style>
	.icon.ok {
		color: var(--ok);
	}
	.icon.warn {
		color: var(--warn);
	}
	.cols {
		display: grid;
		gap: var(--space-4);
		align-items: start;
	}
	@media (min-width: 1000px) {
		.cols {
			grid-template-columns: 3fr 2fr;
		}
	}
</style>
