// KI-Aktionen per Rechtsklick: Text markieren -> Rechtsklick -> „Mit KI bearbeiten …“ -> Aktionsleiste an der Markierung.
// Funktioniert auf jeder Webseite: Der Rechtsklick gibt der Erweiterung Zugriff auf genau diesen Tab (activeTab),
// es braucht keine Berechtigung für alle Seiten. Die Leiste selbst (ki_palette.js) wird erst dann eingeschleust.
// KI-Anfragen laufen über den lokalen Scanner: dort liegen Server-Adresse und Token; bei externen Servern wird
// vorher anonymisiert und danach zurückübersetzt.
/* global callHost */

const MENU_ID = "dw-ki";
const CONTEXTS = ["selection", "editable"];
let menuItems = [];           // zuletzt geladene Aktionen (auch für Tests)
let menuInfo = { server: null };
let menuBuild = Promise.resolve();

function serverLabel(r) {
  if (!r?.llm) return null;
  const model = r.llm.split(":").slice(1).join(":").split("@")[0];
  return `${model} · ${r.extern ? `extern${r.anonym ? " anonymisiert" : ""}` : "lokal"}`;
}

function buildMenus() {
  // nacheinander ausführen, sonst kollidieren gleichzeitige Aufrufe (doppelte IDs)
  menuBuild = menuBuild.then(async () => {
    await chrome.contextMenus.removeAll();
    chrome.contextMenus.create({ id: MENU_ID, title: "Mit KI bearbeiten …", contexts: CONTEXTS });
    const r = await callHost({ action: "list_actions" });
    menuItems = r?.ok ? r.actions : [];
    menuInfo = { server: r?.ok ? serverLabel(r) : null, noHost: !r?.ok };
  }).catch((e) => console.warn("Datenwächter: Menü", e));
  return menuBuild;
}

async function inject(tabId, frameId) {
  const target = { tabId, frameIds: [frameId] };
  await chrome.scripting.executeScript({ target, files: ["ki_palette.js"] });
  const call = (func, ...args) => chrome.scripting.executeScript({ target, func, args }).then((x) => x[0]?.result);
  return call;
}

// Rechtsklick -> Aktionsleiste öffnen
async function openPalette(tabId, frameId = 0) {
  const call = await inject(tabId, frameId);
  const sel = await call(() => globalThis.__dwKI.capture());
  if (!sel?.text?.trim()) {
    await call(() => globalThis.__dwKI.toast("Erst Text markieren – dann Rechtsklick → „Mit KI bearbeiten …“"));
    return false;
  }
  if (!menuItems.length || menuInfo.noHost) await buildMenus();
  if (menuInfo.noHost) {
    await call(() => globalThis.__dwKI.toast("Für KI-Aktionen bitte den lokalen Datenwächter-Scanner installieren."));
    return false;
  }
  return call((actions, info) => globalThis.__dwKI.open(actions, info), menuItems, menuInfo);
}

// Aktion direkt ausführen (ohne Leiste) – z. B. für Tests oder künftige Tastenkürzel
async function runAction(actionId, tabId, frameId = 0) {
  const call = await inject(tabId, frameId);
  const sel = await call(() => globalThis.__dwKI.capture());
  if (!sel?.text?.trim()) {
    await call((r) => globalThis.__dwKI.apply(r), { ok: false, error: "Kein Text markiert." });
    return null;
  }
  const action = menuItems.find((a) => a.id === actionId) || { name: actionId };
  await call((name) => globalThis.__dwKI.busy(name), action.name);
  const r = await callHost({ action: "run_action", id: actionId, text: sel.text });
  await call((res) => globalThis.__dwKI.apply(res), r);
  return r;
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === MENU_ID && tab?.id !== undefined) openPalette(tab.id, info.frameId || 0);
});

// Auswahl in der Leiste -> KI-Anfrage über den lokalen Scanner
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "kiRun") return false;
  const { id, custom, mode, text } = msg.request || {};
  callHost(custom ? { action: "run_action", custom, mode, text } : { action: "run_action", id, text }).then(sendResponse);
  return true;
});
