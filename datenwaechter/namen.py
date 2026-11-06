"""Namen erkennen – ohne KI, ohne Internet.

Drei Wege, die sich ergänzen:
1. Vornamenliste (vornamen.txt, ~1.500 Namen): „Mia Schneider“, „Anna-Lena“, „Schneider, Thomas“, „Mias Kita“
2. Typische Stellen: „Liebe Mia,“, „Viele Grüße\\nThomas“, „Name: …“, „Familie Schneider“, „Sohn Lukas (5)“, „Fr. Weber“
3. Weitere Nennungen: Ist „Thomas Schneider“ einmal erkannt, wird auch „Schneider“ oder „Thomas“ allein markiert.

Dieselbe Logik steckt in extension/detectors.js (Browser-Erweiterung, Handy-App); tests/fixtures/namen.json prüft beide.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .detectors import MITTEL, Finding

WORT = r"[^\W\d_]+(?:-[^\W\d_]+)*"
_WORT = re.compile(WORT)
_LEER = re.compile(r"[ \t\u00a0]{1,3}")
_KOMMA = re.compile(r",[ \t]*")
_PARTIKEL = re.compile(r"(?i:von und zu|von der|von den|van der|van den|van de|de la|von|van|vom|zur|zu|de|da|di|del|della|du|dos|ten|ter|le|la)(?=[ \t]+[A-ZÄÖÜ])[ \t]+")
_INITIALEN = re.compile(r"(?:[A-ZÄÖÜ][a-zäöü]?\.[ \t]*){1,3}(?=[A-ZÄÖÜ]|(?i:von|van|de|zu)[ \t])")
_MITTEL_INITIAL = re.compile(r"[ \t]+[A-ZÄÖÜ]\.(?=[ \t]+(?:[A-ZÄÖÜ]|(?i:von|van|de|zu|dos)[ \t]))")
_END_INITIAL = re.compile(r"[ \t]+[A-ZÄÖÜ]\.(?![\w])")
ABKUERZUNGEN = frozenset("""USA PDF CEO CTO CFO COO EDV DSGVO KFZ EKG MRT OP ICU ITS EU UK USB LDL HDL CRP TSH DIN ISO
COPD AIDS HIV BMI KI AI OK NIDDM IDDM KHK AVK TIA ARDS ERCP PET MRSA ZNS GmbH AG KG UG SE OHG GBR VIP PIN TAN SMS
FAQ API URL HTML PDF ZIP HRB USt BIC IBAN SWIFT DATEV ELSTER MBA MSC PHD MD BSC LLM DDR""".split())

STOPP = frozenset("""
Der Die Das Dem Den Des Ein Eine Einen Einem Einer Eines Kein Keine Ich Du Er Sie Es Wir Ihr Ihre Ihren Ihrem Ihrer
Mein Meine Meinen Meinem Meiner Dein Deine Deinen Sein Seine Seinen Unser Unsere Euer Eure Man Und Oder Aber Doch Denn
Sondern Wenn Weil Dass Daß Ob Als Wie Was Wer Wo Wann Warum Wieso Weshalb Welche Welcher Welches Dieser Diese Dieses
Im In Am An Auf Aus Bei Mit Nach Seit Von Vom Vor Zu Zum Zur Für Über Unter Ohne Um Durch Gegen Bis Ab Hier Da Dort
Dann Jetzt Heute Morgen Gestern Bald Noch Schon Auch Nur Sehr Ganz Gerne Gern Bitte Danke Ja Nein Hallo Hi Hey Moin
Servus Tschüss Liebe Lieber Liebes Gruß Grüße Viele Beste Herzliche Freundliche Schöne Geehrte Geehrter Herr Herrn
Frau Fräulein Dr Prof Doktor Hr Fr Drs DDr Prim Doz PD OA Univ Priv Dra Familie Fam Eheleute Ehepaar Geschwister Team Alle Allen Zusammen Kollegen Kolleginnen
Kollege Kollegin Eltern Kinder Kind Sohn Tochter Mutter Vater Mama Papa Oma Opa Onkel Tante Bruder Schwester Mann
Ehemann Ehefrau Partner Partnerin Freund Freundin Freunde Leute Damen Herren Kunden Kunde Kundin Mitglieder Mitarbeiter
Mitarbeiterin Mitarbeitende Teilnehmer Teilnehmende Nachbarn Nachbar Gemeinde Gäste Schüler Schülerin Lehrer Lehrerin
Arzt Ärztin Patient Patientin Chef Chefin Schatz Liebling Baby
Montag Dienstag Mittwoch Donnerstag Freitag Samstag Sonnabend Sonntag Januar Februar März April Mai Juni Juli August
September Oktober November Dezember Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March
June July October December Ostern Weihnachten Silvester Pfingsten
Zeit Lust Angst Hunger Durst Recht Glück Pech Geld Hausaufgaben Fieber Schule Kita Kindergarten Geburtstag Termin
Termine Urlaub Besuch Bescheid Ärger Probleme Problem Schmerzen Husten Post Dienst Schicht Training Unterricht Ferien
Nachricht Hilfe Fragen Frage Interesse Antwort Brief Mail Email Telefon Handy Nummer Adresse Konto Vertrag Antrag
Rechnung Unterlagen Dokument Dokumente Datei Seite Kapitel Anlage Anhang Betreff Datum Uhr Euro Jahre Jahr Monate
Monat Wochen Woche Tage Tag Stunden Minuten Punkt Ende Anfang Hause Haus Wohnung Zimmer Auto Arbeit Job Büro Praxis
Klinik Krankenhaus Gericht Amt Jugendamt Finanzamt Polizei Bank Sparkasse Versicherung Stadt Straße Str Weg Platz
Gasse Allee Ring Deutschland Österreich Schweiz Berlin Hamburg München Köln Frankfurt Stuttgart Düsseldorf Leipzig
Dresden Hannover Bremen Nürnberg Wien Zürich Unterhalt Sorgerecht Umgang Scheidung Trennung Diagnose Therapie Befund
The A An And Or Of To On At For With From By Is Are Was Were Be Has Have Had Do Does Did Not No Yes Hello Dear Thanks
Thank Regards Best Kind Cheers Mr Mrs Ms Miss Sir Madam Everyone
Welt World Jungs Mädels Ladies Gentlemen Folks Guys Everybody All There Community Support Admin Kollegium Klasse Leser
Leserinnen Abonnenten Fans Nutzer Nutzerinnen Interessierte Bewerber Bewerberinnen Studierende Kundinnen Gast Zusammen
""".split())

ORG = frozenset("""
GmbH AG KG UG OHG eV Inc Ltd LLC Corp Co SE Holding Gruppe Group Team Abteilung Verwaltung Kundenservice Kundendienst
Service Support Bank Sparkasse Versicherung Praxis Kanzlei Redaktion Stadt Gemeinde Amt Landratsamt Jobcenter Agentur
Finanzamt Schule Kita Kindergarten Verein Vorstand Geschäftsführung Personalabteilung Buchhaltung Firma Hotel
Restaurant Stiftung Institut Universität Hochschule Klinik Klinikum Krankenhaus Apotheke Zentrum Center Verlag Studio
Shop Markt Steuerberatung Rechtsanwälte Partner Partnerschaft Kundencenter Gericht Jugendamt
""".split())


@lru_cache(maxsize=1)
def lexikon() -> tuple[frozenset, frozenset]:
    """(eindeutige Vornamen, mehrdeutige Vornamen) aus vornamen.txt."""
    sicher, mehrdeutig = set(), set()
    for line in Path(__file__).with_name("vornamen.txt").read_text(encoding="utf-8").splitlines():
        for w in line.split("#")[0].split():
            (mehrdeutig if w.endswith("?") else sicher).add(w.rstrip("?"))
    return frozenset(sicher - mehrdeutig), frozenset(mehrdeutig)


def write_extension_names() -> None:
    """Überträgt vornamen.txt in die Browser-Erweiterung (extension/vornamen.js), die auch die Handy-App nutzt."""
    target = Path(__file__).resolve().parent.parent / "extension" / "vornamen.js"
    target.write_text("// Automatisch aus datenwaechter/vornamen.txt erzeugt – dort ändern, dann:\n"
                      "//   python -c \"import datenwaechter.namen as n; n.write_extension_names()\"\n"
                      "globalThis.DWVornamen = " + json.dumps(extension_data(), ensure_ascii=False) + ";\n",
                      encoding="utf-8")


def extension_data() -> dict:
    from .inhalte import MEDIKAMENTE
    sicher, mehrdeutig = lexikon()
    return {"sicher": sorted(sicher), "mehrdeutig": sorted(mehrdeutig), "stopp": sorted(STOPP), "org": sorted(ORG),
            "medikamente": sorted(MEDIKAMENTE), "abkuerzungen": sorted(ABKUERZUNGEN), "koerper": sorted(KOERPER)}


# --------------------------------------------------------------------------- Hilfen

def _gross(w: str) -> bool:
    return w[:1].isupper() and any(c.islower() for c in w[1:])


def _vorname(w: str, namen: frozenset, versal: bool = False) -> bool:
    teile = w.split("-")
    if versal:
        teile = [t[:1] + t[1:].lower() for t in teile]
    elif not _gross(w):
        return False
    return all(t in namen for t in teile)


_NOMEN_ENDUNG = re.compile(r"(?i)(?:ung|tion|ation|heit|keit|schaft|tät|amt|itis|ektomie|tomie|plastik|skopie|graphie|"
                           r"therapie|logie|ismus|ierung)$")
_STRASSE_DANACH = re.compile(r"[ \t]+[\w.-]*(?:straße|strasse|str\.|weg|gasse|platz|allee|ring|damm|ufer|chaussee|pfad|"
                             r"steig)(?![\w])", re.IGNORECASE)
_STRASSE_WORT = re.compile(r"(?i)[\w-]*(?:straße|strasse|gasse|allee|chaussee)$")


def _nachname(w: str, versal: bool = False) -> bool:
    if len(w) > 6 and _NOMEN_ENDUNG.search(w):   # „Rektumamputation“, „Kreisjugendamt“ sind keine Namen
        return False
    if re.fullmatch(r"[IVXLCDM]+", w) or (w.isupper() and len(w) == 2):   # „II“ (Station), „OT“ (Abkürzung)
        return False
    if versal or (w.isupper() and len(w) >= 3):   # „Beatrice DE BEAUHARNAIS“, „Pierre JOUBERT“
        return (w.isupper() and len(w) > 1 and (w[:1] + w[1:].lower()) not in STOPP and w not in ABKUERZUNGEN
                and w.upper() not in {a.upper() for a in ABKUERZUNGEN})
    return _gross(w) and len(w) > 1 and w not in STOPP and w not in ORG


def _name_ab(text: str, pos: int, max_teile: int = 3, komma: bool = False) -> tuple[int, int] | None:
    """Liest ab pos einen Namen aus großgeschriebenen Wörtern (Partikel wie „von“, Initialen wie „M.“ erlaubt)."""
    vorn = pos
    part = _PARTIKEL.match(text, pos)
    if part and part.group().split()[0].lower() not in ("zu", "zur", "zum", "vom", "la", "le", "da"):
        pos = part.end()
    m = _WORT.match(text, pos)
    if not m:
        return None
    versal = m.group().isupper() and len(m.group()) > 1
    if not _nachname(m.group(), versal):
        return None
    start, ende, teile = vorn, m.end(), 1
    while teile < max_teile:
        p = ende
        mi = _MITTEL_INITIAL.match(text, p)
        if mi:   # „Holger M. Recklinghausen“
            p = mi.end()
        sep = _LEER.match(text, p) or (komma and _KOMMA.match(text, p))
        if not sep:
            break
        nach_komma = "," in sep.group()
        p = sep.end()
        part = _PARTIKEL.match(text, p)
        if part and not versal:
            p = part.end()
        n = _WORT.match(text, p)
        if n and (_STRASSE_DANACH.match(text, n.end()) or _STRASSE_WORT.search(n.group())):
            break   # „Dr. Pierre JOUBERT Innsbrucker Landstraße 22a“: dort beginnt die Adresse
        if not n or not (_nachname(n.group(), versal) or (nach_komma and _nachname(n.group()))):
            if n and n.group() in ORG:
                return None          # „Musterfirma GmbH“ ist kein Name
            break
        ende, teile = n.end(), teile + 1
    ei = _END_INITIAL.match(text, ende)   # „Hendlbein H.“
    if ei:
        ende = ei.end()
    return start, ende


def _nur_leer(text: str, a: int, b: int) -> bool:
    return bool(_LEER.fullmatch(text, a, b))


_LISTENANFANG = re.compile(r"(?:^[ \t]*(?:(?:\d{1,3}[.)]|[•*\-–])[ \t]*)?|[:;][ \t]*)$")
_DATUM_VOR = re.compile(r"\d[.]?[ \t]*$")
_DATUM_NACH = re.compile(r"\.?[ \t]*\d")


def _wie_datum(text: str, s: int, e: int) -> bool:
    """„15. August“, „Jan. 2024“, „Max. 5 Personen“ sind keine Namen."""
    return bool(_DATUM_VOR.search(text[max(0, s - 6):s]) or _DATUM_NACH.match(text, e))


def _f(text: str, s: int, e: int, label: str = "Name") -> Finding:
    return Finding("PERSON", label, text[s:e], s, e, MITTEL)


# --------------------------------------------------------------------------- 1. Vornamenliste

def _aus_liste(text: str) -> list[Finding]:
    sicher, mehrdeutig = lexikon()
    alle = sicher | mehrdeutig
    toks = list(_WORT.finditer(text))
    out: list[Finding] = []
    i = 0
    while i < len(toks):
        w, s, e = toks[i].group(), toks[i].start(), toks[i].end()
        versal = w.isupper() and len(w) > 1
        if _vorname(w, alle, versal):
            j = i + 1   # weitere Vornamen: „Anna Lena“
            while (j < len(toks) and j - i < 3 and _nur_leer(text, toks[j - 1].end(), toks[j].start())
                   and _vorname(toks[j].group(), alle, versal)):
                j += 1
            ende = toks[j - 1].end()
            sep = _LEER.match(text, ende)
            if sep and "\n" not in text[ende:sep.end()]:
                p = sep.end()
                part = _PARTIKEL.match(text, p)
                if part and not versal:
                    p = part.end()
                n = _WORT.match(text, p)
                if n and _nachname(n.group(), versal):
                    out.append(_f(text, s, n.end()))
                    i = j
                    while i < len(toks) and toks[i].start() < n.end():
                        i += 1
                    continue
            if j > i + 1:                      # „Thomas Peter“: zwei Vornamen = Vor- und Nachname
                out.append(_f(text, s, ende))
            elif not versal and _vorname(w, sicher) and not _wie_datum(text, s, e):
                out.append(_f(text, s, e, "Vorname"))
            i = j
            continue
        # „Schneider, Thomas“ (Listen, Formulare) – nur am Zeilenanfang oder nach Doppelpunkt/Aufzählung
        if (i + 1 < len(toks) and _nachname(w) and not _vorname(w, alle)
                and _KOMMA.fullmatch(text, e, toks[i + 1].start())
                and _vorname(toks[i + 1].group(), alle)
                and not _wie_datum(text, toks[i + 1].start(), toks[i + 1].end())
                and _LISTENANFANG.search(text[text.rfind("\n", 0, s) + 1:s])):
            nach = toks[i + 2] if i + 2 < len(toks) else None
            if not (nach and _nur_leer(text, toks[i + 1].end(), nach.start()) and _nachname(nach.group())):
                out.append(_f(text, s, toks[i + 1].end()))
                i += 2
                continue
        # Genitiv: „Mias Kita“, „Pauls Zeugnis“
        if not versal and w.endswith("s") and len(w) > 3 and _vorname(w[:-1], sicher) and w not in sicher:
            out.append(_f(text, s, e - 1, "Vorname"))
        i += 1
    return out


# --------------------------------------------------------------------------- 2. Typische Stellen

_TITELWORT = (r"(?:(?:(?:Univ|UNIV|univ|Priv|PRIV|Ao)\.?[ \t-]?)?(?:Prof|PROF|Doz|DOZ|DDr|DDR|Drs|Dr|DR|PD|Prim|PRIM|Mag|"
              r"Dipl\.-[A-Za-zäöü]+|Dipl|med|MED|dent|vet|univers|univer|univ|UNIV|jur|phil|rer\.?[ \t]?nat|mult|habil|"
              r"h\.[ \t]?c|OA|OÄ|Ass|MSc|MBA|PhD|MD)"
              r"(?:\.(?:in|a)?|ª|in\.?(?![\w])|a\.?(?![\w]))?|Kollegin|Kollege)")
_TITEL = re.compile(r"(?<![\w])(?:(?:Hr\.|Fr\.|Herrn?|HERRN?|Frau|FRAU|Mr\.?|Mrs\.?|Ms\.?|Miss)[ \t]+"
                    rf"(?:{_TITELWORT}[ \t]*)*"
                    r"|(?:(?:Univ|UNIV|Priv|PRIV)\.?[ \t-]?(?:Prof|PROF|Doz|DOZ)|Prof|PROF|Doz|DOZ|DDr|DDR|Drs|Dr|DR|Prim|PRIM)"
                    r"(?:\.(?:in|a)?|ª|in\.?(?![\w])|a\.?(?![\w]))?"
                    r"(?:[ \t]+|(?=med|MED|univ|UNIV|rer|phil|jur|dent|vet))"
                    rf"(?:{_TITELWORT}[ \t]*)*"
                    r"|(?:PD|OA|OÄ|Ass\.?)[ \t]+(?=(?:Dr|Prof|Doz)))")
_TITEL_KETTE = re.compile(rf"(?:{_TITELWORT}[ \t]*)*")
_ANREDE = re.compile(r"(?i)(?:^|(?<=[\s>„\"(]))(?:liebe[rs]?|hallo|hi|hey|moin|servus|dear|hello|ciao|salut|"
                     r"guten (?:tag|morgen|abend))[ \t]+")
_GRUSS = re.compile(r"(?im)^[ \t]*(?:(?:mit[ \t]+)?(?:[a-zäöüß.]+[ \t]+){0,3}(?:grüßen|grüssen|grüße|grüsse|gruß|gruss)|lg|vg|mfg|"
                    r"hochachtungsvoll|best regards|kind regards|best wishes|warm regards|regards|cheers|bis bald|"
                    r"bis dann|dein|deine|euer|eure|ihr|ihre)[ \t]*[,.!]?[ \t]*(?:\n[ \t]*){1,2}")
_GRUSS_ZEILE = re.compile(r"(?im)^[ \t]*(?:dein|deine|euer|eure|lg|vg|gruß|grüße|cheers)[ \t,]+")
_FELD = re.compile(r"(?i)\b(?:vor-? und (?:nach|zu)name|(?:nach)?name,[ ]?vorname|vorname,[ ]?(?:nach)?name|"
                   r"vollständiger name|vorname[n]?|nachname|familienname|zuname|geburtsname|rufname|"
                   r"name (?:des kindes|der mutter|des vaters|der patientin|des patienten)|"
                   r"patient(?:in)?|mieter(?:in)?|vermieter(?:in)?|kunde|kundin|kontoinhaber(?:in)?|inhaber(?:in)?|"
                   r"antragsteller(?:in)?|arbeitnehmer(?:in)?|mitarbeiter(?:in)?|ehemann|ehefrau|ehepartner(?:in)?|"
                   r"kind|sohn|tochter|vater|mutter|schüler(?:in)?|empfänger(?:in)?|absender(?:in)?|"
                   r"versicherte[r]?|versicherungsnehmer(?:in)?|bewerber(?:in)?|ansprechpartner(?:in)?|"
                   r"verfasser(?:in)?|erziehungsberechtigte[r]?|unterzeichner(?:in)?|teilnehmer(?:in)?|"
                   r"mandant(?:in)?|klient(?:in)?|beschuldigte[r]?|kläger(?:in)?|beklagte[r]?|zeug(?:e|in)|"
                   r"betreuer(?:in)?|vormund|full name|first name|last name|surname|given name|name)[ \t]*:[ \t]*")
_BERUF = re.compile(r"(?i)(?<![\w])(?:[a-zäöü-]*(?:arzt|ärztin|direktor|direktorin|leiter|leiterin|psychologe|psychologin|"
                    r"therapeut|therapeutin|orthoptist|orthoptistin|pfleger|pflegerin|hebamme|primar|primaria|primarius|"
                    r"sachbearbeiter|sachbearbeiterin))[ \t]*:[ \t]*")
_VERFASST = re.compile(r"(?i)(?<![\w])(?:(?:geschrieben|erstellt|diktiert|vidiert|untersucht|befundet|unterschrieben|"
                       r"freigegeben|behandelt|überwiesen)[ \t]+(?:von|durch)|untersuchung durch|gez\.)[: \t]+")
_FAMILIE = re.compile(r"\b(?:Familie|Fam\.|Eheleute|Ehepaar|Geschwister)[ \t]+")
_VERWANDT = re.compile(r"\b(?:Sohn|Tochter|Kind|Enkel(?:in|kind)?|Bruder|Schwester|Ehemann|Ehefrau|Mann|Partner(?:in)?|"
                       r"Freund(?:in)?|Lebensgefährt(?:e|in)|Verlobte[r]?|Vater|Mutter|Papa|Mama|Oma|Opa|Onkel|Tante|"
                       r"Cousine?|Neffe|Nichte|Schwager|Schwägerin|Kollege|Kollegin|Chef(?:in)?|Nachbar(?:in)?|"
                       r"Patient(?:in|en)?|Pat\.|Klient(?:in)?|Mandant(?:in)?|Schüler(?:in)?|Azubi|Ex-Mann|Ex-Frau|Exmann|"
                       r"Exfrau|Stief(?:sohn|tochter|vater|mutter)|Pflegekind|Baby)[ \t]+")
_PATIENT = re.compile(r"\b(?:Patient(?:in|en)?|Pat\.)\s+")   # nach „Patientin“ steht fast immer ein Name
_NUR_INITIAL = re.compile(r"([A-ZÄÖÜ]\.)(?=[ \t]*(?:[,;:)]|\s+[a-zäöüß]|$))")
_ALTER = re.compile(r"[ \t]*\([ \t]*\d{1,2}\b")
_ZEILENENDE = re.compile(r"[ \t]*(?:\n|$|,)")


def _an_stellen(text: str) -> list[Finding]:
    sicher, mehrdeutig = lexikon()
    out: list[Finding] = []

    def nimm(m, teile, *, komma=False, danach=None, bedingung=None, titel=True, und=False, initial_allein=False):
        pos = m.end()
        if titel:
            pos = _TITEL_KETTE.match(text, pos).end()
        ini = _INITIALEN.match(text, pos)
        span = _name_ab(text, ini.end() if ini else pos, teile, komma)
        if span is None and initial_allein:   # „Herr K.“, „Frau I.“ – abgekürzter Name
            nur = _NUR_INITIAL.match(text, pos)
            if nur:
                out.append(_f(text, nur.start(1), nur.end(1)))
                return
        if span and ini:
            span = (ini.start(), span[1])
        if span and und:   # „Drs. Seiler und Wantzer“
            u = re.compile(r"[ \t]+und[ \t]+").match(text, span[1])
            zweiter = _name_ab(text, u.end(), 2) if u else None
            if zweiter:
                out.append(_f(text, *zweiter))
        if not span:
            return
        if danach and not danach.match(text, span[1]):
            return
        if bedingung and not bedingung(span):
            return
        out.append(_f(text, *span))

    for m in _TITEL.finditer(text):
        nimm(m, 3, komma=True, und=True, initial_allein=True)
    for m in _PATIENT.finditer(text):
        nimm(m, 3, komma=True, initial_allein=True)
    for m in _BERUF.finditer(text):
        nimm(m, 3)
    for m in _VERFASST.finditer(text):
        nimm(m, 3)
    for m in _ANREDE.finditer(text):
        nimm(m, 2, danach=re.compile(r"[ \t]*(?:[,!:;]|\n|$)"))
    for m in _GRUSS.finditer(text):
        nimm(m, 3, danach=_ZEILENENDE)
    for m in _GRUSS_ZEILE.finditer(text):
        nimm(m, 3, danach=re.compile(r"[ \t]*(?:\n|$|[.!])"))
    for m in _FELD.finditer(text):
        nimm(m, 4, komma=True)
    for m in _FAMILIE.finditer(text):
        nimm(m, 2)
    alle = sicher | mehrdeutig
    for m in _VERWANDT.finditer(text):
        if m.group().startswith(("Patient", "Pat.")):   # eigene Regel _PATIENT
            continue
        nimm(m, 2, bedingung=lambda sp: (_vorname((_WORT.search(text, sp[0]) or _WORT.match(text, sp[0])).group(), alle)
                                         or bool(_ALTER.match(text, sp[1]))))
    return out


# --------------------------------------------------------------------------- 3. Weitere Nennungen

def weitere_nennungen(text: str, personen: list[Finding]) -> list[Finding]:
    """Findet jeden Bestandteil erkannter Namen auch einzeln wieder („Schneider“, „Thomas“, „Mias“)."""
    mehrdeutig = lexikon()[1]
    teile = set()
    for f in personen:
        for t in _WORT.findall(f.text):
            if len(t) >= 3 and (_gross(t) or t.isupper()) and t not in STOPP and t not in ORG and t not in ABKUERZUNGEN:
                teile.add(t)
    out: list[Finding] = []
    for t in sorted(teile):
        if t in KOERPER:
            continue   # Dr. Leber ja – aber nicht jede „Leber“ im Befund
        for m in re.finditer(rf"(?<![^\W\d_])(?<!-){re.escape(t)}(?=s?(?!-|[^\W\d_]))", text):
            davor = text[max(0, m.start() - 12):m.start()]
            if _ARTIKEL_DAVOR.search(davor):
                continue   # „die Leber“, „im Schädel“ – Wort, nicht der Arzt Dr. Leber
            if t in mehrdeutig and _SATZANFANG.search(text[:m.start()]):
                continue   # „Ernst der Lage“ – mehrdeutiger Vorname am Satzanfang
            out.append(_f(text, m.start(), m.end()))
    return out


KOERPER = frozenset("""Leber Niere Nieren Herz Lunge Magen Darm Milz Galle Blase Becken Schädel Knie Hüfte Schulter
Rücken Haut Blut Hals Kopf Fuß Hand Arm Bein Auge Ohr Nase Mund Zahn Brust Bauch Knochen Muskel Nerv Gehirn Hirn Zunge
Lippe Ferse Zehe Finger Daumen Wade Nacken Kiefer Rippe Wirbel Becker""".split()) - {"Becker"}

_ARTIKEL_DAVOR = re.compile(r"(?i)(?<![\w])(?:der|die|das|den|dem|des|ein|eine|einen|einem|einer|eines|kein|keine|sein|seine|"
                            r"seinen|seinem|seiner|ihr|ihre|ihren|ihrem|ihrer|mein|meine|unser|unsere|zur|zum|im|am|vom|"
                            r"beim|ins|ans|beide|beiden)[ \t]+$")
_SATZANFANG = re.compile(r"(?:^|[.!?\n])[ \t\u00a0]*$")


_NACH_NAME = None


def geburtsdaten_nach_namen(text: str, personen: list[Finding]) -> list[Finding]:
    """„Albers (* 4.4.1997)“, „Haefner, Heinz, * 21.3.1979“, „Andrea Ilgner, 21.10.1982, wohnhaft …“"""
    global _NACH_NAME
    if _NACH_NAME is None:
        from .detectors import _DATUM
        _NACH_NAME = re.compile(rf"(?i)[ \t]*[,(]?[ \t]*(?:(?P<m>\*|geb\.?(?:[ \t]*am)?[ \t]*:?)[ \t]*)?(?P<d>{_DATUM})"
                                r"(?P<n>[ \t]*[,)]|[ \t]+wohnhaft)?")
    out: list[Finding] = []
    for f in personen:
        m = _NACH_NAME.match(text, f.end)
        if m and (m.group("m") or m.group("n")):
            out.append(Finding("GEBURTSDATUM", "Geburtsdatum", m.group("d"), m.start("d"), m.end("d"), MITTEL))
    return out


def finde(text: str) -> list[Finding]:
    """Namen aus Vornamenliste und typischen Stellen (ohne „weitere Nennungen“)."""
    return _aus_liste(text) + _an_stellen(text)
