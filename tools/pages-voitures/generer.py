#!/usr/bin/env python3
"""Génère docs/voitures/<slug>.html (une page par voiture) et docs/voitures/index.html.

Entrée : calculs.json, produit par le moteur Wattlas lui-même (le harnais JVM
gps-app/tools/pages-voitures, qui fait tourner engine/ + bases IRVE/péages +
graphe France v3 avec les réglages par défaut de l'appli). Ce script ne
calcule AUCUN chiffre de trajet : il met en forme, arrondit comme l'appli
(Java, HALF_UP) et choisit les phrases selon les caractéristiques.

Usage : python tools/pages-voitures/generer.py [--calculs chemin.json]
Python 3.9+, bibliothèque standard seulement.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ICI = Path(__file__).resolve().parent
DEPOT = ICI.parent.parent
DOCS = DEPOT / "docs"
SORTIE = DOCS / "voitures"
SITE = "https://wattlas.fr"
PRIX_DOMICILE = 0.20  # €/kWh, réglage par défaut de l'appli (StopPlanner.Config.homePricePerKwh)

# --------------------------------------------------------------------------
# Catalogue : noms affichés, regroupements
# --------------------------------------------------------------------------

# Abréviations du catalogue développées à l'affichage (le catalogue reste tel quel).
DEVELOPPE = [
    (r"\bGrande Aut\.", "Grande Autonomie"),
    (r"\bER$", "Extended Range"),
]

# Nom « familier » (« votre Mégane ») et « famille » (h1, FAQ) quand la règle
# automatique ne suffit pas. Clé = modèle du catalogue.
FAMILLE = {
    "Mégane E-Tech EV60": ("Mégane E-Tech", "Mégane"),
    "Scénic E-Tech 87 kWh": ("Scénic E-Tech", "Scénic"),
    "4 E-Tech 52 kWh": ("Renault 4 E-Tech", "Renault 4"),
    "5 E-Tech 52 kWh": ("Renault 5 E-Tech", "Renault 5"),
    "Twingo E-Tech": ("Twingo E-Tech", "Twingo"),
    "Zoe R135 52 kWh": ("Zoe", "Zoe"),
    "A290": ("Alpine A290", "A290"),
    "#1": ("Smart #1", "Smart #1"),
    "#3": ("Smart #3", "Smart #3"),
    "6e": ("Mazda 6e", "Mazda 6e"),
    "6e Long Range": ("Mazda 6e", "Mazda 6e"),
    "MX-30": ("Mazda MX-30", "MX-30"),
    "Spring": ("Dacia Spring", "Spring"),
    "500e 42 kWh": ("Fiat 500e", "500e"),
    "2 Long Range": ("Polestar 2", "Polestar 2"),
    "bZ4X": ("Toyota bZ4X", "bZ4X"),
    "e:Ny1": ("Honda e:Ny1", "e:Ny1"),
    "C10": ("Leapmotor C10", "C10"),
    "T03": ("Leapmotor T03", "T03"),
    "Cooper SE": ("Mini Cooper SE", "Mini"),
    "Cyberster": ("MG Cyberster", "Cyberster"),
    "MG5": ("MG5", "MG5"),
    "Marvel R": ("MG Marvel R", "Marvel R"),
    "ZS EV": ("MG ZS EV", "ZS EV"),
    "ZS EV 51 kWh": ("MG ZS EV", "ZS EV"),
    "S5 EV 49 kWh": ("MG S5 EV", "S5 EV"),
    "S5 EV 64 kWh": ("MG S5 EV", "S5 EV"),
    "Atto 3": ("BYD Atto 3", "Atto 3"),
    "Dolphin": ("BYD Dolphin", "Dolphin"),
    "Seal AWD": ("BYD Seal", "Seal"),
    "Avenger Electric": ("Jeep Avenger", "Avenger"),
    "Puma Gen-E": ("Ford Puma Gen-E", "Puma"),
    "Explorer EV ER": ("Ford Explorer", "Explorer"),
    "Mustang Mach-E ER": ("Mustang Mach-E", "Mach-E"),
    "Leaf e+ 62 kWh": ("Nissan Leaf", "Leaf"),
    "Ariya 87 kWh": ("Nissan Ariya", "Ariya"),
    "Niro EV": ("Kia Niro EV", "Niro"),
    "Q6 e-tron": ("Audi Q6 e-tron", "Q6 e-tron"),
    "Q4 40 e-tron": ("Audi Q4 e-tron", "Q4 e-tron"),
    "Q4 45 e-tron": ("Audi Q4 e-tron", "Q4 e-tron"),
    "i4 eDrive40": ("BMW i4", "i4"),
    "iX1 xDrive30": ("BMW iX1", "iX1"),
    "iX3": ("BMW iX3", "iX3"),
    "EQA 250": ("Mercedes EQA", "EQA"),
    "EQB 300": ("Mercedes EQB", "EQB"),
    "EX30 ER": ("Volvo EX30", "EX30"),
    "EX40 ER": ("Volvo EX40", "EX40"),
    "XC40 Recharge ER": ("Volvo XC40 Recharge", "XC40"),
    "Model 3 Grande Aut.": ("Tesla Model 3", "Model 3"),
    "Model 3 Propulsion": ("Tesla Model 3", "Model 3"),
    "Model Y Grande Aut.": ("Tesla Model Y", "Model Y"),
    "Model Y Propulsion": ("Tesla Model Y", "Model Y"),
    "Model S": ("Tesla Model S", "Model S"),
    "Model X": ("Tesla Model X", "Model X"),
    "ID. Buzz 77 kWh": ("ID. Buzz", "ID. Buzz"),
    "ID.4 Pro 2023": ("ID.4", "ID.4"),
    "Corsa Electric 54 kWh": ("Opel Corsa électrique", "Corsa"),
    "Corsa-e 50 kWh": ("Opel Corsa-e", "Corsa-e"),
    "Mokka Electric 54 kWh": ("Opel Mokka électrique", "Mokka"),
    "Mokka-e 50 kWh": ("Opel Mokka-e", "Mokka-e"),
    "Born 58 kWh": ("Cupra Born", "Born"),
    "Born 77 kWh": ("Cupra Born", "Born"),
    "ë-C3": ("Citroën ë-C3", "ë-C3"),
    "ë-C4 50 kWh": ("Citroën ë-C4", "ë-C4"),
    "ë-C4 54 kWh": ("Citroën ë-C4", "ë-C4"),
    "ë-C4 X 50 kWh": ("Citroën ë-C4 X", "ë-C4 X"),
    "ë-C4 X 54 kWh": ("Citroën ë-C4 X", "ë-C4 X"),
    "MG4 Urban 54 kWh": ("MG4 Urban", "MG4"),
    "MG4 51 kWh": ("MG4", "MG4"),
    "MG4 64 kWh": ("MG4", "MG4"),
    "MG4 77 kWh": ("MG4", "MG4"),
    "MG4 XPower": ("MG4 XPower", "MG4"),
}

# Modèles assez connus pour se passer de la marque dans les phrases
# (« une Mégane E-Tech EV60 », « une ID.3 Pro 58 kWh ») ; les autres la gardent.
SANS_MARQUE = ("Mégane", "Scénic", "Twingo", "Zoe", "ID.", "e-2", "e-3", "e-5", "Ioniq", "Kona", "Enyaq", "Elroq", "MG4", "MG5")

# Versions regroupées : même marque, même batterie, même pic de charge, conso à
# moins de 5 % d'écart. La première garde la page, l'autre y est citée.
REGROUPE = {
    # MG4 XPower : batterie et charge de la MG4 64 kWh, 4 % de conso en plus.
    "MG4 XPower": "MG4 64 kWh",
}

# Page déjà en ligne et indexée : ses phrases d'origine (variante 0) sont figées.
FIGEES = {"renault-megane-e-tech-ev60"}


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def slugify(s: str) -> str:
    s = sans_accents(s).lower().replace("+", " plus ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def modele_affiche(model: str) -> str:
    out = model
    for pat, rep in DEVELOPPE:
        out = re.sub(pat, rep, out)
    return out


def nom_complet(brand: str, model: str) -> str:
    """« MG MG4 64 kWh » → « MG4 64 kWh » : pas de marque répétée."""
    mod = modele_affiche(model)
    return mod if mod.startswith(brand) else f"{brand} {mod}"


def famille_auto(brand: str, model: str) -> tuple[str, str]:
    """(famille, familier) quand FAMILLE ne dit rien."""
    if model in FAMILLE:
        return FAMILLE[model]
    m = re.sub(r"\s*\(.*?\)", "", model)
    m = re.sub(r"\s*\d+(?:[.,]\d+)?\s*kWh", "", m)
    m = re.sub(r"\s+(Pro S|Pro|Pure|GTX|Urban|XPower|Long Range|Grande Aut\.|Propulsion|\d\d)$", "", m).strip()
    m = re.sub(r"\s+(Pro S|Pro|Pure|GTX|Urban|XPower|Long Range|Grande Aut\.|Propulsion|\d\d)$", "", m).strip()
    cryptique = bool(re.match(r"^[\d#]", m)) or len(m) <= 3
    fam = f"{brand} {m}" if cryptique else m
    return fam, fam


# --------------------------------------------------------------------------
# Formats (arrondis HALF_UP comme String.format côté Java/Kotlin)
# --------------------------------------------------------------------------

def _q(x: float, places: str) -> Decimal:
    return Decimal(repr(float(x))).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def ent(x: float) -> int:
    return int(_q(x, "1"))


def eur(x: float) -> str:
    return f"{_q(x, '0.01')}".replace(".", ",") + " €"


def dec1(x: float) -> str:
    return f"{_q(x, '0.1')}".replace(".", ",")


def kwh_txt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else dec1(x)


def duree(minutes: float | int) -> str:
    m = ent(minutes) if not isinstance(minutes, int) else minutes
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d}"


NOMBRES = {0: "zéro", 1: "un", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six",
           7: "sept", 8: "huit", 9: "neuf", 10: "dix", 11: "onze", 12: "douze"}


def en_lettres(n: int) -> str:
    return NOMBRES.get(n, str(n))


def arrets(n: int) -> str:
    return "sans arrêt" if n == 0 else ("1 arrêt" if n == 1 else f"{n} arrêts")


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def attr(s: str) -> str:
    return html.escape(s, quote=True)


# --------------------------------------------------------------------------
# Choix de phrases : stable par page, différent d'une page à l'autre
# --------------------------------------------------------------------------

class Choix:
    def __init__(self, slug: str):
        self.slug = slug
        self.fige = slug in FIGEES

    def __call__(self, cle: str, options: list):
        if self.fige or len(options) == 1:
            return options[0]
        h = int(hashlib.sha1(f"{self.slug}|{cle}".encode()).hexdigest(), 16)
        return options[h % len(options)]


# --------------------------------------------------------------------------
# Lecture des calculs
# --------------------------------------------------------------------------

def autonomie(v: dict, vitesse: float, temp: float) -> dict:
    for a in v["autonomie"]:
        if a["v"] == vitesse and a["t"] == temp:
            return a
    raise KeyError((vitesse, temp))


def trajet(v: dict, de: str, a: str, temp: float) -> dict | None:
    for t in v["trajets"]:
        if t["de"] == de and t["a"] == a and t["t"] == temp:
            return t if t.get("options") else None
    return None


def option(t: dict | None, tier: str) -> dict | None:
    if not t:
        return None
    for o in t["options"]:
        if o["tier"] == tier:
            return o
    return None


def autoroute(t: dict | None) -> dict | None:
    """L'option « Autoroute » (palier FREE) ; None si le moteur l'a écartée."""
    return option(t, "FREE")


def plus_rapide(t: dict | None) -> dict | None:
    if not t or not t.get("options"):
        return None
    return min(t["options"], key=lambda o: o["total_min"])


def trop_d_arrets(t: dict | None) -> bool:
    """Vrai si le moteur a écarté l'autoroute parce qu'il faudrait trop d'arrêts."""
    return bool(t) and any(e.startswith("FREE:") and "arrêts nécessaires" in e for e in t.get("ecartes", []))


