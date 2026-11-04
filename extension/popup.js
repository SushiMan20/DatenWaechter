// Kleines Fenster beim Klick auf das Datenwächter-Symbol in der Browserleiste.
const $ = (id) => document.getElementById(id);
const SITES = /^https:\/\/(claude\.ai|chatgpt\.com|chat\.openai\.com|gemini\.google\.com|copilot\.microsoft\.com|chat\.mistral\.ai|www\.perplexity\.ai)\//;
const send = (msg) => chrome.runtime.sendMessage(msg);

let renderSeq = 0;

async function render() {
  const mine = ++renderSeq; // überholte Durchläufe verwerfen (Zähler ändern sich laufend)
  const { aktiv, pauseBis } = await send({ type: "state" });
  const { stats } = await chrome.storage.local.get({ stats: {} });
  let tabUrl = "";
  try { [{ url: tabUrl = "" } = {}] = await chrome.tabs.query({ active: true, currentWindow: true }); } catch { /* ohne Tab-Zugriff */ }
  if (mine !== renderSeq) return;
  const today = new Date().toISOString().slice(0, 10);
  for (const k of ["geprueft", "gewarnt", "anonymisiert"]) $(k).textContent = stats.datum === today ? stats[k] || 0 : 0;

  $("switch").classList.toggle("on", aktiv);
  $("switch").setAttribute("aria-checked", String(aktiv));
  $("shield").src = `icons/${aktiv ? "aktiv" : "pause"}-48.png`;
  $("title").textContent = aktiv ? "Schutz aktiv" : "Schutz pausiert";
  $("title").style.color = aktiv ? "" : "var(--orange)";
  $("pauseRow").style.display = aktiv ? "" : "none";

  if (!aktiv) {
    $("sub").textContent = pauseBis
      ? `Bis ${new Date(pauseBis).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })} – danach automatisch wieder an`
      : "Uploads werden nicht geprüft";
  } else if (tabUrl && SITES.test(tabUrl)) {
    $("sub").textContent = `Wacht über ${new URL(tabUrl).hostname}`;
  } else {
    $("sub").textContent = "Wacht über deine KI-Chats";
  }
}

async function renderHost() {
  const r = await send({ type: "ping", fresh: true });
  if (r?.ok) {
    $("hostDot").className = "dot ok";
    $("hostText").textContent = `Verbunden · Texterkennung: ${r.ocr || "fehlt"} · Gesichter: ${r.faces ? "ja" : "nein"}`;
    $("aiDot").className = r.llm ? "dot ok" : "dot";
    $("aiText").textContent = r.llm ? `KI: ${r.llm.split(":").slice(1).join(":")}` : "Stichwörter (kein KI-Server eingerichtet)";
  } else {
    $("hostDot").className = "dot warn";
    $("hostText").textContent = "Nicht installiert – PDFs, Word und Bilder werden nicht geprüft";
    $("aiText").textContent = "Stichwörter";
  }
}

$("switch").addEventListener("click", async () => {
  const { aktiv } = await send({ type: "state" }); // gespeicherter Zustand zählt, nicht die Anzeige
  await send({ type: "setActive", aktiv: !aktiv });
  render();
});
document.querySelectorAll("[data-min]").forEach((b) => b.addEventListener("click", async () => {
  await send({ type: "setActive", aktiv: false, minutes: Number(b.dataset.min) });
  render();
}));
chrome.storage.onChanged.addListener(render);
async function renderActions() {
  const r = await send({ type: "refreshMenus" });
  const n = r?.actions?.length || 0;
  $("actDot").className = n && $("aiDot").classList.contains("ok") ? "dot ok" : "dot";
  $("actText").textContent = n
    ? `${n} Aktionen per Rechtsklick: ${r.actions.slice(0, 3).map((a) => a.name).join(", ")} …`
    : "Braucht lokalen Scanner und KI-Server";
}

render();
renderHost().then(renderActions);
