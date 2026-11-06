"""Firmen, Beträge und medizinische Inhalte – einstellbar unter „Was soll geschwärzt werden?“.

Grundsatz: Heikel ist vor allem der Bezug zu einer Person. „Interpretiere CRP 200, Leukos 15.000“ ist anonym und darf
so an eine KI; ein Arztbrief mit Name und Geburtsdatum nicht. Deshalb gilt:
- Person (Name, Adresse, Geburtsdatum, Kontakt, IBAN, Ausweis-/Steuer-/Versichertennummer …): immer
- Firmen & Kunden (Firmennamen, Kunden-/Vertrags-/Angebotsnummern, Aktenzeichen): Standard an
- Preise & Beträge: Standard aus
- Medizinische Inhalte (Diagnosen, ICD-Codes, Medikamente, Laborwerte): Standard aus

Dieselbe Logik steckt in extension/detectors.js (Browser-Erweiterung, Handy-App).
"""

from __future__ import annotations

import re

from .detectors import MITTEL, Finding

GRUPPEN = ("firmen", "betraege", "medizin")

# Typen, die eine Person erkennbar machen (für „Themen-Warnung nur mit Person“)
IDENTITAET = frozenset({
    "PERSON", "ADRESSE", "GEBURTSDATUM", "EMAIL", "TELEFON", "IBAN", "KREDITKARTE", "STEUER_ID", "STEUERNUMMER",
    "SOZIALVERSICHERUNG", "KRANKENVERSICHERUNG", "AUSWEIS", "KFZ", "STANDORT", "KENNNUMMER", "GERAETE_ID",
})

# --------------------------------------------------------------------------- Firmen

RECHTSFORM = re.compile(
    r"(?<![\w&])(?:GmbH\s*&\s*Co\.\s*KG(?:aA)?|AG\s*&\s*Co\.\s*KG|gGmbH|GmbH|mbH|UG\s*\(haftungsbeschränkt\)|UG|"
    r"KGaA|AG|KG|OHG|GbR|PartG(?:\s*mbB)?|e\.\s?K\.|e\.\s?Kfm\.|e\.\s?V\.|eG|SE|Ltd\.?|Limited|Inc\.?|LLC|Corp\.?|"
    r"S\.A\.|B\.V\.|N\.V\.|Sp\.\s?z\s?o\.\s?o\.|s\.r\.o\.)(?![\w])")
_WORT = re.compile(r"[\w][\w.&'+-]*")
_VERBINDER = {"&", "und", "für", "+"}
_KEINE_FIRMA_DAVOR = {"Der", "Die", "Das", "Den", "Dem", "Des", "Firma", "Fa.", "Unternehmen", "Kunde", "Kundin",
                      "Auftraggeber", "Auftragnehmer", "An", "Von", "Bei", "Mit", "Für", "Und", "Ihre", "Ihr", "Unsere",
                      "Unser", "Eine", "Ein", "Sitz", "Gesellschaft:", "Registergericht", "Amtsgericht", "Wir", "Sie"}


def _gross(w: str) -> bool:
    """Teil eines Firmennamens: groß geschrieben, keine Nummer („AN-2024-0815“), keine Abkürzung („Nr.“)."""
    if sum(c.isdigit() for c in w) >= 2 or (w.endswith(".") and w not in ("Dr.", "St.")):
        return False
    return w[:1].isupper() or (w[:1].isdigit() and any(c.isalpha() for c in w))


