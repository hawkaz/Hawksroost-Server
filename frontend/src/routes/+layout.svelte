<script lang="ts">
	import '@fontsource/bitter/latin-600.css';
	import '@fontsource/bitter/latin-800.css';
	import '@fontsource/ibm-plex-sans/latin-400.css';
	import '@fontsource/ibm-plex-sans/latin-500.css';
	import '@fontsource/ibm-plex-sans/latin-600.css';
	import '@fontsource/ibm-plex-mono/latin-400.css';
	import '@fontsource/ibm-plex-mono/latin-500.css';
	import '../app.css';

	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Calendar, Cctv, CloudSun, ListChecks, Radio, Settings, Shield, Sun } from '@lucide/svelte';
	import Avatar from '#lib/components/Avatar.svelte';
	import Lockup from '#lib/components/Lockup.svelte';
	import Mark from '#lib/components/Mark.svelte';
	import Toast from '#lib/components/Toast.svelte';
	import { session } from '#lib/session.svelte.ts';
	import { theme } from '#lib/theme.svelte.ts';

	let { children } = $props();

	const PUBLIC = ['/login', '/invite/', '/reset/'];
	const isPublic = $derived(PUBLIC.some((p) => page.url.pathname === p || page.url.pathname.startsWith(p)));

	const tabs = $derived([
		{ href: '/', label: 'Today', icon: Sun },
		{ href: '/calendar', label: 'Calendar', icon: Calendar },
		{ href: '/lists', label: 'Lists', icon: ListChecks },
		{ href: '/cameras', label: 'Cameras', icon: Cctv },
		...(session.radioEnabled ? [{ href: '/radio', label: 'Radio', icon: Radio }] : [])
	]);
	const extra = $derived([
		{ href: '/weather', label: 'Weather', icon: CloudSun },
		{ href: '/settings', label: 'Settings', icon: Settings },
		...(session.can('admin') ? [{ href: '/admin', label: 'Admin', icon: Shield }] : [])
	]);

	const TITLES: Record<string, string> = {
		'/': 'Today',
		'/calendar': 'Calendar',
		'/lists': 'Lists',
		'/cameras': 'Cameras',
		'/radio': 'Radio',
		'/weather': 'Weather',
		'/settings': 'Settings',
		'/admin': 'Admin'
	};
	const section = $derived('/' + (page.url.pathname.split('/')[1] ?? ''));
	const title = $derived(TITLES[section] ?? 'Hawksroost');
	const active = (href: string) => (href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href));

	// Cameras and Radio are always dark.
	$effect(() => {
		theme.forcedDark = section === '/cameras' || section === '/radio';
	});
	$effect(() => {
		document.documentElement.dataset.theme = theme.dark ? 'dark' : 'light';
	});

	$effect(() => {
		if (!session.loaded) {
			session.load().then((me) => {
				if (!me && !isPublic) goto(`/login?next=${encodeURIComponent(page.url.pathname + page.url.search)}`);
			});
		}
	});

	$effect(() => {
		if ('serviceWorker' in navigator && location.protocol === 'https:') {
			navigator.serviceWorker.register('/service-worker.js', { type: 'module' }).catch(() => {});
		}
	});
</script>

<svelte:head><title>{isPublic ? 'Hawksroost' : `${title} · Hawksroost`}</title></svelte:head>

