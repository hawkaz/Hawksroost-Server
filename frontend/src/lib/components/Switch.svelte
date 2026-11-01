<script lang="ts">
	// On/off switch. 44px tap area; the label is read by screen readers.
	let {
		checked,
		label,
		disabled = false,
		onchange
	}: { checked: boolean; label: string; disabled?: boolean; onchange: (on: boolean) => void } = $props();
</script>

<button
	type="button"
	role="switch"
	class="switch"
	aria-checked={checked}
	aria-label={label}
	{disabled}
	onclick={() => onchange(!checked)}
>
	<span class="track"><span class="knob"></span></span>
</button>

<style>
	.switch {
		flex: none;
		display: inline-grid;
		place-items: center;
		min-width: var(--tap);
		min-height: var(--tap);
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
	}
	.switch:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.track {
		position: relative;
		width: 48px;
		height: 28px;
		border-radius: var(--radius-pill);
		background: var(--line);
		border: 1px solid var(--line);
		transition: background 0.15s;
	}
	.knob {
		position: absolute;
		top: 2px;
		left: 2px;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--surface);
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
		transition: transform 0.15s;
	}
	[aria-checked='true'] .track {
		background: var(--primary);
		border-color: var(--primary);
	}
	[aria-checked='true'] .knob {
		transform: translateX(20px);
		background: var(--on-primary);
	}
	@media (prefers-reduced-motion: reduce) {
		.track,
		.knob {
			transition: none;
		}
	}
</style>
