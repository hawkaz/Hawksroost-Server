<script lang="ts">
	import { page } from '$app/state';
	import { session } from '#lib/session.svelte.ts';
	const links = [
		['/admin', 'People'],
		['/admin/integrations', 'Integrations'],
		['/admin/radio', 'Radio'],
		['/admin/health', 'Health']
	];
</script>

<h1>Admin</h1>
{#if !session.can('admin')}
	<p class="notice warn">Only admins can see this.</p>
{:else}
	<nav class="pill-tabs" style="overflow-x:auto;max-width:100%">
		{#each links as [href, label] (href)}<a {href} class:on={page.url.pathname === href}>{label}</a>{/each}
	</nav>
{/if}
