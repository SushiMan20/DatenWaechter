// Läuft im Kontext der Chat-Seite (world: MAIN), damit auch versteckte Upload-Wege geprüft werden:
// 1. „Datei hinzufügen“-Knöpfe, die ein unsichtbares <input type=file> erzeugen, das nie im Dokument hängt.
//    Solche Eingabefelder hängen wir in einen versteckten Container, damit content.js ihr change-Ereignis sieht.
// 2. Der moderne Dateidialog window.showOpenFilePicker(): ausgewählte Dateien werden erst geprüft.
(() => {
  "use strict";
  const park = () => {
    let p = document.getElementById("__datenwaechter_inputs");
    if (!p) {
      p = document.createElement("div");
      p.id = "__datenwaechter_inputs";
      p.hidden = true;
      (document.body || document.documentElement).append(p);
    }
    return p;
  };
  const attach = (el) => {
    if (el instanceof HTMLInputElement && el.type === "file" && !el.isConnected) park().append(el);
  };
  for (const name of ["click", "showPicker"]) {
    const orig = HTMLInputElement.prototype[name];
    if (!orig) continue;
    HTMLInputElement.prototype[name] = function (...args) {
      attach(this);
      return orig.apply(this, args);
    };
  }

  if (typeof window.showOpenFilePicker === "function") {
    const origPicker = window.showOpenFilePicker;
    let seq = 0;
    window.showOpenFilePicker = async function (...args) {
      const handles = await origPicker.apply(this, args);
      const files = await Promise.all(handles.map((h) => h.getFile()));
      const id = `dw${Date.now()}_${seq++}`;
      const result = await new Promise((resolve) => {
        const onMsg = (e) => {
          if (e.source === window && e.data?.__datenwaechter === "result" && e.data.id === id) {
            window.removeEventListener("message", onMsg);
            resolve(e.data.files);
          }
        };
        window.addEventListener("message", onMsg);
        window.postMessage({ __datenwaechter: "check", id, files }, "*");
      });
      if (!result) throw new DOMException("The user aborted a request.", "AbortError");
      return result.map((f) => ({
        kind: "file", name: f.name,
        getFile: async () => f,
        isSameEntry: async () => false,
        queryPermission: async () => "granted",
        requestPermission: async () => "granted",
      }));
    };
  }
})();
