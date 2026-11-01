// Who's signed in, plus a few app-wide flags.
import { api, ApiError } from './api';
import type { Me, Permission } from './types';

class Session {
	me = $state<Me | null>(null);
	loaded = $state(false);
	/** The app couldn't ask who's signed in (offline, cabin restarting). Not the same as signed out. */
	unreachable = $state(false);
	radioEnabled = $state(false);

	async load(): Promise<Me | null> {
		try {
			this.me = await api.get<Me>('/api/auth/me', 12000);
			this.unreachable = false;
		} catch (e) {
			// Only "not signed in" signs you out; a dropped connection or a restart doesn't.
			const signedOut = e instanceof ApiError && e.status === 401;
			if (signedOut) this.me = null;
			this.unreachable = !signedOut && !this.me;
		}
		this.loaded = true;
		if (this.me) this.refreshFeatures();
		return this.me;
	}

	async refreshFeatures() {
		try {
			const s = await api.get<{ enabled: boolean }>('/api/radio/status');
			this.radioEnabled = s.enabled;
		} catch {
			this.radioEnabled = false;
		}
	}

	can(p: Permission): boolean {
		return !!this.me?.can[p];
	}

	async logout() {
		await api.post('/api/auth/logout');
		this.me = null;
	}
}

export const session = new Session();
