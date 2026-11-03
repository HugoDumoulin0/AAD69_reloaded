"""Structures de données de base d'AAD69.

Ce module définit les trois objets que tout le reste du programme manipule :

- Enonce          : un énoncé élémentaire à 8 cases (Pêcheux 1969, annexe V, § 8) ;
- RelationBinaire : un lien Ei ψ Ej entre deux énoncés (annexe V, § 7 et § 9) ;
- Graphe          : l'ensemble des énoncés et des relations d'une séquence.

Aucune analyse linguistique ici : ce module décrit seulement la forme des données.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

# Case vide. Le livre écrit φ ; on écrit Ø pour ne pas confondre avec les opérateurs φ1, φ2…
VIDE = "Ø"

# Les 8 classes morpho-syntaxiques, dans l'ordre du livre (annexe V, § 8).
CASES = ("F", "D1", "N1", "V", "ADV", "PP", "D2", "N2_3")

# Opérateurs de dépendance ψ de 1969 (annexe I, p. 115 ; annexe V, § 7 ; chap. II, p. 83).
# Code utilisé dans nos fichiers -> symbole du livre.
#
# Provenance des gloses : δ1, δ2, α et φα suivent l'annexe V, § 7. Les gloses de φ1 à φ6 sont
# celles de l'ANNEXE I (corpus d'Alice), qui est notre référence : ce ne sont pas des valeurs
# fixes du livre. Au chapitre I, la numérotation des φ est locale à chaque exemple (φ1 =
# « soudain », p. 76 ; φ1 = « puisque », p. 79 ; φ5 = « lorsque », p. 84).
#
# Cette table est une table de NOTATION, pas une liste fermée : RelationBinaire accepte tout
# code non vide, en particulier les connecteurs 01 à 99 de 1972. Deux notations du manuel de
# 1972 n'y figurent pas, parce qu'elles n'appartiennent pas au codage de 1969 :
# - 99 : « connexion à un énoncé vide » (manuel, annexe 2) ; voir Eφ ci-dessous ;
# - δ′ : relative explicative, opposée à la déterminative δ (manuel, p. 50, note 5) ; les
#   tableaux du manuel codent pourtant les relatives par 01 / 02. Repérer une relative
#   explicative relève de l'étape 3 (E3-13).
OPERATEURS_1969 = {
    "d1": "δ1",          # Ej détermine le sujet N1 de Ei (annexe V, § 7)
    "d2": "δ2",          # Ej détermine le complément N2/3 de Ei (annexe V, § 7)
    "phi0": "φ0",        # relation d'ordre minimale ; ouverture du discours Eφ φ0 E1 (postulat 7)
    "phi1": "φ1",        # annexe I : simultanéité temporelle (lorsque)
    "phi2": "φ2",        # annexe I : marque d'arrêt non qualifiée (.)
    "phi3": "φ3",        # annexe I : coordination associative (et)
    "phi4": "φ4",        # annexe I : marque d'arrêt qualifiée (:)
    "phi5": "φ5",        # annexe I : conséquence (si… que)
    "phi6": "φ6",        # utilisé dans l'annexe I, non défini dans le livre
    "phi_alpha": "φα",   # Ej est postérieur à Ei dans la séquence
    "alpha": "α",        # relation à trois places (annexe V, § 7)
}

# Eφ, l'énoncé vide (postulat 7, p. 66 : « Eφ φ0 E1 », E1 étant l'énoncé initial du discours).
# Il n'est PAS stocké dans les graphes (décision E1-5) : un énoncé dont toutes les cases sont
# vides serait identique d'un discours à l'autre et créerait des zones de similitude
# artificielles à l'étape 4 ; aucune référence publiée (annexes I et III) ne le contient.
# Il est VIRTUEL : on considère que le premier énoncé de chaque discours dépend de Eφ.
# `Graphe.avertissements()` vérifie ce que cette convention suppose (une seule source par
# discours, postulat 8).


@dataclass(frozen=True)
class Enonce:
    """Un énoncé élémentaire E = < F, D1, N1, V, ADV, PP, D2, N2/3 >.

    `indice` est le numéro de l'énoncé dans la séquence (comme dans l'annexe I).
    `discours` identifie le discours d'origine : la comparaison (étape 4) ne
    compare que des énoncés de discours différents.
    `source` indique d'où vient l'énoncé (par exemple « alice-3:12 » = phrase
    alice-3, mot 12) : utile pour vérifier une extraction à la main.
    Les cases non remplies valent VIDE.
    """

    indice: int
    F: str = VIDE
    D1: str = VIDE
    N1: str = VIDE
    V: str = VIDE
    ADV: str = VIDE
    PP: str = VIDE
    D2: str = VIDE
    N2_3: str = VIDE
    discours: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        for nom in CASES:
            valeur = getattr(self, nom)
            if not isinstance(valeur, str) or valeur.strip() == "":
                raise ValueError(f"Énoncé {self.indice} : la case {nom} doit être une chaîne non vide (utiliser VIDE).")

    def cases(self) -> tuple[str, ...]:
        """Les 8 cases dans l'ordre du livre. C'est ce que compare l'étape 4."""
        return tuple(getattr(self, nom) for nom in CASES)


