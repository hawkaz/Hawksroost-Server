<script lang="ts">
	// Admin: pick the sign-in screen photo. Shrinks big photos before upload.
	import { api } from '#lib/api.ts';
	import { toast } from '#lib/toast.svelte.ts';

	let current = $state<string | null>(null);
	let busy = $state(false);

	$effect(() => {
		api.get<{ login_photo: string | null }>('/api/auth/config').then((c) => (current = c.login_photo)).catch(() => {});
	});

	async function shrink(file: File): Promise<Blob> {
		let img: ImageBitmap;
		try {
			img = await createImageBitmap(file);
		} catch {
			throw new Error("This browser can't read that photo. Try a JPEG or PNG.");
		}
		const scale = Math.min(1, 2400 / Math.max(img.width, img.height));
		const canvas = document.createElement('canvas');
		canvas.width = Math.round(img.width * scale);
		canvas.height = Math.round(img.height * scale);
		canvas.getContext('2d')!.drawImage(img, 0, 0, canvas.width, canvas.height);
		return new Promise((resolve, reject) =>
			canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not read that photo.'))), 'image/jpeg', 0.85)
		);
	}

	async function pick(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0];
		if (!file) return;
		busy = true;
		try {
			const r = await api.upload<{ url: string }>('/api/admin/login-photo', await shrink(file));
			current = r.url;
			toast.show('Sign-in photo updated.');
		} catch (err) {
			toast.error(err);
		} finally {
			busy = false;
			(e.target as HTMLInputElement).value = '';
		}
	}
	async function remove() {
		try {
			await api.del('/api/admin/login-photo');
			current = null;
			toast.show('Back to plain pine.');
		} catch (e) {
			toast.error(e);
		}
	}
</script>

<section class="card stack">
	<h2>Sign-in photo</h2>
	<p class="small muted">Shown behind the sign-in and invite screens. A wide, calm photo works best: the cabin, the lake, the pines.</p>
	{#if current}
		<div class="preview" style={`background-image:linear-gradient(rgba(42,38,34,.4),rgba(42,38,34,.4)),url('${current}')`}></div>
	{:else}
		<div class="preview empty">Plain pine</div>
	{/if}
	<div class="row wrap">
		<label class="btn secondary" class:busy>
			{busy ? 'Uploading…' : current ? 'Change photo' : 'Choose photo'}
			<input type="file" accept="image/jpeg,image/png,image/webp,image/heic" onchange={pick} disabled={busy} class="sr-only" />
		</label>
		{#if current}<button type="button" class="btn text" onclick={remove}>Use plain pine</button>{/if}
	</div>
</section>

<style>
	.preview {
		aspect-ratio: 16 / 9;
		max-width: 100%;
		border-radius: var(--radius-md);
		background-size: cover;
		background-position: center;
		background-color: var(--pine);
	}
	.empty {
		display: grid;
		place-items: center;
		color: var(--cream);
		font: 500 11px/14px var(--font-data);
		letter-spacing: 0.12em;
		text-transform: uppercase;
	}
	.busy {
		opacity: 0.6;
	}
</style>
