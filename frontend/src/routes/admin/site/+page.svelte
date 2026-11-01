<script lang="ts">
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import LoginPhoto from '#lib/components/admin/LoginPhoto.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	let s = $state<Record<string, Record<string, unknown>> | null>(null);
	$effect(() => {
		if (session.can('admin')) api.get<typeof s>('/api/admin/settings').then((v) => (s = v)).catch(toast.error.bind(toast));
	});

	const FIELDS: Field[] = [
		{ key: 'site_name', label: 'App name', help: 'Shown on the sign-in page, in emails and on the home screen icon.' },
		{ key: 'public_url', label: 'Web address', type: 'url', placeholder: 'https://hawksroost.live', help: 'Used in invite links, emails and Google sign-in.' },
		{ key: 'units', label: 'Units', type: 'select', options: [['imperial', '°F, mph, inches'], ['metric', '°C, km/h, mm']] }
	];
</script>

<div class="stack">
	<AdminNav title="Site" />
	{#if s}
		<div class="cols">
			<SettingsForm section="general" title="Basics" fields={FIELDS} bind:values={s.general} />
			<LoginPhoto />
		</div>
	{/if}
</div>

<style>
	.cols {
		display: grid;
		gap: var(--space-4);
		align-items: start;
	}
	@media (min-width: 1000px) {
		.cols {
			grid-template-columns: 1fr 1fr;
		}
	}
</style>
