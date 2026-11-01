<script lang="ts">
	import { page } from '$app/state';
	import { ChevronLeft, ChevronRight, Plus, TriangleAlert } from '@lucide/svelte';
	import { api, qs } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { addDays, cabinToday, dateRange, isoDate, nights, parseDate } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';
	import type { Booking, Person } from '#lib/types.ts';

	const today = cabinToday();
	const start0 = page.url.searchParams.get('date') ?? today;
	let month = $state(parseDate(start0.slice(0, 8) + '01'));
	let bookings = $state<Booking[]>([]);
	let selected = $state<string | null>(null);

	// Editor
	let open = $state(false);
	let editing = $state<Booking | null>(null);
	let form = $state({ title: '', start_date: today, end_date: addDays(today, 2), note: '', people_ids: [] as number[], others: '' });
	let everyone = $state<Person[]>([]);
	let busy = $state(false);
	let feedUrl = $state('');

	const monthLabel = $derived(month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }));
	const weeks = $derived.by(() => {
		const first = new Date(month);
		const startOffset = first.getDay();
		const gridStart = new Date(first);
		gridStart.setDate(first.getDate() - startOffset);
		const out: string[][] = [];
		for (let w = 0; w < 6; w++) {
			const row: string[] = [];
			for (let d = 0; d < 7; d++) {
				const x = new Date(gridStart);
				x.setDate(gridStart.getDate() + w * 7 + d);
				row.push(isoDate(x));
			}
			out.push(row);
		}
		return out[5][0].slice(0, 7) !== isoDate(month).slice(0, 7) ? out.slice(0, 5) : out;
	});
	const monthKey = $derived(isoDate(month).slice(0, 7));

	function on(day: string): Booking[] {
		return bookings.filter((b) => (b.kind === 'stay' ? b.start_date <= day && day < b.end_date : b.start_date === day));
	}
	const listed = $derived(
		selected ? on(selected) : bookings.filter((b) => b.end_date >= `${monthKey}-01` && b.start_date <= `${monthKey}-31`)
	);
	const byId = $derived(new Map(bookings.map((b) => [b.id, b])));

	async function load() {
		const first = weeks[0][0];
		const last = weeks[weeks.length - 1][6];
		try {
			bookings = await api.get<Booking[]>(`/api/calendar${qs({ start: first, end: last })}`);
		} catch (e) {
			toast.error(e);
		}
	}
	$effect(() => {
		void monthKey;
		load();
	});

	function shift(n: number) {
		const m = new Date(month);
		m.setMonth(m.getMonth() + n);
		month = m;
		selected = null;
	}

	async function loadPeople() {
		if (!everyone.length) everyone = await api.get<Person[]>('/api/calendar/people').catch(() => []);
	}
	function newBooking(day?: string) {
		editing = null;
		const s = day ?? (selected || today);
		form = { title: '', start_date: s, end_date: addDays(s, 2), note: '', people_ids: session.me ? [session.me.id] : [], others: '' };
		loadPeople();
		open = true;
	}
	function edit(b: Booking) {
		editing = b;
		form = {
			title: b.title, start_date: b.start_date, end_date: b.kind === 'stay' ? b.end_date : addDays(b.start_date, 1),
			note: b.note ?? '', people_ids: (b.people.length ? b.people : [b.user]).map((p) => p.id), others: b.others ?? ''
		};
		loadPeople();
		open = true;
	}
	function togglePerson(id: number) {
		form.people_ids = form.people_ids.includes(id) ? form.people_ids.filter((x) => x !== id) : [...form.people_ids, id];
	}
	/** Who's on a visit, for labels: "Chris, Dana +2" style. */
	const who = (b: Booking) => [...(b.people.length ? b.people : [b.user]).map((p) => p.name), ...(b.others ? [b.others] : [])];
	const short = (b: Booking) => {
		const names = who(b);
		return names.length > 2 ? `${names[0]} +${names.length - 1}` : names.join(' & ');
	};
	const lead = (b: Booking) => (b.people.length ? b.people[0] : b.user);
	const canEdit = (b: Booking) => session.can('admin') || (session.can('edit') && b.user.id === session.me?.id);

	async function save(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		try {
			if (!form.people_ids.length && !form.others.trim()) throw new Error('Pick who’s coming.');
			const body = { ...form, kind: 'stay', others: form.others.trim() || null };
			const saved = editing
				? await api.put<Booking>(`/api/calendar/${editing.id}`, body)
				: await api.post<Booking>('/api/calendar', body);
			open = false;
			await load();
			if (saved.overlaps.length) {
				const other = saved.overlaps.map((id) => { const b = byId.get(id); return b ? short(b) : null; }).filter(Boolean);
				toast.show(`Saved. Heads up: overlaps with ${other.join(' and ') || 'another stay'}.`);
			} else toast.show(editing ? 'Booking updated.' : `Booked ${dateRange(saved.start_date, saved.end_date)}.`);
		} catch (err) {
			toast.error(err);
		} finally {
			busy = false;
		}
	}
	async function remove() {
		if (!editing || !confirm('Delete this booking?')) return;
		try {
			await api.del(`/api/calendar/${editing.id}`);
			open = false;
			await load();
			toast.show('Booking deleted.');
		} catch (e) {
			toast.error(e);
		}
	}
	async function showFeed() {
		try {
			feedUrl = (await api.get<{ url: string }>('/api/calendar/feed')).url;
		} catch (e) {
			toast.error(e);
		}
	}
