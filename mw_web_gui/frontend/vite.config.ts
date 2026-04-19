import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

/**
 * Single cloudflared tunnel covers EVERY backend channel:
 *   /ws   -> foxglove_bridge (ws://localhost:8765)  via WebSocket proxy
 *   /api  -> dispatch HTTP helper (http://localhost:5174)
 * This way the browser only needs the cloudflared URL — no secondary
 * ?wsUrl= param, no cross-origin headaches.
 */
const BRIDGE_WS_PORT = 8765;
const DISPATCH_HTTP_PORT = 5174;

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/ws': {
        target: `ws://localhost:${BRIDGE_WS_PORT}`,
        ws: true,
        rewriteWsOrigin: true,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/ws/, ''),
      },
      '/api': {
        target: `http://localhost:${DISPATCH_HTTP_PORT}`,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: true,
  },
});