@dataclass(frozen=True)
class RelationBinaire:
    """Une relation binaire b = Ei ψ Ej (annexe V, § 9).

    `gauche` et `droit` sont des indices d'énoncés. `operateur` est un code
    (par exemple "d1" ou "phi_alpha") ; on accepte aussi des codes hors de
    OPERATEURS_1969, en particulier les connecteurs de 1972.

    Deux indications facultatives, qui ne changent pas l'identité de la relation (deux relations
    sont égales si elles ont mêmes gauche, opérateur et droit, quelles que soient ces indications ;
    les fichiers de référence, qui n'ont que trois colonnes, restent donc comparables) :

    - `saturation` : la relation a été ajoutée par saturation et non lue directement dans la
      phrase (livre, p. 62-63 et 82) : ordre φα entre les dépendants d'un même énoncé (E3-7),
      sujet partagé par des verbes coordonnés (E3-8).
    - `variante` : numéro de l'analyse quand une phrase est « irrémédiablement ambiguë » et
      qu'on enregistre ses deux interprétations (livre, p. 82). 0 = analyse principale ; 1, 2…
      = analyses concurrentes. Toutes les étapes traitent ces relations comme les autres (c'est
      ce que fait Pêcheux) ; le numéro sert à savoir de quelle lecture vient chacune. Aucune
      règle automatique n'en crée : c'est l'analyste qui juge qu'une phrase est ambiguë.
    """

    gauche: int
    operateur: str
    droit: int
    saturation: bool = field(default=False, compare=False)
    variante: int = field(default=0, compare=False)

    def __post_init__(self) -> None:
        if self.gauche == self.droit:
            raise ValueError(f"Relation invalide : l'énoncé {self.gauche} ne peut pas dépendre de lui-même.")
        if not self.operateur:
            raise ValueError("Relation invalide : opérateur vide.")
        if not isinstance(self.variante, int) or self.variante < 0:
            raise ValueError(f"Relation invalide : variante {self.variante!r} (entier positif ou nul attendu).")