{#if isPublic}
	{@render children()}
{:else if session.me}
	<div class="shell">
		<aside class="sidebar">
			<a href="/" class="brand" aria-label="Home"><Lockup /></a>
			<nav>
				{#each [...tabs, ...extra] as t (t.href)}
					<a href={t.href} class:on={active(t.href)} aria-current={active(t.href) ? 'page' : undefined}>
						<t.icon size={20} strokeWidth={1.75} />{t.label}
					</a>
				{/each}
			</nav>
			<a class="me" href="/settings"><Avatar person={session.me} size={32} /><span>{session.me.name}</span></a>
		</aside>

		<header class="topbar">
			<a href="/" aria-label="Home"><Mark size={30} /></a>
			<span class="title">{title}</span>
			<a href="/weather" class="btn icon" aria-label="Weather"><CloudSun size={22} strokeWidth={1.75} /></a>
			<a href="/settings" class="btn icon" aria-label="Settings"><Avatar person={session.me} size={30} /></a>
		</header>

		<main>
			<div class="content">{@render children()}</div>
		</main>

		<nav class="tabbar" style="--n:{tabs.length}">
			{#each tabs as t (t.href)}
				<a href={t.href} class:on={active(t.href)} aria-current={active(t.href) ? 'page' : undefined}>
					<t.icon size={24} strokeWidth={1.75} />
					<span>{t.label}</span>
				</a>
			{/each}
		</nav>
	</div>
{:else}
	<div class="loading" aria-busy="true"><Mark size={64} hawk="var(--pine)" /></div>
{/if}

<Toast />

<style>
	.loading {
		min-height: 100vh;
		display: grid;
		place-items: center;
	}
	.topbar {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		gap: var(--space-3);
		height: calc(var(--topbar-h) + env(safe-area-inset-top));
		padding: env(safe-area-inset-top) var(--space-2) 0 var(--space-4);
		background: var(--header);
		color: var(--cream);
	}
	.topbar > a:first-child {
		display: flex;
	}
	.topbar .title {
		flex: 1;
		font: 800 20px/26px var(--font-display);
	}
	.topbar .btn.icon {
		color: var(--cream);
	}
	main {
		padding: var(--space-4) var(--space-4) calc(var(--tabbar-h) + var(--space-6) + env(safe-area-inset-bottom));
	}
	.content {
		max-width: 1120px;
		margin: 0 auto;
	}
	.tabbar {
		position: fixed;
		inset: auto 0 0 0;
		z-index: 20;
		display: grid;
		grid-template-columns: repeat(var(--n), 1fr);
		height: calc(var(--tabbar-h) + env(safe-area-inset-bottom));
		padding-bottom: env(safe-area-inset-bottom);
		background: var(--surface);
		border-top: 1px solid var(--line);
	}
	.tabbar a {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		text-decoration: none;
		color: var(--text-muted);
		font: 500 11px/14px var(--font-ui);
	}
	.tabbar a.on {
		color: var(--accent);
	}
	.sidebar {
		display: none;
	}

	@media (min-width: 900px) {
		.topbar,
		.tabbar {
			display: none;
		}
		.shell {
			display: grid;
			grid-template-columns: 240px 1fr;
			min-height: 100vh;
		}
		.sidebar {
			display: flex;
			flex-direction: column;
			gap: var(--space-5);
			position: sticky;
			top: 0;
			height: 100vh;
			padding: var(--space-5) var(--space-4);
			background: var(--header);
			color: var(--cream);
		}
		.brand {
			text-decoration: none;
			padding: 0 var(--space-2);
		}
		.sidebar nav {
			display: flex;
			flex-direction: column;
			gap: 2px;
			flex: 1;
		}
		.sidebar nav a,
		.me {
			display: flex;
			align-items: center;
			gap: var(--space-3);
			min-height: var(--tap);
			padding: 0 var(--space-3);
			border-radius: var(--radius-md);
			color: rgba(247, 239, 223, 0.82);
			text-decoration: none;
			font: 500 15px/20px var(--font-ui);
		}
		.sidebar nav a:hover,
		.me:hover {
			background: rgba(247, 239, 223, 0.08);
		}
		.sidebar nav a.on {
			background: rgba(247, 239, 223, 0.12);
			color: var(--cream);
			box-shadow: inset 3px 0 0 var(--gold);
		}
		main {
			padding: var(--space-6) var(--space-6) var(--space-7);
		}
	}
</style>
