<script lang="ts">
	// Sign-in screens: pine backdrop (swap for a family photo with a 40% ink scrim later).
	import type { Snippet } from 'svelte';
	import Lockup from './Lockup.svelte';
	let { children }: { children: Snippet } = $props();
</script>

<div class="frame">
	<div class="inner">
		<Lockup size={56} />
		<div class="card stack">{@render children()}</div>
	</div>
</div>

<style>
	.frame {
		min-height: 100vh;
		background: var(--pine);
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
