<script lang="ts">
	import { toast } from '#lib/toast.svelte.ts';
</script>

{#if toast.message}
	<div class="toast" class:error={toast.kind === 'error'} role="status" aria-live="polite">{toast.message}</div>
{/if}

<style>
	.toast {
		position: fixed;
		left: 50%;
		transform: translateX(-50%);
		bottom: calc(var(--tabbar-h) + var(--space-4) + env(safe-area-inset-bottom));
		max-width: min(480px, calc(100vw - 32px));
		background: var(--ink);
		color: var(--cream);
		border-radius: var(--radius-md);
		padding: var(--space-3) var(--space-4);
		box-shadow: var(--shadow-overlay);
		z-index: 100;
		font-size: 15px;
	}
	.toast.error {
		background: var(--danger);
		color: #fff;
	}
	@media (min-width: 700px) {
		.toast {
			bottom: var(--space-5);
		}
	}
</style>
