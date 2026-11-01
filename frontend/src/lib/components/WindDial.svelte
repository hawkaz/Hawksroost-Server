<script lang="ts">
	// Compass dial: the copper pointer sits on the side the wind is coming FROM.
	import { compass } from '#lib/format.ts';
	let { dir, speed, gust, size = 188 }: { dir: number | null; speed: string; gust: string; size?: number } = $props();
	const C = 100;
	const R = 84;
	const ticks = Array.from({ length: 72 }, (_, i) => i * 5);
	const pt = (deg: number, r: number) => {
		const a = ((deg - 90) * Math.PI) / 180;
		return [C + r * Math.cos(a), C + r * Math.sin(a)];
	};
</script>

<svg viewBox="0 0 200 200" width={size} height={size} role="img" aria-label={`Wind ${dir != null ? `from the ${compass(dir)}` : 'calm'}, ${speed}, gusts ${gust}`}>
	<circle cx={C} cy={C} r={R} class="ring" />
	{#each ticks as t (t)}
		{@const [ax, ay] = pt(t, R)}
		{@const [bx, by] = pt(t, R - (t % 90 === 0 ? 10 : t % 30 === 0 ? 6 : 3))}
		<line x1={ax} y1={ay} x2={bx} y2={by} class="tick" class:major={t % 90 === 0} />
	{/each}
	{#each [['N', 0], ['E', 90], ['S', 180], ['W', 270]] as [l, d] (l)}
		{@const [lx, ly] = pt(d as number, R - 22)}
		<text x={lx} y={ly + 4} text-anchor="middle" class="card">{l}</text>
	{/each}
	{#if dir != null}
		{@const [tx, ty] = pt(dir, R + 2)}
		{@const [lx2, ly2] = pt(dir - 7, R - 16)}
		{@const [rx2, ry2] = pt(dir + 7, R - 16)}
		<path d={`M${tx},${ty} L${lx2},${ly2} L${rx2},${ry2} Z`} class="pointer" />
	{/if}
	<text x={C} y={C + 2} text-anchor="middle" class="speed">{speed}</text>
	<text x={C} y={C + 22} text-anchor="middle" class="sub">{dir != null ? `from ${compass(dir)}` : 'calm'}</text>
	<text x={C} y={C + 38} text-anchor="middle" class="sub">gusts {gust}</text>
</svg>

<style>
	svg {
		display: block;
		max-width: 100%;
		height: auto;
	}
	.ring {
		fill: none;
		stroke: var(--line);
		stroke-width: 1;
	}
	.tick {
		stroke: var(--text-muted);
		stroke-width: 1;
		opacity: 0.6;
	}
	.tick.major {
		stroke: var(--text);
		stroke-width: 2;
		opacity: 1;
	}
	.card {
		fill: var(--text-muted);
		font: 600 12px var(--font-ui);
	}
	.pointer {
		fill: var(--accent);
	}
	.speed {
		fill: var(--text);
		font: 400 26px var(--font-data);
	}
	.sub {
		fill: var(--text-muted);
		font: 400 12px var(--font-ui);
	}
</style>
