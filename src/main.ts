import './app.css';
import App from './App.svelte';
import { mount } from 'svelte';

const app = mount(App, { target: document.getElementById('app')! });

export default app;

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').then((reg) => {
    reg.addEventListener('updatefound', () => {
      const newWorker = reg.installing;
      if (!newWorker) return;
      newWorker.addEventListener('statechange', () => {
        if (newWorker.state === 'activated' && navigator.serviceWorker.controller) {
          newWorker.postMessage('skipWaiting');
        }
      });
    });

    const sw = reg.active || reg.waiting || reg.installing;
    if (sw && sw.state === 'activated') {
      precacheLoadedAssets(sw);
    } else if (sw) {
      sw.addEventListener('statechange', () => {
        if (sw.state === 'activated') precacheLoadedAssets(sw);
      });
    }
  }).catch(() => {});
}

function precacheLoadedAssets(sw: ServiceWorker) {
  const scripts = [...document.querySelectorAll<HTMLScriptElement>('script[src]')].map(s => s.src);
  const styles = [...document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')].map(l => l.href);
  const urls = [location.href, ...scripts, ...styles].filter(u => u.startsWith(location.origin));
  sw.postMessage({ type: 'PRECACHE_ASSETS', urls });
}
