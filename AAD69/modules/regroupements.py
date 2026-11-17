"""Étape 5 bis — Regroupement hiérarchique de relations à partir des zones de similitude.

NB : ni le livre (1969) ni le manuel (1972) ne définissent de regroupement hiérarchique :
complément personnel, construit sur deux notions du manuel — la proximité entre deux
relations, « estimée par la comparaison du contenu des cases des huit groupes
morpho-syntaxiques des deux énoncés «gauches» (A) et (C) d'une part, et des deux
énoncés «droits» (B) et (D) d'autre part » (1972, p. 44), ici le score de zone de
l'étape 4 (somme des deux proximités) ; et la borne pa = 28 (p. 122), dont le double,
S_MAX = 56, sert d'échelle de distance.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from itertools import combinations

from .comparaison import POIDS_1969, Poids, zones_de_similitude
from .domaines1972 import Domaine1972
from .modele import Enonce, RelationBinaire

S_MAX = 56
LIENS = ("simple", "moyen", "complet")


def score_maximum(poids: Poids = POIDS_1969, regle: str = "somme") -> float:
    """Renvoie le score maximal qu'une zone peut atteindre avec ces réglages.

    Le score d'une zone additionne deux proximités si `regle` vaut `somme` ;
    avec `moyenne`, il correspond à une seule proximité maximale.
    """
    # Pour chaque case, retient le plus grand poids applicable à une égalité.
    p_max = sum(
        max(poids.identiques[c], poids.vides.get(c) or 0, poids.copules if c == "V" else 0)
        for c in poids.identiques
    )
    return 2 * p_max if regle == "somme" else p_max


@dataclass(frozen=True)
class Fusion:
    """Étape de regroupement de deux groupes dans le dendrogramme.

    `a` et `b` identifient les groupes réunis ; `distance` indique leur
    écart ; `nouveau` identifie le groupe créé ; `taille` compte ses relations.
    """

    a: int
    b: int
    distance: float
    nouveau: int
    taille: int


@dataclass
class Dendrogramme:
    """Historique des fusions successives entre relations.

    `feuilles` contient les relations de départ et `fusions` décrit les
    regroupements construits par la classification hiérarchique.
    """

    feuilles: list[RelationBinaire]
    fusions: list[Fusion] = field(default_factory=list)
    s_max: float = S_MAX

    def groupes(self, seuil: float) -> list[list[RelationBinaire]]:
        """Coupe le dendrogramme au seuil et renvoie les groupes obtenus.

        Les fusions de distance strictement inférieure au seuil sont conservées.
        Les groupes réduits à une seule relation ne sont pas renvoyés.
        """
        # Chaque feuille et chaque fusion reçoit un identifiant de groupe.
        parent = list(range(len(self.feuilles) + len(self.fusions)))

        def racine(i: int) -> int:
            # Remonte au groupe final, en raccourcissant le chemin à chaque étape.
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        # Une fusion sous le seuil relie ses deux groupes au groupe nouvellement créé.
        for fusion in self.fusions:
            if fusion.distance < seuil:
                parent[racine(fusion.a)] = fusion.nouveau
                parent[racine(fusion.b)] = fusion.nouveau

        # Regroupe les relations de départ selon leur groupe final.
        par_racine: dict[int, list[RelationBinaire]] = {}
        for i, relation in enumerate(self.feuilles):
            par_racine.setdefault(racine(i), []).append(relation)
        # Les groupes d'une seule relation ne constituent pas un regroupement.
        groupes = [
            sorted(g, key=lambda r: (r.gauche, r.droit))
            for g in par_racine.values()
            if len(g) > 1
        ]
        return sorted(groupes, key=lambda g: (g[0].operateur, g[0].gauche, g[0].droit))


def similarites(
    enonces: list[Enonce],
    relations: list[RelationBinaire],
    poids: Poids = POIDS_1969,
    intermediaires: bool = False,
    annulation: bool = True,
    operateurs_exclus: set[str] = frozenset({"phi_alpha"}),
    regle: str = "somme",
) -> dict[tuple[RelationBinaire, RelationBinaire], float]:
    """Calcule le score de similarité de chaque paire de relations comparable.

    Réutilise les zones de similitude de l'étape 4. La borne est abaissée à
    moins l'infini pour conserver les paires comparables même si leur score
    est inférieur au seuil habituel.
    """
    zones = zones_de_similitude(
        enonces,
        relations,
        poids,
        borne=-math.inf,
        regle=regle,
        intermediaires=intermediaires,
        annulation=annulation,
        operateurs_exclus=operateurs_exclus,
    )
    resultat = {}
    for zone in zones:
        # Reconstitue les deux relations comparées par la zone et stocke leur score.
        a = RelationBinaire(zone.gauche[0], zone.operateur, zone.droite[0])
        b = RelationBinaire(zone.gauche[1], zone.operateur, zone.droite[1])
        resultat[(a, b)] = resultat[(b, a)] = zone.score
    return resultat


def cah(
    relations: list[RelationBinaire],
    sim: dict[tuple[RelationBinaire, RelationBinaire], float],
    lien: str = "simple",
    s_max: float = S_MAX,
) -> Dendrogramme:
    """Construit un dendrogramme par classification ascendante hiérarchique.

    À chaque étape, fusionne les deux groupes les plus proches. Le paramètre
    `lien` choisit comment calculer la distance entre groupes : minimum
    (`simple`), moyenne (`moyen`) ou maximum (`complet`). Les relations sans
    score de similarité ne contribuent pas à cette distance.
    """
    if lien not in LIENS:
        raise ValueError(f"lien doit valoir {LIENS}")

    # Les relations sont dédupliquées et triées pour stabiliser les identifiants.
    feuilles = sorted(set(relations), key=lambda r: (r.operateur, r.gauche, r.droit))
    actifs = {i: [i] for i in range(len(feuilles))}
    stats: dict[tuple[int, int], list[float]] = {}
    # Initialise la distance des paires comparables : distance = score maximal - similarité.
    for i, j in combinations(range(len(feuilles)), 2):
        a, b = feuilles[i], feuilles[j]
        if a.operateur == b.operateur and (a, b) in sim:
            distance = s_max - sim[(a, b)]
            stats[(i, j)] = [distance, distance, distance, 1]

    def valeur(st: list[float]) -> float:
        # Les statistiques conservent min, max, somme et nombre de paires comparées.
        minimum, maximum, somme, nombre = st
        if lien == "simple":
            return minimum
        if lien == "complet":
            return maximum
        return somme / nombre

    tas = [(valeur(st), i, j) for (i, j), st in stats.items()]
    heapq.heapify(tas)
    dendrogramme = Dendrogramme(feuilles, s_max=s_max)
    suivant = len(feuilles)

    # Le tas fournit à chaque tour la fusion candidate de plus petite distance.
    while tas:
        distance, i, j = heapq.heappop(tas)
        # Ignore les entrées périmées laissées dans le tas après une fusion.
        if i not in actifs or j not in actifs or (i, j) not in stats:
            continue
        if valeur(stats[(i, j)]) != distance:
            continue

        # Crée un nouvel identifiant et rassemble les membres des deux groupes.
        nouveau = suivant
        suivant += 1
        membres = actifs.pop(i) + actifs.pop(j)
        dendrogramme.fusions.append(Fusion(i, j, distance, nouveau, len(membres)))

        # Met à jour la distance entre le nouveau groupe et chaque groupe restant.
        for k in list(actifs):
            st_i = stats.pop((min(i, k), max(i, k)), None)
            st_j = stats.pop((min(j, k), max(j, k)), None)
            if st_i is None and st_j is None:
                continue
            if st_i is None or st_j is None:
                st = list(st_i or st_j)
            else:
                st = [
                    min(st_i[0], st_j[0]),
                    max(st_i[1], st_j[1]),
                    st_i[2] + st_j[2],
                    st_i[3] + st_j[3],
                ]
            stats[(min(k, nouveau), max(k, nouveau))] = st
            heapq.heappush(tas, (valeur(st), min(k, nouveau), max(k, nouveau)))

        stats.pop((i, j), None)
        actifs[nouveau] = membres

    return dendrogramme


def seuil_de_la_borne(borne: float, s_max: float = S_MAX) -> float:
    """Convertit la borne de similarité en seuil de distance pour couper l'arbre.

    La conversion conserve la condition stricte des zones : distance inférieure
    au seuil équivaut à un score supérieur à la borne (p. 97, annexe III p. 123).
    """
    # La distance est calculée comme le score maximal moins le score observé.
    return s_max - borne


def borne_valide(valeur, defaut: float, s_max: float = S_MAX) -> float:
    """Convertit une valeur en borne valide, ou renvoie la valeur par défaut.

    Une borne doit être un nombre fini compris entre zéro et `s_max`. Le
    défaut est lui-même ramené à cet intervalle avant d'être utilisé.
    """
    # Protège aussi le défaut si sa valeur dépasse l'intervalle autorisé.
    defaut_valide = min(max(defaut, 0), s_max)
    try:
        borne = float(valeur)
    except (TypeError, ValueError):
        return defaut_valide
    # Rejette les nombres infinis, NaN et les valeurs hors intervalle.
    return borne if math.isfinite(borne) and 0 <= borne <= s_max else defaut_valide


def en_domaines(groupes: list[list[RelationBinaire]]) -> dict[str, Domaine1972]:
    """Convertit les groupes de relations en domaines numérotés G1, G2, etc."""
    # Le premier élément donne le connecteur commun au groupe.
    return {
        f"G{i}": Domaine1972(groupe[0].operateur, tuple(groupe))
        for i, groupe in enumerate(groupes, 1)
    }


@dataclass
class Accord:
    """Compte les paires de relations communes ou propres aux deux regroupements."""

    communes: int
    seulement_reference: int
    seulement_autre: int

    @property
    def precision(self) -> float:
        """Part des paires de l'autre regroupement qui sont aussi dans la référence."""
        total = self.communes + self.seulement_autre
        return self.communes / total if total else 1.0

    @property
    def rappel(self) -> float:
        """Part des paires de référence retrouvées dans l'autre regroupement."""
        total = self.communes + self.seulement_reference
        return self.communes / total if total else 1.0

    @property
    def f1(self) -> float:
        """Moyenne harmonique de la précision et du rappel."""
        precision, rappel = self.precision, self.rappel
        return 2 * precision * rappel / (precision + rappel) if precision + rappel else 0.0


