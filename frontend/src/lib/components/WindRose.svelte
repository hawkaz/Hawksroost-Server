<script lang="ts">
	// Where the wind came from over the period. Petal length = share of the time;
	// shades of one colour (light → dark) = speed bands. Legend lists the bands.
	let { sectors, calm, total, classLabels }: { sectors: number[][]; calm: number; total: number; classLabels: string[] } = $props();
	const C = 110;
	const R = 92;
	const shares = $derived(sectors.map((row) => row.map((n) => (total ? n / total : 0))));
	const maxShare = $derived(Math.max(0.05, ...shares.map((r) => r.reduce((a, b) => a + b, 0))));
	const ringStep = $derived(maxShare > 0.2 ? 0.1 : 0.05);
	const rings = $derived(Array.from({ length: Math.floor(maxShare / ringStep) }, (_, i) => (i + 1) * ringStep));
	const scale = (s: number) => (s / maxShare) * R;
	const OPACITY = [0.35, 0.55, 0.78, 1];
	function petal(i: number, r0: number, r1: number) {
		const a0 = ((i * 22.5 - 9 - 90) * Math.PI) / 180;
		const a1 = ((i * 22.5 + 9 - 90) * Math.PI) / 180;
		const p = (r: number, a: number) => `${(C + r * Math.cos(a)).toFixed(1)},${(C + r * Math.sin(a)).toFixed(1)}`;
		return `M${p(r0, a0)} L${p(r1, a0)} A${r1},${r1} 0 0 1 ${p(r1, a1)} L${p(r0, a1)} A${r0},${r0} 0 0 0 ${p(r0, a0)} Z`;
	}
	const pct = (n: number) => `${Math.round(n * 100)}%`;
</script>

{#if total}
	<div class="rose">
		<svg viewBox="0 0 220 220" role="img" aria-label="Wind rose">
			{#each rings as r (r)}
				<circle cx={C} cy={C} r={scale(r)} class="ringline" />
				<text x={C + 3} y={C - scale(r) + 11} class="ringlbl">{pct(r)}</text>
			{/each}
			<line x1={C} y1={C - R} x2={C} y2={C + R} class="ringline" />
			<line x1={C - R} y1={C} x2={C + R} y2={C} class="ringline" />
			{#each shares as row, i (i)}
				{@const cum = row.map((_, k) => row.slice(0, k + 1).reduce((a, b) => a + b, 0))}
				{#each row as s, k (k)}
					{#if s > 0}
						<path d={petal(i, scale(k ? cum[k - 1] : 0), scale(cum[k]))} class="petal" style="opacity:{OPACITY[k]}">
							<title>{['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][i]} · {classLabels[k]}: {pct(s)}</title>
						</path>
					{/if}
				{/each}
			{/each}
			<text x={C} y={12} text-anchor="middle" class="card">N</text>
			<text x={214} y={C + 4} text-anchor="end" class="card">E</text>
			<text x={C} y={218} text-anchor="middle" class="card">S</text>
			<text x={6} y={C + 4} class="card">W</text>
		</svg>
		<ul class="legend">
			{#each classLabels as l, k (k)}
				<li><span class="sw" style="opacity:{OPACITY[k]}"></span>{l}</li>
			{/each}
			<li class="muted">Calm {pct(total ? calm / total : 0)} of the time</li>
		</ul>
	</div>
{:else}
	<p class="muted">No wind readings in this period yet.</p>
{/if}

<style>
	.rose {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		align-items: center;
	}
	svg {
		width: 220px;
		max-width: 100%;
		height: auto;
	}
	.ringline {
		fill: none;
		stroke: var(--line);
	}
	.ringlbl {
		fill: var(--text-muted);
		font: 400 10px var(--font-data);
	}
	.petal {
		fill: var(--accent);
		stroke: var(--surface);
		stroke-width: 1;
	}
	.card {
		fill: var(--text-muted);
		font: 600 12px var(--font-ui);
	}
	.legend {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		font-size: 14px;
	}
	.legend li {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.sw {
		width: 14px;
		height: 14px;
		border-radius: 3px;
		background: var(--accent);
	}
</style>