def firmen(text: str) -> list[Finding]:
    """„Müller Bau GmbH“, „Schneider & Partner mbB“, „Gesellschaft für Informatik e.V.“, „Acme Ltd.“"""
    out: list[Finding] = []
    for m in RECHTSFORM.finditer(text):
        if m.group().startswith("AG") and re.match(r"[ \t]+[A-ZÄÖÜ][a-zäöüß]", text[m.end():m.end() + 3]):
            continue   # „AG München“ = Amtsgericht
        zeile_start = text.rfind("\n", 0, m.start()) + 1
        davor = text[zeile_start:m.start()]
        toks = list(_WORT.finditer(davor))
        start = None
        anzahl = 0
        for t in reversed(toks):
            zwischen = davor[t.end():(start if start is not None else len(davor))]
            if not re.fullmatch(r"[ \t]*(?:[&+][ \t]*)?", zwischen):
                break       # Satzzeichen/Klammer dazwischen: Name endet hier
            w = t.group()
            if _gross(w):
                start = t.start()
                anzahl += 1
            elif w in _VERBINDER and anzahl:
                start = t.start()
            else:
                break
            if anzahl >= 5:
                break
        if start is None:
            continue
        form = m.group()
        if form in ("KG", "AG", "SE", "eG") and re.search(
                r"(?:ung|ion|tät|heit|keit|schaft|therapie|gymnastik)$", davor[start:].strip()):
            continue   # „Krankengymnastik KG“, „Bewegungsverschlechterung KG“: medizinische Abkürzungen
        # führende Füllwörter („Die“, „Firma“) und Verbinder abschneiden
        teil = davor[start:]
        while True:
            erster = _WORT.match(teil)
            if erster and (erster.group() in _KEINE_FIRMA_DAVOR or erster.group() in _VERBINDER):
                teil = teil[erster.end():].lstrip(" \t&+")
                continue
            break
        if not teil.strip() or not _gross(teil.strip()):
            continue
        s = m.start() - len(teil)
        out.append(Finding("FIRMA", "Firma / Organisation", text[s:m.end()], s, m.end(), MITTEL, gruppe="firmen"))
    return out


_KLINIK = re.compile(
    r"(?<![\w-])(?:(?:Städt\.|Städtisches|Ev\.|Evangelisches|Kath\.|Katholisches|Kreis|St\.|Sankt)[ \t]+)?"
    r"(?:[A-ZÄÖÜ][\w-]*?(?:[Kk]rankenhaus(?:es)?|[Kk]linikum|[Kk]liniken|[Kk]linik|[Ss]pital|[Ss]anatorium|"
    r"KRANKENHAUS|KLINIKUM|KLINIK|SPITAL)|Klinikum|Krankenhaus|Spital|Uniklinik(?:um)?|Universitätsklinikum|"
    r"UNIKLINIK(?:UM)?|UNIVERSITÄTSKLINIKUM|MVZ|Praxis(?:gemeinschaft)?(?=[ \t]+(?:Dr|Prof|[A-ZÄÖÜ][a-zäöü]+[ \t]+[A-ZÄÖÜ])))"
    r"(?![\w])((?:[ \t]+(?:(?:der|des|für|am|an der|im|St\.|Sankt|Bad|Dr\.|Prof\.)[ \t]+)?[A-ZÄÖÜ][\w.-]*(?![\w])){0,4})")


def kliniken(text: str) -> list[Finding]:
    """„Diakonissenkrankenhaus Berlin“, „Klinikum DD“, „Sankt-Klara-Spital Klagenfurt“ – nicht „das Krankenhaus“."""
    out = []
    for m in _KLINIK.finditer(text):
        kern = m.group()[:len(m.group()) - len(m.group(1))].split()[-1]
        if kern in ("Klinikum", "Krankenhaus", "Spital", "Klinik", "MVZ", "Praxis") and not m.group(1).strip():
            continue
        if kern.lower() in ("klinik", "kliniken", "uniklinik", "uniklinikum", "universitätsklinikum", "poliklinik") \
                and not m.group(1).strip():   # „in der Uniklinik“ ist kein Name
            continue
        out.append(Finding("FIRMA", "Klinik / Einrichtung", m.group(), m.start(), m.end(), MITTEL, gruppe="firmen"))
    return out


# --------------------------------------------------------------------------- Medizin

