<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import AuthFrame from '#lib/components/AuthFrame.svelte';
	import GoogleButton from '#lib/components/GoogleButton.svelte';
	import { session } from '#lib/session.svelte.ts';

	const token = page.params.token ?? '';
	let invite = $state<{ email: string | null; name: string | null; role: string } | null>(null);
	let cfg = $state<{ google: boolean } | null>(null);
	let error = $state('');
	let name = $state('');
	let email = $state('');
	let password = $state('');
	let busy = $state(false);

	$effect(() => {
		api
			.get<{ email: string | null; name: string | null; role: string }>(`/api/auth/invite/${token}`)
			.then((i) => {
				invite = i;
				name = i.name ?? '';
				email = i.email ?? '';
			})
			.catch((e) => (error = e.message));
		api.get<{ google: boolean }>('/api/auth/config').then((c) => (cfg = c)).catch(() => {});
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			await api.post(`/api/auth/invite/${token}`, { name, email, password });
			await session.load();
			goto('/settings?welcome=1');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong.';
		} finally {
			busy = false;
		}
	}
</script>

<AuthFrame>
	<h1>Welcome</h1>
	{#if error}<p class="notice danger" role="alert">{error}</p>{/if}
	{#if invite}
		<p>You're invited to the family cabin app{invite.role === 'admin' ? ' as an admin' : ''}. Set up your account.</p>
		{#if cfg?.google}
			<GoogleButton href={`/api/auth/google/start?invite=${encodeURIComponent(token)}&next=/settings`} label="Sign up with Google" />
			<div class="label" style="text-align:center">or make a password</div>
		{/if}
		<form class="stack" onsubmit={submit}>
			<label class="field"><span>Your first name</span><input autocomplete="given-name" required bind:value={name} /></label>
			<label class="field"><span>Email</span><input type="email" autocomplete="email" required bind:value={email} /></label>
			<label class="field"
				><span>Password (8 or more characters)</span><input
					type="password"
					autocomplete="new-password"
					minlength="8"
					required
					bind:value={password}
				/></label
			>
			<button class="btn block" disabled={busy}>Create account</button>
		</form>
	{/if}
</AuthFrame>
