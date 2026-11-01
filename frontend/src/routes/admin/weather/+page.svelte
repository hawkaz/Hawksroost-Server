<script lang="ts">
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	let s = $state<Record<string, Record<string, unknown>> | null>(null);
	let heard = $state<Record<string, string>>({});
	$effect(() => {
		if (!session.can('admin')) return;
		Promise.all([api.get<typeof s>('/api/admin/settings'), api.get<Record<string, string>>('/api/admin/tempest/devices')])
			.then(([v, d]) => ((s = v), (heard = d)))
			.catch(toast.error.bind(toast));
	});

	const FIELDS: Field[] = [
		{ key: 'enabled', label: 'Listen for the Tempest hub', type: 'checkbox' },
		{ key: 'serial', label: 'Station serial (optional)', placeholder: 'ST-00012345', help: 'Only needed if a neighbour’s station shows up on your network.' },
		{ key: 'elevation_ft', label: 'Station elevation in feet', type: 'number', help: 'Lets the app show sea-level pressure like the forecast does. Leave at 0 to show the pressure the station measures.' },
		{ key: 'station_id', label: 'Station ID (for the forecast, optional)', placeholder: '12345' },
		{ key: 'api_token', label: 'Personal access token (for the forecast, optional)', type: 'password', help: 'tempestwx.com → Settings → Data Authorizations → Create Token.' }
	];
</script>

<div class="stack">
	<AdminNav title="Weather" />
	{#if s}
		<SettingsForm section="tempest" title="Tempest station" fields={FIELDS} bind:values={s.tempest}>
			{#snippet intro()}
				<p class="small muted">Live readings come straight from the hub on the cabin network, so there’s nothing to sign in to. The forecast needs the station ID and a token.</p>
				{#if Object.keys(heard).length}
					<p class="small muted">Heard on the network:</p>
					<ul class="list heard">
						{#each Object.entries(heard) as [serial, kind] (serial)}
							<li><span class="data">{serial}</span><span class="small muted">{kind === 'hub_status' ? 'Hub' : 'Station'}</span></li>
						{/each}
					</ul>
				{:else}
					<p class="notice warn">No Tempest heard on the network yet. Check the hub is powered and on the same network as the laptop.</p>
				{/if}
			{/snippet}
		</SettingsForm>
	{/if}
</div>

<style>
	.heard li {
		min-height: 36px;
		justify-content: space-between;
	}
</style>
