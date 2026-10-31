<script lang="ts">
	// One series over time: 2px line, 10% wash, hairline grid, crosshair + tooltip.
	// Single series → no legend; the card title names it. Table view underneath.
	let {
		points,
		format,
		label,
		height = 160,
		zeroBased = false
	}: {
		points: { t: string; v: number | null }[];
		format: (v: number) => string;
		label: string;
		height?: number;
		zeroBased?: boolean;
	} = $props();

	let width = $state(300);
	let hover = $state<number | null>(null);
	const PAD = { l: 40, r: 12, t: 10, b: 22 };

	const data = $derived(points.filter((p) => p.v != null) as { t: string; v: number }[]);
	const times = $derived(data.map((p) => new Date(p.t).getTime()));
	const t0 = $derived(Math.min(...times));
	const t1 = $derived(Math.max(...times));

	function niceTicks(lo: number, hi: number, n = 4): number[] {
		if (lo === hi) return [lo];
		const raw = (hi - lo) / n;
		const mag = 10 ** Math.floor(Math.log10(raw));
		const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
		const out = [];
		for (let v = Math.floor(lo / step) * step; v <= hi + step * 0.001; v += step) out.push(+v.toFixed(6));
		return out;
	}
	const yTicks = $derived.by(() => {
		if (!data.length) return [0];
		const vs = data.map((p) => p.v);
		let lo = Math.min(...vs);
		let hi = Math.max(...vs);
		if (zeroBased) lo = Math.min(0, lo);
		if (lo === hi) hi = lo + 1;
		return niceTicks(lo, hi);
	});
	const y0 = $derived(yTicks[0]);
	const y1 = $derived(yTicks[yTicks.length - 1]);
	const x = (t: number) => PAD.l + ((t - t0) / Math.max(1, t1 - t0)) * (width - PAD.l - PAD.r);
	const y = (v: number) => PAD.t + (1 - (v - y0) / Math.max(1e-9, y1 - y0)) * (height - PAD.t - PAD.b);
	const path = $derived(data.map((p, i) => `${i ? 'L' : 'M'}${x(times[i]).toFixed(1)},${y(p.v).toFixed(1)}`).join(''));
	const area = $derived(
		data.length ? `${path}L${x(t1).toFixed(1)},${y(y0)}L${x(t0).toFixed(1)},${y(y0)}Z` : ''
	);
	const xTicks = $derived.by(() => {
		if (!data.length) return [];
		const n = width < 500 ? 3 : 6;
		return Array.from({ length: n + 1 }, (_, i) => t0 + ((t1 - t0) * i) / n);
	});
	const span = $derived(t1 - t0);
	const tick = (t: number) =>
		new Date(t).toLocaleString('en-US', span > 2 * 86400000 ? { weekday: 'short', timeZone: 'America/Phoenix' } : { hour: 'numeric', timeZone: 'America/Phoenix' }).toLowerCase();
	const when = (t: string) => new Date(t).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'America/Phoenix' });

	function move(e: PointerEvent) {
		const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
		const px = e.clientX - rect.left;
		let best = 0;
		for (let i = 1; i < data.length; i++) if (Math.abs(x(times[i]) - px) < Math.abs(x(times[best]) - px)) best = i;
		hover = data.length ? best : null;
	}
</script>

<div class="chart" bind:clientWidth={width}>
	{#if data.length < 2}
		<p class="muted small" style="height:{height}px;display:grid;place-items:center">Not enough data yet.</p>
	{:else}
		<svg {width} {height} role="img" aria-label={label} onpointermove={move} onpointerleave={() => (hover = null)}>
			{#each yTicks as v (v)}
				<line x1={PAD.l} x2={width - PAD.r} y1={y(v)} y2={y(v)} class="grid" />
				<text x={PAD.l - 6} y={y(v) + 4} text-anchor="end" class="axis">{format(v)}</text>
			{/each}
			{#each xTicks as t, i (i)}
				<text x={x(t)} y={height - 6} text-anchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'} class="axis">{tick(t)}</text>
			{/each}
			<path d={area} class="area" />
			<path d={path} class="line" />
			{#if hover != null}
				{@const p = data[hover]}
				<line x1={x(times[hover])} x2={x(times[hover])} y1={PAD.t} y2={height - PAD.b} class="cross" />
				<circle cx={x(times[hover])} cy={y(p.v)} r="5" class="dot" />
			{/if}
		</svg>
		{#if hover != null}
			{@const p = data[hover]}
			<div class="tip" style="left:{Math.min(Math.max(x(times[hover]), 70), width - 70)}px">
				<span class="data">{format(p.v)}</span><span class="small muted">{when(p.t)}</span>
			</div>
		{/if}
		<details class="small">
			<summary class="muted">Show as table</summary>
			<table>
				<thead><tr><th>Time</th><th>{label}</th></tr></thead>
				<tbody>{#each data as p (p.t)}<tr><td>{when(p.t)}</td><td class="data">{format(p.v)}</td></tr>{/each}</tbody>
			</table>
		</details>
	{/if}
</div>

<style>
	.chart {
		position: relative;
		width: 100%;
		min-width: 0;
		overflow: hidden;
	}
	svg {
		display: block;
		touch-action: pan-y;
	}
	.grid {
		stroke: var(--line);
		stroke-width: 1;
	}
	.axis {
		fill: var(--text-muted);
		font: 400 11px var(--font-data);
	}
	.line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 2;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.area {
		fill: var(--accent);
		opacity: 0.1;
	}
	.cross {
		stroke: var(--text-muted);
		stroke-width: 1;
	}
	.dot {
		fill: var(--accent);
		stroke: var(--surface);
		stroke-width: 2;
	}
	.tip {
		position: absolute;
		top: 0;
		transform: translateX(-50%);
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius-sm);
		box-shadow: var(--shadow-overlay);
		padding: 4px 8px;
		display: flex;
		flex-direction: column;
		pointer-events: none;
		white-space: nowrap;
	}
	details {
		margin-top: var(--space-2);
	}
	table {
		width: 100%;
		border-collapse: collapse;
		margin-top: var(--space-2);
		max-height: 240px;
		display: block;
		overflow-y: auto;
	}
	th,
	td {
		text-align: left;
		padding: 2px 8px 2px 0;
		border-bottom: 1px solid var(--line);
	}
</style>
