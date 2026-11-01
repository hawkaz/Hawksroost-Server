<script lang="ts">
	// Live video through go2rtc (MSE, falling back to HLS, then still frames).
	// Stops by itself after a few minutes so the cabin's Starlink upload isn't
	// used by a forgotten tab.
	import { Minus, Play, Plus } from '@lucide/svelte';

	let { stream, name, idleMinutes = 5 }: { stream: string; name: string; idleMinutes?: number } = $props();

	let host: HTMLDivElement | undefined = $state();
	let playing = $state(true);
	let ready = $state(false);
	let failed = $state(false);
	let live = $state(false); // picture actually arriving
	let stalled = $state(false); // nothing after a while
	let attempt = $state(0);
	const STALL_S = 20;

	// --- Picture zoom, done in the browser so it works with any camera ---
	let frame: HTMLDivElement | undefined = $state();
	let scale = $state(1);
	let tx = $state(0);
	let ty = $state(0);
	const MAX_ZOOM = 6;

	function clamp() {
		if (!frame) return;
		const mx = (frame.clientWidth * (scale - 1)) / 2;
		const my = (frame.clientHeight * (scale - 1)) / 2;
		tx = Math.max(-mx, Math.min(mx, tx));
		ty = Math.max(-my, Math.min(my, ty));
	}
	/** Zoom to `next`, keeping the point (cx, cy) — relative to the centre — where it is. */
	function zoomTo(next: number, cx = 0, cy = 0) {
		const s = Math.max(1, Math.min(MAX_ZOOM, next));
		const k = s / scale;
		tx = cx - (cx - tx) * k;
		ty = cy - (cy - ty) * k;
		scale = s;
		if (s === 1) tx = ty = 0;
		clamp();
	}
	const points = new Map<number, { x: number; y: number }>();
	let pinch: { d: number; s: number } | null = null;
	let drag = $state<{ x: number; y: number; tx: number; ty: number } | null>(null);
	function rel(e: { clientX: number; clientY: number }) {
		const r = frame!.getBoundingClientRect();
		return { x: e.clientX - r.left - r.width / 2, y: e.clientY - r.top - r.height / 2 };
	}
	function down(e: PointerEvent) {
		points.set(e.pointerId, rel(e));
		if (points.size === 2) {
			const [a, b] = [...points.values()];
			pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, s: scale };
			drag = null;
		} else if (points.size === 1 && scale > 1) {
			drag = { ...rel(e), tx, ty };
			frame?.setPointerCapture(e.pointerId);
		}
	}
	function move(e: PointerEvent) {
		if (!points.has(e.pointerId)) return;
		points.set(e.pointerId, rel(e));
		if (pinch && points.size === 2) {
			const [a, b] = [...points.values()];
			zoomTo((pinch.s * Math.hypot(a.x - b.x, a.y - b.y)) / pinch.d, (a.x + b.x) / 2, (a.y + b.y) / 2);
		} else if (drag) {
			const p = rel(e);
			tx = drag.tx + p.x - drag.x;
			ty = drag.ty + p.y - drag.y;
			clamp();
		}
	}
	function up(e: PointerEvent) {
		points.delete(e.pointerId);
		if (points.size < 2) pinch = null;
		if (points.size === 0) drag = null;
	}
	// Ctrl + scroll on a mouse; trackpad pinch arrives the same way.
	function wheel(e: WheelEvent) {
		if (!e.ctrlKey && !e.metaKey) return;
		e.preventDefault();
		const p = rel(e);
		// A mouse notch is ~100; trackpad pinch sends many small steps.
		zoomTo(scale * Math.exp(-Math.max(-100, Math.min(100, e.deltaY)) * 0.004), p.x, p.y);
	}
	function doubleTap(e: MouseEvent) {
		const p = rel(e);
		zoomTo(scale > 1 ? 1 : 2.5, p.x, p.y);
	}
	$effect(() => {
		// Not passive, so Ctrl + scroll zooms the picture instead of the page.
		const f = frame;
		if (!f) return;
		f.addEventListener('wheel', wheel, { passive: false });
		return () => f.removeEventListener('wheel', wheel);
	});
	$effect(() => {
		// The browser's own video controls would be magnified too, so hide them while zoomed.
		const zoomed = scale > 1;
		if (!live) return;
		const v = host?.querySelector('video');
		if (v) v.controls = !zoomed;
	});

	async function loadComponent() {
		if (customElements.get('video-stream')) return;
		const url = new URL('/video/video-stream.js', location.origin).href;
		await import(/* @vite-ignore */ url);
	}

	$effect(() => {
		void attempt;
		if (!playing || !host) return;
		const el = host;
		live = false;
		stalled = false;
		scale = 1;
		tx = ty = 0;
		const started = Date.now();
		// Watch for the first picture; say so if none comes instead of showing a black box.
		const watch = setInterval(() => {
			const v = el.querySelector('video');
			if (v && (v.readyState >= 2 || v.poster)) {
				live = true;
				stalled = false;
			} else if (!live && Date.now() - started > STALL_S * 1000) {
				stalled = true;
			}
		}, 1000);
		let player: HTMLElement & { src?: string; mode?: string; background?: boolean } | null = null;
		let cancelled = false;
		loadComponent()
			.then(() => {
				if (cancelled) return;
				player = document.createElement('video-stream') as typeof player;
				player!.mode = 'mse,hls,mjpeg';
				player!.style.cssText = 'display:block;width:100%;height:100%';
				el.replaceChildren(player!);
				player!.src = `/video/api/ws?src=${encodeURIComponent(stream)}`;
				ready = true;
				failed = false;
			})
			.catch(() => (failed = true));
		const stop = setTimeout(() => (playing = false), idleMinutes * 60_000);
		return () => {
			cancelled = true;
			clearTimeout(stop);
			clearInterval(watch);
			el.replaceChildren();
			ready = false;
		};
	});
