<script lang="ts">
	// Admin page heading. Sub-pages get a way back to the overview and, on wider
	// screens, a row of links to the other sections.
	import { page } from '$app/state';
	import { session } from '#lib/session.svelte.ts';
	import { ADMIN_SECTIONS } from './sections.ts';

	let { title }: { title?: string } = $props();
</script>

<header class="head">
	{#if title}<a href="/admin" class="small muted">← Admin</a>{/if}
	<h1>{title ?? 'Admin'}</h1>
</header>
{#if !session.can('admin')}
	<p class="notice warn">Only admins can see this.</p>
{:else if title}
	<nav class="subnav" aria-label="Admin sections">
		{#each ADMIN_SECTIONS as s (s.href)}
			<a href={s.href} class:on={page.url.pathname.startsWith(s.href)} aria-current={page.url.pathname.startsWith(s.href) ? 'page' : undefined}>{s.label}</a>
		{/each}
	</nav>
{/if}

<style>
	.head {
		display: flex;
		flex-direction: column;
	}
	.subnav {
		display: none;
	}
	@media (min-width: 700px) {
		.subnav {
			display: flex;
			gap: var(--space-1);
			overflow-x: auto;
			scrollbar-width: none;
			border-bottom: 1px solid var(--line);
		}
		.subnav a {
			flex: none;
			display: inline-flex;
			align-items: center;
			min-height: var(--tap);
			padding: 0 var(--space-3);
			color: var(--text-muted);
			text-decoration: none;
			font: 500 14px/20px var(--font-ui);
			border-bottom: 2px solid transparent;
			margin-bottom: -1px;
		}
		.subnav a:hover {
			color: var(--text);
		}
		.subnav a.on {
			color: var(--text);
			border-bottom-color: var(--accent);
		}
	}
</style>
