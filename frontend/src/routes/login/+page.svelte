<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import AuthFrame from '#lib/components/AuthFrame.svelte';
	import GoogleButton from '#lib/components/GoogleButton.svelte';
	import { session } from '#lib/session.svelte.ts';

	let cfg = $state<{ google: boolean; email: boolean } | null>(null);
	let email = $state('');
	let password = $state('');
	let error = $state(page.url.searchParams.get('error') ?? '');
	let busy = $state(false);
	let forgot = $state(false);
	let sent = $state(false);
	const next = page.url.searchParams.get('next') ?? '/';

	$effect(() => {
		api.get<{ google: boolean; email: boolean }>('/api/auth/config').then((c) => (cfg = c)).catch(() => {});
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			if (forgot) {
				await api.post('/api/auth/forgot', { email });
				sent = true;
			} else {
				await api.post('/api/auth/login', { email, password });
				await session.load();
				goto(next.startsWith('/') ? next : '/');
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong.';
		} finally {
			busy = false;
		}
	}
</script>

<AuthFrame>
	<h1>{forgot ? 'Reset password' : 'Sign in'}</h1>
	{#if error}<p class="notice danger" role="alert">{error}</p>{/if}
	{#if sent}
		<p>If there's an account for {email}, a reset link is on its way. Check your email.</p>
		<button class="btn secondary" onclick={() => ((forgot = false), (sent = false))}>Back to sign in</button>
	{:else}
		{#if cfg?.google && !forgot}
			<GoogleButton href={`/api/auth/google/start?next=${encodeURIComponent(next)}`} />
			<div class="or label">or</div>
		{/if}
		<form class="stack" onsubmit={submit}>
			<label class="field"><span>Email</span><input type="email" autocomplete="email" required bind:value={email} /></label>
			{#if !forgot}
				<label class="field"
					><span>Password</span><input type="password" autocomplete="current-password" required bind:value={password} /></label
				>
			{/if}
			<button class="btn block" disabled={busy}>{forgot ? 'Send reset link' : 'Sign in'}</button>
		</form>
		{#if forgot}
			<button class="btn text" onclick={() => (forgot = false)}>Back to sign in</button>
		{:else if cfg?.email}
			<button class="btn text" onclick={() => (forgot = true)}>Forgot password?</button>
		{:else}
			<p class="small muted">Forgot your password? Ask Chris or another admin for a reset link.</p>
		{/if}
	{/if}
	<p class="small muted">This is a private family app. Accounts are by invite only.</p>
</AuthFrame>

<style>
	.or {
		text-align: center;
	}
</style>
