"""Prépare l'archive ZIP téléchargeable d'une analyse.

Ce module écrit les tables en CSV, les réglages en JSON et un journal Markdown.
Il n'a pas besoin de Flask : l'interface lui transmet les résultats déjà calculés.

Contenu de l'archive :
    LISEZMOI.md                 ce que contient le zip
    journal.md                  réglages appliqués, écarts au livre, noms des hyperdomaines
    reglages_<version>.json     réglages exacts (pour refaire l'analyse)
    <version>/enonces.csv, relations.csv, zones.csv, chaines.csv (1969),
              anaphores.csv (si le corpus vient de textes), domaines.csv, synthese_domaines.csv, relations_domaines.csv,
              matrice_relations_domaines.csv, hyperdomaines.csv
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict
from datetime import datetime

from aad69.pipeline import Resultats
from aad69.reglages import CATALOGUE, Reglages

from . import tables


def _csv(lignes: list[dict]) -> str:
    """Convertit des lignes de dictionnaires en texte CSV avec en-tête."""
    if not lignes:
        return ""
    # Les clés de la première ligne définissent l'ordre et le nom des colonnes.
    sortie = io.StringIO()
    ecrivain = csv.DictWriter(sortie, fieldnames=list(lignes[0]))
    ecrivain.writeheader()
    ecrivain.writerows(lignes)
    return sortie.getvalue()


def reglages_dict(r: Reglages) -> dict:
    """Convertit les réglages en dictionnaire sérialisable en JSON."""
    d = asdict(r)
    # `asdict` ne sérialise pas les poids sous la forme détaillée attendue par l'export.
    d["poids"] = {"identiques": r.poids.identiques, "vides": r.poids.vides, "copules": r.poids.copules}
    return d


def journal_markdown(resultats: dict[str, Resultats], noms_hyper: dict[str, dict[int, str]],
                     source: str, corrections: list[dict] | None = None) -> str:
    """Rédige le journal de l'analyse en Markdown.

    Le journal indique la provenance du corpus, les résultats principaux,
    les réglages appliqués, les écarts au livre et les corrections manuelles.
    """
    # Le journal rassemble les informations séparément pour chaque version analysée.
    l = [f"# Journal de l'analyse AAD69 — {datetime.now():%Y-%m-%d %H:%M}", "",
         f"**Corpus** : {source}", ""]
    for version, res in resultats.items():
        l += [f"## Version {version}", "",
              f"- discours : {len(res.corpus.discours)} ; énoncés : {len(res.corpus.enonces)} ; "
              f"relations : {len(res.corpus.relations)}",
              f"- zones de similitude / quadruplets : {len(res.zones)}",
              f"- domaines : {len(res.domaines)} ; hyperdomaines : {len(res.hyperdomaines)}"]
        if res.coefficient is not None:
            l.append(f"- coefficient d'homogénéité (1972) : {res.coefficient:.2f}")
        l += ["", "### Réglages appliqués", "", "| réglage | valeur | décisions |", "|---|---|---|"]
        # Décrit chaque réglage avec sa valeur et les décisions qui l'expliquent.
        for nom, reglage in CATALOGUE.items():
            valeur = getattr(res.reglages, nom)
            if nom == "poids":
                valeur = "p. 92" if valeur == Reglages().poids else "modifiés (voir JSON)"
            l.append(f"| {reglage.libelle} | {valeur} | {reglage.decisions} |")
        # Ajoute les différences entre les réglages actifs et les valeurs du livre.
        ecarts = res.reglages.ecarts()
        l += ["", "### Écarts aux réglages du livre", ""]
        l += ([f"- **{r.libelle}** ({r.decisions}) : livre = {livre}, ici = {ici}. {r.explication}"
               for r, livre, ici in ecarts] or ["Aucun : réglages du livre."])
        noms = noms_hyper.get(version, {})
        if any(noms.values()):
            l += ["", "### Noms donnés aux hyperdomaines (interprétation de l'analyste, H3)", ""]
            l += [f"- H{n} : {nom}" for n, nom in sorted(noms.items()) if nom]
        miennes = [c for c in (corrections or []) if c["version"] == version]
        l += ["", "### Énoncés corrigés à la main (I6)", ""]
        l += ([f"- énoncé {c['énoncé']}, case {c['case']} : « {c['extraction automatique']} » → « {c['valeur retenue']} »"
               for c in miennes] or ["Aucun : énoncés de l'extraction automatique."])
        l.append("")
    l += ["Les décisions citées (D1, C2…) sont expliquées dans docs/decisions.md du projet."]
    return "\n".join(l)


LISEZMOI = """# Export AAD69

- journal.md : réglages, écarts au livre, énoncés corrigés à la main, noms des hyperdomaines.
- corrections.csv : chaque case corrigée à la main (version, énoncé, case, avant, après).
- linguiste.csv : décisions du linguiste LLM appliquées, refusées ou écartées par la validation, avec leur raison (LG5).
- <version>/anaphores.csv : chaque pronom examiné, son antécédent, la règle et le statut (I7).
- reglages_<version>.json : réglages exacts, pour refaire l'analyse.
- <version>/ : un CSV par étape (énoncés, relations, zones, chaînes, domaines, relations entre
  domaines, matrice, hyperdomaines). Les colonnes sont celles affichées dans l'interface.
- <version>/regroupements.csv : groupes du regroupement hiérarchique, pour les trois liens, à la
  borne des réglages actifs.
"""


def zip_resultats(resultats: dict[str, Resultats], noms_hyper: dict[str, dict[int, str]] | None = None,
                  source: str = "", corrections: list[dict] | None = None,
                  linguiste: list[dict] | None = None) -> bytes:
    """Construit l'archive ZIP contenant les résultats et les traces de l'analyse.

    `corrections` contient une ligne par case corrigée (version, énoncé, case,
    valeur automatique et valeur retenue). `linguiste`, si fourni, contient les
    décisions à exporter. Les tables sont les mêmes que celles affichées dans
    l'interface.
    """
    # Des valeurs par défaut vides simplifient l'écriture des entrées facultatives.
    noms_hyper = noms_hyper or {}
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LISEZMOI.md", LISEZMOI)
        z.writestr("journal.md", journal_markdown(resultats, noms_hyper, source, corrections))
        if corrections:
            z.writestr("corrections.csv", _csv(corrections))
        if linguiste:
            z.writestr("linguiste.csv", _csv(linguiste))
        # Écrit les réglages et les tables séparément pour chaque version.
        for version, res in resultats.items():
            z.writestr(f"reglages_{version}.json", json.dumps(reglages_dict(res.reglages), ensure_ascii=False, indent=2))
            fichiers = {
                "enonces": tables.table_enonces(res),
                "relations": tables.table_relations(res),
                "zones": tables.table_zones(res),
                "domaines": tables.table_domaines(res),
                "synthese_domaines": tables.synthese_domaines(res),
                "relations_domaines": tables.table_relations_domaines(res),
                "matrice_relations_domaines": tables.matrice_relations_domaines(res),
                "hyperdomaines": tables.table_hyperdomaines(res, noms_hyper.get(version)),
                "regroupements": tables.table_regroupements(res),
            }
            # N'inclut les tables facultatives que si les données correspondantes existent.
            if res.corpus.anaphores:
                fichiers["anaphores"] = tables.table_anaphores(res)
            if version == "1969":
                fichiers["chaines"] = tables.table_chaines(res)
            for nom, lignes in fichiers.items():
                z.writestr(f"{version}/{nom}.csv", _csv(lignes))
    return tampon.getvalue()
