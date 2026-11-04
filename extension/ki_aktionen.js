// KI-Aktionen im Rechtsklick-Menü: Text markieren -> Rechtsklick -> „Datenwächter KI“ -> z. B. „Umformulieren“.
// Funktioniert auf jeder Webseite: Der Rechtsklick gibt der Erweiterung Zugriff auf genau diesen Tab (activeTab),
// es braucht keine Berechtigung für alle Seiten. Die KI-Anfrage läuft über den lokalen Scanner (dort liegen
// Server-Adresse und Token; bei externen Servern wird vorher anonymisiert und danach zurückübersetzt).
/* global callHost */

const MENU_ROOT = "dw-ki";
const CONTEXTS = ["selection", "editable"];
let menuItems = [];           // zuletzt geladene Aktionen (auch für Tests)
let menuBuild = Promise.resolve();

function buildMenus() {
  // nacheinander ausführen, sonst kollidieren gleichzeitige Aufrufe (doppelte IDs)
  menuBuild = menuBuild.then(async () => {
    await chrome.contextMenus.removeAll();
    chrome.contextMenus.create({ id: MENU_ROOT, title: "Datenwächter KI", contexts: CONTEXTS });
    const r = await callHost({ action: "list_actions" });
    const info = (title) => chrome.contextMenus.create({ id: `dw-info-${title}`, parentId: MENU_ROOT, title, enabled: false, contexts: CONTEXTS });
    if (!r?.ok) {
      menuItems = [];
      info("Lokaler Scanner nicht installiert");
      return;
    }
    menuItems = r.actions;
    if (!r.llm) info("Kein KI-Server eingerichtet");
    for (const a of r.actions) {
      chrome.contextMenus.create({ id: `dw-a:${a.id}`, parentId: MENU_ROOT, title: a.name, contexts: CONTEXTS, enabled: !!r.llm });
    }
  }).catch((e) => console.warn("Datenwächter: Menü", e));
  return menuBuild;
}

async function runAction(actionId, tabId, frameId = 0) {
  const target = { tabId, frameIds: [frameId] };
  const action = menuItems.find((a) => a.id === actionId) || { name: actionId };
  const [{ result: sel }] = await chrome.scripting.executeScript({ target, func: captureSelection });
  if (!sel?.text?.trim()) {
    await chrome.scripting.executeScript({ target, func: applyResult, args: [{ ok: false, error: "Kein Text markiert." }] });
    return null;
  }
  await chrome.scripting.executeScript({ target, func: showBusy, args: [action.name] });
  const r = await callHost({ action: "run_action", id: actionId, text: sel.text });
  await chrome.scripting.executeScript({ target, func: applyResult, args: [r] });
  return r;
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (typeof info.menuItemId === "string" && info.menuItemId.startsWith("dw-a:") && tab?.id !== undefined) {
    runAction(info.menuItemId.slice(5), tab.id, info.frameId || 0);
  }
});

// ---------------------------------------------------------------------------------------------------
// Die folgenden Funktionen werden in die Webseite eingeschleust und müssen deshalb in sich geschlossen sein.

function captureSelection() {
  const el = document.activeElement;
  const st = { kind: "page", el, text: "" };
  const isField = el && (el.tagName === "TEXTAREA" ||
    (el.tagName === "INPUT" && /^(text|search|email|url|tel|)$/i.test(el.type || "")));
  if (isField) {
    let a = el.selectionStart, b = el.selectionEnd;
    if (a === b) { a = 0; b = el.value.length; }          // nichts markiert -> ganzes Feld
    Object.assign(st, { kind: "input", start: a, end: b, text: el.value.slice(a, b) });
  } else {
    const sel = getSelection();
    const editable = el && el.isContentEditable;
    if (sel.rangeCount && !sel.isCollapsed) {
      st.range = sel.getRangeAt(0).cloneRange();
      st.text = sel.toString();
      st.kind = editable && el.contains(st.range.commonAncestorContainer) ? "editable" : "page";
    } else if (editable) {                                  // nichts markiert -> ganzes Eingabefeld
      st.range = document.createRange();
      st.range.selectNodeContents(el);
      st.text = el.innerText;
      st.kind = "editable";
    }
  }
  globalThis.__datenwaechterSel = st;
  return { text: st.text, kind: st.kind };
}

