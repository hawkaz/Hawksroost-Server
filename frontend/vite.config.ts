import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
			},
			// Single-page app: nginx serves 200.html for any route.
			adapter: adapter({ fallback: '200.html' })
		})
	],
	server: {
		proxy: { '/api': 'http://127.0.0.1:8000', '/video': 'http://127.0.0.1:8080' }
	}
});
