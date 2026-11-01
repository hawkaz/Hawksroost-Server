<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import AuthFrame from '#lib/components/AuthFrame.svelte';
	import GoogleButton from '#lib/components/GoogleButton.svelte';
	import { session } from '#lib/session.svelte.ts';

	interface Cfg { google: boolean; email: boolean }
	let cfg = $state<Cfg | null>(null);
	let mode = $state<'signin' | 'forgot' | 'sent'>('signin');
	let email = $state('');
	let password = $state('');
	let remember = $state(true);
	let error = $state(page.url.searchParams.get('error') ?? '');
	let busy = $state(false);
	const next = page.url.searchParams.get('next') ?? '/';

	$effect(() => {
		api.get<Cfg>('/api/auth/config').then((c) => (cfg = c)).catch(() => {});
	});

	async function signIn(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			await api.post('/api/auth/login', { email, password, remember });
			await session.load();
			goto(next.startsWith('/') ? next : '/');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong.';
		} finally {
			busy = false;
		}
	}
	async function sendReset(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			await api.post('/api/auth/forgot', { email });
			mode = 'sent';
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong.';
		} finally {
			busy = false;
		}
	}
	const googleHref = $derived(`/api/auth/google/start?next=${encodeURIComponent(next)}&remember=${remember ? 1 : 0}`);
</script>

<AuthFrame>
	{#if mode === 'signin'}
		<h1>Sign in</h1>
		{#if error}<p class="notice danger" role="alert">{error}</p>{/if}
		{#if cfg?.google}
			<GoogleButton href={googleHref} />
			<div class="divider"><span>or</span></div>
		{/if}
		<form class="stack" onsubmit={signIn}>
			<label class="field"><span>Email</span><input id="email" type="email" autocomplete="email" required bind:value={email} /></label>
			<label class="field"><span>Password</span><input id="password" type="password" autocomplete="current-password" required bind:value={password} /></label>
			<div class="spread">
				<label class="check"><input id="remember" type="checkbox" bind:checked={remember} /> Remember me</label>
				<button type="button" class="btn text" onclick={() => ((mode = 'forgot'), (error = ''))}>Forgot password?</button>
			</div>
			<button class="btn block" disabled={busy}>Sign in</button>
		</form>
		<p class="foot">New here? <a href="/request-access">Request access</a></p>
	{:else if mode === 'forgot'}
		<h1>Reset your password</h1>
		<p class="muted">Enter the email you sign in with.</p>
		{#if error}<p class="notice danger" role="alert">{error}</p>{/if}
		<form class="stack" onsubmit={sendReset}>
			<label class="field"><span>Email</span><input id="reset-email" type="email" autocomplete="email" required bind:value={email} /></label>
			<button class="btn block" disabled={busy}>Send reset link</button>
		</form>
		<button class="btn text" onclick={() => (mode = 'signin')}>Back to sign in</button>
	{:else}
		<h1>Check your email</h1>
		{#if cfg?.email}
			<p>If {email} has an account, a link to set a new password is on its way. It works for 2 days.</p>
		{:else}
			<p>An admin has been told you need a new password. They'll send you a link to set one.</p>
		{/if}
		<button class="btn secondary" onclick={() => ((mode = 'signin'), (password = ''))}>Back to sign in</button>
	{/if}
</AuthFrame>

<style>
	.divider {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		color: var(--text-muted);
		font-size: 13px;
	}
	.divider::before,
	.divider::after {
		content: '';
		flex: 1;
		height: 1px;
		background: var(--line);
	}
	.check {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		min-height: var(--tap);
		cursor: pointer;
	}
	.foot {
		text-align: center;
		color: var(--text-muted);
		border-top: 1px solid var(--line);
		padding-top: var(--space-4);
	}
	.foot a {
		color: var(--accent);
		font-weight: 500;
	}
</style>
