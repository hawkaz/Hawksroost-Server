// Small fetch wrapper: JSON in/out, cookie session, friendly errors.
import { goto } from '$app/navigation';

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

// Older iPhones (iOS 15) have no AbortSignal.timeout; they just wait as before.
const timeout = (ms: number) => ('timeout' in AbortSignal ? AbortSignal.timeout(ms) : undefined);

async function request<T>(method: string, path: string, body?: unknown, timeoutMs = 30000): Promise<T> {
	let res: Response;
	try {
		res = await fetch(path, {
			method,
			credentials: 'same-origin',
			headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
			body: body !== undefined ? JSON.stringify(body) : undefined,
			signal: timeout(timeoutMs)
		});
	} catch (e) {
		if (e instanceof DOMException && e.name === 'TimeoutError')
			throw new ApiError(0, 'The cabin is taking too long to answer. Try again in a minute.');
		throw new ApiError(0, "Can't reach the cabin right now. Check your connection.");
	}
	if (res.status === 401 && !path.startsWith('/api/auth/')) {
		const next = location.pathname + location.search;
		goto(`/login?next=${encodeURIComponent(next)}`);
		throw new ApiError(401, 'Please sign in.');
	}
	if (!res.ok) {
		let message = `Something went wrong (${res.status}).`;
		try {
			const data = await res.json();
			if (typeof data.detail === 'string') message = data.detail;
		} catch {
			/* not JSON */
		}
		if (res.status === 502 || res.status === 504) message = 'The cabin server is restarting. Try again in a minute.';
		throw new ApiError(res.status, message);
	}
	if (res.status === 204) return undefined as T;
	return res.json() as Promise<T>;
}

async function upload<T>(path: string, blob: Blob): Promise<T> {
	const res = await fetch(path, { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': blob.type }, body: blob });
	if (!res.ok) {
		let message = `Upload failed (${res.status}).`;
		try {
			const data = await res.json();
			if (typeof data.detail === 'string') message = data.detail;
		} catch {
			/* not JSON */
		}
		throw new ApiError(res.status, message);
	}
	return res.json() as Promise<T>;
}

export const api = {
	upload,
	get: <T>(path: string, timeoutMs?: number) => request<T>('GET', path, undefined, timeoutMs),
	post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
	put: <T>(path: string, body: unknown = {}) => request<T>('PUT', path, body),
	patch: <T>(path: string, body: unknown = {}) => request<T>('PATCH', path, body),
	del: <T>(path: string) => request<T>('DELETE', path)
};

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
	const p = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
	const s = p.toString();
	return s ? `?${s}` : '';
}