def limite_arrets(t: dict) -> int:
    """Limite d'arrêts du moteur pour ce trajet (elle suit la distance depuis le 31/10)."""
    for e in t.get("ecartes", []):
        m = re.search(r"Plus de (\d+) arrêts", e)
        if e.startswith("FREE:") and m:
            return int(m.group(1))
    return 8


def peage_txt(o: dict) -> str:
    return eur(o["peage_eur"]) if o["peage_exact"] else "≈ " + eur(o["peage_eur"])


def peage_mots(o: dict) -> str:
    return eur(o["peage_eur"]) if o["peage_exact"] else "environ " + eur(o["peage_eur"])


def raisons(o: dict, fr: dict) -> str:
    """Pourquoi une option bat l'autoroute : seulement ce que les chiffres montrent."""
    r = []
    if o["peage_eur"] < fr["peage_eur"]:
        r.append(f"{eur(fr['peage_eur'] - o['peage_eur'])} de péage en moins")
    if o["recharge_eur"] < fr["recharge_eur"]:
        r.append(f"{eur(fr['recharge_eur'] - o['recharge_eur'])} de recharge en moins")
    if o["charge_min"] < fr["charge_min"]:
        r.append(f"{duree(ent(fr['charge_min']) - ent(o['charge_min']))} de charge en moins")
    return (" : " + ", ".join(r)) if r else ""


def classe_option(o: dict) -> str:
    if o["tier"] == "FREE":
        return "opt"
    if o["tier"] == "ECO":
        return "opt eco"
    return "opt mix"


# --------------------------------------------------------------------------
# Une page
# --------------------------------------------------------------------------

TRAJETS = [("Paris", "Lyon", "lyon"), ("Lyon", "Marseille", "marseille"), ("Paris", "Marseille", "pm")]


