<script lang="ts">
	import { api } from '#lib/api.ts';
	import CameraThumb from '#lib/components/CameraThumb.svelte';
	import { ago } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import type { CameraInfo } from '#lib/types.ts';

	let cams = $state<CameraInfo[] | null>(null);
	$effect(() => {
		api.get<CameraInfo[]>('/api/cameras').then((c) => (cams = c)).catch(() => (cams = []));
	});
	const online = $derived(cams?.filter((c) => c.online).length ?? 0);
	const WHAT: Record<string, string> = { person: 'Person', vehicle: 'Vehicle', animal: 'Animal', motion: 'Motion' };
</script>

<div class="stack">
	<div class="spread"><h1>Cameras</h1>{#if cams?.length}<span class="small muted">{online === cams.length ? (cams.length === 1 ? 'Online' : `All ${cams.length} online`) : `${online} of ${cams.length} online`}</span>{/if}</div>
	{#if cams && !cams.length}
		<div class="card empty">
			<p>No cameras yet.</p>
			<p>{session.can('admin') ? 'Add one in Admin → Cameras.' : 'An admin can add them.'}</p>
		</div>
	{:else if cams}
		<div class="grid grid-2">
			{#each cams as c (c.id)}
				<a href={`/cameras/${c.id}`} class="tile-link">
					<CameraThumb id={c.id} name={c.name} online={c.online} every={20} />
					<div class="small muted meta">
						{#if !c.online}{c.name} camera is offline{c.last_ok_at ? ` since ${ago(c.last_ok_at)}` : ''}.{:else if c.last_event}{WHAT[c.last_event.type] ?? 'Motion'} {ago(c.last_event.at)}{:else}No motion lately.{/if}
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.tile-link {
		text-decoration: none;
		color: inherit;
	}
	.meta {
		margin-top: var(--space-2);
	}
</style>
