#!/usr/bin/env python3
"""Contrôles des pages voiture : balises équilibrées, liens internes résolus,
JSON-LD valide et identique au texte visible, pas de None/nan, titres et
descriptions uniques. Usage : python tools/pages-voitures/verifier.py"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"
VIDES = {"meta", "link", "br", "img", "input", "hr", "source", "path", "rect"}


class Verif(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pile, self.erreurs, self.liens, self.ids = [], [], [], set()
        self.titre, self.desc, self.dans_titre, self.ld, self.dans_ld = "", "", False, [], False
        self.summaries, self.dans_sum, self.cur = [], False, ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a" and "href" in a:
            self.liens.append(a["href"])
        if tag == "meta" and a.get("name") == "description":
            self.desc = a.get("content", "")
        if tag == "title":
            self.dans_titre = True
        if tag == "script" and a.get("type") == "application/ld+json":
            self.dans_ld = True
        if tag == "summary":
            self.dans_sum, self.cur = True, ""
        if tag not in VIDES:
            self.pile.append((tag, self.getpos()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VIDES:
            self.pile.pop()

    def handle_endtag(self, tag):
        if tag in VIDES:
            return
        if tag == "title":
            self.dans_titre = False
        if tag == "script":
            self.dans_ld = False
        if tag == "summary":
            self.dans_sum = False
            self.summaries.append(self.cur)
        if not self.pile or self.pile[-1][0] != tag:
            self.erreurs.append(f"</{tag}> inattendu ligne {self.getpos()[0]} (ouvert : {self.pile[-1] if self.pile else None})")
            return
        self.pile.pop()

    def handle_data(self, data):
        if self.dans_titre:
            self.titre += data
        if self.dans_ld:
            self.ld.append(data)
        if self.dans_sum:
            self.cur += data


def main() -> int:
    pages = sorted((DOCS / "voitures").glob("*.html"))
    problemes, titres, descs = [], {}, {}
    for f in pages:
        txt = f.read_text(encoding="utf-8")
        v = Verif()
        v.feed(txt)
        nom = f.name
        if v.pile:
            problemes.append(f"{nom}: balises non fermées {v.pile}")
        problemes += [f"{nom}: {e}" for e in v.erreurs]
        visible = re.sub(r"<[^>]+>", " ", txt)
        for mot in (r"\bNone\b", r"\bnan\b", r"\bnull\b", r"\{", r"\binf\b", r"\b1 arrêts\b", r"\b0 arrêts?\b", r"\bun arrêts\b"):
            if re.search(mot, re.sub(r"<style>.*?</style>|<script.*?</script>", "", txt, flags=re.S)):
                problemes.append(f"{nom}: motif suspect {mot}")
        for h in v.liens:
            if h.startswith("#"):
                if h[1:] not in v.ids:
                    problemes.append(f"{nom}: ancre {h} absente")
            elif h.startswith("/"):
                cible = DOCS / h.lstrip("/").split("#")[0]
                if h.endswith("/"):
                    cible = cible / "index.html"
                if not cible.exists():
                    problemes.append(f"{nom}: lien cassé {h}")
        if v.ld:
            try:
                ld = json.loads("".join(v.ld))
                qs = [q["name"] for q in ld["mainEntity"]]
                if qs != v.summaries[: len(qs)]:
                    problemes.append(f"{nom}: FAQ JSON-LD ≠ questions visibles")
            except Exception as e:  # noqa: BLE001
                problemes.append(f"{nom}: JSON-LD invalide ({e})")
        if not v.titre or not v.desc:
            problemes.append(f"{nom}: titre ou description vide")
        titres.setdefault(v.titre, []).append(nom)
        descs.setdefault(v.desc, []).append(nom)
        if len(v.titre) > 70:
            problemes.append(f"{nom}: titre long ({len(v.titre)})")
        if len(v.desc) > 170:
            problemes.append(f"{nom}: description longue ({len(v.desc)})")
    problemes += [f"titre en double : {t!r} {n}" for t, n in titres.items() if len(n) > 1]
    problemes += [f"description en double : {n}" for d, n in descs.items() if len(n) > 1]
    sm = (DOCS / "sitemap.xml").read_text(encoding="utf-8")
    for f in pages:
        u = "https://wattlas.fr/voitures/" + ("" if f.name == "index.html" else f.name)
        if f"<loc>{u}</loc>" not in sm:
            problemes.append(f"sitemap : {u} absente")
    print(f"{len(pages)} fichiers contrôlés, {len(problemes)} problème(s)")
    for p in problemes:
        print(" -", p)
    return 1 if problemes else 0


if __name__ == "__main__":
    sys.exit(main())
