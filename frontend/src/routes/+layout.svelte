<script lang="ts">
	import '@fontsource/bitter/latin-600.css';
	import '@fontsource/bitter/latin-800.css';
	import '@fontsource/ibm-plex-sans/latin-400.css';
	import '@fontsource/ibm-plex-sans/latin-500.css';
	import '@fontsource/ibm-plex-sans/latin-600.css';
	import '@fontsource/ibm-plex-mono/latin-400.css';
	import '@fontsource/ibm-plex-mono/latin-500.css';
	import '../app.css';

	import { afterNavigate, goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		Calendar, Cctv, CloudSun, Ellipsis, ListChecks, Radio, Satellite, Settings, Shield, ShoppingCart, Sun
	} from '@lucide/svelte';
	import Avatar from '#lib/components/Avatar.svelte';
	import Lockup from '#lib/components/Lockup.svelte';
	import Mark from '#lib/components/Mark.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import Toast from '#lib/components/Toast.svelte';
	import { session } from '#lib/session.svelte.ts';
	import { theme } from '#lib/theme.svelte.ts';

	let { children } = $props();

	const PUBLIC = ['/login', '/invite/', '/reset/', '/request-access'];
	const isPublic = $derived(PUBLIC.some((p) => page.url.pathname === p || page.url.pathname.startsWith(p)));

	// Everything people use, in one order. Phones show the first five as tabs and the rest under More.
	const nav = $derived([
		{ href: '/', label: 'Today', icon: Sun },
		{ href: '/calendar', label: 'Calendar', icon: Calendar },
		{ href: '/shopping', label: 'Shopping', icon: ShoppingCart },
		{ href: '/lists', label: 'To-do', icon: ListChecks },
		{ href: '/cameras', label: 'Cameras', icon: Cctv },
		{ href: '/weather', label: 'Weather', icon: CloudSun },
		{ href: '/starlink', label: 'Starlink', icon: Satellite },
		...(session.radioEnabled ? [{ href: '/radio', label: 'Radio', icon: Radio }] : [])
	]);
	const tail = $derived([
		{ href: '/settings', label: 'Settings', icon: Settings },
		...(session.can('admin') ? [{ href: '/admin', label: 'Admin', icon: Shield }] : [])
	]);
	const tabs = $derived(nav.slice(0, 5));
	const more = $derived([...nav.slice(5), ...tail]);

	const TITLES: Record<string, string> = {
		'/': 'Today', '/calendar': 'Calendar', '/shopping': 'Shopping', '/lists': 'To-do', '/cameras': 'Cameras', '/radio': 'Radio',
		'/weather': 'Weather', '/starlink': 'Starlink', '/settings': 'Settings', '/admin': 'Admin'
	};
	const section = $derived('/' + (page.url.pathname.split('/')[1] ?? ''));
	const title = $derived(TITLES[section] ?? 'Hawksroost');
	const active = (href: string) => (href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href));
	const moreActive = $derived(more.some((m) => active(m.href)));
	let moreOpen = $state(false);
	afterNavigate(() => (moreOpen = false));

	// Cameras and Radio are always dark (brand guide).
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
		<!-- Tablets get an icon rail, desktops the full sidebar (same element, two widths). -->
		<aside class="sidebar">
			<a href="/" class="brand" aria-label="Home">
				<span class="full"><Lockup /></span>
				<span class="compact"><Mark size={36} /></span>
			</a>
			<nav aria-label="Main">
				{#each nav as t (t.href)}
					<a href={t.href} class:on={active(t.href)} aria-current={active(t.href) ? 'page' : undefined} title={t.label}>
						<t.icon size={20} strokeWidth={1.75} /><span>{t.label}</span>
					</a>
				{/each}
			</nav>
			<nav class="lower" aria-label="Account">
				{#each tail as t (t.href)}
					<a href={t.href} class:on={active(t.href)} aria-current={active(t.href) ? 'page' : undefined} title={t.label}>
						<t.icon size={20} strokeWidth={1.75} /><span>{t.label}</span>
					</a>
				{/each}
				<a class="me" href="/settings" title={session.me.name}><Avatar person={session.me} size={30} /><span>{session.me.name}</span></a>
			</nav>
		</aside>

		<header class="topbar">
			<a href="/" aria-label="Home" class="home"><Mark size={30} /></a>
			<span class="title">{title}</span>
			<a href="/settings" class="btn icon" aria-label="Settings"><Avatar person={session.me} size={30} /></a>
		</header>

		<main>
			<div class="content">{@render children()}</div>
		</main>

		<nav class="tabbar" aria-label="Main">
			{#each tabs as t (t.href)}
				<a href={t.href} class:on={active(t.href)} aria-current={active(t.href) ? 'page' : undefined}>
					<t.icon size={24} strokeWidth={1.75} />
					<span>{t.label}</span>
				</a>
			{/each}
			<button class:on={moreActive} onclick={() => (moreOpen = true)} aria-haspopup="dialog">
				<Ellipsis size={24} strokeWidth={1.75} />
				<span>More</span>
			</button>
		</nav>
	</div>

	<Sheet bind:open={moreOpen} title="More">
		<div class="more-grid">
			{#each more as t (t.href)}
				<a href={t.href} class="more-item" class:on={active(t.href)}>
					<t.icon size={24} strokeWidth={1.75} /><span>{t.label}</span>
				</a>
			{/each}
		</div>
	</Sheet>
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

	/* ---------- Phone (< 700px): top bar + bottom tabs ---------- */
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
	.home {
		display: flex;
	}
	.topbar .title {
		flex: 1;
		font: 800 20px/26px var(--font-display);
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
		grid-template-columns: repeat(6, 1fr);
		height: calc(var(--tabbar-h) + env(safe-area-inset-bottom));
		padding-bottom: env(safe-area-inset-bottom);
		background: var(--surface);
		border-top: 1px solid var(--line);
	}
	.tabbar a,
	.tabbar button {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		text-decoration: none;
		color: var(--text-muted);
		font: 500 11px/14px var(--font-ui);
		background: none;
		border: 0;
		cursor: pointer;
	}
	.tabbar .on {
		color: var(--accent);
	}
	.sidebar {
		display: none;
	}
	.more-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--space-2);
	}
	.more-item {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-4) var(--space-2);
		border-radius: var(--radius-md);
		border: 1px solid var(--line);
		text-decoration: none;
		color: var(--text);
		font: 500 14px/18px var(--font-ui);
	}
	.more-item.on {
		border-color: var(--accent);
		color: var(--accent);
	}

	/* ---------- Tablet (700–899px): icon rail ---------- */
	@media (min-width: 700px) {
		.topbar,
		.tabbar {
			display: none;
		}
		.shell {
			display: grid;
			grid-template-columns: 80px 1fr;
			min-height: 100vh;
		}
		.sidebar {
			display: flex;
			flex-direction: column;
			gap: var(--space-5);
			position: sticky;
			top: 0;
			height: 100vh;
			padding: var(--space-4) var(--space-2) var(--space-4);
			background: var(--header);
			color: var(--cream);
			overflow-y: auto;
		}
		.brand {
			text-decoration: none;
			display: flex;
			justify-content: center;
		}
		.brand .full {
			display: none;
		}
		.sidebar nav {
			display: flex;
			flex-direction: column;
			gap: 2px;
		}
		.sidebar nav:first-of-type {
			flex: 1;
		}
		.sidebar nav a {
			display: flex;
			flex-direction: column;
			align-items: center;
			gap: 2px;
			min-height: 52px;
			justify-content: center;
			padding: var(--space-1);
			border-radius: var(--radius-md);
			color: rgba(247, 239, 223, 0.82);
			text-decoration: none;
			font: 500 11px/14px var(--font-ui);
		}
		.sidebar nav a:hover {
			background: rgba(247, 239, 223, 0.08);
		}
		.sidebar nav a.on {
			background: rgba(247, 239, 223, 0.12);
			color: var(--cream);
		}
		.me span {
			display: none;
		}
		main {
			padding: var(--space-5) var(--space-5) var(--space-7);
		}
	}

	/* ---------- Desktop (≥ 900px): full sidebar ---------- */
	@media (min-width: 900px) {
		.shell {
			grid-template-columns: 240px 1fr;
		}
		.sidebar {
			padding: var(--space-5) var(--space-4);
		}
		.brand {
			justify-content: flex-start;
			padding: 0 var(--space-2);
		}
		.brand .full {
			display: block;
		}
		.brand .compact {
			display: none;
		}
		.sidebar nav a {
			flex-direction: row;
			justify-content: flex-start;
			gap: var(--space-3);
			min-height: var(--tap);
			padding: 0 var(--space-3);
			font: 500 15px/20px var(--font-ui);
		}
		.sidebar nav a.on {
			box-shadow: inset 3px 0 0 var(--gold);
		}
		.me span {
			display: inline;
		}
		main {
			padding: var(--space-6) var(--space-6) var(--space-7);
		}
	}
</style>
