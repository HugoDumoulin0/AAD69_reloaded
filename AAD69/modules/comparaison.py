"""Étape 4 — Comparaison des énoncés et zones de similitude.

Commun aux versions 1969 et 1972 : une « zone de similitude » (1969) est ce que le
manuel de 1972 appelle un « quadruplet » (2 relations = 4 énoncés). Les deux versions
ne divergent qu'à l'étape 5 (chaînes et domaines).

Vocabulaire
-----------
- vecteur π : pour deux énoncés, 1 par case identique, 0 par case différente (Alg. 1, p. 89) ;
- proximité p : somme des poids des cases identiques (p. 92) ;
- proximité P : p corrigée par les énoncés intermédiaires (Alg. 2, p. 93) ;
- zone de similitude : deux relations de même opérateur, Ei ψ Ek et Ej ψ Em, dont
  les énoncés gauches (Ei, Ej) et droits (Ek, Em) sont assez proches (p. 95-97).

Décisions (journal des décisions, 10 octobre 2026)
---------------------------------------------------
D1. Règle de la zone : SOMME P1 + P2 > borne par défaut.
    Le chapitre II (p. 97) écrit la moyenne (P1 + P2) / 2 > pα, mais l'annexe III
    (p. 123) applique la somme : 13 + 20 = 33 > 28. Seule la somme reproduit l'exemple
    du livre. La moyenne reste disponible : regle="moyenne".
D2. Poids : ceux de la p. 92, appliqués tels quels. Ils donnent p(33, 59) = 13 et
    p(33, 88) = 13, là où l'annexe III écrit 12. Les 7 autres valeurs du livre sont
    retrouvées. L'écart ne change aucune zone (33 et 32 > 28 dans les deux cas).
D3. Alg. 2 (énoncés intermédiaires) : programmé mais désactivé par défaut
    (intermediaires=False), car l'annexe III ne l'applique pas (« les opérations ayant
    été effectuées à la main, on a négligé d'appliquer les algorithmes Alg. 1 et Alg. 2 »).
D4. Borne par défaut : 28, valeur de l'annexe III (« la demi-somme des poids maximum
    de deux couples d'énoncés »).
D5. « * » dans PP (complément direct) compte comme un terme identique, poids 3.
    Nécessaire pour retrouver p(32, 58) = 20.
D6. Annulation de la différence répétée (Remarque 1, p. 97) : activée par défaut, car
    elle fait partie d'Alg. 3 et n'est pas signalée comme omise dans l'annexe III.
D7. On ne compare que des relations venant de DISCOURS DIFFÉRENTS : c'est la comparaison
    entre surfaces discursives qui fait apparaître les substitutions.
D8. φα (relation d'ordre) ne forme pas de zone (operateurs_exclus).
Journal complet : docs/decisions.md
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations

from .modele import CASES, VIDE, Enonce, RelationBinaire

COPULES = {"ε", "E"}


@dataclass(frozen=True)
class Poids:
    """Poids accordés aux cases identiques lors de la comparaison de deux énoncés.

    `identiques` donne les points d'une même valeur non vide dans chaque case.
    `vides` donne les points de deux cases vides ; `None` signifie qu'elles
    ne rapportent aucun point. `copules` est le poids particulier de deux
    copules identiques dans la case V. Les valeurs par défaut suivent
    provisoirement Pêcheux (1969, p. 92, note 1).
    """

    identiques: dict = field(default_factory=lambda: {
        "F": 3, "D1": 2, "N1": 5, "V": 5, "ADV": 3, "PP": 3, "D2": 2, "N2_3": 5})
    vides: dict = field(default_factory=lambda: {
        "F": None, "D1": 1, "N1": None, "V": None, "ADV": 1, "PP": 1, "D2": 1, "N2_3": 1})
    copules: int = 2

    def maximum(self) -> int:
        """Renvoie la somme des poids prévus pour huit cases identiques."""
        # Additionne les huit poids : cela donne le score maximal théorique.
        return sum(self.identiques.values())


POIDS_1969 = Poids()


def vecteur_pi(ei: Enonce, ej: Enonce) -> tuple[int, ...]:
    """Compare les huit cases de deux énoncés, position par position.

    Renvoie un vecteur de huit valeurs : `1` quand les cases sont identiques,
    `0` quand elles diffèrent. L'ordre des valeurs est celui de `CASES`.
    C'est le vecteur π de l'algorithme 1 (p. 89).
    """
    # zip conserve l'ordre des cases ; int transforme chaque comparaison en 0 ou 1.
    return tuple(int(a == b) for a, b in zip(ei.cases(), ej.cases()))


def proximite(ei: Enonce, ej: Enonce, poids: Poids = POIDS_1969) -> int:
    """Calcule la proximité `p` de deux énoncés à partir de leurs cases identiques.

    Pour chaque case identique, ajoute le poids défini dans `poids`. Deux
    cases vides utilisent les poids de `vides` ; deux copules identiques en V
    utilisent le poids spécial `copules`. Des valeurs différentes ne rapportent
    aucun point. La somme correspond à la proximité `p` de la page 92.
    """
    total = 0
    for case, a, b in zip(CASES, ei.cases(), ej.cases()):
        # Une différence entre les deux valeurs ne contribue pas au score.
        if a != b:
            continue
        # Les cases vides et les copules ont des poids particuliers.
        if a == VIDE:
            total += poids.vides.get(case) or 0
        elif case == "V" and a in COPULES:
            total += poids.copules
        else:
            total += poids.identiques[case]
    return total


def proximite_corrigee(ei: Enonce, ej: Enonce, ensemble: list[Enonce], poids: Poids = POIDS_1969) -> float:
    """Calcule la proximité corrigée `P` en tenant compte des énoncés intermédiaires.

    Pour chaque autre énoncé `Ex` de `ensemble`, calcule la moyenne de
    `p(ei, Ex)` et `p(Ex, ej)`. Renvoie la plus grande valeur entre la
    proximité directe `p(ei, ej)` et toutes ces moyennes. C'est la lecture
    retenue de l'algorithme 2 (p. 93-94).
    """
    p1 = proximite(ei, ej, poids)
    # La proximité directe reste le minimum : un intermédiaire ne peut que l'augmenter.
    meilleure = p1
    for ex in ensemble:
        # ei et ej ne sont pas des « autres » énoncés intermédiaires.
        if ex.indice in (ei.indice, ej.indice):
            continue
        # Ex relie ei à ej ; on retient le meilleur chemin indirect rencontré.
        moyenne = (proximite(ei, ex, poids) + proximite(ex, ej, poids)) / 2
        meilleure = max(meilleure, moyenne)
    return meilleure


def annuler_difference_repetee(gi: Enonce, gj: Enonce, dk: Enonce, dm: Enonce) -> tuple[Enonce, Enonce]:
    """Applique la remarque 1 (p. 97) à la paire d'énoncés de droite.

    Une différence de valeurs déjà présente dans `gi` et `gj` ne doit pas
    être comptée une seconde fois dans `dk` et `dm`. Pour chaque opposition
    non vide déjà observée à gauche, les mêmes valeurs dans les énoncés de
    droite sont remplacées par `x1`. Renvoie les énoncés de droite modifiés ;
    si aucune opposition ne correspond, renvoie les originaux.
    """
    # Repère les oppositions déjà présentes entre les deux énoncés de gauche.
    oppositions = {(a, b) for a, b in zip(gi.cases(), gj.cases()) if a != b and VIDE not in (a, b)}
    if not oppositions:
        return dk, dm
    nouv_k, nouv_m = {}, {}
    for case, a, b in zip(CASES, dk.cases(), dm.cases()):
        # Si la même opposition réapparaît à droite, on la neutralise dans les deux énoncés.
        if (a, b) in oppositions:
            nouv_k[case] = nouv_m[case] = "x1"
    if not nouv_k:
        return dk, dm
    return replace(dk, **nouv_k), replace(dm, **nouv_m)


@dataclass(frozen=True)
class Zone:
    """Zone de similitude formée de deux relations ayant le même opérateur.

    `gauche` contient les indices des deux énoncés dominants ; `droite`,
    ceux des deux énoncés dépendants. `operateur` est leur opérateur commun.
    `P1` et `P2` sont les proximités corrigées des deux paires d'énoncés ;
    `score` est leur somme ou leur moyenne selon la règle choisie. Le manuel
    de 1972 appelle cette structure un « quadruplet ».
    """

    gauche: tuple[int, int]   # (Ei, Ej)
    operateur: str            # ψ
    droite: tuple[int, int]   # (Ek, Em)
    P1: float
    P2: float
    score: float


def zones_de_similitude(enonces: list[Enonce], relations: list[RelationBinaire], poids: Poids = POIDS_1969,
                        borne: float = 28, regle: str = "somme", intermediaires: bool = False,
                        annulation: bool = True, operateurs_exclus: set[str] = frozenset({"phi_alpha"})
                        ) -> list[Zone]:
    """Repère les zones de similitude parmi les relations du corpus.

    Deux relations peuvent former une zone si elles ont le même opérateur,
    si elles proviennent de discours différents et si leurs deux paires
    d'énoncés atteignent la borne choisie. La fonction renvoie une `Zone`
    par paire qui satisfait ces conditions.

    `regle` vaut `somme` ou `moyenne` pour combiner les deux proximités ;
    la comparaison à `borne` est stricte (`score > borne`). Avec
    `intermediaires=True`, utilise l'algorithme 2 pour calculer les proximités.
    Avec `annulation=True`, applique la remarque 1 à la paire d'énoncés de
    droite. `operateurs_exclus` liste les opérateurs ignorés ; par défaut,
    φα est exclu parce qu'il marque l'ordre, pas une dépendance.

    Les choix et valeurs par défaut sont documentés par les décisions D1 à D8
    en tête du module.
    """
    if regle not in ("somme", "moyenne"):
        raise ValueError("regle doit valoir 'somme' ou 'moyenne'")
    # Permet de retrouver rapidement chaque énoncé à partir de son indice.
    par_indice = {e.indice: e for e in enonces}

    def P(a: Enonce, b: Enonce) -> float:
        """Choisit la proximité directe ou sa correction par les intermédiaires."""
        return proximite_corrigee(a, b, enonces, poids) if intermediaires else proximite(a, b, poids)

    zones = []
    # Chaque paire de relations est examinée une seule fois.
    for bx, by in combinations(relations, 2):
        # Une zone exige le même opérateur, qui ne doit pas être exclu.
        if bx.operateur != by.operateur or bx.operateur in operateurs_exclus:
            continue
        # Les relations ont la forme gi → dk et gj → dm.
        gi, gj = par_indice[bx.gauche], par_indice[by.gauche]
        dk, dm = par_indice[bx.droit], par_indice[by.droit]
        # D7 : ignorer les paires dont les énoncés de gauche viennent du même discours.
        if gi.discours and gi.discours == gj.discours:
            continue
        # Compare d'abord les énoncés de gauche.
        p1 = P(gi, gj)
        if annulation:
            dk, dm = annuler_difference_repetee(gi, gj, dk, dm)
        # Puis compare les énoncés de droite, après l'annulation éventuelle.
        p2 = P(dk, dm)
        # La zone est retenue uniquement si son score dépasse strictement la borne.
        score = p1 + p2 if regle == "somme" else (p1 + p2) / 2
        if score > borne:
            zones.append(Zone((bx.gauche, by.gauche), bx.operateur, (bx.droit, by.droit), p1, p2, score))
    return zones
