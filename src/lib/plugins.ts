export interface PluginManifest {
  name: string;
  version: string;
  description?: string;
  entrypoint: string;
}

export interface PluginInstance {
  manifest: PluginManifest;
  module: any;
  element?: HTMLElement;
}

let _plugins: PluginInstance[] = [];

export function getPlugins(): PluginInstance[] { return _plugins; }

export async function loadPlugin(url: string): Promise<PluginInstance> {
  const resp = await fetch(url);
  const text = await resp.text();
  const blob = new Blob([text], { type: 'application/javascript' });
  const blobUrl = URL.createObjectURL(blob);
  const mod = await import(/* @vite-ignore */ blobUrl);
  URL.revokeObjectURL(blobUrl);
  const manifest: PluginManifest = mod.manifest || { name: 'Unknown', version: '0.0.0', entrypoint: url };
  const instance: PluginInstance = { manifest, module: mod };
  if (typeof mod.mount === 'function') {
    const el = document.createElement('div');
    mod.mount(el);
    instance.element = el;
  }
  _plugins.push(instance);
  return instance;
}

export function unloadPlugin(name: string) {
  const idx = _plugins.findIndex(p => p.manifest.name === name);
  if (idx >= 0) {
    const p = _plugins[idx];
    if (p.module.unmount) p.module.unmount();
    if (p.element) p.element.remove();
    _plugins.splice(idx, 1);
  }
}

export function getPluginApi() {
  return {
    version: '3.2.0',
    subscribe: (event: string, cb: Function) => {
      window.addEventListener(`pllink:${event}`, (e: any) => cb(e.detail));
    },
    emit: (event: string, data: any) => {
      window.dispatchEvent(new CustomEvent(`pllink:${event}`, { detail: data }));
    },
  };
}