class Page:
    def __init__(self, v: dict, meta: dict, rangs: dict, tous: list, proches: list, regroupees: list):
        self.v = v
        self.meta = meta
        self.brand = v["brand"]
        self.model = v["model"]
        self.slug = v["slug"]
        self.c = Choix(self.slug)
        self.mod = modele_affiche(self.model)
        self.nom = nom_complet(self.brand, self.model)
        fam, self.familier = famille_auto(self.brand, self.model)
        self.famille = fam
        # « une Mégane E-Tech EV60 » : sans la marque si le nom du modèle se suffit.
        self.court = self.mod if self.model.startswith(SANS_MARQUE) else self.nom
        self.rangs = rangs
        self.tous = tous
        self.proches = proches
        self.regroupees = regroupees

        self.a110 = autonomie(v, 110.0, 20.0)
        self.a130 = autonomie(v, 130.0, 20.0)
        self.a110f = autonomie(v, 110.0, 0.0)
        self.a130f = autonomie(v, 130.0, 0.0)
        self.ch = v["charge"]
        self.t = {k: (trajet(v, de, a, 20.0), trajet(v, de, a, 0.0)) for de, a, k in TRAJETS}

    # ---- profil de la voiture (pour choisir les phrases) ----
    @property
    def petite(self) -> bool:
        return self.v["kwh"] < 45

    @property
    def grande(self) -> bool:
        return self.a130["km100_10"] >= 330

    @property
    def charge_lente(self) -> bool:
        return self.ch["min20"] > 45

    @property
    def charge_vive(self) -> bool:
        return self.ch["min20"] <= 20

    @property
    def lourde(self) -> bool:
        return self.v["base"] >= 17.5

    # ---- textes ----
    def titre(self) -> str:
        if self.c.fige:
            return f"{self.court} : autonomie autoroute et coût trajet"
        km = ent(self.a130["km100_10"])
        pl = autoroute(self.t["lyon"][0])
        cands = [
            f"{self.nom} : autonomie sur autoroute et coût d'un trajet",
            f"{self.nom} : {km} km à 130 km/h, coût d'un long trajet",
            f"Autonomie {self.nom} sur autoroute : {km} km à 130 km/h",
        ]
        if pl:
            cands.append(f"{self.nom} : autonomie autoroute et Paris–Lyon à {eur(pl['total_eur'])}")
        cands = [t for t in cands if len(t) <= 66] or [f"{self.nom} : autonomie et coût trajet"]
        return self.c("titre", cands)

    def description(self) -> str:
        km = ent(self.a130["km100_10"])
        s = f"{self.court} sur autoroute : {km} km de 100 à 10 % à 130 km/h."
        pl = autoroute(self.t["lyon"][0])
        if pl:
            s += f" Paris–Lyon : {arrets(pl['arrets'])}, {duree(pl['total_min'])}, {eur(pl['total_eur'])} de recharge et péage."
        return s + " Calcul Wattlas."

    def og_titre(self) -> str:
        return self.c("og", [
            f"{self.nom} : autonomie sur autoroute et coût réel d'un trajet",
            f"{self.nom} : autonomie réelle et prix d'un long trajet",
            f"{self.nom} sur autoroute : autonomie, recharges et facture",
        ])

    def h1(self) -> str:
        f = self.famille
        km = ent(self.a130["km80_10"])
        if self.grande:
            opts = [f"{f} : ce que coûte vraiment un long trajet",
                    f"{f} : {km} km d'autoroute entre deux recharges",
                    f"{f} : autonomie et coût réel d'un long trajet"]
        elif self.petite:
            opts = [f"{f} : jusqu'où sur autoroute, et pour combien ?",
                    f"{f} sur long trajet : arrêts et facture",
                    f"{f} : ce que coûte vraiment un long trajet"]
        else:
            opts = [f"{f} : ce que coûte vraiment un long trajet",
                    f"{f} : autonomie et coût réel d'un long trajet",
                    f"{f} : combien d'arrêts, combien d'euros ?"]
        return self.c("h1", opts)

    def chapo(self) -> str:
        return self.c("chapo", [
            "Autonomie sur autoroute, arrêts recharge et facture complète, péage compris. Calculé par Wattlas sur de vrais trajets.",
            "Combien de kilomètres à 130 km/h, combien d'arrêts, combien d'euros, péage compris. Chiffres calculés par Wattlas sur trois trajets réels.",
            "Autonomie à 110 et 130 km/h, été comme hiver, et prix de trois trajets types, recharge et péage compris. Calcul Wattlas.",
        ])

    def sous_autonomie(self) -> str:
        base = "De 100 à 10 % de batterie, sur le plat."
        if self.c.fige:
            return base + " Plus on roule vite et plus il fait froid, plus elle fond."
        km = ent(self.a130["km100_10"])
        kmf = ent(self.a130f["km100_10"])
        r = self.rangs
        if self.petite:
            s = self.c("sa", [
                f"Avec {kwh_txt(self.v['kwh'])} kWh utiles, c'est une batterie de ville et de trajets régionaux : sur autoroute, les arrêts se rapprochent.",
                f"{kwh_txt(self.v['kwh'])} kWh utiles : sur autoroute, il faut s'arrêter souvent, surtout en hiver ({kmf} km à 0 °C).",
            ])
        elif self.charge_lente:
            s = self.c("sa", [
                f"Sa charge rapide plafonne à {ent(self.v['peak'])} kW : sur long trajet, c'est le temps de charge plus que l'autonomie qui allonge le voyage.",
                f"La charge rapide monte au plus à {ent(self.v['peak'])} kW : les arrêts sont longs, d'où l'intérêt de partir batterie pleine.",
            ])
        elif self.grande:
            s = self.c("sa", [
                f"À 130 km/h par temps doux, elle va plus loin que {r['pct_auto']} % des voitures du catalogue Wattlas.",
                f"{km} km à 130 km/h par temps doux : dans le catalogue Wattlas, {r['pct_auto']} % des voitures font moins.",
            ])
        else:
            s = self.c("sa", [
                "Plus on roule vite et plus il fait froid, plus elle fond.",
                f"Plus on roule vite et plus il fait froid, plus elle fond : de {km} km à 130 km/h par temps doux, elle passe à {kmf} km à 0 °C.",
                (f"À 130 km/h, elle se place au-dessus de {r['pct_auto']} % des voitures du catalogue Wattlas ; le froid lui retire {km - kmf} km."
                 if 10 <= r['pct_auto'] <= 90 else
                 f"À 130 km/h, le froid lui retire {km - kmf} km : {km} km par temps doux, {kmf} km à 0 °C."),
            ])
        return f"{base} {s}"

    # ---- blocs ----
    def bloc_head(self) -> str:
        desc = self.description()
        faq = self.faq()
        ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": r}}
                for q, r in faq[:3]
            ],
        }
        url = f"{SITE}/voitures/{self.slug}.html"
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(self.titre())}</title>
<meta name="description" content="{attr(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="Wattlas">
<meta property="og:locale" content="fr_FR">
<meta property="og:title" content="{attr(self.og_titre())}">
<meta property="og:description" content="{attr(desc)}">
<meta property="og:image" content="https://wattlas.fr/og-facture.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=2)}
</script>
{STYLE}
</head>
<body>
"""

    def cta(self, suffixe: str = "", style: str = "", texte: str = "▶ Calculer mon trajet, gratuit") -> str:
        st = f' style="{style}"' if style else ""
        return (f'<a class="cta"{st} href="https://play.google.com/store/apps/details?id=fr.wattlas&amp;referrer='
                f'utm_source%3Dwattlas.fr%26utm_medium%3Dsite%26utm_content%3Dvoiture-{self.slug}{suffixe}">{texte}</a>')

    def bloc_hero(self) -> str:
        kpis = [(f"{ent(self.a130['km80_10'])} km", "entre deux recharges rapides à 130 km/h"),
                (duree(self.ch["min20"]), "pour une charge de 10 à 80 %")]
        pl = autoroute(self.t["lyon"][0])
        if pl:
            kpis.append((eur(pl["total_eur"]), "Paris → Lyon par l'autoroute, recharge + péage"))
        k = "\n".join(f'      <div class="kpi"><b>{a}</b><span>{esc(b)}</span></div>' for a, b in kpis)
        return f"""
