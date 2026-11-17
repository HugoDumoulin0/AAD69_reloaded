"""Étape 7 — Hyperdomaines (Pêcheux 1969, annexe III, p. 126).

Ce que dit le livre
-------------------
« Les domaines ont été ordonnés de manière à ce que les inclusions et intersections (⊃, ⊂, ∩)
soient regroupées : on aboutit ainsi à des regroupements de domaines (ou hyperdomaines)
caractérisés par le fait que tous les domaines d'un hyperdomaine ont au moins une origine
commune. » (p. 126) Exemple : 29 domaines (p. 125) -> 10 hyperdomaines (p. 126), nommés
par l'analyste (« naissance », « réception de l'ordre », « combat »…). Certains
hyperdomaines n'ont qu'un domaine (31, 51, 71, 91, p. 126).

Vocabulaire
-----------
- deux domaines se RECOUPENT s'ils ont au moins une origine en commun, c'est-à-dire s'ils
  sont reliés par ⊕, ⊃, ⊂ ou ∩ (1969), ou par IDORG, INCLU ou INTER (1972) ;
- un HYPERDOMAINE est un groupe de domaines reliés de proche en proche par ce recoupement.

Notes
---------------------------------------------------
H1. Regroupement de PROCHE EN PROCHE (composantes connexes) : si A recoupe B et B recoupe C,
    A, B et C forment un seul hyperdomaine. Le découpage est ainsi unique. Pour chaque groupe,
    on calcule en plus l'origine commune à TOUS ses domaines (`origine_commune`) : si elle est
    vide, la lecture stricte du texte (« au moins une origine commune » à tous) ne serait pas
    vérifiée, et on le voit.
H2. Les hyperdomaines sont une notion du livre (1969). Le manuel de 1972 n'en parle pas
    (le mot n'y apparaît pas) ; pour la sortie 1972, on les calcule quand même, marqués
    « extension, absente du manuel ».
H3. Le programme NUMÉROTE les hyperdomaines (ordre d'apparition des domaines) ; il ne les
    NOMME pas. Le nom est une interprétation de l'analyste (p. 126 : « on peut attribuer
    une dénomination indiquant leur fonction dans le discours »).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hyperdomaine:
    """Groupe de domaines qui se recoupent directement ou indirectement.

    `numero` identifie le groupe, `domaines` en donne les noms et
    `origine_commune` contient les origines présentes dans tous ses domaines.
    Cette dernière valeur peut être vide si le lien entre domaines est indirect.
    """

    numero: int
    domaines: tuple[str, ...]
    origine_commune: set[int]   # origines communes à TOUS les domaines du groupe (peut être vide)


def hyperdomaines(origines_par_domaine: dict[str, set[int]]) -> list[Hyperdomaine]:
    """Regroupe les domaines qui partagent des origines, directement ou indirectement.

    Deux domaines sont reliés s'ils ont au moins une origine en commun.
    La relation est ensuite étendue de proche en proche : si A recoupe B
    et B recoupe C, les trois domaines forment un hyperdomaine (H1).
    Chaque hyperdomaine reçoit un numéro et l'intersection de toutes les
    origines de ses domaines est conservée.
    """
    # Garder l'ordre d'entrée permet de numéroter les hyperdomaines de façon stable (H3).
    noms = list(origines_par_domaine)
    parent = {n: n for n in noms}

    def racine(n):
        # Retrouve le représentant du groupe et raccourcit le chemin parcouru.
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    # Relie deux domaines dès qu'ils partagent une origine.
    for i, a in enumerate(noms):
        for b in noms[i + 1:]:
            if origines_par_domaine[a] & origines_par_domaine[b]:
                parent[racine(b)] = racine(a)

    # Rassemble les domaines ayant le même représentant en conservant leur ordre.
    groupes: dict[str, list[str]] = {}
    for n in noms:  # l'ordre des domaines donne l'ordre des groupes (H3)
        groupes.setdefault(racine(n), []).append(n)

    resultat = []
    for numero, membres in enumerate(groupes.values(), 1):
        # Calcule les origines qui appartiennent à chacun des domaines du groupe.
        commune = set.intersection(*(set(origines_par_domaine[m]) for m in membres))
        resultat.append(Hyperdomaine(numero, tuple(membres), commune))
    return resultat
