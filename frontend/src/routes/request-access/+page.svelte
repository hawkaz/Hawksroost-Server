<script lang="ts">
	import { api } from '#lib/api.ts';
	import AuthFrame from '#lib/components/AuthFrame.svelte';

	let name = $state('');
	let email = $state('');
	let message = $state('');
	let busy = $state(false);
	let sent = $state(false);
	let error = $state('');

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			await api.post('/api/auth/request-access', { name, email, message: message || null });
			sent = true;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong.';
		} finally {
			busy = false;
		}
	}
</script>

<AuthFrame>
	{#if sent}
		<h1>Request sent</h1>
		<p>Thanks, {name}. An admin will look at it and send an invite to {email} if it's approved.</p>
		<a class="btn secondary" href="/login">Back to sign in</a>
	{:else}
		<h1>Request access</h1>
		<p class="muted">Hawksroost is private. Tell the admins who you are and they'll send you an invite.</p>
		{#if error}<p class="notice danger" role="alert">{error}</p>{/if}
		<form class="stack" onsubmit={submit}>
			<label class="field"><span>Your name</span><input id="ra-name" autocomplete="name" required maxlength="80" bind:value={name} /></label>
			<label class="field"><span>Email</span><input id="ra-email" type="email" autocomplete="email" required bind:value={email} /></label>
			<label class="field"><span>Note for the admins (optional)</span><textarea id="ra-note" maxlength="1000" bind:value={message} placeholder="How you know the family"></textarea></label>
			<button class="btn block" disabled={busy}>Send request</button>
		</form>
		<a class="btn text" href="/login">Back to sign in</a>
	{/if}
</AuthFrame>
