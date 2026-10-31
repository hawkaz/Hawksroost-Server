<script lang="ts">
	// Sign-in screens: the admin's cabin photo under a 40% ink scrim, or plain pine.
	import type { Snippet } from 'svelte';
	import Lockup from './Lockup.svelte';
	let { children }: { children: Snippet } = $props();
	let photo = $state<string | null>(null);

	$effect(() => {
		fetch('/api/auth/config')
			.then((r) => (r.ok ? r.json() : null))
			.then((c) => (photo = c?.login_photo ?? null))
			.catch(() => {});
	});
</script>

<div class="frame" style={photo ? `background-image:linear-gradient(rgba(42,38,34,.4),rgba(42,38,34,.4)),url('${photo}')` : ''}>
	<div class="inner">
		<Lockup size={56} />
		<div class="card stack">{@render children()}</div>
	</div>
</div>

<style>
	.frame {
		min-height: 100vh;
		background-color: var(--pine);
		background-size: cover;
		background-position: center;
		display: grid;
		place-items: center;
		padding: var(--space-5) var(--space-4);
	}
	.inner {
		width: 100%;
		max-width: 400px;
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
		align-items: center;
	}
	.card {
		width: 100%;
		padding: var(--space-5);
	}
</style>
