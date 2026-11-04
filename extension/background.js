// Hintergrund der Erweiterung:
// 1. Verbindung zum lokalen Python-Scanner (Native Messaging, Antworten in Teilen à max. 1 MB)
// 2. Zustand (aktiv / pausiert) samt Symbol in der Browserleiste
// 3. Tageszähler (geprüft / gewarnt / anonymisiert) – nur Zahlen, keine Inhalte
const HOST = "de.datenwaechter.host";
let pingCache = null; // { time, reply }

// ------------------------------------------------------------------ Lokaler Scanner
function callHost(request) {
  return new Promise((resolve) => {
    let port;
    try {
      port = chrome.runtime.connectNative(HOST);
    } catch (e) {
      resolve({ ok: false, noHost: true, error: String(e) });
      return;
    }
    const parts = [];
    let received = 0, finished = false;
    port.onMessage.addListener((m) => {
      if (parts[m.part] === undefined) received++;
      parts[m.part] = m.data;
      if (received === m.of) {
        finished = true;
        port.disconnect();
        try { resolve(JSON.parse(parts.join(""))); } catch { resolve({ ok: false, error: "Antwort des Scanners unlesbar" }); }
      }
    });
    port.onDisconnect.addListener(() => {
      if (finished) return;
      const msg = chrome.runtime.lastError?.message || "Scanner beendet";
      resolve({ ok: false, noHost: /not found|forbidden|Specified native messaging host/i.test(msg), error: msg });
    });
    port.postMessage(request);
  });
}

async function ping(fresh = false) {
  if (!fresh && pingCache && Date.now() - pingCache.time < 30_000) return pingCache.reply;
  const reply = await callHost({ action: "ping" });
  pingCache = { time: Date.now(), reply };
  return reply;
}

// ------------------------------------------------------------------ Zustand + Symbol
const today = () => new Date().toISOString().slice(0, 10);

async function getState() {
  const s = await chrome.storage.local.get({ aktiv: true, pauseBis: 0 });
  if (!s.aktiv && s.pauseBis && Date.now() >= s.pauseBis) {   // Pause abgelaufen
    await chrome.storage.local.set({ aktiv: true, pauseBis: 0 });
    return { aktiv: true, pauseBis: 0 };
  }
  return s;
}

async function updateIcon() {
  const { aktiv, pauseBis } = await getState();
  const state = aktiv ? "aktiv" : "pause";
  await chrome.action.setIcon({ path: { 16: `icons/${state}-16.png`, 32: `icons/${state}-32.png`, 48: `icons/${state}-48.png` } });
  await chrome.action.setBadgeText({ text: aktiv ? "" : "AUS" });
  await chrome.action.setBadgeBackgroundColor({ color: "#ef6c00" });
  const until = pauseBis ? ` bis ${new Date(pauseBis).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}` : "";
  await chrome.action.setTitle({ title: aktiv ? "Datenwächter – Schutz aktiv" : `Datenwächter – pausiert${until}` });
}

async function setActive(aktiv, minutes = 0) {
  const pauseBis = !aktiv && minutes ? Date.now() + minutes * 60_000 : 0;
  await chrome.storage.local.set({ aktiv, pauseBis });
  await chrome.alarms.clear("weiter");
  if (pauseBis) chrome.alarms.create("weiter", { when: pauseBis });
  await updateIcon();
}

async function countStat(key, n = 1) {
  const { stats } = await chrome.storage.local.get({ stats: {} });
  const s = stats.datum === today() ? stats : { datum: today(), geprueft: 0, gewarnt: 0, anonymisiert: 0 };
  s[key] = (s[key] || 0) + n;
  await chrome.storage.local.set({ stats: s });
}

chrome.alarms.onAlarm.addListener((a) => { if (a.name === "weiter") setActive(true); });
chrome.runtime.onInstalled.addListener(updateIcon);
chrome.runtime.onStartup.addListener(updateIcon);

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "ping") ping(msg.fresh).then(sendResponse);
  else if (msg?.type === "host") callHost(msg.request).then(sendResponse);
  else if (msg?.type === "setActive") setActive(msg.aktiv, msg.minutes).then(() => sendResponse({ ok: true }));
  else if (msg?.type === "stat") countStat(msg.key, msg.n).then(() => sendResponse({ ok: true }));
  else if (msg?.type === "state") getState().then(sendResponse);
  else return false;
  return true; // Antwort kommt asynchron
});
