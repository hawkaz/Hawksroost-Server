<script lang="ts">
	// Live video through go2rtc (MSE, falling back to HLS, then still frames).
	// Stops by itself after a few minutes so the cabin's Starlink upload isn't
	// used by a forgotten tab — and to keep video traffic through Cloudflare small.
	import { Play } from '@lucide/svelte';

	let { stream, name, idleMinutes = 5 }: { stream: string; name: string; idleMinutes?: number } = $props();

	let host: HTMLDivElement | undefined = $state();
	let playing = $state(true);
	let ready = $state(false);
	let failed = $state(false);

	async function loadComponent() {
		if (customElements.get('video-stream')) return;
		const url = new URL('/video/video-stream.js', location.origin).href;
		await import(/* @vite-ignore */ url);
	}

	$effect(() => {
		if (!playing || !host) return;
		const el = host;
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
			el.replaceChildren();
			ready = false;
		};
	});
</script>

<div class="player">
	{#if playing}
		<div class="video" bind:this={host}></div>
		{#if failed}<div class="over">Video isn't available right now.</div>{/if}
		<div class="badge"><span class="chip live">Live</span></div>
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
	.video {
		width: 100%;
		height: 100%;
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
