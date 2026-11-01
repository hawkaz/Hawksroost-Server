<script lang="ts">
	// The message itself, plus a screen-reader region that's always there (a region added
	// together with its text often isn't read out). One instance on the page, and one in
	// each open sheet, which covers the page while it's open.
	import { toast } from '#lib/toast.svelte.ts';

	let { inSheet = false }: { inSheet?: boolean } = $props();
	const active = $derived(inSheet || toast.sheets === 0);
</script>

{#if active}
	<div class="sr-only" role="status" aria-live="polite" aria-atomic="true">{toast.message ?? ''}</div>
	{#if toast.message}
		<div class="toast" class:error={toast.kind === 'error'} class:in-sheet={inSheet} aria-hidden="true">{toast.message}</div>
	{/if}
{/if}

<style>
	.toast {
		position: fixed;
		left: 50%;
		transform: translateX(-50%);
		bottom: calc(var(--tabbar-h) + var(--space-4) + env(safe-area-inset-bottom));
		width: max-content;
		max-width: min(480px, calc(100vw - 32px));
		background: var(--ink);
		color: var(--cream);
		border-radius: var(--radius-md);
		padding: var(--space-3) var(--space-4);
		box-shadow: var(--shadow-overlay);
		z-index: 100;
		font-size: 15px;
		pointer-events: none;
	}
	.toast.error {
		background: var(--danger);
		color: #fff;
	}
	/* Phones: a sheet fills the bottom of the screen, so its messages show at the top. */
	.toast.in-sheet {
		bottom: auto;
		top: calc(env(safe-area-inset-top) + var(--space-4));
	}
	@media (min-width: 700px) {
		.toast,
		.toast.in-sheet {
			top: auto;
			bottom: var(--space-5);
		}
	}
</style>
