"""Étape 5b — Domaines par transitivité (version 1972, Haroche & Pêcheux, § 3.22, p. 44-45).

Ce que dit le manuel
--------------------
« deux relations R1 et R2 (ou deux chaînes de relations) appartiennent au même domaine si
la proximité entre R1 et R2 satisfait à la condition imposée (c'est-à-dire si R1 et R2
appartiennent à un même quadruplet), ou s'il existe une relation R3 (ou chaîne de relations
de même longueur) telle que les proximités entre R1 et R3 d'une part, R2 et R3 d'autre part,
satisfont à cette même condition (principe de transitivité). » (1972, p. 45)


Un quadruplet (1972) = une zone de similitude (1969) : on réutilise zones_de_similitude
(le programme compare les relations de chaque discours à celles des autres, retient les
couples de même connecteur, puis applique la borne : 1972, p. 44).

Note de lecture
---------------------------------------------------
T1. Transitivité COMPLÈTE : domaine = composante connexe du graphe dont les nœuds sont les
    relations et les arêtes les quadruplets (A~B, B~C, C~D -> un domaine). Le texte ne
    parle que d'un intermédiaire R3 ; pris à la lettre, le résultat dépendrait de l'ordre
    de traitement. Le manuel parle de « principe de transitivité » (introduit au
    § 3.212, cf. p. 46) et attend de lui des rapprochements « non-évidents » du strict
    point de vue syntaxique (p. 46).
T2. On regroupe des RELATIONS, pas des chaînes : le tableau des domaines (p. 51) ne
    contient que des relations simples, une relation par ligne. Les chaînes restent
    propres à 1969 (étape 5a).
T3. Coefficient d'homogénéité (p. 45) : quadruplets effectivement formés / quadruplets
    théoriques. « Théorique » = ce qu'on obtiendrait si TOUTES les paires de relations
    comparées formaient un quadruplet, c'est-à-dire avaient le même connecteur ET
    passaient la borne ; les paires comparées sont celles de relations de discours
    différents (« le programme principal commence par comparer les relations binaires
    de chaque discours à celles de tous les autres discours », p. 44). Le coefficient
    vaut 1 si chaque paire comparable forme un quadruplet (homogénéité maximum,
    « cas où le coefficient serait égal à l'unité », p. 45). Les opérateurs exclus (φα)
    ne comptent pas au dénominateur : ils ne peuvent pas former de quadruplet.

"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .comparaison import POIDS_1969, Poids, Zone, zones_de_similitude
from .modele import Enonce, RelationBinaire


@dataclass(frozen=True)
class Domaine1972:
    """Domaine composé de relations partageant le même connecteur.

    Les relations sont réunies lorsqu'elles sont reliées directement ou
    indirectement par des quadruplets.
    """

    connecteur: str
    relations: tuple[RelationBinaire, ...]

    @property
    def gauches(self) -> set[int]:
        """Renvoie les indices des énoncés à gauche des relations du domaine.

        Ces énoncés-origines servent aux relations entre domaines (INCLU,
        IDORG, INTER, p. 50).
        """
        # On extrait l'énoncé de départ de chaque relation.
        return {r.gauche for r in self.relations}

    @property
    def droites(self) -> set[int]:
        """Renvoie les indices des énoncés à droite des relations du domaine."""
        # On extrait l'énoncé d'arrivée de chaque relation.
        return {r.droit for r in self.relations}


def relations_du_quadruplet(z: Zone) -> tuple[RelationBinaire, RelationBinaire]:
    """Convertit une zone de similitude en ses deux relations binaires.

    Pour une zone `(Ei/Ej) ψ (Ek/Em)`, les relations correspondantes sont
    `Ei ψ Ek` et `Ej ψ Em`.
    """
    # Chaque relation associe les indices d'un même côté gauche et droit.
    return (RelationBinaire(z.gauche[0], z.operateur, z.droite[0]),
            RelationBinaire(z.gauche[1], z.operateur, z.droite[1]))


def domaines_par_transitivite(quadruplets: list[Zone]) -> list[Domaine1972]:
    """Forme les domaines comme composantes connexes des relations.

    Deux relations reliées par un quadruplet appartiennent au même domaine.
    La transitivité étend ce regroupement : si A est liée à B et B à C,
    les trois relations sont dans le même domaine (T1).
    """
    parent: dict[RelationBinaire, RelationBinaire] = {}

    def racine(r):
        # Crée un groupe pour une relation jamais rencontrée.
        parent.setdefault(r, r)
        # Remonte jusqu'au représentant du groupe, en raccourcissant le chemin.
        while parent[r] != r:
            parent[r] = parent[parent[r]]
            r = parent[r]
        return r

    # Chaque quadruplet unit les deux relations qu'il met en correspondance.
    for z in quadruplets:
        a, b = relations_du_quadruplet(z)
        parent[racine(a)] = racine(b)

    # Rassemble les relations qui ont le même représentant de groupe.
    groupes: dict[RelationBinaire, list[RelationBinaire]] = {}
    for r in parent:
        groupes.setdefault(racine(r), []).append(r)

    # Trie les relations et les domaines pour obtenir un résultat stable.
    cle = lambda r: (r.gauche, r.droit)  # noqa: E731
    domaines = [Domaine1972(g[0].operateur, tuple(sorted(g, key=cle))) for g in groupes.values()]
    return sorted(domaines, key=lambda d: (d.connecteur, cle(d.relations[0])))


def domaines_1972(enonces: list[Enonce], relations: list[RelationBinaire], poids: Poids = POIDS_1969,
                  borne: float = 28, **options) -> list[Domaine1972]:
    """Construit les domaines de 1972 à partir des relations du corpus.

    Commence par repérer les quadruplets (zones de similitude), avec les
    réglages de comparaison fournis, puis regroupe les relations reliées par
    ces quadruplets en appliquant la transitivité.
    """
    # Les options sont transmises au calcul des zones (seuil, règle, etc.).
    return domaines_par_transitivite(zones_de_similitude(enonces, relations, poids, borne, **options))


def coefficient_homogeneite(enonces: list[Enonce], relations: list[RelationBinaire], quadruplets: list[Zone],
                            operateurs_exclus: set[str] = frozenset({"phi_alpha"})) -> float:
    """Calcule la part des quadruplets effectivement formés parmi les comparaisons possibles.

    Le dénominateur compte les paires de relations provenant de discours
    différents, en excluant les opérateurs indiqués. Le numérateur est le
    nombre de quadruplets trouvés. C'est le coefficient décrit p. 45 (T3).
    Si aucune paire n'est comparable, renvoie 0.
    """
    # Associe chaque indice d'énoncé à son discours pour filtrer les paires.
    discours = {e.indice: e.discours for e in enonces}
    # Les relations portant un opérateur exclu ne font pas partie du dénominateur.
    comparables = [r for r in relations if r.operateur not in operateurs_exclus]
    # Compte les paires dont les énoncés de gauche viennent de discours distincts.
    theorique = sum(1 for a, b in combinations(comparables, 2)
                    if not discours[a.gauche] or discours[a.gauche] != discours[b.gauche])
    # Évite une division par zéro lorsqu'il n'existe aucune paire comparable.
    return len(quadruplets) / theorique if theorique else 0.0
