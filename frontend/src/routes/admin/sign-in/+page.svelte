<script lang="ts">
	import { Copy } from '@lucide/svelte';
	import { api } from '#lib/api.ts';
	import AdminNav from '#lib/components/admin/AdminNav.svelte';
	import SettingsForm, { type Field } from '#lib/components/admin/SettingsForm.svelte';
	import { session } from '#lib/session.svelte.ts';
	import { toast } from '#lib/toast.svelte.ts';

	let s = $state<Record<string, Record<string, unknown>> | null>(null);
	let testTo = $state(session.me?.email ?? '');
	$effect(() => {
		if (session.can('admin')) api.get<typeof s>('/api/admin/settings').then((v) => (s = v)).catch(toast.error.bind(toast));
	});

	async function testEmail() {
		try {
			await api.post('/api/admin/settings/email/test', { to: testTo });
			toast.show(`Test email sent to ${testTo}.`);
		} catch (e) {
			toast.error(e);
		}
	}
	function copy(t: string) {
		navigator.clipboard?.writeText(t).then(() => toast.show('Copied.'));
	}

	const EMAIL: Field[] = [
		{ key: 'api_key', label: 'Brevo API key', type: 'password', help: 'In Brevo: SMTP & API → API keys → Generate. It starts with xkeysib- (an SMTP key won’t work).' },
		{ key: 'from_email', label: 'Send from', type: 'email', placeholder: 'cabin@hawksroost.live', help: 'An address on a domain you’ve verified in Brevo. Emails show the app name as the sender.' }
	];
	const GOOGLE: Field[] = [
		{ key: 'enabled', label: 'Allow “Continue with Google”', type: 'checkbox' },
		{ key: 'client_id', label: 'Client ID' },
		{ key: 'client_secret', label: 'Client secret', type: 'password' }
	];
</script>

<div class="stack">
	<AdminNav title="Sign-in & email" />
	{#if s}
		<p class="muted intro">People always sign in with their email and a password. Email lets the app send invites, password resets and requests to join. Google sign-in is an optional extra.</p>
		<div class="cols">
			<SettingsForm section="email" title="Email (Brevo)" fields={EMAIL} bind:values={s.email}>
				{#snippet intro()}<p class="small muted">Email is on once both are filled in. Without it, you send invite and reset links yourself, and requests to join only reach admins as notifications.</p>{/snippet}
				{#snippet actions()}
					<input type="email" bind:value={testTo} class="test-to" aria-label="Send a test to" />
					<button type="button" class="btn secondary" onclick={testEmail}>Send test</button>
				{/snippet}
			</SettingsForm>

			<SettingsForm section="google" title="Google sign-in" fields={GOOGLE} bind:values={s.google}>
				{#snippet intro()}
					<div class="small muted stack" style="gap:8px">
						<p>In Google Cloud Console: APIs &amp; Services → Credentials → Create credentials → OAuth client ID → Web application. Add this as an authorised redirect URI:</p>
						<div class="row"><input readonly value={s!.google.redirect_uri as string} /><button type="button" class="btn icon secondary" aria-label="Copy" onclick={() => copy(s!.google.redirect_uri as string)}><Copy size={18} strokeWidth={1.75} /></button></div>
						<p>OAuth consent screen: External, publishing status “In production”. Only the basic email and profile scopes are used, so no Google review is needed.</p>
					</div>
				{/snippet}
			</SettingsForm>
		</div>
	{/if}
</div>

<style>
	.intro {
		max-width: 70ch;
	}
	.test-to {
		max-width: 260px;
	}
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