</script>

<div class="stack">
	<div class="spread">
		<div class="row" style="gap:4px">
			<button class="btn icon secondary" onclick={() => shift(-1)} aria-label="Previous month"><ChevronLeft size={20} strokeWidth={1.75} /></button>
			<h1 class="h2 month">{monthLabel}</h1>
			<button class="btn icon secondary" onclick={() => shift(1)} aria-label="Next month"><ChevronRight size={20} strokeWidth={1.75} /></button>
		</div>
		{#if session.can('edit')}<button class="btn" onclick={() => newBooking()}><Plus size={18} strokeWidth={1.75} />Book</button>{/if}
	</div>

	<div class="layout">
	<div class="cal card" role="grid" aria-label={monthLabel}>
		<div class="dow" role="row">
			{#each ['S', 'M', 'T', 'W', 'T', 'F', 'S'] as d, i (i)}<span class="label" role="columnheader">{d}</span>{/each}
		</div>
		{#each weeks as week (week[0])}
			<div class="week" role="row">
				{#each week as d (d)}
					{@const items = on(d)}
					<button
						class="day"
						class:other={d.slice(0, 7) !== monthKey}
						class:today={d === today}
						class:sel={d === selected}
						role="gridcell"
						aria-label={`${parseDate(d).toDateString()}${items.length ? `, ${items.length} booked` : ''}`}
						onclick={() => (selected = selected === d ? null : d)}
					>
						<span class="num data">{parseDate(d).getDate()}</span>
						{#each items.slice(0, 3) as b (b.id)}
							<span
								class="bar"
								class:logistics={b.kind === 'logistics'}
								class:clash={b.overlaps.length > 0}
								style="--c:var(--fam-{lead(b).color})">{b.kind === 'stay' ? short(b) : b.title}</span
							>
						{/each}
						{#if items.length > 3}<span class="more small">+{items.length - 3}</span>{/if}
					</button>
				{/each}
			</div>
		{/each}
	</div>

	<aside class="side">
	<section class="card">
		<div class="card-head">
			<h2 class="h3">{selected ? parseDate(selected).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }) : 'This month'}</h2>
			{#if selected && session.can('edit')}<button class="btn text" onclick={() => newBooking(selected!)}>Book from this day</button>{/if}
		</div>
		{#if listed.length}
			<ul class="list">
				{#each listed as b (b.id)}
					<li>
						<div class="avatars">{#each (b.people.length ? b.people : [b.user]).slice(0, 3) as p (p.id)}<Avatar person={p} size={28} />{/each}</div>
						<div class="grow">
							<div>{b.kind === 'stay' ? `${who(b).join(', ')} · ${b.title}` : b.title}</div>
							<div class="small muted data">
								{dateRange(b.start_date, b.end_date)}{b.kind === 'stay' ? ` · ${nights(b.start_date, b.end_date)} nights` : ' · logistics'}
							</div>
							{#if b.overlaps.length}
								<div class="small warn row" style="gap:4px"><TriangleAlert size={14} strokeWidth={1.75} />Overlaps with {b.overlaps.map((id) => byId.get(id)?.user.name ?? 'another stay').join(', ')}</div>
							{/if}
							{#if b.note}<div class="small muted">{b.note}</div>{/if}
						</div>
						{#if canEdit(b)}<button class="btn text" onclick={() => edit(b)}>Edit</button>{/if}
					</li>
				{/each}
			</ul>
		{:else}
			<p class="muted">{selected ? 'Nothing on this day.' : 'No bookings this month. The cabin is free.'}</p>
		{/if}
	</section>

	<section class="card">
		<div class="spread">
			<div><h2 class="h3">Calendar apps</h2><p class="small muted">See the cabin bookings in the calendar you already use, on any device.</p></div>
			<button class="btn secondary" onclick={showFeed}>Get link</button>
		</div>
		{#if feedUrl}
			<input readonly value={feedUrl} onfocus={(e) => (e.target as HTMLInputElement).select()} style="margin-top:12px" />
			<ul class="small muted feed-help">
				<li><strong>Outlook</strong> (web or Windows): Add calendar → Subscribe from web, then paste the link.</li>
				<li><strong>Google Calendar</strong> (on a computer): Other calendars → + → From URL.</li>
				<li><strong>iPhone or iPad</strong>: Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar.</li>
				<li><strong>Mac</strong>: Calendar app → File → New Calendar Subscription.</li>
			</ul>
			<p class="small muted">Keep this link private: anyone with it can see the bookings.</p>
		{/if}
	</section>
	</aside>
	</div>
</div>

<Sheet bind:open title={editing ? 'Edit visit' : 'Book the cabin'}>
	<form class="stack" onsubmit={save}>
		<label class="field"><span>What for</span><input required maxlength="120" bind:value={form.title} placeholder="Weekend at the lake" /></label>
		<div class="grid grid-2">
			<label class="field"><span>Arrive</span><input type="date" required bind:value={form.start_date} /></label>
			<label class="field"><span>Leave</span><input type="date" required min={addDays(form.start_date, 1)} bind:value={form.end_date} /></label>
		</div>
		<fieldset class="who">
			<legend>Who’s coming</legend>
			<div class="people">
				{#each everyone as p (p.id)}
					<button type="button" class="person" class:on={form.people_ids.includes(p.id)} aria-pressed={form.people_ids.includes(p.id)} onclick={() => togglePerson(p.id)}>
						<Avatar person={p} size={26} /><span>{p.name}</span>
					</button>
				{/each}
			</div>
			<label class="field"><span>Anyone else (optional)</span><input maxlength="200" bind:value={form.others} placeholder="The kids, the Smiths" /></label>
		</fieldset>
		<label class="field"><span>Note (optional)</span><textarea bind:value={form.note} maxlength="2000"></textarea></label>
		<div class="spread">
			{#if editing}<button type="button" class="btn text" style="color:var(--danger)" onclick={remove}>Delete</button>{:else}<span></span>{/if}
			<button class="btn" disabled={busy}>{editing ? 'Save' : 'Book it'}</button>
		</div>
	</form>
</Sheet>

<style>
	.who {
		border: 0;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}
	.who legend {
		font-size: 13px;
		line-height: 18px;
		color: var(--text-muted);
		padding: 0;
		margin-bottom: var(--space-2);
	}
	.people {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.person {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		min-height: var(--tap);
		padding: 0 var(--space-3) 0 var(--space-2);
		border-radius: var(--radius-pill);
		border: 1px solid var(--line);
		background: var(--surface);
		color: var(--text);
		font: 500 15px/20px var(--font-ui);
		cursor: pointer;
		opacity: 0.6;
	}
	.person.on {
		opacity: 1;
		border-color: var(--primary);
		box-shadow: inset 0 0 0 1px var(--primary);
	}
	.avatars {
		display: flex;
		flex: none;
	}
	.avatars :global(> *:not(:first-child)) {
		margin-left: -8px;
	}
	/* Calendar on the left, the month's bookings and calendar apps on the right when there's room. */
	.layout {
		display: grid;
		gap: var(--space-4);
		align-items: start;
	}
	.layout > * {
		min-width: 0;
	}
	.side {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	@media (min-width: 1150px) {
		.layout {
			grid-template-columns: minmax(0, 1fr) 320px;
		}
		.side .spread {
			flex-direction: column;
			align-items: flex-start;
		}
	}
	.h3 {
		font: 600 17px/24px var(--font-display);
	}
	.feed-help {
		margin: var(--space-3) 0 var(--space-2);
		padding-left: var(--space-5);
	}
	.feed-help li + li {
		margin-top: var(--space-1);
	}
	.cal {
		padding: var(--space-2);
	}
	.month {
		text-align: center;
		min-width: 0;
		font-size: 18px;
	}
	@media (min-width: 900px) {
		.month {
			min-width: 180px;
			font-size: 20px;
		}
	}
	.dow,
	.week {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		gap: 2px;
	}
	.dow span {
		text-align: center;
		padding: var(--space-1) 0;
	}
	.day {
		min-height: 64px;
		border: 1px solid transparent;
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--text);
		padding: 2px;
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 2px;
		cursor: pointer;
		font: inherit;
		text-align: left;
		min-width: 0;
	}
	.day:hover {
		background: var(--bg);
	}
	.day.other {
		opacity: 0.45;
	}
	.day.today {
		border-color: var(--copper);
	}
	.day.sel {
		background: var(--bg);
		border-color: var(--line);
	}
	.num {
		font-size: 12px;
		line-height: 16px;
		padding-left: 2px;
	}
	.bar {
		display: block;
		background: var(--c);
		color: var(--snow);
		border-radius: 3px;
		font: 500 10px/14px var(--font-ui);
		padding: 0 3px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.bar.logistics {
		background: transparent;
		color: var(--text);
		border: 1px solid var(--c);
	}
	.bar.clash {
		box-shadow: inset 0 -2px 0 var(--warn);
	}
	.more {
		font-size: 10px;
		line-height: 12px;
		color: var(--text-muted);
	}
	.warn {
		color: var(--warn);
	}
	@media (min-width: 900px) {
		.day {
			min-height: 96px;
			padding: 4px;
		}
		.bar {
			font-size: 12px;
			line-height: 18px;
		}
	}
</style>
