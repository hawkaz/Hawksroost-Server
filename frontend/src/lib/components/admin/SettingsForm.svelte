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
		columns = false,
		intro,
		actions
	}: {
		section: string;
		title: string;
		fields: Field[];
		values: Record<string, unknown>;
		/** Lay short fields out side by side on wide screens. */
		columns?: boolean;
		intro?: Snippet;
		actions?: Snippet;
	} = $props();
	const toggles = $derived(fields.filter((f) => f.type === 'checkbox'));
	const inputs = $derived(fields.filter((f) => f.type !== 'checkbox'));

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
			const blank = v === '' || v === null || v === undefined;
			// A cleared number goes as null, so the server asks for one rather than saving 0.
			body[f.key] = f.type === 'password' && v === '' ? null : f.type === 'number' ? (blank ? null : Number(v)) : v;
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
		{#each toggles as f (f.key)}
			<label class="spread" style="min-height:44px"><span>{f.label}</span><input type="checkbox" bind:checked={draft[f.key] as boolean} /></label>
		{/each}
		<div class="inputs" class:columns>
		{#each inputs as f (f.key)}
			{#if f.type === 'select'}
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
		</div>
		<div class="row wrap">
			<button class="btn" disabled={busy}>Save</button>
			{@render actions?.()}
		</div>
	</form>
</section>

<style>
	.inputs {
		display: grid;
		gap: var(--space-4);
	}
	@media (min-width: 900px) {
		.inputs.columns {
			grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
			align-items: start;
		}
	}
</style>