<header class="hero">
  <div class="in">
    <div class="top">
      <a class="home" href="/">
        <svg width="34" height="34" viewBox="0 0 108 108" aria-hidden="true"><rect width="108" height="108" rx="24" fill="#FFFFFF"/><path d="M60.83 23.62 L37.30 59.32 L51.27 59.32 L46.40 84.38 L70.70 47.92 L56.43 47.92 Z" fill="#2F5BFF"/></svg>
        Wattlas
      </a>
      <span class="pill">{esc(self.nom)}</span>
    </div>
    <h1>{esc(self.h1())}</h1>
    <p>{esc(self.chapo())}</p>
    <div class="kpis">
{k}
    </div>
    {self.cta()}
  </div>
</header>
"""

    def bloc_autonomie(self) -> str:
        rows = [("110 km/h, temps doux", self.a110, ""), ("130 km/h, temps doux", self.a130, ""),
                ("110 km/h, 0 °C", self.a110f, " cold"), ("130 km/h, 0 °C", self.a130f, " cold")]
        mx = max(r[1]["km100_10"] for r in rows)
        bars = "\n".join(
            f'      <div class="bar"><div class="l">{lab} <em>{ent(a["km100_10"])} km</em></div>'
            f'<div class="track"><div class="fill{cl}" style="width:{ent(a["km100_10"] / mx * 100)}%"></div></div></div>'
            for lab, a, cl in rows)
        chips = [f'<span class="chip">Conso à 130 km/h : <b>{dec1(self.a130["conso"])} kWh/100 km</b></span>',
                 f'<span class="chip">Charge 10→80 % : <b>{duree(self.ch["min20"])}</b> l\'été, <b>{duree(self.ch["min0"])}</b> à 0 °C</span>',
                 f'<span class="chip">Batterie : <b>{kwh_txt(self.v["kwh"])} kWh</b> utiles</span>']
        if self.v["peak"] > 50 and self.v["kwh"] <= 52:
            chips.append(f'<span class="chip">Sur une borne de 50 kW : <b>{duree(self.ch["min20_50kw"])}</b> de 10 à 80 %</span>')
        if self.charge_lente or self.v["peak"] <= 60:
            chips.append(f'<span class="chip">Pic de charge : <b>{ent(self.v["peak"])} kW</b></span>')
        ch = "\n".join("      " + c for c in chips)
        return f"""
<section>
  <div class="in">
    <h2>Autonomie réelle sur autoroute</h2>
    <p class="sub">{esc(self.sous_autonomie())}</p>
    <div class="bars">
{bars}
    </div>
    <div class="chips">
{ch}
    </div>
  </div>
</section>
"""

    def sous_trajet(self, k: str, ete: dict) -> str:
        fr = autoroute(ete)
        eco = option(ete, "ECO")
        if not fr:
            alt = plus_rapide(ete)
            if trop_d_arrets(ete):
                return (f"{ent(alt['km'])} km. Par l'autoroute, il faudrait plus de {en_lettres(limite_arrets(ete))} arrêts, au-delà de ce que Wattlas propose : "
                        f"restent les itinéraires plus lents, où la voiture consomme moins.")
            return f"{ent(alt['km'])} km, {arrets(alt['arrets'])} par l'itinéraire le plus rapide retenu."
        km = ent(fr["km"])
        mix_mieux = [o for o in ete["options"] if o["tier"] not in ("FREE", "ECO")
                     and ent(o["total_min"]) < ent(fr["total_min"]) and o["total_eur"] < fr["total_eur"]]
        if mix_mieux and not self.c.fige:
            o = mix_mieux[0]
            return (f"{km} km par l'autoroute. Ici, l'option « {o['label']} » arrive {duree(ent(fr['total_min']) - ent(o['total_min']))} "
                    f"plus tôt et coûte {ent(fr['total_eur'] - o['total_eur'])} € de moins" + raisons(o, fr) + ".")
        if k == "lyon":
            if eco and eco is not fr and ent(eco["total_min"]) > ent(fr["total_min"]):
                gain = duree(ent(eco["total_min"]) - ent(fr["total_min"]))
                diff = ent(fr["total_eur"] - eco["total_eur"])
                return self.c("st-lyon", [
                    f"{km} km. Par l'autoroute, {gain} de gagnée pour {diff} € de plus que l'itinéraire économe.",
                    f"{km} km. L'autoroute fait gagner {gain} sur l'itinéraire économe, pour {diff} € de plus.",
                    f"{km} km. {diff} € d'écart entre l'autoroute et l'itinéraire économe, qui demande {gain} de plus.",
                ])
            return f"{km} km par l'autoroute, {arrets(fr['arrets'])}."
        if k == "marseille":
            n, m = fr["arrets"], fr["charge_min"]
            if n == 0:
                return self.c("st-mars", [
                    f"{km} km. D'une traite par l'A7 : aucun arrêt recharge, arrivée avec {ent(fr['arrivee_soc'])} %.",
                    f"{km} km. Pas besoin de recharger en route par l'A7 : il reste {ent(fr['arrivee_soc'])} % à l'arrivée.",
                ])
            if n == 1 and ent(m) <= 12:
                return self.c("st-mars", [
                    f"{km} km. Presque d'une traite : un arrêt de {ent(m)} minutes suffit par l'A7.",
                    f"{km} km. Un seul arrêt court par l'A7, {ent(m)} minutes de charge.",
                ])
            if n == 1:
                return self.c("st-mars", [
                    f"{km} km. Un arrêt par l'A7, {duree(m)} de charge.",
                    f"{km} km. Par l'A7, une recharge de {duree(m)} en chemin.",
                ])
            return self.c("st-mars", [
                f"{km} km. {cap(en_lettres(n))} arrêts par l'A7, {duree(m)} de charge au total.",
                f"{km} km. Même sur ce trajet moyen, {en_lettres(n)} arrêts par l'A7 ({duree(m)} de charge).",
            ])
        n, m = fr["arrets"], fr["charge_min"]
        if n >= 5:
            return self.c("st-pm", [
                f"{km} km. {cap(en_lettres(n))} arrêts par l'autoroute, {duree(m)} de charge : sur cette distance, la batterie impose son rythme.",
                f"{km} km. Par l'autoroute, {en_lettres(n)} arrêts et {duree(m)} branché au total.",
            ])
        return self.c("st-pm", [
            f"{km} km. {cap(arrets(n)) if n < 2 else cap(en_lettres(n)) + ' arrêts'} par l'autoroute, {duree(m)} de charge au total.",
            f"{km} km. Par l'autoroute : {arrets(n)} et {duree(m)} de charge au total.",
        ])

    def bloc_trajets(self) -> str:
        presents = [(de, a, k) for de, a, k in TRAJETS if self.t[k][0]]
        if not presents:
            return ""
        tabs = "".join(f'<a href="#{k}">{de} → {a}</a>' for de, a, k in presents)
        blocs = []
        for i, (de, a, k) in enumerate(presents):
            ete = self.t[k][0]
            opts = []
            for o in ete["options"]:
                opts.append(
                    f'        <div class="{classe_option(o)}"><div class="tag">{esc(o["label"])}</div><div class="price">{eur(o["total_eur"])}</div>'
                    f'<div class="time">{duree(o["total_min"])} · {arrets(o["arrets"])}</div>\n'
                    f'          <dl><dt>Recharge</dt><dd>{eur(o["recharge_eur"])}</dd><dt>Péage</dt><dd>{peage_txt(o)}</dd></dl></div>')
            note = ""
            if i == len(presents) - 1:
                maison = ent((autoroute(ete) or plus_rapide(ete))["domicile_kwh"] * PRIX_DOMICILE)
                note = (f'\n      <p class="note">Départ batterie pleine, arrivée avec 15 % au moins, temps doux. '
                        f"Le plein de départ à la maison s'ajoute (environ {maison} €). ≈ : péage estimé sur une partie du trajet.</p>")
            blocs.append(f"""
    <div class="trip" id="{k}">
      <h3>{de} → {a}</h3>
      <p class="sub">{esc(self.sous_trajet(k, ete))}</p>
      <div class="opts">
{chr(10).join(opts)}
      </div>{note}
    </div>""")
        manquants = [f"{de} → {a}" for de, a, k in TRAJETS if not self.t[k][0]]
        absent = ""
        if manquants:
            absent = (f'\n    <p class="note">{" et ".join(manquants)} : le moteur n\'a pas trouvé de plan de recharge '
                      f"complet pour cette voiture, le trajet n'est pas chiffré ici.</p>")
        n = len(presents)
        titre = {1: "Un trajet, sa facture", 2: "Deux trajets, deux factures", 3: "Trois trajets, trois factures"}[n]
        return f"""
