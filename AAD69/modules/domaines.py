"""Étape 5a — Chaînes de similitude, catégories et domaines (version 1969).

Vocabulaire
-----------
- chaîne : suite de zones imbriquées ; la droite d'une zone est la gauche de la suivante.
  Exemple (p. 123) : (φ2, δ2) (31/57) (32/58) (33/59) = 2 zones, 3 couples ;
- groupe opérateur : la suite des opérateurs d'une chaîne, ici (φ2, δ2) ;
- séquence : une des deux « lignes » d'une chaîne, ici (31, 32, 33) et (57, 58, 59) ;
- catégorie : les chaînes de même groupe opérateur ;
- domaine : dans une catégorie, les chaînes homogènes entre elles (p. 104).

Notes de lecture
---------------------------------------------------
C1. Seules les chaînes MAXIMALES sont gardées. Quand la droite d'une zone est la gauche
    d'une autre zone, les deux s'enchaînent en UNE seule chaîne : la seconde ne commence
    pas une chaîne nouvelle, elle prolonge la première. Exemple (p. 123) : (31/57) φ2
    (32/58) et (32/58) δ2 (33/59) donnent une seule chaîne, (φ2, δ2)(31/57)(32/58)(33/59),
    et pas deux. C'est ce que fait l'annexe III (chaînes de 3 couples, p. 124).

C2. Homogénéité (Alg. 4, p. 100) : on compare la SOMME de deux proximités à la borne,
    pas la moyenne. Une proximité vaut au plus 28 : la moyenne de deux proximités ne peut
    donc jamais dépasser 28. Même incohérence et même choix qu'en D1.
    NB : le livre écrit les quatre valeurs en moyennes (P(I) = (P(E1, E3) + P(E5, E7))/2,
    etc., p. 100) ; la borne ps (p. 100) n'est jamais chiffrée dans le livre, la valeur
    28 par défaut reprend pa (annexe III, p. 122).
    
C3. Domaine = les chaînes d'une même catégorie reliées par un CHEMIN d'homogénéité
    (composante connexe), et non « toutes homogènes deux à deux ». Le livre dit « un
    ensemble de chaînes d'une même catégorie, tel que les chaînes soient homogènes
    entre elles » (p. 99 et 104) sans trancher entre les deux lectures ; l'annexe III
    tranche (p. 125) : le domaine (φ2, δ2) contient à la fois (5/31)(6/32)(7/33) et
    (85/98)(86/99)(88/100), qui n'ont AUCUNE séquence commune : elles ne sont pas
    homogènes directement, mais (5/31)(6/32)(7/33) partage (5, 6, 7) avec (5/85)(6/86)
    (7/88), qui partage (85, 86, 88) avec (85/98)(86/99)(88/100) : elles sont reliées
    en deux pas. D'où le « de proche en proche » du code. « Homogènes » se dit de deux
    façons (paramètre critere) :
    - "alg5" : même groupe opérateur + Alg. 4 positif sur toutes les paires de zones
      successives (chapitre II, p. 100-102) ;
    - "sequence_commune" : les deux chaînes partagent une séquence (analyse manuelle
      de l'annexe III : « deux chaînes sont homogènes si elles comportent une séquence
      commune », p. 124).
C4. Le livre admet que deux chaînes de catégories différentes peuvent être homogènes
    si leurs groupes opérateurs ne diffèrent que par un δ1 final : l'adjonction développe
    un énoncé sous forme métonymique (« le président » / « le président de la
    République », p. 102). Cette exception n'est pas programmée.
"""

from __future__ import annotations

from dataclasses import dataclass

from .comparaison import POIDS_1969, Poids, Zone, proximite
from .modele import Enonce


