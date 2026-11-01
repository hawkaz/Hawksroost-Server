<script lang="ts">
	// Weather condition → icon. Names follow Tempest's forecast icons (clear-day,
	// partly-cloudy-night, possibly-rainy-day, thunderstorm, …) plus "night" from the app.
	// Matched by keywords so new or unexpected names still get a sensible icon.
	import {
		Cloud, CloudFog, CloudHail, CloudLightning, CloudMoon, CloudMoonRain, CloudRain, CloudSnow, CloudSun,
		CloudSunRain, Moon, Sun, Wind
	} from '@lucide/svelte';

	let { icon, label = '', size = 24 }: { icon: string | null | undefined; label?: string; size?: number } = $props();

	const Comp = $derived.by(() => {
		const i = (icon ?? '').toLowerCase();
		const night = i.includes('night');
		if (i.includes('thunder')) return CloudLightning;
		if (i.includes('snow')) return CloudSnow;
		if (i.includes('sleet') || i.includes('hail')) return CloudHail;
		if (i.includes('possibly') && i.includes('rain')) return night ? CloudMoonRain : CloudSunRain;
		if (i.includes('rain') || i.includes('drizzle')) return CloudRain;
		if (i.includes('fog')) return CloudFog;
		if (i.includes('wind')) return Wind;
		if (i.includes('partly')) return night ? CloudMoon : CloudSun;
		if (i.includes('cloud')) return Cloud;
		if (night) return Moon;
		return Sun;
	});
</script>

{#if icon}
	<span class="wi" role={label ? 'img' : undefined} aria-label={label || undefined} aria-hidden={label ? undefined : 'true'}>
		<Comp {size} strokeWidth={1.6} />
	</span>
{/if}

<style>
	.wi {
		display: inline-flex;
		color: var(--accent);
		flex: none;
	}
</style>