<section class="trips">
  <div class="in">
    <h2>{titre}</h2>
    <p class="sub">Pour chaque destination, Wattlas compare l'autoroute aux itinéraires qui évitent le péage.</p>
    <nav class="tabs">{tabs}</nav>
{chr(10).join(blocs)}{absent}
  </div>
</section>
"""

    def bloc_hiver(self) -> str:
        cartes = []
        for de, a, k in TRAJETS:
            ete, hiv = self.t[k]
            fe, fh = autoroute(ete), autoroute(hiv)
            if fe and not fh and trop_d_arrets(hiv) and plus_rapide(hiv):
                alt = plus_rapide(hiv)
                cartes.append(f'      <div class="wcard"><h4>{de} → {a}</h4><div class="big">+ de {limite_arrets(hiv)} arrêts</div>'
                              f'<div class="vs">par l\'autoroute, au lieu de {fe["arrets"]} · option « {esc(alt["label"])} » : '
                              f'{duree(alt["total_min"])}, {arrets(alt["arrets"])}</div></div>')
                continue
            if not fe or not fh:
                continue
            if fh["arrets"] != fe["arrets"]:
                big = arrets(fh["arrets"])
                avant = "aucun" if fe["arrets"] == 0 else str(fe["arrets"])
                lieu = "au lieu d'aucun" if fe["arrets"] == 0 else f"au lieu de {avant}"
                vs = f"{lieu} · {duree(fh['charge_min'])} de charge · {duree(fh['total_min'])} au total"
            else:
                big = duree(fh["total_min"])
                vs = (f"au lieu de {duree(fe['total_min'])} · {duree(fh['charge_min'])} de charge · "
                      f"{eur(fh['recharge_eur'])} de recharge")
            cartes.append(f'      <div class="wcard"><h4>{de} → {a}</h4><div class="big">{big}</div><div class="vs">{vs}</div></div>')
        if not cartes:
            return ""
        sub = self.c("hiver", [
            "À 0 °C, la voiture consomme plus et charge moins vite. Mêmes trajets, par l'autoroute :",
            "Par 0 °C, la consommation monte et la charge ralentit. Les mêmes trajets, par l'autoroute :",
            "Au froid, il faut plus d'énergie et la batterie l'accepte moins vite. Mêmes trajets à 0 °C, par l'autoroute :",
        ])
        return f"""
<section class="winter">
  <div class="in">
    <h2>❄ En hiver, ce qui change</h2>
    <p class="sub">{esc(sub)}</p>
    <div class="wgrid">
{chr(10).join(cartes)}
    </div>
  </div>
</section>
"""

    def bloc_dl(self) -> str:
        f = self.familier
        h = self.c("dl", [f"Votre trajet, votre {f}", f"Avant de partir en {f}", f"Votre {f}, votre itinéraire"])
        return f"""
<section>
  <div class="in">
    <div class="dl">
      <div><h2>{esc(h)}</h2><p>Wattlas calcule vos arrêts et la facture complète avant de partir. Gratuit, sans compte, sans pub. Android, France.</p></div>
      {self.cta("-bas", "margin-top:0", "▶ Google Play")}
    </div>
  </div>
