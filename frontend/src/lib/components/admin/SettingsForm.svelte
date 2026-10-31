<script lang="ts" module>
	export interface Field {
		key: string;
		label: string;
		type?: 'text' | 'password' | 'number' | 'checkbox' | 'select' | 'email' | 'url';
		options?: [string, string][];
		help?: string;
		placeholder?: string;
	}
</script>

<script lang="ts">
	// One integration's settings. Secret fields are write-only: blank keeps the saved value.
	import type { Snippet } from 'svelte';
	import { api } from '#lib/api.ts';
	import { toast } from '#lib/toast.svelte.ts';

	let {
		section,
		title,
		fields,
		values = $bindable(),
		intro,
		actions
	}: { section: string; title: string; fields: Field[]; values: Record<string, unknown>; intro?: Snippet; actions?: Snippet } = $props();

	let draft = $state<Record<string, unknown>>({});
	let busy = $state(false);
	$effect(() => {
		const d: Record<string, unknown> = {};
		for (const f of fields) d[f.key] = f.type === 'password' ? '' : values[f.key];
		draft = d;
	});

	async function save(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		const body: Record<string, unknown> = {};
		for (const f of fields) {
			const v = draft[f.key];
			body[f.key] = f.type === 'password' && v === '' ? null : f.type === 'number' ? Number(v) : v;
		}
		try {
			values = await api.put(`/api/admin/settings/${section}`, body);
			toast.show(`${title} saved.`);
		} catch (err) {
			toast.error(err);
		} finally {
			busy = false;
		}
	}
</script>

<section class="card">
	<form class="stack" onsubmit={save}>
		<h2>{title}</h2>
		{@render intro?.()}
		{#each fields as f (f.key)}
			{#if f.type === 'checkbox'}
				<label class="spread" style="min-height:44px"><span>{f.label}</span><input type="checkbox" bind:checked={draft[f.key] as boolean} /></label>
			{:else if f.type === 'select'}
				<label class="field"><span>{f.label}</span><select bind:value={draft[f.key]}>{#each f.options ?? [] as [v, l] (v)}<option value={v}>{l}</option>{/each}</select></label>
			{:else}
				<label class="field">
					<span>{f.label}</span>
					<input
						type={f.type ?? 'text'}
						bind:value={draft[f.key]}
						autocomplete="off"
						placeholder={f.type === 'password' && values[`${f.key}_set`] ? 'Saved — leave blank to keep' : (f.placeholder ?? '')}
					/>
					{#if f.help}<span class="small muted">{f.help}</span>{/if}
				</label>
			{/if}
		{/each}
		<div class="row wrap">
			<button class="btn" disabled={busy}>Save</button>
			{@render actions?.()}
		</div>
	</form>
</section>
