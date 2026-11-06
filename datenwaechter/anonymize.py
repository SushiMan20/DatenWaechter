"""Ersetzt Funde durch Platzhalter wie [PERSON_1] und kann sie später zurückübersetzen.

Gleiche Werte bekommen denselben Platzhalter, damit die KI Zusammenhänge versteht
(„[PERSON_1] überweist an [PERSON_2]“). Die Zuordnung bleibt nur lokal im Speicher.
"""

from __future__ import annotations

import re

from .detectors import Finding, scan_text

_WORT = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


class Anonymizer:
    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._by_placeholder: dict[str, str] = {}
        self._counter: dict[str, int] = {}

    def placeholder(self, f: Finding) -> str:
        key = (f.kind, f.text.strip())
        if key not in self._by_value and f.kind == "PERSON":
            same = self._same_person(key[1])
            if same:   # „Herr Schneider“ nach „Herrn Thomas Schneider“ = dieselbe Person
                self._by_value[key] = same
                if len(f.text) > len(self._by_placeholder[same]):
                    self._by_placeholder[same] = f.text
        if key not in self._by_value:
            n = self._counter.get(f.kind, 0) + 1
            self._counter[f.kind] = n
            ph = f"[{f.kind}_{n}]"
            self._by_value[key] = ph
            self._by_placeholder[ph] = f.text
        return self._by_value[key]

    def _same_person(self, value: str) -> str | None:
        """Teil eines Namens ↔ voller Name: „Schneider“ oder „Mia“ ↔ „Mia Schneider“.

        Bei mehreren Kandidaten (Familie!) wird nichts zusammengelegt.
        """
        parts = _WORT.findall(value)
        if not parts:
            return None
        matches = set()
        for (kind, v), ph in self._by_value.items():
            if kind != "PERSON":
                continue
            vparts = _WORT.findall(v)
            known = _WORT.findall(self._by_placeholder[ph])
            if not vparts or not known:
                continue
            if len(parts) == 1:
                # Einzelname → passt zu jeder Person mit diesem Vor- oder Nachnamen
                if parts[0].lower() in (vparts[-1].lower(), vparts[0].lower()) and len(vparts) > 1:
                    matches.add(ph)
                elif len(vparts) == 1 and parts[0].lower() == vparts[0].lower():
                    matches.add(ph)
            elif len(known) == 1 and known[0].lower() in (parts[0].lower(), parts[-1].lower()):
                # voller Name → nur an einen Einzelnamen, der noch keiner anderen Person gehört
                matches.add(ph)
        return matches.pop() if len(matches) == 1 else None

    def anonymize(self, text: str, findings: list[Finding] | None = None, use_ki: bool = False) -> str:
        if findings is None:
            findings = scan_text(text, use_ki=use_ki)
        parts, last = [], 0
        for f in sorted(findings, key=lambda f: f.start):
            if f.start < last:
                continue
            parts.append(text[last:f.start])
            parts.append(self.placeholder(f))
            last = f.end
        parts.append(text[last:])
        return "".join(parts)

    def restore(self, text: str) -> str:
        """Setzt die Originalwerte in eine KI-Antwort wieder ein."""
        if not self._by_placeholder:
            return text
        pattern = re.compile("|".join(re.escape(p) for p in sorted(self._by_placeholder, key=len, reverse=True)))
        return pattern.sub(lambda m: self._by_placeholder[m.group(0)], text)

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._by_placeholder)

    def load(self, mapping: dict[str, str]) -> None:
        """Übernimmt eine bestehende Zuordnung (z. B. aus der Browser-Erweiterung), damit Platzhalter eindeutig bleiben."""
        for ph, orig in mapping.items():
            m = re.fullmatch(r"\[([A-Z_]+)_(\d+)\]", ph)
            if not m:
                continue
            kind, n = m.group(1), int(m.group(2))
            self._by_value[(kind, orig.strip())] = ph
            self._by_placeholder[ph] = orig
            self._counter[kind] = max(self._counter.get(kind, 0), n)

    def clear(self) -> None:
        self.__init__()
