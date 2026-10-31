<script lang="ts">
	import { page } from '$app/state';
	import { Check, Pencil, Plus, RotateCcw, Trash2 } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { ago, dateRange } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';
	import type { Person, ShoppingItem, Task, TaskList } from '#lib/types.ts';

	const tab = $derived(page.url.searchParams.get('tab') === 'todo' ? 'todo' : 'shopping');
	const canEdit = $derived(session.can('edit'));

	// --- Shopping ---
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
		} catch (e) {
			toast.error(e);
		}
	}

	// --- To-do ---
	let lists = $state<TaskList[]>([]);
	let people = $state<Person[]>([]);
	let quick = $state<Record<number, string>>({});
	let showDone = $state<Record<number, boolean>>({});
	let taskOpen = $state(false);
	let editingTask = $state<Task | null>(null);
	let tform = $state({ title: '', notes: '', priority: 1, assignee_id: '' as string | number, due_date: '', list_id: 0 });
	let listOpen = $state(false);
	let listForm = $state({ id: 0, name: '' });

	async function loadTasks() {
		try {
			lists = await api.get('/api/lists/tasks');
		} catch (e) {
			toast.error(e);
		}
	}
	async function loadPeople() {
		// Assignee picker: anyone who has added or done something, plus me.
		const seen = new Map<number, Person>();
		if (session.me) seen.set(session.me.id, session.me);
		for (const l of lists) for (const t of l.tasks) for (const p of [t.assignee, t.created_by, t.done_by]) if (p) seen.set(p.id, p);
		for (const i of [...shop.open, ...shop.acquired]) for (const p of [i.added_by, i.acquired_by]) if (p) seen.set(p.id, p);
		people = [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
	}
	async function quickAdd(l: TaskList, e: SubmitEvent) {
		e.preventDefault();
		const title = (quick[l.id] ?? '').trim();
		if (!title) return;
		try {
			await api.post(`/api/lists/tasks/${l.id}/items`, { title });
			quick[l.id] = '';
			await loadTasks();
		} catch (err) {
			toast.error(err);
		}
	}
	async function toggle(t: Task) {
		try {
			await api.patch(`/api/lists/tasks/items/${t.id}`, { done: !t.done_at });
			await loadTasks();
		} catch (e) {
			toast.error(e);
		}
	}
	function openTask(t: Task) {
		editingTask = t;
		tform = { title: t.title, notes: t.notes ?? '', priority: t.priority, assignee_id: t.assignee?.id ?? '', due_date: t.due_date ?? '', list_id: t.list_id };
		loadPeople();
		taskOpen = true;
	}
	async function saveTask(e: SubmitEvent) {
		e.preventDefault();
		if (!editingTask) return;
		try {
			await api.patch(`/api/lists/tasks/items/${editingTask.id}`, {
				title: tform.title,
				notes: tform.notes || null,
				priority: Number(tform.priority),
				assignee_id: tform.assignee_id === '' ? null : Number(tform.assignee_id),
				due_date: tform.due_date || null,
				list_id: Number(tform.list_id)
			});
			taskOpen = false;
			await loadTasks();
		} catch (err) {
			toast.error(err);
		}
	}
	async function deleteTask() {
		if (!editingTask || !confirm('Delete this task?')) return;
		await api.del(`/api/lists/tasks/items/${editingTask.id}`);
		taskOpen = false;
		await loadTasks();
	}
	function openList(l?: TaskList) {
		listForm = { id: l?.id ?? 0, name: l?.name ?? '' };
		listOpen = true;
	}
	async function saveList(e: SubmitEvent) {
		e.preventDefault();
		try {
			if (listForm.id) await api.patch(`/api/lists/tasks/${listForm.id}`, { name: listForm.name });
			else await api.post('/api/lists/tasks', { name: listForm.name });
			listOpen = false;
			await loadTasks();
		} catch (err) {
			toast.error(err);
		}
	}
	async function deleteList() {
		if (!listForm.id || !confirm('Delete this whole list and its tasks?')) return;
		await api.del(`/api/lists/tasks/${listForm.id}`);
		listOpen = false;
		await loadTasks();
	}
	async function resetList(l: TaskList) {
		if (!confirm(`Untick everything on "${l.name}"?`)) return;
		await api.post(`/api/lists/tasks/${l.id}/reset`);
		await loadTasks();
	}

	$effect(() => {
		loadShop();
		loadTasks();
	});
	const PRIORITY = ['Low', 'Normal', 'High'];
</script>

<div class="stack">
	<div class="pill-tabs" role="tablist">
		<a href="?tab=shopping" class:on={tab === 'shopping'} role="tab" aria-selected={tab === 'shopping'}>Shopping</a>
		<a href="?tab=todo" class:on={tab === 'todo'} role="tab" aria-selected={tab === 'todo'}>To-do</a>
	</div>

	{#if tab === 'shopping'}
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
	{:else}
		{#each lists as l (l.id)}
			{@const open = l.tasks.filter((t) => !t.done_at)}
			{@const done = l.tasks.filter((t) => t.done_at)}
			<section class="card">
				<div class="card-head">
					<h2>{l.name}</h2>
					<div class="row" style="gap:4px">
						<span class="label">{done.length} / {l.tasks.length}</span>
						{#if canEdit}
							<button class="btn icon" aria-label="Untick all" title="Untick all" onclick={() => resetList(l)}><RotateCcw size={18} strokeWidth={1.75} /></button>
							<button class="btn icon" aria-label="Rename list" onclick={() => openList(l)}><Pencil size={18} strokeWidth={1.75} /></button>
						{/if}
					</div>
				</div>
				<ul class="list">
					{#each open as t (t.id)}
						<li>
							{#if canEdit}<button class="check" aria-label={`Done: ${t.title}`} onclick={() => toggle(t)}></button>{/if}
							<button class="grow plain" onclick={() => canEdit && openTask(t)}>
								<div>{t.title}{#if t.priority === 2}<span class="chip warn" style="margin-left:8px">High</span>{/if}</div>
								{#if t.notes || t.due_date}<div class="small muted">{t.due_date ? `Due ${dateRange(t.due_date, t.due_date)}` : ''}{t.due_date && t.notes ? ' · ' : ''}{t.notes ?? ''}</div>{/if}
							</button>
							{#if t.assignee}<Avatar person={t.assignee} size={26} />{/if}
						</li>
					{/each}
					{#if showDone[l.id]}
						{#each done as t (t.id)}
							<li>
								{#if canEdit}<button class="check on" aria-label={`Not done: ${t.title}`} onclick={() => toggle(t)}><Check size={16} strokeWidth={2.5} /></button>{/if}
								<div class="grow"><div class="done">{t.title}</div><div class="small muted">{t.done_by?.name ?? 'Someone'} · {ago(t.done_at)}</div></div>
							</li>
						{/each}
					{/if}
				</ul>
				{#if !open.length && !showDone[l.id]}<p class="muted">Nothing to do. Go sit on the porch.</p>{/if}
				{#if canEdit}
					<form class="row" style="margin-top:12px" onsubmit={(e) => quickAdd(l, e)}>
						<input class="grow" placeholder="Add a task" bind:value={quick[l.id]} maxlength="200" aria-label={`Add to ${l.name}`} />
						<button class="btn quick" aria-label="Add task"><Plus size={22} strokeWidth={1.75} /></button>
					</form>
				{/if}
				{#if done.length}<button class="btn text" onclick={() => (showDone[l.id] = !showDone[l.id])}>{showDone[l.id] ? 'Hide' : 'Show'} done ({done.length})</button>{/if}
			</section>
		{/each}
		{#if canEdit}<button class="btn secondary" onclick={() => openList()}><Plus size={18} strokeWidth={1.75} />New list</button>{/if}
	{/if}
</div>

<Sheet bind:open={taskOpen} title="Task">
	<form class="stack" onsubmit={saveTask}>
		<label class="field"><span>Task</span><input required maxlength="200" bind:value={tform.title} /></label>
		<label class="field"><span>Notes</span><textarea bind:value={tform.notes}></textarea></label>
		<div class="grid grid-2">
			<label class="field"><span>Priority</span><select bind:value={tform.priority}>{#each PRIORITY as p, i (i)}<option value={i}>{p}</option>{/each}</select></label>
			<label class="field"><span>Who's doing it</span><select bind:value={tform.assignee_id}><option value="">Anyone</option>{#each people as p (p.id)}<option value={p.id}>{p.name}</option>{/each}</select></label>
			<label class="field"><span>Due</span><input type="date" bind:value={tform.due_date} /></label>
			<label class="field"><span>List</span><select bind:value={tform.list_id}>{#each lists as l (l.id)}<option value={l.id}>{l.name}</option>{/each}</select></label>
		</div>
		<div class="spread">
			<button type="button" class="btn text" style="color:var(--danger)" onclick={deleteTask}>Delete</button>
			<button class="btn">Save</button>
		</div>
	</form>
</Sheet>

<Sheet bind:open={listOpen} title={listForm.id ? 'Rename list' : 'New list'}>
	<form class="stack" onsubmit={saveList}>
		<label class="field"><span>Name</span><input required maxlength="80" bind:value={listForm.name} placeholder="Spring projects" /></label>
		<div class="spread">
			{#if listForm.id}<button type="button" class="btn text" style="color:var(--danger)" onclick={deleteList}>Delete list</button>{:else}<span></span>{/if}
			<button class="btn">Save</button>
		</div>
	</form>
</Sheet>

<style>
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
	.check.on {
		background: var(--ok);
		border-color: var(--ok);
	}
	.done {
		text-decoration: line-through;
		color: var(--text-muted);
	}
	.plain {
		background: none;
		border: 0;
		padding: 0;
		text-align: left;
		color: inherit;
		font: inherit;
		cursor: pointer;
		min-height: var(--tap);
		display: flex;
		flex-direction: column;
		justify-content: center;
	}
</style>