MEDIKAMENTE = frozenset("""
Ibuprofen Paracetamol Metamizol Novalgin Diclofenac Voltaren Naproxen ASS Aspirin Tilidin Tramadol Oxycodon Morphin
Fentanyl Hydromorphon Tapentadol Pregabalin Lyrica Gabapentin Metformin Insulin Lantus Levemir Novorapid Humalog
Ozempic Semaglutid Mounjaro Tirzepatid Wegovy Trulicity Dulaglutid Jardiance Empagliflozin Dapagliflozin Forxiga
Sitagliptin Januvia Glimepirid L-Thyroxin Levothyroxin Euthyrox Thiamazol Carbimazol Ramipril Enalapril Lisinopril
Candesartan Valsartan Losartan Olmesartan Telmisartan Amlodipin Lercanidipin Bisoprolol Metoprolol Nebivolol
Carvedilol Propranolol Torasemid Furosemid Hydrochlorothiazid HCT Spironolacton Eplerenon Entresto Sacubitril
Simvastatin Atorvastatin Rosuvastatin Pravastatin Ezetimib Clopidogrel Prasugrel Ticagrelor Apixaban Eliquis
Rivaroxaban Xarelto Edoxaban Lixiana Dabigatran Pradaxa Marcumar Phenprocoumon Heparin Enoxaparin Clexane Digitoxin
Amiodaron Pantoprazol Omeprazol Esomeprazol Ranitidin Allopurinol Febuxostat Colchicin Prednisolon Prednison
Dexamethason Hydrocortison Cortison Budesonid Salbutamol Formoterol Salmeterol Tiotropium Spiriva Montelukast
Cetirizin Loratadin Desloratadin Amoxicillin Ampicillin Penicillin Cefuroxim Cefaclor Ciprofloxacin Levofloxacin
Doxycyclin Clarithromycin Azithromycin Clindamycin Cotrimoxazol Nitrofurantoin Fosfomycin Metronidazol Aciclovir
Valaciclovir Oseltamivir Paxlovid Sertralin Citalopram Escitalopram Fluoxetin Paroxetin Venlafaxin Duloxetin
Mirtazapin Bupropion Agomelatin Trazodon Amitriptylin Doxepin Opipramol Quetiapin Olanzapin Risperidon Aripiprazol
Haloperidol Clozapin Lithium Lamotrigin Valproat Levetiracetam Keppra Carbamazepin Oxcarbazepin Topiramat
Lorazepam Tavor Diazepam Valium Alprazolam Oxazepam Zopiclon Zolpidem Melatonin Methylphenidat Ritalin Medikinet
Elvanse Lisdexamfetamin Atomoxetin Strattera Donepezil Memantin Levodopa Madopar Pramipexol Ropinirol Sumatriptan
Rizatriptan Methotrexat Adalimumab Humira Etanercept Infliximab Rituximab Tamoxifen Letrozol Anastrozol Trastuzumab
Pembrolizumab Nivolumab Imatinib Sildenafil Viagra Tadalafil Cialis Finasterid Tamsulosin Truvada Descovy Biktarvy
Methadon Buprenorphin Subutex Naltrexon Disulfiram Vareniclin Champix Estradiol Progesteron Dienogest Levonorgestrel
Mirena Testosteron Clomifen Letrozol Folsäure Eisensulfat Ferrosanol Vitamin-D3 Dekristol Cholecalciferol
""".split())
_MEDIKAMENT = re.compile(r"(?<![\w-])(" + "|".join(sorted((re.escape(m) for m in MEDIKAMENTE), key=len, reverse=True))
                         + r")(?:[ \t]+\d+(?:[.,]\d+)?[ \t]?(?:mg|µg|mcg|g|ml|IE|I\.E\.|%))?(?![\w-])", re.IGNORECASE)


def medikamente(text: str) -> list[Finding]:
    return [Finding("MEDIKAMENT", "Medikament", m.group(), m.start(), m.end(), MITTEL, gruppe="medizin")
            for m in _MEDIKAMENT.finditer(text)]


def finde(text: str) -> list[Finding]:
    return firmen(text) + kliniken(text) + medikamente(text)
