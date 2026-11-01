<script lang="ts">
	import { Plus, RotateCcw, Trash2 } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import { ago } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';
	import type { ShoppingItem } from '#lib/types.ts';

	const canEdit = $derived(session.can('edit'));

	let shop = $state<{ open: ShoppingItem[]; acquired: ShoppingItem[]; stores: string[] }>({ open: [], acquired: [], stores: [] });
	let newItem = $state({ text: '', qty: '', store: '' });
	let showGot = $state(false);

	const groups = $derived.by(() => {
		const m = new Map<string, ShoppingItem[]>();
		for (const i of shop.open) {
			const k = i.store || 'Anywhere';
			m.set(k, [...(m.get(k) ?? []), i]);
		}
		return [...m.entries()].sort(([a], [b]) => (a === 'Anywhere' ? 1 : b === 'Anywhere' ? -1 : a.localeCompare(b)));
	});

	async function loadShop() {
		try {
			shop = await api.get('/api/lists/shopping');
		} catch (e) {
			toast.error(e);
		}
	}
	async function addItem(e: SubmitEvent) {
		e.preventDefault();
		if (!newItem.text.trim()) return;
		try {
			const it = await api.post<ShoppingItem>('/api/lists/shopping', newItem);
			toast.show(`Added ${it.text}${it.store ? ` to ${it.store}` : ''}.`);
			newItem = { text: '', qty: '', store: newItem.store };
			await loadShop();
		} catch (err) {
			toast.error(err);
		}
	}
	async function setAcquired(i: ShoppingItem, acquired: boolean) {
		try {
			await api.patch(`/api/lists/shopping/${i.id}`, { acquired });
			await loadShop();
		} catch (e) {
			toast.error(e);
		}
	}
	async function removeItem(i: ShoppingItem) {
		try {
			await api.del(`/api/lists/shopping/${i.id}`);
			await loadShop();
			toast.show(`Removed ${i.text}.`, 'info', { label: 'Undo', run: () => restore(i) });
		} catch (e) {
			toast.error(e);
		}
	}
	async function restore(i: ShoppingItem) {
		try {
			await api.post('/api/lists/shopping', { text: i.text, qty: i.qty, store: i.store });
			await loadShop();
			toast.show(`${i.text} is back on the list.`);
		} catch (e) {
			toast.error(e);
		}
	}

	
	$effect(() => {
		loadShop();
	});
</script>

<div class="stack">
	<div class="spread wrap">
		<h1>Shopping</h1>
		{#if shop.open.length}<span class="small muted">{shop.open.length} {shop.open.length === 1 ? 'thing' : 'things'} to get</span>{/if}
	</div>

	{#if canEdit}
		<form class="card add" onsubmit={addItem}>
			<label class="field grow"><span>Item</span><input bind:value={newItem.text} placeholder="e.g. Firewood, 1 cord" maxlength="200" /></label>
			<label class="field qty"><span>Qty</span><input bind:value={newItem.qty} placeholder="2" maxlength="40" /></label>
			<label class="field store"><span>Where</span><input bind:value={newItem.store} list="stores" placeholder="Flagstaff run" maxlength="60" /></label>
			<datalist id="stores">{#each shop.stores as s (s)}<option value={s}></option>{/each}</datalist>
			<button class="btn quick" aria-label="Add item"><Plus size={22} strokeWidth={1.75} /></button>
		</form>
	{/if}

	{#if groups.length}
		<div class="stores">
		{#each groups as [store, items] (store)}
			<section class="card">
				<div class="card-head"><h2>{store}</h2><span class="label">{items.length} {items.length === 1 ? 'item' : 'items'}</span></div>
				<ul class="list">
					{#each items as i (i.id)}
						<li>
							{#if canEdit}
								<button class="check" aria-label={`Got ${i.text}`} onclick={() => setAcquired(i, true)}></button>
							{/if}
							<div class="grow">
								<div>{i.text}</div>
								<div class="small muted">Added by {i.added_by?.name ?? 'someone'} · {ago(i.added_at)}</div>
							</div>
							{#if i.qty}<span class="data">{i.qty}</span>{/if}
							{#if canEdit}<button class="btn icon" aria-label={`Remove ${i.text}`} onclick={() => removeItem(i)}><Trash2 size={18} strokeWidth={1.75} /></button>{/if}
						</li>
					{/each}
				</ul>
			</section>
		{/each}
		</div>
	{:else}
		<div class="card empty"><p>Nothing on the list.</p><p>The cupboards must be full.</p></div>
	{/if}

	{#if shop.acquired.length}
		<button class="btn text" onclick={() => (showGot = !showGot)}>{showGot ? 'Hide' : 'Show'} what people got ({shop.acquired.length})</button>
		{#if showGot}
			<section class="card">
				<ul class="list">
					{#each shop.acquired as i (i.id)}
						<li>
							<div class="grow">
								<div class="done">{i.text}{i.qty ? ` · ${i.qty}` : ''}</div>
								<div class="small muted">Got by {i.acquired_by?.name ?? 'someone'} · {ago(i.acquired_at)} · added by {i.added_by?.name ?? 'someone'}</div>
							</div>
							{#if canEdit}<button class="btn icon" aria-label="Put back on list" onclick={() => setAcquired(i, false)}><RotateCcw size={18} strokeWidth={1.75} /></button>{/if}
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	{/if}
</div>

<style>
	.stores {
		display: grid;
		gap: var(--space-4);
		align-items: start;
	}
	.stores > * {
		min-width: 0;
	}
	@media (min-width: 1000px) {
		.stores {
			grid-template-columns: 1fr 1fr;
		}
	}

	.add {
		display: flex;
		gap: var(--space-2);
		align-items: flex-end;
		flex-wrap: wrap;
	}
	.add .grow {
		flex: 1 1 100%;
	}
	.qty {
		width: 72px;
	}
	.store {
		flex: 1;
	}
	@media (min-width: 900px) {
		.add {
			flex-wrap: nowrap;
		}
		.add .grow {
			flex: 1;
		}
		.store {
			width: 200px;
			flex: none;
		}
	}
	.check {
		width: 26px;
		height: 26px;
		flex: none;
		border-radius: var(--radius-sm);
		border: 2px solid var(--line);
		background: var(--surface);
		cursor: pointer;
		display: grid;
		place-items: center;
		color: var(--snow);
		position: relative;
	}
	.check::after {
		content: '';
		position: absolute;
		inset: -9px;
	}
	.check:hover {
		border-color: var(--ok);
	}
	.done {
		text-decoration: line-through;
		color: var(--text-muted);
	}
</style>