</section>
"""

    def faq(self) -> list[tuple[str, str]]:
        c, f = self.court, self.famille
        out = []
        q1 = self.c("q1", [f"Quelle autonomie sur autoroute pour une {c} ?",
                           f"Combien de kilomètres à 130 km/h avec une {c} ?",
                           f"Quelle est l'autonomie réelle d'une {c} sur autoroute ?"])
        r1 = (f"À 130 km/h sur le plat, Wattlas estime {ent(self.a130['km100_10'])} km entre 100 % et 10 % de batterie "
              f"par temps doux (20 °C), et {ent(self.a130f['km100_10'])} km à 0 °C. Entre deux recharges rapides, de 80 % à 10 %, "
              f"comptez {ent(self.a130['km80_10'])} km l'été et {ent(self.a130f['km80_10'])} km l'hiver.")
        if not self.c.fige:
            r1 += f" À 110 km/h, la portée passe à {ent(self.a110['km100_10'])} km par temps doux."
        out.append((q1, r1))

        ete = self.t["lyon"][0]
        fr = autoroute(ete)
        if fr:
            q2 = self.c("q2", [f"Combien coûte un Paris–Lyon en {f} électrique ?" if self.c.fige else f"Combien coûte un Paris–Lyon en {f} ?",
                               f"Quel budget pour un Paris–Lyon en {f} ?",
                               f"Paris–Lyon en {f} : combien de recharge et de péage ?"])
            n = fr["arrets"]
            avec = "sans arrêt" if n == 0 else ("avec un arrêt" if n == 1 else f"avec {en_lettres(n)} arrêts")
            r2 = (f"Par l'autoroute, au départ de Paris avec une batterie pleine, Wattlas calcule {eur(fr['recharge_eur'])} de recharge "
                  f"en route et {peage_mots(fr)} de péage, soit {eur(fr['total_eur'])}, pour {duree(fr['total_min'])} de trajet {avec}. "
                  f"Le plein de départ à la maison s'y ajoute.")
            eco = option(ete, "ECO")
            if eco and eco is not fr:
                r2 += f" Par les nationales, le même trajet coûte {eur(eco['total_eur'])} et prend {duree(eco['total_min'])}."
            out.append((q2, r2))

        ete, hiv = self.t["pm"]
        fe, fh = autoroute(ete), autoroute(hiv)
        if not fe and trop_d_arrets(ete) and plus_rapide(ete):
            alt = plus_rapide(ete)
            q3 = self.c("q3", [f"Combien d'arrêts recharge pour un Paris–Marseille en {f} ?",
                               f"Paris–Marseille en {f} : combien d'arrêts ?",
                               f"Combien de fois recharger une {f} entre Paris et Marseille ?"])
            out.append((q3, f"Par l'autoroute, il faudrait plus de {en_lettres(limite_arrets(ete))} arrêts, même par temps doux : Wattlas ne le propose pas. "
                            f"L'option « {alt['label']} » demande {en_lettres(alt['arrets'])} arrêts, {duree(alt['charge_min'])} de charge "
                            f"et {duree(alt['total_min'])} de trajet, pour {eur(alt['total_eur'])}."))
        if fe:
            q3 = self.c("q3", [f"Combien d'arrêts recharge pour un Paris–Marseille en {f} ?",
                               f"Paris–Marseille en {f} : combien d'arrêts ?",
                               f"Combien de fois recharger une {f} entre Paris et Marseille ?"])
            n = fe["arrets"]
            tete = "Aucun arrêt" if n == 0 else ("Un arrêt" if n == 1 else f"{cap(en_lettres(n))} arrêts")
            r3 = (f"{tete} par l'autoroute par temps doux, pour {duree(fe['charge_min'])} de charge et "
                  f"{duree(fe['total_min'])} de trajet au total.")
            if not fh and trop_d_arrets(hiv):
                r3 += f" À 0 °C, il en faudrait plus de {en_lettres(limite_arrets(hiv))} par l'autoroute : Wattlas propose alors un itinéraire plus lent."
            if fh:
                if fh["arrets"] != n:
                    r3 += f" À 0 °C, Wattlas en prévoit {en_lettres(fh['arrets'])}, pour {duree(fh['charge_min'])} de charge."
                else:
                    r3 += f" À 0 °C, le nombre d'arrêts ne change pas, mais la charge passe à {duree(fh['charge_min'])}."
            out.append((q3, r3))

        m = self.meta
        borne = ""
        if self.ch["borne_kw"] > 150:
            borne = f" Temps de charge 10→80 % sur une borne d'au moins {ent(self.ch['borne_kw'])} kW."
        regr = ""
        for g in self.regroupees:
            regr += (f" La {g['brand']} {modele_affiche(g['model'])} partage cette batterie ({kwh_txt(g['kwh'])} kWh, "
                     f"{ent(g['peak'])} kW) ; sa consommation un peu plus forte donne {ent(autonomie(g, 130.0, 20.0)['km100_10'])} km "
                     f"à 130 km/h au lieu de {ent(self.a130['km100_10'])}.")
        r4 = (f"Du moteur de calcul de Wattlas, le même que dans l'appli, le {date_fr(m['calcule_le'])} : fiche {self.court} du catalogue "
              f"({kwh_txt(self.v['kwh'])} kWh utiles, pic de charge {ent(self.v['peak'])} kW), départ à 100 %, arrivée avec 15 % au moins, "
              f"recharge jusqu'à 80 % au plus, sans trafic. Recharge au tarif public sans abonnement du réseau de chaque borne "
              f"(relevé du {date_fr(m['prix_generated'])}, estimé par réseau). Bornes : base nationale des IRVE du {date_fr(m['irve_date'])}. "
              f"Péage : grilles 2026 des sociétés d'autoroute. La disponibilité des bornes n'est pas remontée en direct. "
              f"Ces prix changent et seront recalculés.{borne}{regr}")
        out.append(("D'où viennent ces chiffres ?", r4))
        return out

    def bloc_faq(self) -> str:
        det = "\n".join(f"    <details><summary>{esc(q)}</summary><p>{esc(r)}</p></details>" for q, r in self.faq())
        prox = " · ".join(f'<a href="/voitures/{p["slug"]}.html">{esc(nom_complet(p["brand"], p["model"]))}</a>' for p in self.proches)
        prox_l = f'\n    <p class="more" style="margin-top:10px;font-size:15px">Autonomie voisine : {prox} · <a href="/voitures/">toutes les voitures</a></p>' if prox else ""
        return f"""
<section style="padding-top:0">
  <div class="in">
    <h2>Questions fréquentes</h2>
{det}
    <p class="more" style="margin-top:22px;font-size:15px">À lire aussi : <a href="/cout-trajet-voiture-electrique.html">le vrai coût d'un trajet</a> · <a href="/peage-voiture-electrique.html">péage : autoroute ou nationale ?</a> · <a href="/itineraire-voiture-electrique-hors-ligne.html">planifier sans réseau</a></p>{prox_l}
  </div>
</section>
"""

    def bloc_pied(self) -> str:
        fam_marque = re.sub(rf"^{re.escape(self.brand)}\s+", "", self.familier)
        if fam_marque == self.brand or re.match(r"^[\d#]", fam_marque) or len(fam_marque) <= 2:
            marques = f"La marque {esc(self.brand)} et le nom {esc(self.mod)} appartiennent à leurs propriétaires."
        else:
            marques = f"{esc(self.brand)} et {esc(fam_marque)} sont des marques de leurs propriétaires."
        return f"""
<footer>
  <div class="in">
    Données cartographiques © les contributeurs OpenStreetMap (ODbL). Bornes : Base nationale des IRVE, data.gouv.fr (Licence Ouverte). Péages : OpenTollData (ODbL) et grilles officielles des sociétés d'autoroute. Météo : Open-Meteo (CC-BY 4.0).<br>
    {marques} Wattlas est une application indépendante, affiliée à aucun constructeur, réseau de recharge ou organisme public.
    <a href="/confidentialite.html">Confidentialité</a> · <a href="mailto:contact@wattlas.fr">contact@wattlas.fr</a>
  </div>