def paires(groupes: list[set[RelationBinaire]]) -> set[frozenset[RelationBinaire]]:
    """Liste chaque paire de relations réunies dans un même groupe.

    Le résultat permet de comparer deux regroupements même si leurs groupes
    portent des noms ou des numéros différents.
    """
    return {
        frozenset((a, b))
        for groupe in groupes
        for a, b in combinations(sorted(groupe, key=lambda r: (r.gauche, r.droit, r.operateur)), 2)
    }


def accord(
    reference: list[set[RelationBinaire]],
    autre: list[set[RelationBinaire]],
) -> Accord:
    """Compare deux regroupements en comptant leurs paires communes et différentes."""
    # Compare les relations paire par paire, indépendamment du nom des groupes.
    p_reference, p_autre = paires(reference), paires(autre)
    return Accord(
        len(p_reference & p_autre),
        len(p_reference - p_autre),
        len(p_autre - p_reference),
    )


def relations_des_domaines(domaines: dict) -> list[set[RelationBinaire]]:
    """Extrait les relations représentées par chaque domaine 1969 ou 1972.

    Les domaines 1972 contiennent directement leurs relations. Pour les
    domaines 1969, celles-ci sont reconstruites à partir des chaînes.
    """
    sortie = []
    for domaine in domaines.values():
        # Les domaines 1972 fournissent déjà la liste des relations.
        if hasattr(domaine, "relations"):
            sortie.append(set(domaine.relations))
            continue
        # Dans une chaîne 1969, chaque opérateur relie les couples voisins.
        relations = set()
        for chaine in domaine.chaines:
            for k, operateur in enumerate(chaine.operateurs):
                (g1, g2), (d1, d2) = chaine.couples[k], chaine.couples[k + 1]
                relations.add(RelationBinaire(g1, operateur, d1))
                relations.add(RelationBinaire(g2, operateur, d2))
        sortie.append(relations)
    return sortie


