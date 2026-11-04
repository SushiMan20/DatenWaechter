// Verbindung zum lokalen Python-Scanner (Native Messaging). Antworten kommen in Teilen (max. 1 MB je Nachricht).
const HOST = "de.datenwaechter.host";
let pingCache = null; // { time, reply }

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

async function ping() {
  if (pingCache && Date.now() - pingCache.time < 30_000) return pingCache.reply;
  const reply = await callHost({ action: "ping" });
  pingCache = { time: Date.now(), reply };
  return reply;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "ping") ping().then(sendResponse);
  else if (msg?.type === "host") callHost(msg.request).then(sendResponse);
  else return false;
  return true; // Antwort kommt asynchron
});
