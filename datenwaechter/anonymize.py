"""Ersetzt Funde durch Platzhalter wie [PERSON_1] und kann sie später zurückübersetzen.

Gleiche Werte bekommen denselben Platzhalter, damit die KI Zusammenhänge versteht
(„[PERSON_1] überweist an [PERSON_2]“). Die Zuordnung bleibt nur lokal im Speicher.
"""

from __future__ import annotations

import re

from .detectors import Finding, scan_text


class Anonymizer:
    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._by_placeholder: dict[str, str] = {}
        self._counter: dict[str, int] = {}

    def placeholder(self, f: Finding) -> str:
        key = (f.kind, f.text.strip())
        if key not in self._by_value:
            n = self._counter.get(f.kind, 0) + 1
            self._counter[f.kind] = n
            ph = f"[{f.kind}_{n}]"
            self._by_value[key] = ph
            self._by_placeholder[ph] = f.text
        return self._by_value[key]

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

    def clear(self) -> None:
        self.__init__()
