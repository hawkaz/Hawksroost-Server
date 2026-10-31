// Who's signed in, plus a few app-wide flags.
import { api } from './api';
import type { Me, Permission } from './types';

class Session {
	me = $state<Me | null>(null);
	loaded = $state(false);
	radioEnabled = $state(false);

	async load(): Promise<Me | null> {
		try {
			this.me = await api.get<Me>('/api/auth/me');
		} catch {
			this.me = null;
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
