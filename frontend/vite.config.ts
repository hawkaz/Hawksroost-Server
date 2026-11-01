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
		// Keep the browser's Host header so the API's same-origin check passes in dev.
		proxy: {
			'/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
			'/video': { target: 'http://127.0.0.1:8080', changeOrigin: false, ws: true }
		}
	}
});
