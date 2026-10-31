// Light / dark / follow the phone. Cameras and Radio are always dark (brand guide).
export type ThemePref = 'system' | 'light' | 'dark';

function read(): ThemePref {
	try {
		return (localStorage.getItem('theme') as ThemePref) || 'system';
	} catch {
		return 'system';
	}
}

class Theme {
	pref = $state<ThemePref>(read());
	forcedDark = $state(false);
	systemDark = $state(typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches);

	constructor() {
		if (typeof matchMedia !== 'undefined') {
			matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => (this.systemDark = e.matches));
		}
	}

	get dark() {
		return this.forcedDark || this.pref === 'dark' || (this.pref === 'system' && this.systemDark);
	}

	set(pref: ThemePref) {
		this.pref = pref;
		try {
			localStorage.setItem('theme', pref);
		} catch {
			/* private mode */
		}
	}
}

export const theme = new Theme();
