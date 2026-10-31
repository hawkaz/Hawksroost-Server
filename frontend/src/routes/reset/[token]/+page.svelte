<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import AuthFrame from '#lib/components/AuthFrame.svelte';
	import { session } from '#lib/session.svelte.ts';

	const token = page.params.token ?? '';
	let who = $state<string | null>(null);
	let error = $state('');
	let password = $state('');
	let busy = $state(false);

	$effect(() => {
		api.get<{ name: string }>(`/api/auth/reset/${token}`).then((r) => (who = r.name)).catch((e) => (error = e.message));
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		try {
			await api.post(`/api/auth/reset/${token}`, { password });
			await session.load();
			goto('/');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong.';
		} finally {
			busy = false;
		}
	}
</script>

<AuthFrame>
	<h1>New password</h1>
	{#if error}<p class="notice danger" role="alert">{error}</p>{/if}
	{#if who}
		<p>Hi {who}. Pick a new password.</p>
		<form class="stack" onsubmit={submit}>
			<label class="field"
				><span>New password (8 or more characters)</span><input
					type="password"
					autocomplete="new-password"
					minlength="8"
					required
					bind:value={password}
				/></label
			>
			<button class="btn block" disabled={busy}>Save and sign in</button>
		</form>
	{/if}
</AuthFrame>
