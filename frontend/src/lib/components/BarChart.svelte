<script lang="ts">
	// One series of columns (e.g. rain per day). Value on the cap, tooltip on hover.
	let {
		bars,
		format,
		label,
		height = 140
	}: { bars: { key: string; label: string; v: number }[]; format: (v: number) => string; label: string; height?: number } = $props();

	let width = $state(300);
	let hover = $state<number | null>(null);
	const PAD = { t: 18, b: 22 };
	const max = $derived(Math.max(...bars.map((b) => b.v), 0));
	const slot = $derived(width / Math.max(1, bars.length));
	const bw = $derived(Math.min(24, slot * 0.6));
	const h = (v: number) => (max > 0 ? (v / max) * (height - PAD.t - PAD.b) : 0);
</script>

<div class="chart" bind:clientWidth={width}>
	<svg {width} {height} role="img" aria-label={label}>
		<line x1="0" x2={width} y1={height - PAD.b} y2={height - PAD.b} class="base" />
		{#each bars as b, i (b.key)}
			{@const cx = slot * i + slot / 2}
			{@const bh = h(b.v)}
			<g role="presentation" onpointerenter={() => (hover = i)} onpointerleave={() => (hover = null)}>
				<rect x={slot * i} y="0" width={slot} height={height} fill="transparent" />
				{#if bh > 0}
					<path
						class="bar"
						d={`M${cx - bw / 2},${height - PAD.b} v${-(bh - Math.min(4, bh))} q0,${-Math.min(4, bh)} ${Math.min(4, bh)},${-Math.min(4, bh)} h${bw - 2 * Math.min(4, bh)} q${Math.min(4, bh)},0 ${Math.min(4, bh)},${Math.min(4, bh)} v${bh - Math.min(4, bh)} z`}
					/>
				{/if}
				{#if hover === i || (b.v > 0 && b.v === max)}
					<text x={cx} y={height - PAD.b - bh - 4} text-anchor="middle" class="val">{format(b.v)}</text>
				{/if}
				<text x={cx} y={height - 6} text-anchor="middle" class="axis">{b.label}</text>
			</g>
		{/each}
	</svg>
	<details class="small">
		<summary class="muted">Show as table</summary>
		<table><tbody>{#each bars as b (b.key)}<tr><td>{b.label}</td><td class="data">{format(b.v)}</td></tr>{/each}</tbody></table>
	</details>
</div>

<style>
	.chart {
		width: 100%;
		min-width: 0;
		overflow: hidden;
	}
	svg {
		display: block;
	}
	.bar {
		fill: var(--accent);
	}
	.base {
		stroke: var(--line);
	}
	.axis {
		fill: var(--text-muted);
		font: 400 11px var(--font-data);
	}
	.val {
		fill: var(--text);
		font: 500 11px var(--font-data);
	}
	details {
		margin-top: var(--space-2);
	}
	table {
		width: 100%;
		border-collapse: collapse;
	}
	td {
		padding: 2px 8px 2px 0;
		border-bottom: 1px solid var(--line);
	}
</style>
