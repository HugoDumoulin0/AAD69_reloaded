"""Étape 6 — Relations entre domaines.

1969 : Pêcheux, p. 104-108 (Alg. 6 et Alg. 7) 
1972 : Haroche & Pêcheux, p. 49-50 (§ 3.313) 

Vocabulaire
-----------
- En DÉPEND de Ek (Ek ⇒ En) : il existe une suite de relations qui mène de Ek à En dans le
  graphe d'un discours (« concaténation de dépendances directes », p. 104) ;
- ORIGINE d'une séquence : son premier énoncé, « l'énoncé placé à gauche » (p. 106) ;
- une séquence Sn COMMANDE une séquence Sn' (Sn → Sn') : l'origine de Sn' dépend de celle de Sn ;(Sₙ = la séquence numéro n. s1, s2...)
- ORIGINES d'un domaine : l'ensemble des origines de ses séquences.

Relations entre deux domaines Dx et Dy (1969, p. 106-107, testées dans l'ordre d'Alg. 7)
------------------------------------------------------------------------------------------
  ORIGINES_COMMUNES  Dx ⊕ Dy   mêmes origines
  INCLUT             Dx ⊃ Dy   les origines de Dy sont une partie de celles de Dx
  INTERSECTION       Dx ∩ Dy   origines en partie communes, sans inclusion
  puis, si les origines sont disjointes :
  DEP1   toute séquence de Dx commande une séquence de Dy, et toute séquence de Dy dépend de Dx
  DEP2   toute séquence de Dx commande…, sans que toute séquence de Dy dépende de Dx
  DEP3   certaines (pas toutes) séquences de Dx commandent…, et toute séquence de Dy dépend de Dx
  DEP4   certaines séquences de Dx commandent…, sans que toute séquence de Dy dépende de Dx
  RECIPROQUE         Dx — Dy   des séquences de chacun commandent des séquences de l'autre
  DISJOINTS          Dx ∥ Dy   aucune origine commune, aucune dépendance

Relations 1972 (p. 50) : IDORG (origines identiques), INCLU (Dj INCLU Di : origines de Dj
toutes parmi celles de Di), INTER (intersection non vide) ; sinon le programme n'indique que
la POSSIBILITÉ d'une dépendance.

Notes:
---------------------------------------------------
R1. Dépendance entre énoncés = accessibilité dans le graphe, en explorant TOUS les chemins.
    L'organigramme Alg. 6 (p. 105), lu à la lettre, ne suit qu'une branche.
R2. φα (relation d'ordre) n'est pas une dépendance : exclue du graphe (comme D8).
R3. Origines d'un domaine = ses énoncés gauches : position 1 des chaînes (1969),
    énoncés gauches des relations (1972). Comme « commander » ne dépend que de l'origine,
    quantifier sur les séquences revient à quantifier sur leurs origines.
R4. La dépendance est testée dans les deux sens ; si seul Dy commande Dx, la relation
    est écrite « y DEPk x ». Les 4 flèches du livre, peu lisibles sur le scan, sont
    nommées DEP1 à DEP4 d'après les définitions du texte.
R5. 1972 : « dépendance possible » = au moins une origine de l'un commande une origine
    de l'autre. Pas de degré : le manuel dit que ce calcul est « actuellement à l'étude ».
R6. Les dépendances se calculent sur le graphe qu'on fournit (Dependances). Si ce graphe est
    partiel (ex. tableau p. 51 du manuel), le résultat l'est aussi.

"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .modele import RelationBinaire

NON_DEPENDANCE = frozenset({"phi_alpha"})

SYMBOLES_1969 = {
    "ORIGINES_COMMUNES": "⊕", "INCLUT": "⊃", "INTERSECTION": "∩",
    "DEP1": "⇒ (degré 1)", "DEP2": "⇒ (degré 2)", "DEP3": "→ (degré 3)", "DEP4": "→ (degré 4)",
    "RECIPROQUE": "—", "DISJOINTS": "∥",
}


class Dependances:
    """Graphe des dépendances entre énoncés.

    Une relation `Ek → En` ajoute une flèche de `Ek` vers `En`. `Ek` est
    considéré comme dépendant de `En` s'il existe un chemin entre eux.
    Les opérateurs exclus, notamment φα, ne sont pas ajoutés au graphe (R1-R2).
    """

    def __init__(self, relations: list[RelationBinaire], exclus: frozenset[str] = NON_DEPENDANCE):
        # Pour chaque énoncé, mémorise les énoncés atteints par une flèche directe.
        self.successeurs: dict[int, set[int]] = {}
        for r in relations:
            if r.operateur not in exclus:
                self.successeurs.setdefault(r.gauche, set()).add(r.droit)
        self._cache: dict[int, set[int]] = {}

    def accessibles(self, ek: int) -> set[int]:
        """Renvoie tous les énoncés atteignables depuis `ek` par une ou plusieurs flèches."""
        if ek not in self._cache:
            # Explore tous les chemins en évitant de revisiter un énoncé.
            vus, pile = set(), list(self.successeurs.get(ek, ()))
            while pile:
                e = pile.pop()
                if e not in vus:
                    vus.add(e)
                    pile.extend(self.successeurs.get(e, ()))
            # Garde le résultat pour éviter de reparcourir le graphe depuis `ek`.
            self._cache[ek] = vus
        return self._cache[ek]

    def depend(self, ek: int, en: int) -> bool:
        """Indique si `en` est atteignable depuis `ek`, sauf si les deux sont identiques."""
        return ek != en and en in self.accessibles(ek)


@dataclass(frozen=True)
class RelationDomaines:
    """Relation entre deux domaines, représentée par ses noms et son type.

    Par exemple, `x="5", type="INCLU", y="1"` se lit « 5 inclut 1 ».
    """

    x: str
    type: str
    y: str


def origines(domaine) -> set[int]:
    """Renvoie les énoncés-origines d'un domaine (R3).

    Pour un domaine 1969, ce sont les indices à la première position des
    chaînes. Pour un domaine 1972, ce sont les indices à gauche des relations.
    """
    # Les deux versions n'exposent pas les origines sous le même attribut.
    if hasattr(domaine, "positions"):
        return set(domaine.positions[0])
    return set(domaine.gauches)


def _commande(ox: set[int], oy: set[int], g: Dependances) -> tuple[set[int], set[int]]:
    """Repère les origines reliées par une dépendance de Dx vers Dy.

    Renvoie d'abord les origines de `ox` qui atteignent au moins une origine
    de `oy`, puis les origines de `oy` atteintes par au moins une origine de `ox`.
    """
    # Une origine commande l'autre dès qu'un chemin de dépendance les relie.
    commandent = {a for a in ox if any(g.depend(a, b) for b in oy)}
    dependent = {b for b in oy if any(g.depend(a, b) for a in ox)}
    return commandent, dependent


def relation_1969(nx: str, ox: set[int], ny: str, oy: set[int], g: Dependances) -> RelationDomaines:
    """Classe la relation entre deux domaines selon l'algorithme 7 de 1969.

    Compare d'abord leurs origines (égalité, inclusion ou intersection), puis
    examine les dépendances dans les deux sens pour choisir DEP1 à DEP4,
    RECIPROQUE ou DISJOINTS.
    """
    # Copie les ensembles pour ne pas modifier ceux fournis par l'appelant.
    ox, oy = set(ox), set(oy)
    # Les relations portant sur les origines ont priorité sur les dépendances.
    if ox == oy:
        return RelationDomaines(nx, "ORIGINES_COMMUNES", ny)
    if oy < ox:
        return RelationDomaines(nx, "INCLUT", ny)
    if ox < oy:
        return RelationDomaines(ny, "INCLUT", nx)
    if ox & oy:
        return RelationDomaines(nx, "INTERSECTION", ny)

    # Mesure les dépendances de Dx vers Dy, puis de Dy vers Dx.
    cx, dy = _commande(ox, oy, g)
    cy, dx = _commande(oy, ox, g)
    if cx and cy:
        return RelationDomaines(nx, "RECIPROQUE", ny)
    if not cx and not cy:
        return RelationDomaines(nx, "DISJOINTS", ny)
    if not cx:  # R4 : seul Dy commande Dx ; on inverse l'ordre pour nommer la relation.
        nx, ny, ox, oy, cx, dy = ny, nx, oy, ox, cy, dx
    # Les quatre degrés dépendent du caractère total ou partiel des deux ensembles.
    toutes_commandent, toutes_dependent = cx == ox, dy == oy
    degre = {(True, True): "DEP1", (True, False): "DEP2",
             (False, True): "DEP3", (False, False): "DEP4"}[(toutes_commandent, toutes_dependent)]
    return RelationDomaines(nx, degre, ny)


def relation_1972(ni: str, oi: set[int], nj: str, oj: set[int], g: Dependances) -> RelationDomaines:
    """Classe la relation entre deux domaines selon le manuel de 1972 (§ 3.313, p. 50).

    Signale d'abord l'égalité, l'inclusion ou l'intersection des origines.
    Si elles sont disjointes, indique une dépendance possible dès qu'une
    origine de l'un atteint une origine de l'autre (R5).
    """
    # Copie les ensembles pour préserver les valeurs reçues en argument.
    oi, oj = set(oi), set(oj)
    # Vérifie d'abord les relations directement établies par les origines.
    if oi == oj:
        return RelationDomaines(ni, "IDORG", nj)
    if oj < oi:
        return RelationDomaines(nj, "INCLU", ni)
    if oi < oj:
        return RelationDomaines(ni, "INCLU", nj)
    if oi & oj:
        return RelationDomaines(ni, "INTER", nj)
    # En cas d'origines disjointes, cherche une dépendance dans chaque sens.
    i_vers_j = bool(_commande(oi, oj, g)[0])
    j_vers_i = bool(_commande(oj, oi, g)[0])
    if i_vers_j and j_vers_i:
        return RelationDomaines(ni, "DEPENDANCE_POSSIBLE_RECIPROQUE", nj)
    if i_vers_j:
        return RelationDomaines(ni, "DEPENDANCE_POSSIBLE", nj)
    if j_vers_i:
        return RelationDomaines(nj, "DEPENDANCE_POSSIBLE", ni)
    return RelationDomaines(ni, "AUCUNE", nj)


def tableau(origines_par_domaine: dict[str, set[int]], g: Dependances, version: str = "1969"
            ) -> list[RelationDomaines]:
    """Calcule la relation pour chaque paire de domaines.

    `version` choisit les règles de 1969 ou de 1972. Chaque paire n'est
    traitée qu'une fois, comme dans le tableau du livre (p. 127).
    """
    # Sélectionne les règles de classement à appliquer à toutes les paires.
    regle = relation_1969 if version == "1969" else relation_1972
    return [regle(a, origines_par_domaine[a], b, origines_par_domaine[b], g)
            for a, b in combinations(origines_par_domaine, 2)]
