<script lang="ts">
	// Bottom sheet on phones, centred dialog on tablets and computers.
	import { X } from '@lucide/svelte';
	import type { Snippet } from 'svelte';

	let { open = $bindable(false), title, children }: { open: boolean; title: string; children: Snippet } = $props();
	let dialog: HTMLDialogElement | undefined = $state();

	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) dialog.showModal();
		if (!open && dialog.open) dialog.close();
	});
</script>

<dialog bind:this={dialog} onclose={() => (open = false)} onclick={(e) => e.target === dialog && (open = false)}>
	{#if open}
		<div class="sheet">
			<div class="spread head">
				<h2>{title}</h2>
				<button class="btn icon" onclick={() => (open = false)} aria-label="Close"><X size={20} strokeWidth={1.75} /></button>
			</div>
			{@render children()}
		</div>
	{/if}
</dialog>

<style>
	dialog {
		border: 0;
		padding: 0;
		background: transparent;
		color: var(--text);
		max-width: 100vw;
		width: 100%;
		margin: auto auto 0;
	}
	dialog::backdrop {
		background: rgba(42, 38, 34, 0.45);
	}
	.sheet {
		background: var(--surface);
		border-radius: var(--radius-lg) var(--radius-lg) 0 0;
		padding: var(--space-4) var(--space-4) calc(var(--space-5) + env(safe-area-inset-bottom));
		box-shadow: var(--shadow-overlay);
		max-height: 88vh;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.head {
		margin: calc(-1 * var(--space-2)) calc(-1 * var(--space-2)) 0 0;
	}
	@media (min-width: 700px) {
		dialog {
			width: 520px;
			margin: auto;
		}
		.sheet {
			border-radius: var(--radius-lg);
			padding: var(--space-5);
		}
	}
</style>