function showBusy(name) {
  document.querySelectorAll("datenwaechter-ki").forEach((n) => n.remove());
  const host = document.createElement("datenwaechter-ki");
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `<style>
    div { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; background: #263238; color: #fff;
          padding: 10px 14px; border-radius: 8px; font: 13px system-ui, "Segoe UI", sans-serif; }
  </style><div></div>`;
  root.querySelector("div").textContent = `🛡 ${name} … KI arbeitet`;
  document.documentElement.append(host);
}

function applyResult(r) {
  document.querySelectorAll("datenwaechter-ki").forEach((n) => n.remove());
  const st = globalThis.__datenwaechterSel || {};
  const note = r?.sent_to ? `An ${r.sent_to} gesendet${r.anonymized ? " – persönliche Daten vorher anonymisiert" : ""}` : "";

  const panel = (title, text, isError) => {
    const host = document.createElement("datenwaechter-ki");
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>
      .box { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; width: min(460px, 92vw); max-height: 60vh;
             display: flex; flex-direction: column; background: #fff; color: #1f2937; border-radius: 12px;
             box-shadow: 0 10px 40px rgba(0,0,0,.3); font: 14px/1.45 system-ui, "Segoe UI", sans-serif; overflow: hidden; }
      .head { padding: 10px 14px; font-weight: 600; color: #fff; }
      .text { padding: 12px 14px; overflow: auto; white-space: pre-wrap; }
      .note { padding: 0 14px; color: #6b7280; font-size: 12px; }
      .btns { display: flex; gap: 8px; padding: 10px 14px 12px; }
      button { font: inherit; padding: 6px 12px; border-radius: 8px; border: 1px solid #d1d5db; background: #f3f4f6; cursor: pointer; }
      button.main { background: #2e7d32; border-color: #2e7d32; color: #fff; }
      @media (prefers-color-scheme: dark) { .box { background: #27272a; color: #f4f4f5; } button { background: #3f3f46; color: #f4f4f5; border-color: #52525b; } }
    </style><div class="box"><div class="head"></div><div class="text"></div><div class="note"></div><div class="btns"></div></div>`;
    root.querySelector(".head").textContent = `🛡 ${title}`;
    root.querySelector(".head").style.background = isError ? "#c62828" : "#2e7d32";
    root.querySelector(".text").textContent = text;
    root.querySelector(".note").textContent = note;
    const btns = root.querySelector(".btns");
    const add = (label, fn, main) => {
      const b = document.createElement("button");
      b.textContent = label;
      if (main) b.className = "main";
      b.addEventListener("click", fn);
      btns.append(b);
    };
    if (!isError) add("Kopieren", () => navigator.clipboard.writeText(text).then(() => host.remove()), true);
    add("Schließen", () => host.remove());
    document.documentElement.append(host);
    root.querySelector("button").focus();
  };

  if (!r?.ok) return panel("KI-Aktion fehlgeschlagen", r?.error || "Unbekannter Fehler", true);
  const editable = st.kind === "input" || st.kind === "editable";
  if (r.mode === "anzeigen" || !editable || !st.el?.isConnected) return panel(r.name, r.result, false);

  const insert = r.mode === "einfuegen" ? `\n\n${r.result}` : r.result;
  st.el.focus();
  if (st.kind === "input") {
    const s = r.mode === "einfuegen" ? st.end : st.start;
    st.el.setSelectionRange(s, st.end);
    // execCommand hält Rückgängig (Strg+Z) und Frameworks wie React synchron
    if (!document.execCommand("insertText", false, insert)) {
      st.el.setRangeText(insert, s, st.end, "end");
      st.el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  } else {
    const range = st.range;
    if (r.mode === "einfuegen") range.collapse(false);
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    if (!document.execCommand("insertText", false, insert)) {
      range.deleteContents();
      range.insertNode(document.createTextNode(insert));
    }
  }
  const host = document.createElement("datenwaechter-ki");
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `<style>div { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; background: #263238;
    color: #fff; padding: 10px 14px; border-radius: 8px; font: 13px system-ui, "Segoe UI", sans-serif; max-width: 420px; }</style><div></div>`;
  root.querySelector("div").textContent = `✔ ${r.name} – ${r.mode === "einfuegen" ? "eingefügt" : "ersetzt"} (Rückgängig: Strg+Z)${note ? ". " + note : ""}`;
  document.documentElement.append(host);
  setTimeout(() => host.remove(), 4000);
}
