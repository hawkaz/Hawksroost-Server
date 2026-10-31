<script lang="ts">
	import { CircleAlert, CircleCheck } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import { ago } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';

	let h = $state<{ version: string; items: { name: string; ok: boolean; detail: string; last: string | null }[] } | null>(null);
	async function load() {
		h = await api.get<NonNullable<typeof h>>('/api/admin/health').catch(() => null);
	}
	$effect(() => {
		if (!session.can('admin')) return;
		load();
		const t = setInterval(load, 30000);
		return () => clearInterval(t);
	});
</script>

<div class="stack">
	<AdminNav />
	{#if h}
		<section class="card">
			<ul class="list">
				{#each h.items as i (i.name)}
					<li>
						<span style="color:{i.ok ? 'var(--ok)' : 'var(--warn)'}">{#if i.ok}<CircleCheck size={20} strokeWidth={1.75} />{:else}<CircleAlert size={20} strokeWidth={1.75} />{/if}</span>
						<div class="grow"><div>{i.name}</div><div class="small muted">{i.detail}</div></div>
						{#if i.last}<span class="small muted data">{ago(i.last)}</span>{/if}
					</li>
				{/each}
			</ul>
		</section>
		<p class="small muted">Version {h.version}</p>
	{/if}
</div>
