<script lang="ts" module>
	export interface TPoint {
		t: string;
		v: number | null;
		lo?: number | null;
		hi?: number | null;
	}
</script>

<script lang="ts">
	// One measurement over time, drawn to scale.
	// line: 2px line, optional lo–hi band (e.g. daily range, lull–gust); bars: per-bucket totals.
	// Single series → no legend; the card title names it. Hover readout + table view.
	import { CABIN_TZ } from '#lib/format.ts';

	let {
		points,
		kind = 'line',
		label,
		format,
		unit = '',
		start,
		end,
		bucketS = 600,
		height = 190,
		zero = false,
		extremes = true
	}: {
		points: TPoint[];
		kind?: 'line' | 'bars';
		label: string;
		format: (v: number) => string;
		unit?: string;
		start?: string;
		end?: string;
		bucketS?: number;
		height?: number;
		zero?: boolean;
		extremes?: boolean;
	} = $props();

	let width = $state(320);
	let hover = $state<number | null>(null);
	const M = { l: 44, r: 14, t: 24, b: 26 };

	const data = $derived(
		points
			.map((p) => ({ ...p, ms: new Date(p.t).getTime() }))
			.filter((p) => p.v != null || p.lo != null || p.hi != null)
	);
	const x0 = $derived(start ? new Date(start).getTime() : Math.min(...data.map((d) => d.ms)));
	const x1 = $derived(end ? new Date(end).getTime() : Math.max(...data.map((d) => d.ms)) + bucketS * 1000);
	const pw = $derived(Math.max(10, width - M.l - M.r));
	const ph = $derived(height - M.t - M.b);
	const x = (ms: number) => M.l + ((ms - x0) / Math.max(1, x1 - x0)) * pw;

	// --- y scale with "nice" ticks ---
	function nice(lo: number, hi: number, want = 4) {
		if (!isFinite(lo) || !isFinite(hi)) return [0, 1];
		if (lo === hi) {
			lo -= 1;
			hi += 1;
		}
		const raw = (hi - lo) / want;
		const mag = 10 ** Math.floor(Math.log10(raw));
		const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
		const ticks: number[] = [];
		for (let v = Math.floor(lo / step) * step; v <= hi + step * 1e-6; v += step) ticks.push(+v.toFixed(6));
		if (ticks[ticks.length - 1] < hi) ticks.push(+(ticks[ticks.length - 1] + step).toFixed(6));
		return ticks;
	}
	const yTicks = $derived.by(() => {
		const vals = data.flatMap((d) => [d.v, d.lo, d.hi]).filter((v): v is number => v != null);
		if (!vals.length) return [0, 1];
		let lo = Math.min(...vals);
		let hi = Math.max(...vals);
		if (zero || kind === 'bars') lo = Math.min(0, lo);
		if (hi === lo) hi = lo + (Math.abs(lo) || 1) * ((zero || kind === 'bars') && lo >= 0 ? 1 : 0.1);
		const pad = (hi - lo) * 0.08;
		return nice(zero || kind === 'bars' ? lo : lo - pad, hi + pad);
	});
	const y0 = $derived(yTicks[0]);
	const y1 = $derived(yTicks[yTicks.length - 1]);
	const y = (v: number) => M.t + (1 - (v - y0) / Math.max(1e-9, y1 - y0)) * ph;

	// --- time ticks on the cabin's clock ---
	const partsFmt = new Intl.DateTimeFormat('en-US', {
		timeZone: CABIN_TZ, hour: 'numeric', hourCycle: 'h23', weekday: 'short', month: 'short', day: 'numeric'
	});
	const clockFmt = new Intl.DateTimeFormat('en-US', { timeZone: CABIN_TZ, hour: 'numeric', minute: '2-digit' });
	function local(ms: number) {
		const p = Object.fromEntries(partsFmt.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
		return { h: Number(p.hour), wd: p.weekday, md: `${p.month} ${p.day}`, day: Number(p.day) };
	}
	const xTicks = $derived.by(() => {
		const span = x1 - x0;
		const out: { ms: number; text: string; major: boolean }[] = [];
		const first = Math.ceil(x0 / 3600000) * 3600000;
		const hours = span / 3600000;
		if (hours <= 3) {
			// Short spans (live views): clock times every 5, 15 or 30 minutes.
			const step = (hours <= 0.5 ? 5 : hours <= 1.5 ? 15 : 30) * 60000;
			for (let ms = Math.ceil(x0 / step) * step; ms <= x1; ms += step) {
				out.push({ ms, text: clockFmt.format(new Date(ms)).replace(/\s?[AP]M$/i, ''), major: false });
			}
		} else if (hours <= 36) {
			const every = pw < 420 ? 6 : 3;
			for (let ms = first; ms <= x1; ms += 3600000) {
				const l = local(ms);
				if (l.h % every) continue;
				const text = l.h === 0 ? l.wd : l.h === 12 ? 'noon' : `${l.h % 12} ${l.h < 12 ? 'am' : 'pm'}`;
				out.push({ ms, text, major: l.h === 0 });
			}
		} else {
			const days = span / 86400000;
			const every = Math.max(1, Math.ceil(days / Math.max(2, pw / 64)));
			let n = 0;
			for (let ms = first; ms <= x1; ms += 3600000) {
				const l = local(ms);
				if (l.h !== 0) continue;
				if (n++ % every) continue;
				out.push({ ms, text: days <= 9 ? `${l.wd} ${l.day}` : l.md, major: true });
			}
		}
		return out;
	});

	// --- geometry ---
	const gapMs = $derived(bucketS * 2500);
	const segments = $derived.by(() => {
		const segs: (typeof data)[] = [];
		let cur: typeof data = [];
		for (const d of data) {
			if (cur.length && d.ms - cur[cur.length - 1].ms > gapMs) {
				segs.push(cur);
				cur = [];
			}
			cur.push(d);
		}
		if (cur.length) segs.push(cur);
		return segs;
	});
	const mid = (ms: number) => x(ms + (bucketS * 1000) / 2);
	const linePath = (seg: typeof data) =>
		seg.filter((d) => d.v != null).map((d, i) => `${i ? 'L' : 'M'}${mid(d.ms).toFixed(1)},${y(d.v!).toFixed(1)}`).join('');
	const bandPath = (seg: typeof data) => {
		const s = seg.filter((d) => d.lo != null && d.hi != null);
		if (s.length < 2) return '';
		const top = s.map((d, i) => `${i ? 'L' : 'M'}${mid(d.ms).toFixed(1)},${y(d.hi!).toFixed(1)}`).join('');
		const bottom = [...s].reverse().map((d) => `L${mid(d.ms).toFixed(1)},${y(d.lo!).toFixed(1)}`).join('');
		return `${top}${bottom}Z`;
	};
	const hasBand = $derived(data.some((d) => d.lo != null && d.hi != null));
	const washPath = (seg: typeof data) => {
		const s = seg.filter((d) => d.v != null);
		if (s.length < 2) return '';
		const base = y(Math.max(y0, Math.min(0, y1) > y0 ? 0 : y0));
		return `${linePath(s)}L${mid(s[s.length - 1].ms).toFixed(1)},${base}L${mid(s[0].ms).toFixed(1)},${base}Z`;
	};
	const barW = $derived(Math.max(2, Math.min(18, ((bucketS * 1000) / Math.max(1, x1 - x0)) * pw * 0.72)));
	function barPath(d: (typeof data)[number]) {
		const v = d.v ?? 0;
		const top = y(Math.max(v, 0));
		const base = y(0);
		const h = Math.max(0, base - top);
		if (h < 0.5) return '';
		const r = Math.min(2, h, barW / 2);
		const cx = mid(d.ms);
		const l = cx - barW / 2;
		return `M${l},${base}v${-(h - r)}q0,${-r} ${r},${-r}h${barW - 2 * r}q${r},0 ${r},${r}v${h - r}z`;
	}

	const valued = $derived(data.filter((d) => d.v != null));
	const maxP = $derived(valued.length ? valued.reduce((a, b) => (b.v! > a.v! ? b : a)) : null);
	const minP = $derived(valued.length ? valued.reduce((a, b) => (b.v! < a.v! ? b : a)) : null);
	const lastP = $derived(valued.length ? valued[valued.length - 1] : null);

	const when = (ms: number) =>
		new Date(ms).toLocaleString('en-US', {
			timeZone: CABIN_TZ, weekday: 'short', hour: 'numeric', minute: '2-digit',
			...(bucketS < 60 ? { second: '2-digit' } : {})
		});

	function move(e: PointerEvent) {
		const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
		const px = e.clientX - rect.left;
		let best: number | null = null;
		let bestD = Infinity;
		data.forEach((d, i) => {
			const dist = Math.abs(mid(d.ms) - px);
			if (dist < bestD) {
				bestD = dist;
				best = i;
			}
		});
		hover = bestD < 40 ? best : null;
	}
	const hp = $derived(hover != null ? data[hover] : null);
</script>

<div class="chart" bind:clientWidth={width}>
	{#if !data.length}
		<p class="empty-chart" style="height:{height}px">No readings in this period yet.</p>
	{:else}
		<svg {width} {height} role="img" aria-label={label} onpointermove={move} onpointerleave={() => (hover = null)}>
			{#each yTicks as v (v)}
				<line class="grid" x1={M.l} x2={M.l + pw} y1={y(v)} y2={y(v)} />
				<text class="axis" x={M.l - 8} y={y(v) + 4} text-anchor="end">{format(v)}</text>
			{/each}
			{#if unit}<text class="unit" x={M.l - 8} y={12} text-anchor="end">{unit}</text>{/if}
			{#each xTicks as tk (tk.ms)}
				{#if tk.major && kind === 'line'}<line class="day" x1={x(tk.ms)} x2={x(tk.ms)} y1={M.t} y2={M.t + ph} />{/if}
				<text class="axis" class:major={tk.major} x={x(tk.ms)} y={height - 7} text-anchor="middle">{tk.text}</text>
			{/each}

			{#if kind === 'bars'}
				{#each data as d, i (d.ms)}
					<path class="bar" class:on={hover === i} d={barPath(d)} />
				{/each}
			{:else}
				{#each segments as seg, i (i)}
					{#if hasBand}<path class="band" d={bandPath(seg)} />{:else}<path class="wash" d={washPath(seg)} />{/if}
					<path class="line" d={linePath(seg)} />
				{/each}
				{#if lastP}<circle class="dot" cx={mid(lastP.ms)} cy={y(lastP.v!)} r="4" />{/if}
			{/if}

			{#if extremes && maxP && minP && maxP !== minP && hover == null}
				<text class="ext" x={Math.min(Math.max(mid(maxP.ms), M.l + 16), M.l + pw - 16)} y={y(maxP.v!) - 8} text-anchor="middle">{format(maxP.v!)}</text>
				{#if kind === 'line'}
					<text class="ext" x={Math.min(Math.max(mid(minP.ms), M.l + 16), M.l + pw - 16)} y={Math.min(y(minP.v!) + 16, M.t + ph - 2)} text-anchor="middle">{format(minP.v!)}</text>
				{/if}
			{/if}

			{#if hp}
				<line class="cross" x1={mid(hp.ms)} x2={mid(hp.ms)} y1={M.t} y2={M.t + ph} />
				{#if kind === 'line' && hp.v != null}<circle class="dot" cx={mid(hp.ms)} cy={y(hp.v)} r="4.5" />{/if}
			{/if}
		</svg>
		{#if hp}
			<div class="tip" style="left:{Math.min(Math.max(mid(hp.ms), 80), width - 80)}px">
				<span class="data">{hp.v != null ? format(hp.v) : '—'}{#if hp.lo != null && hp.hi != null}<span class="muted"> ({format(hp.lo)}–{format(hp.hi)})</span>{/if}</span>
				<span class="small muted">{when(hp.ms)}</span>
			</div>
		{/if}
		<details class="small">
			<summary class="muted">Show as table</summary>
			<div class="tbl">
				<table>
					<thead><tr><th>Time</th><th>{label}</th>{#if hasBand}<th>Range</th>{/if}</tr></thead>
					<tbody>
						{#each data as d (d.ms)}
							<tr><td>{when(d.ms)}</td><td class="data">{d.v != null ? format(d.v) : '—'}</td>{#if hasBand}<td class="data">{d.lo != null ? format(d.lo) : '—'}–{d.hi != null ? format(d.hi) : '—'}</td>{/if}</tr>
						{/each}
					</tbody>
				</table>
			</div>
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
		overflow: visible;
	}
	.empty-chart {
		display: grid;
		place-items: center;
		color: var(--text-muted);
		font-size: 14px;
		border: 1px dashed var(--line);
		border-radius: var(--radius-md);
	}
	.grid {
		stroke: var(--line);
	}
	.day {
		stroke: var(--line);
		stroke-dasharray: 2 4;
	}
	.axis,
	.unit {
		fill: var(--text-muted);
		font: 400 11px var(--font-data);
		font-variant-numeric: tabular-nums;
	}
	.axis.major {
		fill: var(--text);
	}
	.line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 2;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.wash {
		fill: var(--accent);
		opacity: 0.1;
	}
	.band {
		fill: var(--accent);
		opacity: 0.18;
	}
	.bar {
		fill: var(--accent);
	}
	.bar.on {
		fill: var(--text);
	}
	.dot {
		fill: var(--accent);
		stroke: var(--surface);
		stroke-width: 2;
	}
	.cross {
		stroke: var(--text-muted);
	}
	.ext {
		fill: var(--text);
		font: 500 11px var(--font-data);
		paint-order: stroke;
		stroke: var(--surface);
		stroke-width: 3px;
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
		z-index: 2;
	}
	details {
		margin-top: var(--space-2);
	}
	.tbl {
		max-height: 240px;
		overflow: auto;
		margin-top: var(--space-2);
	}
	table {
		width: 100%;
		border-collapse: collapse;
	}
	th,
	td {
		text-align: left;
		padding: 2px 8px 2px 0;
		border-bottom: 1px solid var(--line);
	}
</style>
