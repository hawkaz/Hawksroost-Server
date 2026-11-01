// Turn notifications on for this device (Web Push).
import { api } from './api';

export function pushSupported(): boolean {
	return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

export function isStandalone(): boolean {
	return matchMedia('(display-mode: standalone)').matches || (navigator as unknown as { standalone?: boolean }).standalone === true;
}

export function isIOS(): boolean {
	return /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

export type Platform = 'ios' | 'android' | 'mac-safari' | 'desktop';

/** Rough guess at the kind of device, for install instructions. */
export function platform(): Platform {
	const ua = navigator.userAgent;
	if (isIOS()) return 'ios';
	if (/android/i.test(ua)) return 'android';
	if (/macintosh/i.test(ua) && /safari/i.test(ua) && !/chrome|chromium|edg\//i.test(ua)) return 'mac-safari';
	return 'desktop';
}

function keyToBytes(base64: string): Uint8Array<ArrayBuffer> {
	const pad = '='.repeat((4 - (base64.length % 4)) % 4);
	const raw = atob((base64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
	const out = new Uint8Array(new ArrayBuffer(raw.length));
	for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
	return out;
}

function deviceLabel(): string {
	const ua = navigator.userAgent;
	if (/iphone/i.test(ua)) return 'iPhone';
	if (/ipad/i.test(ua)) return 'iPad';
	if (/android/i.test(ua)) return 'Android';
	if (/windows/i.test(ua)) return 'Windows PC';
	if (/mac os/i.test(ua)) return 'Mac';
	return 'Browser';
}

export async function currentSubscription(): Promise<PushSubscription | null> {
	if (!pushSupported()) return null;
	const reg = await navigator.serviceWorker.getRegistration();
	return reg ? reg.pushManager.getSubscription() : null;
}

export async function enablePush(publicKey: string): Promise<void> {
	const permission = await Notification.requestPermission();
	if (permission !== 'granted') throw new Error('Notifications are blocked for this site. Allow them in your browser settings.');
	const reg = await navigator.serviceWorker.ready;
	let sub = await reg.pushManager.getSubscription();
	if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyToBytes(publicKey) });
	const json = sub.toJSON();
	await api.post('/api/me/push', { endpoint: json.endpoint, keys: json.keys, device_label: deviceLabel() });
}

export async function disablePush(): Promise<void> {
	const sub = await currentSubscription();
	if (!sub) return;
	await api.post('/api/me/push/remove', { endpoint: sub.endpoint });
	await sub.unsubscribe();
}
