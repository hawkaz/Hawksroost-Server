// Live video player: go2rtc's VideoRTC element (served by go2rtc at /video/video-rtc.js),
// registered as <hawk-video> without go2rtc's demo overlay, which prints words like
// "loading" and "MSE" over the picture. Errors from the video server are sent as a
// "streamerror" event so the page can say the video isn't coming through.

/* eslint-disable @typescript-eslint/no-explicit-any */
let loading: Promise<void> | null = null;

function withEvents(VideoRTC: any): CustomElementConstructor {
	return class HawkVideo extends VideoRTC {
		onopen() {
			const r = super.onopen();
			this.onmessage['hawk'] = (msg: { type: string; value?: string }) => {
				if (msg.type === 'error') this.dispatchEvent(new CustomEvent('streamerror', { detail: msg.value }));
			};
			return r;
		}
	} as unknown as CustomElementConstructor;
}

/** Load and register <hawk-video> once. */
export function loadPlayer(): Promise<void> {
	if (customElements.get('hawk-video')) return Promise.resolve();
	loading ??= (async () => {
		const url = new URL('/video/video-rtc.js', location.origin).href;
		const { VideoRTC } = await import(/* @vite-ignore */ url);
		if (!customElements.get('hawk-video')) customElements.define('hawk-video', withEvents(VideoRTC));
	})().catch((e) => {
		loading = null; // let the next attempt try again
		throw e;
	});
	return loading;
}
