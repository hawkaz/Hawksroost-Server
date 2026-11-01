import { Cctv, CloudSun, House, KeyRound, Radio, Satellite, Server, Users } from '@lucide/svelte';

// Admin is grouped by what you're looking after, not by how it's built.
export const ADMIN_SECTIONS = [
	{ href: '/admin/people', label: 'People', icon: Users, blurb: 'Accounts, invites and requests to join' },
	{ href: '/admin/site', label: 'Site', icon: House, blurb: 'App name, web address, units, sign-in photo' },
	{ href: '/admin/sign-in', label: 'Sign-in & email', icon: KeyRound, blurb: 'Email sending and Google sign-in' },
	{ href: '/admin/cameras', label: 'Cameras', icon: Cctv, blurb: 'Add cameras and set motion alerts' },
	{ href: '/admin/weather', label: 'Weather', icon: CloudSun, blurb: 'Tempest station and forecast' },
	{ href: '/admin/starlink', label: 'Starlink', icon: Satellite, blurb: 'Dish address, sleep schedule, controls' },
	{ href: '/admin/radio', label: 'Radio', icon: Radio, blurb: 'Scanner, channels and recordings' },
	{ href: '/admin/system', label: 'System', icon: Server, blurb: 'Health checks and backups' }
] as const;
