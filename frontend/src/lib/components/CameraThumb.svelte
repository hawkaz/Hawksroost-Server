<script lang="ts">
	// Still picture that refreshes, with name + time on a bottom scrim (brand: 16:9 tiles).
	let { id, name, every = 30, online = true }: { id: number; name: string; every?: number; online?: boolean } = $props();
	let stamp = $state(Date.now());
	let failed = $state(false);
	$effect(() => {
		const timer = setInterval(() => {
			if (!document.hidden) stamp = Date.now();
		}, every * 1000);
		return () => clearInterval(timer);
	});
	const clock = $derived(new Date(stamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/Phoenix' }));
</script>

<div class="tile">
	{#if online && !failed}
		<img src={`/api/cameras/${id}/snapshot?t=${stamp}`} alt={`${name} camera`} onerror={() => (failed = true)} onload={() => (failed = false)} />
	{:else}
		<div class="off">Offline</div>
	{/if}
	<div class="scrim">
		<span>{name}</span><span class="data">{online && !failed ? clock : '—'}</span>
	</div>
</div>

<style>
	.tile {
		position: relative;
		aspect-ratio: 16 / 9;
		background: #111;
		border-radius: var(--radius-md);
		overflow: hidden;
	}
	img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.off {
		height: 100%;
		display: grid;
		place-items: center;
		color: #a79f92;
		font: 500 11px/14px var(--font-data);
		letter-spacing: 0.12em;
		text-transform: uppercase;
	}
	.scrim {
		position: absolute;
		inset: auto 0 0 0;
		display: flex;
		justify-content: space-between;
		padding: var(--space-5) var(--space-3) var(--space-2);
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
		color: #fff;
		font-weight: 500;
		font-size: 14px;
	}
	.scrim .data {
		color: rgba(255, 255, 255, 0.85);
	}
</style>
