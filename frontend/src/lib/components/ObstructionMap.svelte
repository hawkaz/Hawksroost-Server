<script lang="ts">
	// The dish's own map of the sky: centre = straight up, edge = horizon, north at the top.
	// Each dot is a direction the dish has used — light where the signal was clear,
	// red where something (trees, the roof) blocked it.
	let { rows, cols, data, size = 260 }: { rows: number; cols: number; data: string; size?: number } = $props();
	let canvas: HTMLCanvasElement | undefined = $state();

	$effect(() => {
		if (!canvas) return;
		const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
		const dpr = window.devicePixelRatio || 1;
		canvas.width = size * dpr;
		canvas.height = size * dpr;
		const ctx = canvas.getContext('2d')!;
		ctx.scale(dpr, dpr);
		ctx.clearRect(0, 0, size, size);
		const css = getComputedStyle(canvas);
		const clear = css.getPropertyValue('--map-clear').trim() || '#8a9677';
		const blocked = css.getPropertyValue('--map-blocked').trim() || '#c0442e';
		const cw = size / cols;
		const ch = size / rows;
		const toRgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
		const [cr, cg, cb] = toRgb(clear);
		const [br, bg, bb] = toRgb(blocked);
		for (let r = 0; r < rows; r++) {
			for (let c = 0; c < cols; c++) {
				const b = bytes[r * cols + c];
				if (!b) continue;
				const q = (b - 1) / 254; // 1 = clear signal, 0 = blocked
				const mix = (a: number, z: number) => Math.round(z + (a - z) * q);
				ctx.fillStyle = `rgb(${mix(cr, br)},${mix(cg, bg)},${mix(cb, bb)})`;
				ctx.fillRect(c * cw, r * ch, Math.ceil(cw), Math.ceil(ch));
			}
		}
	});
</script>

<div class="map" style="--s:{size}px">
	<canvas bind:this={canvas} style="width:{size}px;height:{size}px" aria-label="Sky obstruction map"></canvas>
	<svg viewBox="0 0 100 100" aria-hidden="true">
		<circle cx="50" cy="50" r="49.5" class="edge" />
		<circle cx="50" cy="50" r="33" class="ring" />
		<circle cx="50" cy="50" r="16.5" class="ring" />
		<line x1="50" y1="1" x2="50" y2="99" class="ring" />
		<line x1="1" y1="50" x2="99" y2="50" class="ring" />
	</svg>
	<span class="dir n">N</span><span class="dir e">E</span><span class="dir s">S</span><span class="dir w">W</span>
</div>

<style>
	.map {
		--map-clear: #8a9677;
		--map-blocked: #c0442e;
		position: relative;
		width: var(--s);
		height: var(--s);
		max-width: 100%;
		margin: 18px;
	}
	:global([data-theme='dark']) .map {
		--map-clear: #a7b394;
		--map-blocked: #e4614a;
	}
	canvas,
	svg {
		position: absolute;
		inset: 0;
		max-width: 100%;
		height: auto;
	}
	.edge {
		fill: none;
		stroke: var(--text-muted);
		stroke-width: 0.6;
	}
	.ring {
		fill: none;
		stroke: var(--line);
		stroke-width: 0.4;
		stroke-dasharray: 1 1.5;
	}
	.dir {
		position: absolute;
		font: 600 12px var(--font-ui);
		color: var(--text-muted);
	}
	.n {
		top: -18px;
		left: 50%;
		transform: translateX(-50%);
	}
	.s {
		bottom: -18px;
		left: 50%;
		transform: translateX(-50%);
	}
	.e {
		right: -14px;
		top: 50%;
		transform: translateY(-50%);
	}
	.w {
		left: -16px;
		top: 50%;
		transform: translateY(-50%);
	}
</style>
