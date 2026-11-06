// Service-Worker: macht die App offline nutzbar und nimmt geteilte Inhalte an (Android „Teilen“ → Datenwächter).
// Er spricht mit keinem Server außer dem, von dem die App selbst kommt.
const VERSION = "__VERSION__";
const APP = "dw-app-" + VERSION;
const LATER = "dw-nachgeladen-__VENDOR__";   // Texterkennung, PDF-Schriften: beim ersten Gebrauch gespeichert
const SHARED = "dw-geteilt";         // geteilte Dateien, bis die App sie abholt
const PRECACHE = __PRECACHE__;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(APP).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) {
      if ((k.startsWith("dw-app-") && k !== APP) || (k.startsWith("dw-nachgeladen-") && k !== LATER)) await caches.delete(k);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;            // fremde Adressen (z. B. eigener KI-Server) nie anfassen
  const scope = new URL(self.registration.scope);
  if (e.request.method === "POST" && url.pathname === scope.pathname + "teilen") {
    e.respondWith(receiveShare(e.request, scope));
    return;
  }
  if (e.request.method !== "GET") return;
  e.respondWith(serve(e.request, url, scope));
});

async function serve(req, url, scope) {
  const isPage = req.mode === "navigate";
  const key = isPage ? scope.href : req;                      // jede Seite der App = index.html (auch ?geteilt=1)
  const hit = await caches.match(key, { ignoreSearch: isPage });
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok && url.pathname.startsWith(scope.pathname + "vendor/")) {
    const copy = res.clone();
    caches.open(LATER).then((c) => c.put(req, copy));
  }
  return res;
}

async function receiveShare(req, scope) {
  const target = new URL("./?geteilt=1", scope);
  try {
    const form = await req.formData();
    const cache = await caches.open(SHARED);
    for (const k of await cache.keys()) await cache.delete(k);
    const files = form.getAll("dateien").filter((f) => f && typeof f === "object" && f.size > 0);
    const meta = { titel: form.get("titel") || "", text: form.get("text") || "", link: form.get("link") || "",
                   dateien: files.map((f, i) => ({ id: i, name: f.name || `datei-${i + 1}`, typ: f.type || "" })) };
    for (const [i, f] of files.entries()) {
      await cache.put(new URL(`./geteilt/${i}`, scope).href, new Response(f, { headers: { "Content-Type": f.type || "application/octet-stream" } }));
    }
    await cache.put(new URL("./geteilt/info", scope).href, new Response(JSON.stringify(meta), { headers: { "Content-Type": "application/json" } }));
  } catch (err) {
    target.searchParams.set("fehler", String(err && err.message || err));
  }
  return Response.redirect(target.href, 303);
}

self.addEventListener("message", (e) => {
  if (e.data === "version") e.source.postMessage({ version: VERSION });
});
