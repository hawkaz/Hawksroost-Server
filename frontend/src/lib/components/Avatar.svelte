<script lang="ts">
	import type { Person } from '#lib/types.ts';
	let { person, size = 28 }: { person: Person | null | undefined; size?: number } = $props();
	const initial = $derived(person?.name?.trim()?.[0]?.toUpperCase() ?? '?');
</script>

<span
	class="avatar"
	style="width:{size}px;height:{size}px;font-size:{Math.round(size * 0.45)}px;background:var(--fam-{person?.color ?? 'smoke'}, var(--smoke))"
	title={person?.name}
	aria-hidden="true">{initial}</span
>

<style>
	.avatar {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-pill);
		color: var(--snow);
		font-family: var(--font-ui);
		font-weight: 600;
		flex: none;
	}
</style>