@dataclass(frozen=True)
class Chaine:
    """Une chaîne contient une suite de couples d’énoncés reliés par des opérateurs.

    Avec n opérateurs, elle contient n + 1 couples.
    Exemple : deux opérateurs relient trois couples successifs :
    (31/57), (32/58), (33/59).
    """

    operateurs: tuple[str, ...]
    couples: tuple[tuple[int, int], ...]

    def sequences(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        # Chaque couple contient un indice de chaque côté ; on rassemble les côtés séparément.
        return tuple(c[0] for c in self.couples), tuple(c[1] for c in self.couples)


def chaines_de_similitude(zones: list[Zone]) -> list[Chaine]:
    """Construit les chaînes en reliant les zones qui se suivent.

    Une zone peut prolonger une autre lorsque son couple de gauche correspond
    au couple de droite de la précédente. La fonction ne conserve que les
    chaînes maximales, c'est-à-dire celles qu'on ne peut plus prolonger (C1).
    L'ordre des deux énoncés d'un couple peut être inversé.
    """
    # On range chaque zone sous son couple gauche, dans les deux sens (31/57 = 57/31).
    suite: dict[tuple[int, int], list[tuple[str, tuple[int, int]]]] = {}
    for z in zones:
        suite.setdefault(z.gauche, []).append((z.operateur, z.droite))
        inverse = (z.gauche[1], z.gauche[0])
        suite.setdefault(inverse, []).append((z.operateur, (z.droite[1], z.droite[0])))

    droites = {z.droite for z in zones} | {(z.droite[1], z.droite[0]) for z in zones}
    resultat: list[Chaine] = []

    def prolonger(ops: tuple[str, ...], couples: tuple[tuple[int, int], ...]):
        # Cherche les zones qui commencent par le dernier couple de la chaîne.
        suivants = [(op, d) for op, d in suite.get(couples[-1], []) if d not in couples]
        if not suivants:
            # Aucun prolongement possible : la chaîne est complète et maximale.
            resultat.append(Chaine(ops, couples))
        for op, d in suivants:
            # Explore récursivement chaque prolongement possible.
            prolonger(ops + (op,), couples + (d,))

    for z in zones:
        # Une chaîne commence à gauche d'une zone qui n'est la droite d'aucune zone.
        if z.gauche not in droites:  # C1 : début de chaîne seulement
            prolonger((z.operateur,), (z.gauche, z.droite))
    return resultat


def par_categorie(chaines: list[Chaine]) -> dict[tuple[str, ...], list[Chaine]]:
    """Regroupe les chaînes selon leur suite d'opérateurs.

    La clé de chaque entrée est le groupe opérateur ; sa valeur contient les
    chaînes qui ont exactement ce même groupe.
    """
    # Le groupe opérateur sert de clé : seules les chaînes de même groupe sont réunies.
    categories: dict[tuple[str, ...], list[Chaine]] = {}
    for c in chaines:
        categories.setdefault(c.operateurs, []).append(c)
    return categories


def zones_homogenes(s_i, s_j, t_i, t_j, enonces: dict[int, Enonce], poids: Poids = POIDS_1969,
                    borne: float = 28, regle: str = "somme") -> bool:
    """Compare deux couples successifs de la chaîne C avec deux de la chaîne C'.

    Chaque couple contient deux énoncés. La fonction calcule quatre scores
    possibles en comparant les énoncés des deux chaînes de différentes façons.
    Les couples sont déclarés homogènes si au moins un score dépasse la borne.
    Par défaut, chaque score est la somme de deux proximités (décision C2).
    """
    # Décompose les deux couples de chaque chaîne en leurs quatre énoncés.
    (e1, e2), (e5, e6) = s_i, s_j
    (e3, e4), (e7, e8) = t_i, t_j

    def P(a, b):
        # Raccourci pour calculer la proximité entre deux énoncés par leur indice.
        return proximite(enonces[a], enonces[b], poids)

    # Calcule les quatre rapprochements possibles entre les côtés des deux chaînes.
    valeurs = [
        P(e1, e3) + P(e5, e7),   # P(I)
        P(e1, e4) + P(e5, e8),   # P(II)
        P(e2, e3) + P(e6, e7),   # P(III)
        P(e2, e4) + P(e6, e8),   # P(IV)
    ]
    if regle == "moyenne":
        # Variante facultative : transforme chaque somme en moyenne de deux proximités.
        valeurs = [v / 2 for v in valeurs]
    # Une seule comparaison au-dessus de la borne suffit pour rendre les couples homogènes.
    return any(v > borne for v in valeurs)


def homogenes(a: Chaine, b: Chaine, enonces: dict[int, Enonce], poids: Poids = POIDS_1969,
              borne: float = 28, regle: str = "somme") -> bool:
    """Indique si deux chaînes de même catégorie sont homogènes.

    Pour chaque paire de couples successifs des chaînes, applique le test
    `zones_homogenes`. Les chaînes sont homogènes si toutes ces comparaisons
    dépassent la borne (algorithme 5, p. 102).
    """
    # L'algorithme ne compare que des chaînes ayant la même suite d'opérateurs.
    if a.operateurs != b.operateurs:
        return False
    # Chaque paire de couples successifs doit satisfaire le test d'homogénéité.
    return all(
        zones_homogenes(a.couples[i], a.couples[i + 1], b.couples[i], b.couples[i + 1],
                        enonces, poids, borne, regle)
        for i in range(len(a.operateurs))
    )


def sequence_commune(a: Chaine, b: Chaine) -> bool:
    """Vérifie si deux chaînes de même catégorie partagent une séquence.

    Une séquence est la suite d'indices d'énoncés d'un côté des couples.
    Ce critère correspond à la comparaison manuelle de l'annexe III (p. 124).
    """
    # L'intersection porte sur les séquences des deux côtés, calculées par Chaine.sequences().
    return a.operateurs == b.operateurs and bool(set(a.sequences()) & set(b.sequences()))


@dataclass(frozen=True)
class Domaine:
    """Ensemble de chaînes reliées qui appartiennent à la même catégorie.

    `groupe` indique leur suite d'opérateurs ; `chaines` contient les chaînes
    du domaine ; `positions` rassemble les indices d'énoncés par rang dans
    les couples de ces chaînes.
    """

    groupe: tuple[str, ...]
    chaines: tuple[Chaine, ...]
    positions: tuple[set[int], ...]

    def enonces(self) -> set[int]:
        # Réunit les indices présents à toutes les positions du domaine.
        return set().union(*self.positions)


def domaines(chaines: list[Chaine], enonces: dict[int, Enonce], critere: str = "alg5",
             poids: Poids = POIDS_1969, borne: float = 28, regle: str = "somme") -> list[Domaine]:
    """Rassemble les chaînes reliées en domaines, catégorie par catégorie.

    Deux chaînes sont reliées selon le critère choisi : `alg5` applique le
    test d'homogénéité des algorithmes 4 et 5 ; `sequence_commune` vérifie
    qu'elles partagent une séquence. Les liens indirects sont suivis aussi :
    si A est reliée à B et B à C, les trois chaînes appartiennent au même
    domaine. Chaque domaine conserve les indices d'énoncés rangés par
    position dans les couples (C3).
    """
    if critere not in ("alg5", "sequence_commune"):
        raise ValueError("critere doit valoir 'alg5' ou 'sequence_commune'")

    def lien(a, b):
        # Choisit le test qui détermine si deux chaînes sont reliées.
        if critere == "alg5":
            return homogenes(a, b, enonces, poids, borne, regle)
        return sequence_commune(a, b)

    resultat = []
    # Les domaines sont construits séparément à l'intérieur de chaque catégorie.
    for groupe, membres in par_categorie(chaines).items():
        restants = list(range(len(membres)))
        while restants:
            # Parcours en profondeur : collecte une chaîne et toutes celles qui lui sont reliées.
            composante, pile = [], [restants.pop(0)]
            while pile:
                i = pile.pop()
                composante.append(i)
                voisins = [j for j in restants if lien(membres[i], membres[j])]
                for j in voisins:
                    restants.remove(j)
                pile.extend(voisins)
            # Conserve les chaînes de la composante et regroupe leurs énoncés par position.
            choisies = tuple(membres[i] for i in sorted(composante))
            positions = tuple(
                {e for c in choisies for e in c.couples[k]} for k in range(len(groupe) + 1))
            resultat.append(Domaine(groupe, choisies, positions))
    return resultat