@dataclass
class Regroupement:
    """Résultat complet d'un regroupement hiérarchique.

    Contient les réglages utilisés, le dendrogramme, les groupes obtenus et
    les domaines correspondants. `accord_aad` contient la comparaison à des
    domaines de référence lorsqu'elle a été demandée.
    """

    lien: str
    borne: float
    s_max: float
    dendrogramme: Dendrogramme
    groupes: list[list[RelationBinaire]]
    domaines: dict[str, Domaine1972]
    accord_aad: Accord | None = None


def regrouper(
    enonces: list[Enonce],
    relations: list[RelationBinaire],
    lien: str = "simple",
    borne: float = 28,
    poids: Poids = POIDS_1969,
    intermediaires: bool = False,
    annulation: bool = True,
    operateurs_exclus: set[str] = frozenset({"phi_alpha"}),
    domaines_aad: dict | None = None,
    regle: str = "somme",
) -> Regroupement:
    """Calcule les groupes hiérarchiques et, si demandé, les compare à une référence.

    `domaines_aad` contient les domaines de référence. Pour que la comparaison
    soit cohérente, ils doivent avoir été produits avec la même borne.
    """
    # Les relations exclues ne participent ni aux similarités ni au dendrogramme.
    comparables = [r for r in relations if r.operateur not in operateurs_exclus]
    s_max = score_maximum(poids, regle)
    # Calcule les scores, construit l'arbre, puis le coupe à la borne choisie.
    sim = similarites(
        enonces, comparables, poids, intermediaires, annulation, operateurs_exclus, regle
    )
    dendrogramme = cah(comparables, sim, lien, s_max)
    groupes = dendrogramme.groupes(seuil_de_la_borne(borne, s_max))
    resultat = Regroupement(lien, borne, s_max, dendrogramme, groupes, en_domaines(groupes))
    if domaines_aad is not None:
        # Compare les paires de relations des domaines de référence à celles obtenues.
        resultat.accord_aad = accord(relations_des_domaines(domaines_aad), [set(g) for g in groupes])
    return resultat