</footer>
</body>
</html>
"""

    def rendre(self) -> str:
        return (self.bloc_head() + self.bloc_hero() + self.bloc_autonomie() + self.bloc_trajets()
                + self.bloc_hiver() + self.bloc_dl() + self.bloc_faq() + self.bloc_pied())


def date_fr(iso: str) -> str:
    y, m, d = str(iso).strip('"')[:10].split("-")
    return f"{d}/{m}/{y}"


STYLE = (ICI / "style.html").read_text(encoding="utf-8").rstrip("\n") if (ICI / "style.html").exists() else ""


# --------------------------------------------------------------------------
# Page index
# --------------------------------------------------------------------------

def rendre_index(pages: list[Page], meta: dict) -> str:
    par_marque: dict[str, list[Page]] = {}
    for p in pages:
        par_marque.setdefault(p.brand, []).append(p)
    marques = sorted(par_marque, key=lambda b: sans_accents(b).lower())
    nav = "".join(f'<a href="#{slugify(b)}">{esc(b)}</a>' for b in marques)
    km_max = max(p.a130["km100_10"] for p in pages)
    blocs = []
    for b in marques:
        lignes = []
        for p in sorted(par_marque[b], key=lambda p: sans_accents(p.mod).lower()):
            pl = autoroute(p.t["lyon"][0])
            prix = eur(pl["total_eur"]).replace(" €", "&nbsp;€") if pl else "—"
            km = p.a130["km100_10"]
            cherche = sans_accents(f"{b} {p.mod}").lower()
            lignes.append(
                f'        <a class="row" href="/voitures/{p.slug}.html" data-q="{attr(cherche)}">'
                f'<span class="m"><b>{esc(p.mod)}</b><small>{kwh_txt(p.v["kwh"])} kWh</small></span>'
                f'<span class="r"><i style="width:{km / km_max * 100:.0f}%"></i></span>'
                f'<span class="k">{ent(km)}&nbsp;km</span><span class="p">{prix}</span></a>')
        n_b = len(par_marque[b])
        blocs.append(f"""
      <div class="bcard" id="{slugify(b)}">
        <div class="bh"><h3>{esc(b)}</h3><span>{n_b} modèle{"s" if n_b > 1 else ""}</span></div>
{chr(10).join(lignes)}
      </div>""")
    n = len(pages)
    kms = sorted(ent(p.a130["km100_10"]) for p in pages)
    prix_min = min(o["total_eur"] for o in (autoroute(p.t["lyon"][0]) for p in pages) if o)
    desc = (f"Autonomie sur autoroute et coût d'un Paris–Lyon pour {n} voitures électriques, marque par marque. "
            f"Chiffres calculés par le moteur Wattlas.")
    url = f"{SITE}/voitures/"
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autonomie et coût de trajet de {n} voitures électriques</title>
<meta name="description" content="{attr(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="Wattlas">
<meta property="og:locale" content="fr_FR">
<meta property="og:title" content="{attr(f'{n} voitures électriques : autonomie sur autoroute et coût réel d’un trajet')}">
<meta property="og:description" content="{attr(desc)}">
<meta property="og:image" content="https://wattlas.fr/og-facture.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
{STYLE}
<style>
  .list{{background:var(--s1)}}
  .tools{{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--s1) 92%,transparent);backdrop-filter:blur(8px);
         margin:0 -16px 22px;padding:12px 16px;border-bottom:1px solid var(--line)}}
  .search{{width:100%;font:inherit;font-size:16px;padding:12px 16px 12px 44px;border-radius:14px;border:1px solid var(--line);
          background:var(--card) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' fill='none' stroke='%235B6472' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='9' cy='9' r='6'/%3E%3Cpath d='m14 14 4 4'/%3E%3C/svg%3E") no-repeat 14px center;color:var(--text)}}
  .search:focus{{outline:2px solid var(--blue);outline-offset:1px;border-color:transparent}}
  .brands{{display:flex;gap:6px;overflow-x:auto;margin-top:10px;padding-bottom:2px;scrollbar-width:none}}
  .brands::-webkit-scrollbar{{display:none}}
  .brands a{{flex:none;text-decoration:none;font-weight:600;font-size:13.5px;padding:5px 11px;border-radius:999px;color:var(--muted);
            background:var(--card);border:1px solid var(--line)}}
  .brands a:hover{{color:var(--blue);border-color:var(--blue)}}
  .legend{{display:flex;justify-content:flex-end;gap:18px;font-size:12.5px;color:var(--muted);margin:0 4px 10px;font-weight:600}}
  .legend .lk{{display:inline-flex;align-items:center;gap:6px}}
  .legend .lk::before{{content:"";width:18px;height:6px;border-radius:9px;background:linear-gradient(90deg,var(--cyan),var(--blue))}}
  .grid{{columns:2 440px;column-gap:18px}}
  .bcard{{break-inside:avoid;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:6px 6px 8px;margin-bottom:18px;
         scroll-margin-top:130px;box-shadow:0 1px 2px rgba(14,17,22,.04)}}
  .bh{{display:flex;align-items:baseline;justify-content:space-between;padding:12px 14px 8px}}
  .bh h3{{margin:0;font-size:19px;letter-spacing:-.02em}}
  .bh span{{font-size:12.5px;color:var(--muted);font-weight:600}}
  .row{{display:grid;grid-template-columns:minmax(0,1fr) 72px 62px 78px;align-items:center;gap:12px;padding:10px 14px;
       border-radius:13px;text-decoration:none;font-variant-numeric:tabular-nums}}
  .row + .row{{box-shadow:inset 0 1px 0 var(--s2)}}
  .row:hover{{background:var(--s1);box-shadow:none}}
  .row:hover + .row{{box-shadow:none}}
  .m{{min-width:0;display:flex;flex-direction:column;line-height:1.25}}
  .m b{{font-size:15.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .m small{{color:var(--muted);font-size:12.5px}}
  .r{{height:6px;background:var(--s2);border-radius:9px;overflow:hidden}}
  .r i{{display:block;height:100%;border-radius:9px;background:linear-gradient(90deg,var(--cyan),var(--blue))}}
  .k{{text-align:right;font-weight:700;font-size:14.5px}}
  .p{{text-align:right;font-weight:800;font-size:14.5px;color:var(--blue)}}
  @media (prefers-color-scheme:dark){{.p{{color:var(--ice)}}}}
  .none{{display:none;text-align:center;color:var(--muted);padding:30px 0}}
  @media (max-width:520px){{
    .row{{grid-template-columns:minmax(0,1fr) 58px 72px;gap:10px}}
    .row .r{{display:none}}
    .legend .lk::before{{display:none}}
  }}
</style>
</head>
<body>

<header class="hero">
  <div class="in">
    <div class="top">
      <a class="home" href="/">
        <svg width="34" height="34" viewBox="0 0 108 108" aria-hidden="true"><rect width="108" height="108" rx="24" fill="#FFFFFF"/><path d="M60.83 23.62 L37.30 59.32 L51.27 59.32 L46.40 84.38 L70.70 47.92 L56.43 47.92 Z" fill="#2F5BFF"/></svg>
        Wattlas
      </a>
      <span class="pill">{n} voitures</span>
    </div>
    <h1>Votre voiture, sur autoroute</h1>
    <p>Pour chaque modèle du catalogue Wattlas : autonomie à 110 et 130 km/h, temps de charge, et prix de trois trajets types, recharge et péage compris.</p>
    <div class="kpis">
      <div class="kpi"><b>{n}</b><span>voitures électriques, {len(marques)} marques</span></div>
      <div class="kpi"><b>{kms[0]} à {kms[-1]} km</b><span>d'autonomie à 130 km/h, de 100 à 10 %</span></div>
      <div class="kpi"><b>dès {eur(prix_min)}</b><span>Paris → Lyon par l'autoroute, recharge + péage</span></div>
    </div>
    <a class="cta" href="https://play.google.com/store/apps/details?id=fr.wattlas&amp;referrer=utm_source%3Dwattlas.fr%26utm_medium%3Dsite%26utm_content%3Dvoitures-index">▶ Calculer mon trajet, gratuit</a>
  </div>
</header>

<section class="list">
  <div class="in">
    <h2>Trouvez votre modèle</h2>
    <p class="sub">Autonomie de 100 à 10 % à 130 km/h par temps doux, et prix d'un Paris → Lyon par l'autoroute au départ batterie pleine.</p>
    <div class="tools">
      <input class="search" type="search" placeholder="Chercher : Megane, Model Y, ID.3…" aria-label="Chercher un modèle" autocomplete="off">
      <nav class="brands" aria-label="Marques">{nav}</nav>
    </div>
    <div class="legend"><span class="lk">Autonomie à 130 km/h</span><span>Paris → Lyon</span></div>
    <div class="grid">{"".join(blocs)}
    </div>
    <p class="none">Aucun modèle ne correspond. Essayez la marque seule.</p>
    <p class="note">Calcul du {date_fr(meta['calcule_le'])} par le moteur de l'appli. Recharge au tarif public sans abonnement de chaque réseau (relevé du {date_fr(meta['prix_generated'])}), bornes de la base nationale des IRVE du {date_fr(meta['irve_date'])}, péage selon les grilles 2026.</p>
  </div>
</section>
<script>
(function(){{
  var q=document.querySelector('.search'),cards=[].slice.call(document.querySelectorAll('.bcard')),none=document.querySelector('.none');
  function norm(s){{return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();}}
  q.addEventListener('input',function(){{
    var w=norm(q.value).split(' ').filter(Boolean),vis=0;
    cards.forEach(function(c){{
      var n=0;[].forEach.call(c.querySelectorAll('.row'),function(r){{
        var t=norm(r.getAttribute('data-q')),t2=t.replace(/ /g,''),ok=w.every(function(x){{return t.indexOf(x)>=0||t2.indexOf(x)>=0;}});
        r.style.display=ok?'':'none';if(ok)n++;}});
      c.style.display=n?'':'none';vis+=n;}});
    none.style.display=vis?'none':'block';
  }});
}})();
</script>

<footer>
  <div class="in">
    Données cartographiques © les contributeurs OpenStreetMap (ODbL). Bornes : Base nationale des IRVE, data.gouv.fr (Licence Ouverte). Péages : OpenTollData (ODbL) et grilles officielles des sociétés d'autoroute.<br>
    Les noms de marques et de modèles appartiennent à leurs propriétaires. Wattlas est une application indépendante, affiliée à aucun constructeur, réseau de recharge ou organisme public.
    <a href="/confidentialite.html">Confidentialité</a> · <a href="mailto:contact@wattlas.fr">contact@wattlas.fr</a>
  </div>
</footer>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Sitemap
# --------------------------------------------------------------------------

def maj_sitemap(slugs: list[str], lastmod: str) -> None:
    f = DOCS / "sitemap.xml"
    txt = f.read_text(encoding="utf-8")
    # Retire les entrées /voitures/ existantes, puis remet la liste complète.
    txt = re.sub(r"  <url>\n    <loc>https://wattlas\.fr/voitures/[^<]*</loc>\n.*?</url>\n", "", txt, flags=re.S)
    ent_ = [("https://wattlas.fr/voitures/", "0.6")] + [(f"https://wattlas.fr/voitures/{s}.html", "0.6") for s in slugs]
    bloc = "".join(f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>monthly</changefreq>\n"
                   f"    <priority>{p}</priority>\n  </url>\n" for u, p in ent_)
    txt = txt.replace("</urlset>", bloc + "</urlset>")
    f.write_text(txt, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calculs", default=str(ICI / "calculs.json"))
    ap.add_argument("--seulement", help="slug à générer seul (essai)")
    ap.add_argument("--sans-sitemap", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.calculs).read_text(encoding="utf-8"))
    meta = {k: data[k] for k in data if k != "vehicles"}
    vehicules = data["vehicles"]
    for v in vehicules:
        v["slug"] = slugify(f"{v['brand']} {modele_affiche(v['model'])}")
    slugs = [v["slug"] for v in vehicules]
    doublons = {s for s in slugs if slugs.count(s) > 1}
    if doublons:
        print("Slugs en double :", doublons, file=sys.stderr)
        return 1

    par_modele = {v["model"]: v for v in vehicules}
    regroupees: dict[str, list] = {}
    gardees = []
    for v in vehicules:
        cible = REGROUPE.get(v["model"])
        if cible and cible in par_modele:
            regroupees.setdefault(cible, []).append(v)
        else:
            gardees.append(v)

    # Rang d'autonomie à 130 km/h parmi les voitures gardées.
    k130 = sorted(autonomie(v, 130.0, 20.0)["km100_10"] for v in gardees)
    n = len(k130)
    pages = []
    for v in gardees:
        km = autonomie(v, 130.0, 20.0)["km100_10"]
        moins = sum(1 for x in k130 if x < km)
        rangs = {"pct_auto": ent(moins / n * 100), "n": n}
        voisins = sorted((w for w in gardees if w is not v),
                         key=lambda w: (abs(autonomie(w, 130.0, 20.0)["km100_10"] - km), w["slug"]))
        # Trois voisins d'autonomie, de préférence d'autres marques.
        proches = [w for w in voisins if w["brand"] != v["brand"]][:2] + [w for w in voisins if w["brand"] == v["brand"]][:1]
        if len(proches) < 3:
            proches = voisins[:3]
        pages.append(Page(v, meta, rangs, gardees, proches, regroupees.get(v["model"], [])))

    SORTIE.mkdir(parents=True, exist_ok=True)
    for p in pages:
        if args.seulement and p.slug != args.seulement:
            continue
        (SORTIE / f"{p.slug}.html").write_text(p.rendre(), encoding="utf-8", newline="\n")
    if args.seulement:
        return 0
    (SORTIE / "index.html").write_text(rendre_index(pages, meta), encoding="utf-8", newline="\n")
    if not args.sans_sitemap:
        maj_sitemap(sorted(p.slug for p in pages), meta["calcule_le"])
    print(f"{len(pages)} pages + index ; regroupées : "
          + ", ".join(f"{g['model']} → {c}" for c, gs in regroupees.items() for g in gs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
