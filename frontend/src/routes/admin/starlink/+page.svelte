<script lang="ts">
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import { ago } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	interface Dish {
		enabled: boolean; reachable: boolean; state_label: string; updated_at: string | null; error: string | null;
		status: { state?: string } | null;
		sleep: { enabled: boolean; start_local: string; duration_min: number } | null;
	}
	let s = $state<Record<string, Record<string, unknown>> | null>(null);
	let dish = $state<Dish | null>(null);
	let sleep = $state({ enabled: false, start_local: '02:00', duration_min: 120 });
	let busy = $state('');

	async function load() {
		try {
			[s, dish] = await Promise.all([api.get<typeof s>('/api/admin/settings'), api.get<Dish>('/api/starlink')]);
			if (dish.sleep) sleep = { enabled: dish.sleep.enabled, start_local: dish.sleep.start_local, duration_min: dish.sleep.duration_min };
		} catch (e) {
			toast.error(e);
		}
	}
	$effect(() => {
		if (session.can('admin')) load();
	});

	async function act(what: string, url: string, body: unknown, ask: string, done: string) {
		if (ask && !confirm(ask)) return;
		busy = what;
		try {
			await api.post(url, body);
			toast.show(done);
			setTimeout(load, 3000);
		} catch (e) {
			toast.error(e);
		} finally {
			busy = '';
		}
	}
	async function saveSleep(e: SubmitEvent) {
		e.preventDefault();
		busy = 'sleep';
		try {
			await api.put('/api/admin/starlink/sleep', { ...sleep, duration_min: Number(sleep.duration_min) });
			toast.show(sleep.enabled ? `Dish will sleep from ${sleep.start_local}.` : 'Sleep schedule off.');
		} catch (err) {
			toast.error(err);
		} finally {
			busy = '';
		}
	}

	const FIELDS: Field[] = [
		{ key: 'enabled', label: 'Watch the Starlink dish', type: 'checkbox' },
		{ key: 'address', label: 'Dish address', placeholder: '192.168.100.1:9200', help: 'Almost always 192.168.100.1:9200. With your own router in bypass mode, the router has to be able to reach that address.' }
	];
	const stowed = $derived(dish?.status?.state === 'STOWED');
	const DURATIONS = [[60, '1 hour'], [120, '2 hours'], [180, '3 hours'], [240, '4 hours'], [360, '6 hours'], [480, '8 hours']] as const;
</script>

<div class="stack">
	<AdminNav title="Starlink" />
	{#if s}
		<div class="cols">
			<div class="stack">
				<SettingsForm section="starlink" title="Connection" fields={FIELDS} bind:values={s.starlink}>
					{#snippet intro()}
						{#if dish?.enabled}
							<p class="small" class:muted={dish.reachable} class:err={!dish.reachable}>
								{dish.reachable ? `${dish.state_label}. Last heard ${ago(dish.updated_at)}.` : (dish.error ?? dish.state_label)}
							</p>
						{/if}
					{/snippet}
				</SettingsForm>

				<section class="card">
					<form class="stack" onsubmit={saveSleep}>
						<h2>Sleep schedule</h2>
						<p class="small muted">The dish can power down for a few hours each night to save power. The internet is off while it sleeps, and so are remote cameras.</p>
						<label class="spread"><span>Sleep every night</span><input type="checkbox" bind:checked={sleep.enabled} /></label>
						<div class="grid grid-2">
							<label class="field"><span>Starts at (cabin time)</span><input type="time" bind:value={sleep.start_local} disabled={!sleep.enabled} /></label>
							<label class="field"><span>For</span>
								<select bind:value={sleep.duration_min} disabled={!sleep.enabled}>
									{#each DURATIONS as [v, l] (v)}<option value={v}>{l}</option>{/each}
								</select>
							</label>
						</div>
						<div><button class="btn" disabled={!!busy || !dish?.reachable}>Save schedule</button></div>
					</form>
				</section>
			</div>

			<section class="card stack">
				<h2>Dish controls</h2>
				{#if !dish?.reachable}<p class="notice warn">The dish isn’t answering, so these won’t work right now.</p>{/if}
				<div class="control">
					<div class="grow"><h3>Restart</h3><p class="small muted">Fixes most odd behaviour. The internet drops for a few minutes, and this page with it.</p></div>
					<button class="btn secondary" disabled={!!busy || !dish?.reachable}
						onclick={() => act('reboot', '/api/admin/starlink/reboot', undefined, 'Restart the dish? The cabin’s internet goes down for a few minutes.', 'Dish is restarting.')}>Restart</button>
				</div>
				<div class="control">
					<div class="grow">
						<h3>{stowed ? 'Unstow' : 'Stow'}</h3>
						<p class="small muted">{stowed ? 'Point the dish back at the sky and reconnect.' : 'Lays the dish flat for storms or moving it. No internet until you unstow.'}</p>
					</div>
					<button class="btn secondary" disabled={!!busy || !dish?.reachable}
						onclick={() => act('stow', '/api/admin/starlink/stow', { stow: !stowed }, stowed ? '' : 'Stow the dish? The cabin’s internet goes off until someone unstows it — from the laptop on the cabin network, or the Starlink app.', stowed ? 'Dish is unstowing.' : 'Dish is stowing.')}>{stowed ? 'Unstow' : 'Stow'}</button>
				</div>
				<div class="control">
					<div class="grow"><h3>Reset obstruction map</h3><p class="small muted">Use after trimming trees or moving the dish. The map rebuilds over the next few hours.</p></div>
					<button class="btn secondary" disabled={!!busy || !dish?.reachable}
						onclick={() => act('map', '/api/admin/starlink/reset-map', undefined, 'Clear the obstruction map? It rebuilds over a few hours.', 'Obstruction map cleared.')}>Reset</button>
				</div>
			</section>
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
	.control {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		padding-top: var(--space-4);
		border-top: 1px solid var(--line);
	}
	.control h3 {
		font-size: 16px;
	}
	.err {
		color: var(--danger);
	}
</style>