</script>

<div class="player">
	{#if playing}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="frame"
			bind:this={frame}
			style:touch-action={scale > 1 ? 'none' : 'pan-y'}
			style:cursor={scale > 1 ? (drag ? 'grabbing' : 'grab') : 'auto'}
			onpointerdown={down}
			onpointermove={move}
			onpointerup={up}
			onpointercancel={up}
			ondblclick={doubleTap}
		>
			<div class="video" bind:this={host} style:transform={`translate(${tx}px, ${ty}px) scale(${scale})`}></div>
		</div>
		{#if failed}
			<div class="over">Video isn't available right now.</div>
		{:else if stalled}
			<button class="over" onclick={() => attempt++}>
				<span>The video isn't coming through.</span>
				<span class="small">Tap to try again.</span>
			</button>
		{/if}
		<div class="badge">
			{#if live}<span class="chip live">Live</span>{:else if !failed && !stalled}<span class="chip">Connecting…</span>{/if}
		</div>
		{#if live}
			<div class="zoom" role="group" aria-label="Zoom the picture">
				<button class="zb" onclick={() => zoomTo(scale / 1.5)} disabled={scale === 1} aria-label="Zoom out"><Minus size={20} strokeWidth={2} /></button>
				{#if scale > 1}<button class="zb level" onclick={() => zoomTo(1)} aria-label="Back to the full picture">{scale.toFixed(1)}×</button>{/if}
				<button class="zb" onclick={() => zoomTo(scale * 1.5)} disabled={scale >= MAX_ZOOM} aria-label="Zoom in"><Plus size={20} strokeWidth={2} /></button>
			</div>
		{/if}
	{:else}
		<button class="over resume" onclick={() => (playing = true)}>
			<Play size={36} strokeWidth={1.75} />
			<span>Paused to save the cabin's internet. Tap to keep watching.</span>
		</button>
	{/if}
	<div class="scrim"><span>{name}</span></div>
</div>

<style>
	.player {
		position: relative;
		aspect-ratio: 16 / 9;
		background: #000;
		border-radius: var(--radius-md);
		overflow: hidden;
	}
	.frame {
		width: 100%;
		height: 100%;
		overflow: hidden;
		user-select: none;
		-webkit-user-select: none;
	}
	.video {
		width: 100%;
		height: 100%;
		transform-origin: center;
	}
	.zoom {
		position: absolute;
		top: var(--space-2);
		right: var(--space-2);
		display: flex;
		gap: 2px;
		background: rgba(0, 0, 0, 0.5);
		border-radius: var(--radius-md);
		padding: 2px;
	}
	.zb {
		min-width: var(--tap);
		height: var(--tap);
		display: grid;
		place-items: center;
		border: 0;
		border-radius: var(--radius-sm);
		background: transparent;
		color: #fff;
		cursor: pointer;
		font: 500 14px/1 var(--font-data);
	}
	.zb:hover:not(:disabled) {
		background: rgba(255, 255, 255, 0.15);
	}
	.zb:disabled {
		opacity: 0.4;
		cursor: default;
	}
	.video :global(video) {
		width: 100%;
		height: 100%;
		object-fit: contain;
		background: #000;
	}
	.over {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		align-items: center;
		justify-content: center;
		text-align: center;
		color: #ede6d8;
		padding: var(--space-4);
		background: rgba(0, 0, 0, 0.55);
		border: 0;
		font: inherit;
		cursor: pointer;
	}
	.badge {
		position: absolute;
		top: var(--space-2);
		left: var(--space-2);
	}
	.scrim {
		position: absolute;
		inset: auto 0 0 0;
		padding: var(--space-5) var(--space-3) var(--space-2);
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
		color: #fff;
		font-weight: 500;
		font-size: 14px;
		pointer-events: none;
	}
</style>
