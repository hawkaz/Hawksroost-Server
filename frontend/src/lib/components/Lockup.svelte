<script lang="ts">
	import Mark from './Mark.svelte';
	let { descriptor = true, size = 44 }: { descriptor?: boolean; size?: number } = $props();
</script>

<div class="lockup">
	<Mark {size} />
	<div>
		<div class="word"><span class="hawk">Hawk</span><span class="az">AZ</span></div>
		{#if descriptor}<div class="desc">Cabin · Mormon Lake</div>{/if}
	</div>
</div>

<style>
	.lockup {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}
	.word {
		font: 800 24px/26px var(--font-display);
	}
	.hawk {
		color: var(--cream);
	}
	.az {
		color: var(--gold);
	}
	.desc {
		font: 500 10px/14px var(--font-data);
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: #a7b394;
		margin-top: 2px;
	}
</style>
