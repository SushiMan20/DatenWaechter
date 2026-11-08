// Hilfsprozess der Gesichtserkennung: rechnet einzelne Vergrößerungsstufen (siehe gesichter.js), damit die Suche
// auf mehrere Prozessorkerne verteilt wird und die Oberfläche bedienbar bleibt.
import { intern } from "./gesichter.js";

self.onmessage = ({ data: { id, eq, b, h, aufgaben } }) => {
  try {
    const cache = {};
    self.postMessage({ id, ergebnis: aufgaben.map((a) => intern.rechnen(eq, b, h, a, cache)) });
  } catch (e) {
    self.postMessage({ id, fehler: String(e?.message || e) });
  }
};
self.postMessage({ bereit: true });
