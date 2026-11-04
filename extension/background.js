// Leitet PDF/Word-Dateien an den lokalen Python-Scanner weiter (Native Messaging).
// Ohne installierte Brücke antwortet sendNativeMessage mit einem Fehler – die Seite zeigt dann einen Hinweis.
const HOST = "de.datenwaechter.host";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "scanFile") return false;
  chrome.runtime.sendNativeMessage(HOST, { action: "scan_file", name: msg.name, data_b64: msg.b64 }, (reply) => {
    if (chrome.runtime.lastError) {
      sendResponse({ ok: false, noHost: true, error: chrome.runtime.lastError.message });
    } else {
      sendResponse(reply);
    }
  });
  return true; // Antwort kommt asynchron
});