@dataclass
class Graphe:
    """Les énoncés d'une séquence et les relations qui les relient.

    Les relations sont gardées dans une liste, alors que l'annexe V, § 9 définit ℬ comme un
    ENSEMBLE. Aucun calcul n'utilise l'ordre de la liste ; et le postulat 11 (p. 68) dit que
    l'ensemble non ordonné suffit à reconstituer la pile, à condition que la saturation soit
    faite, ce qu'elle est (E3-7, E3-8). Les doublons exacts sont signalés par `avertissements()`.
    """

    enonces: dict[int, Enonce] = field(default_factory=dict)
    relations: list[RelationBinaire] = field(default_factory=list)

    def ajouter_enonce(self, enonce: Enonce) -> None:
        if enonce.indice in self.enonces:
            raise ValueError(f"L'énoncé {enonce.indice} existe déjà.")
        self.enonces[enonce.indice] = enonce

    def ajouter_relation(self, relation: RelationBinaire) -> None:
        self.relations.append(relation)

    def erreurs(self) -> list[str]:
        """Liste les relations qui renvoient à un énoncé absent. Vide si le graphe est cohérent."""
        problemes = []
        for r in self.relations:
            for i in (r.gauche, r.droit):
                if i not in self.enonces:
                    problemes.append(f"Relation {r.gauche} {r.operateur} {r.droit} : énoncé {i} absent.")
        return problemes

    def avertissements(self) -> list[str]:
        """Ce qui n'est pas une erreur de référence (voir `erreurs`) mais s'écarte de la structure
        que le livre suppose. Vide si rien n'est à signaler. Rien n'est bloquant.

        - relation exactement dupliquée (même gauche, opérateur, droit) ;
        - cycle (E1 ψ E2 et E2 ψ E1, ou plus long) : les piles du livre n'en produisent pas ;
        - énoncé isolé, dans aucune relation ;
        - postulat 8 (p. 66) : tout énoncé autre que le premier du discours doit apparaître à
          droite d'au moins une relation avant de paraître à gauche. Le premier énoncé en est
          dispensé parce qu'il dépend de Eφ, virtuel (E1-5). Comme ℬ est un ensemble, on vérifie
          qu'il apparaît à droite d'au moins une relation, pas l'ordre d'écriture ;
        - plus d'une source dans un discours : structure S4, à réduire en S3 (p. 66), sinon « le
          premier énoncé du discours », celui qui dépend de Eφ, n'est pas bien défini.

        Les discours sont lus sur les énoncés (`Enonce.discours`) ; le premier énoncé d'un
        discours est celui de plus petit indice.
        """
        messages: list[str] = []
        vus: set[tuple] = set()
        for r in self.relations:
            cle = (r.gauche, r.operateur, r.droit)
            if cle in vus:
                messages.append(f"Relation {r.gauche} {r.operateur} {r.droit} enregistrée deux fois.")
            vus.add(cle)

        for cycle in self._cycles():
            messages.append("Cycle entre les énoncés " + ", ".join(map(str, cycle))
                            + " : chacun dépend, directement ou non, des autres.")

        gauches = {r.gauche for r in self.relations if r.gauche in self.enonces}
        droits = {r.droit for r in self.relations if r.droit in self.enonces}
        isoles = {i for i in self.enonces if i not in gauches | droits}
        for i in sorted(isoles):
            messages.append(f"Énoncé {i} isolé : il n'est dans aucune relation.")

        par_discours: dict[str, list[int]] = {}
        for i, e in self.enonces.items():
            par_discours.setdefault(e.discours, []).append(i)
        for discours, indices in sorted(par_discours.items()):
            premier = min(indices)
            nom = f"discours « {discours} »" if discours else "discours"
            for i in sorted(indices):
                if i != premier and i in gauches and i not in droits:
                    messages.append(f"Postulat 8 ({nom}) : l'énoncé {i} paraît à gauche sans avoir paru à "
                                    f"droite d'aucune relation ; seul le premier énoncé ({premier}) en est dispensé.")
            sources = sorted(i for i in indices if i not in droits and i not in isoles)
            if len(sources) > 1:
                messages.append(f"S4 ({nom}) : {len(sources)} sources ({', '.join(map(str, sources))}) ; "
                                "une seule est attendue (réduction S4 → S3, p. 66).")
        return messages

    def _cycles(self) -> list[list[int]]:
        """Les groupes d'énoncés pris dans un cycle (composantes fortement connexes de plus d'un
        énoncé), par l'algorithme de Kosaraju, sans récursion (les corpus peuvent être longs)."""
        noeuds = sorted({r.gauche for r in self.relations} | {r.droit for r in self.relations})
        avant: dict[int, list[int]] = {v: [] for v in noeuds}
        arriere: dict[int, list[int]] = {v: [] for v in noeuds}
        for r in self.relations:
            avant[r.gauche].append(r.droit)
            arriere[r.droit].append(r.gauche)

        ordre, vus = [], set()
        for depart in noeuds:                 # 1. ordre de fin de parcours
            if depart in vus:
                continue
            vus.add(depart)
            pile = [(depart, iter(avant[depart]))]
            while pile:
                v, suite = pile[-1]
                w = next(suite, None)
                if w is None:
                    pile.pop()
                    ordre.append(v)
                elif w not in vus:
                    vus.add(w)
                    pile.append((w, iter(avant[w])))

        composantes, places = [], set()
        for depart in reversed(ordre):        # 2. parcours du graphe inversé
            if depart in places:
                continue
            composante, pile = [], [depart]
            places.add(depart)
            while pile:
                v = pile.pop()
                composante.append(v)
                for w in arriere[v]:
                    if w not in places:
                        places.add(w)
                        pile.append(w)
            if len(composante) > 1:
                composantes.append(sorted(composante))
        return sorted(composantes)

    def successeurs(self, indice: int) -> list[int]:
        """Les énoncés qui dépendent directement de `indice`."""
        return [r.droit for r in self.relations if r.gauche == indice]

    def sources(self) -> set[int]:
        """Les énoncés qui ne dépendent d'aucun autre : les points de départ du graphe."""
        droits = {r.droit for r in self.relations}
        return {i for i in self.enonces if i not in droits}

    def accessibles(self, depart: int) -> set[int]:
        """Tous les énoncés qu'on peut atteindre en suivant les flèches depuis `depart`."""
        vus, a_visiter = {depart}, [depart]
        while a_visiter:
            courant = a_visiter.pop()
            for suivant in self.successeurs(courant):
                if suivant not in vus:
                    vus.add(suivant)
                    a_visiter.append(suivant)
        return vus


# Vérifie au chargement que les noms de cases et les champs de Enonce restent alignés.
assert CASES == tuple(f.name for f in fields(Enonce))[1:9]
