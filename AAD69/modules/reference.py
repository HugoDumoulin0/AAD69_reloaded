"""Lecture de fichiers CSV contenant des énoncés et des relations.

Ce module convertit des tableaux CSV en objets du programme.
Il sert aussi bien à charger des tableaux de référence qu'à lire les fichiers
fournis par l'utilisateur dans l'interface.

Format des tableaux :
- énoncés : indice, F, D1, N1, V, ADV, PP, D2, N2_3 [, discours] ;
- relations : E_i, operateur, E_j [, operateur_livre, colonne_livre]
  [, saturation (oui / vide), variante (0, 1, 2…)].

Les fonctions dont le nom se termine par `_texte` lisent ces mêmes colonnes
depuis une chaîne de caractères plutôt que depuis un fichier.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .modele import CASES, Enonce, Graphe, RelationBinaire


def _enonces(f, discours: str) -> list[Enonce]:
    """Lit les lignes CSV d'énoncés et les convertit en objets `Enonce`."""
    # Le discours indiqué dans le fichier a priorité ; sinon on utilise la valeur fournie.
    return [
        Enonce(indice=int(ligne["indice"]), discours=ligne.get("discours") or discours,
               **{c: ligne[c] for c in CASES})
        for ligne in csv.DictReader(f)
    ]


def _oui(valeur) -> bool:
    """Convertit les formes courantes de « oui » en valeur booléenne."""
    return (valeur or "").strip().lower() in {"oui", "1", "true", "vrai", "x"}


def _relations(f) -> list[RelationBinaire]:
    """Lit les lignes CSV de relations et les convertit en objets `RelationBinaire`.

    Les colonnes `saturation` et `variante` sont facultatives ; si elles
    manquent, la relation reçoit ses valeurs par défaut.
    """
    # Convertit aussi les colonnes facultatives lorsqu'elles sont présentes.
    return [RelationBinaire(int(ligne["E_i"]), ligne["operateur"], int(ligne["E_j"]),
                            saturation=_oui(ligne.get("saturation")),
                            variante=int(ligne.get("variante") or 0))
            for ligne in csv.DictReader(f)]


def charger_enonces(chemin: str | Path, discours: str = "") -> list[Enonce]:
    """Charge les énoncés depuis un fichier CSV."""
    # `newline=""` laisse le module csv gérer correctement les fins de ligne.
    with open(chemin, encoding="utf-8", newline="") as f:
        return _enonces(f, discours)


def charger_relations(chemin: str | Path) -> list[RelationBinaire]:
    """Charge les relations depuis un fichier CSV."""
    with open(chemin, encoding="utf-8", newline="") as f:
        return _relations(f)


def charger_enonces_texte(texte: str, discours: str = "") -> list[Enonce]:
    """Lit des énoncés CSV depuis du texte, par exemple un fichier déposé dans l'interface."""
    # StringIO permet de réutiliser le même lecteur CSV que pour un fichier.
    return _enonces(io.StringIO(texte), discours)


def charger_relations_texte(texte: str) -> list[RelationBinaire]:
    """Lit des relations CSV depuis du texte, par exemple un fichier déposé dans l'interface."""
    return _relations(io.StringIO(texte))


def charger_graphe(chemin_enonces: str | Path, chemin_relations: str | Path, discours: str = "") -> Graphe:
    """Charge deux fichiers CSV et construit le graphe correspondant.

    Le premier fichier fournit les énoncés ; le second fournit les relations
    qui les relient.
    """
    graphe = Graphe()
    # Ajoute d'abord tous les énoncés, puis les relations qui les référencent.
    for e in charger_enonces(chemin_enonces, discours):
        graphe.ajouter_enonce(e)
    for r in charger_relations(chemin_relations):
        graphe.ajouter_relation(r)
    return graphe
