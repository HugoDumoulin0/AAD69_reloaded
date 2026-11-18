"""Pipeline complet : un corpus de plusieurs discours -> toutes les étapes d'AAD69.

    corpus (énoncés + relations de chaque discours)
      -> 4. zones de similitude / quadruplets
      -> 5. domaines (1969 : chaînes + homogénéité ; 1972 : transitivité)
      -> 6. relations entre domaines
      -> 7. hyperdomaines

Le corpus se construit de deux façons :
- `corpus_depuis_discours` : discours analysés (CoNLL-U) -> étapes 2 et 3, extraction par Grew ;
- `corpus_depuis_tables` : énoncés et relations donnés directement (CSV, comme le livre).

L'interface (dossier interface/) ne fait qu'appeler `executer` et afficher `Resultats`.

Notes 
---------------------------------------------------
I1. Les énoncés sont numérotés sur TOUT le corpus (1, 2, 3… sans recommencer à chaque
    discours), comme dans le tableau p. 51 du manuel. Un numéro désigne un seul énoncé.
I2. Entrées acceptées : textes bruts (via Stanza, voir aad69/analyse.py), CoNLL-U, ou
    tables d'énoncés et de relations (CSV). Les deux dernières ne demandent pas Stanza.
I3. Comme F et les déterminants sont codés différemment en 1969 et en 1972, l'extraction
    est refaite pour chaque version : les deux sorties partent du même texte, pas des mêmes
    énoncés.
I7. Les anaphores sont rétablies avant l'extraction (manuel § 3.12, p. 14, aad69/anaphores.py),
    sauf si le réglage `resoudre_anaphores` est désactivé. La table pronom -> antécédent de chaque
    discours est gardée dans `Corpus.anaphores`, pour l'affichage et l'évaluation.
I6. Les corrections faites à la main sont gardées À PART des énoncés produits automatiquement
    (`appliquer_corrections`) : on peut toujours voir la valeur d'origine, annuler une correction,
    et l'export dit ce qui a été corrigé. Une correction vaut pour UNE version (F et les
    déterminants ne se codent pas pareil en 1969 et en 1972).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .anaphores import appliquer, resoudre
from .comparaison import Zone, zones_de_similitude
from .conllu import Phrase
from .domaines import Chaine, Domaine, chaines_de_similitude, domaines
from .domaines1972 import Domaine1972, coefficient_homogeneite, domaines_par_transitivite
from .hyperdomaines import Hyperdomaine, hyperdomaines
from .modele import CASES, VIDE, Enonce, RelationBinaire
from .reglages import Reglages
from .relations import relier
from .relations_domaines import Dependances, RelationDomaines, origines, tableau

# linguiste.py (partie LLM, non publiée sur GitHub) peut être absent : sans lui, seul
# `corpus_depuis_tables` fonctionne (premier prototype sans LLM).
try:
    from .linguiste import ajouter_latents, appliquer_rattachements, marquer_inseparables, remplacer_anaphores
except ImportError:
    ajouter_latents = appliquer_rattachements = marquer_inseparables = remplacer_anaphores = None


@dataclass
class Corpus:
    """Énoncés et relations qui constituent le corpus à analyser.

    `version` indique le codage des énoncés ; `None` signifie qu'ils ont été
    fournis tels quels. `anaphores` conserve, pour chaque discours, les
    résolutions appliquées aux pronoms.
    """

    enonces: list[Enonce]
    relations: list[RelationBinaire]
    version: str | None = None   # codage des énoncés (None : tables données telles quelles)
    anaphores: dict[str, dict] = field(default_factory=dict)   # discours -> {(phrase, mot): Resolution}

    @property
    def discours(self) -> list[str]:
        """Renvoie les noms des discours dans leur ordre d'apparition."""
        vus = []
        for e in self.enonces:
            if e.discours not in vus:
                vus.append(e.discours)
        return vus


def _avec_latents(lecture, latents, discours):
    """Ajoute à une lecture les énoncés latents proposés par la règle Grew G13.

    Une décision déjà présente pour le même mot est conservée ; les propositions
    encore « à vérifier » ne bloquent pas l'ajout de la règle. Sans énoncé latent,
    la lecture reçue est renvoyée telle quelle.
    """
    if not latents:
        return lecture
    from .linguiste import Decision, Lecture
    base = lecture if lecture is not None else Lecture(discours)
    # Une décision déjà tranchée l'emporte ; une proposition encore à vérifier ne bloque pas G13.
    deja = {(d.sent_id, d.mot) for d in base.decisions if d.type == "latent" and d.etat != "a_verifier"}
    # Convertit les propositions G13 non couvertes par une décision en décisions acceptées.
    ajouts = [Decision("latent", s, o, "règle Grew G13", complement=l, etat="acceptee", source="grew")
              for s, o, l in latents if (s, o) not in deja]
    return replace(base, decisions=list(base.decisions) + ajouts)


def corpus_depuis_discours(discours: dict[str, list[Phrase]], version: str = "1969",
                           anaphores: bool = True, lectures: dict | None = None,
                           ensembles_1969: bool = False) -> Corpus:
    """Extrait les énoncés et relations de discours déjà analysés en CoNLL-U.

    Pour chaque discours, applique dans l'ordre les éventuelles corrections du
    linguiste, les normalisations Grew, le rétablissement des anaphores,
    l'extraction des énoncés puis le calcul des relations. Les indices sont
    ensuite décalés pour être uniques dans l'ensemble du corpus (I1).

    `lectures` associe un nom de discours à sa lecture du linguiste. Si le
    module `linguiste.py` est absent, cette fonction s'arrête avec un message
    explicite ; pour un premier prototype, utiliser `corpus_depuis_tables`.
    `ensembles_1969` indique si les noms coordonnés forment un seul ensemble
    en 1969 (annexe I) ou sont extraits séparément comme en 1972 (LG6).
    """
    # Sans le module optionnel du linguiste, l'entrée par discours n'est pas disponible.
    if appliquer_rattachements is None:
        raise SystemExit("linguiste.py absent (partie LLM non publiée) : "
                         "utilisez corpus_depuis_tables(), le pipeline marche sans lui.")
    # Importe les traitements Grew de normalisation et d'extraction.
    from .extraction_grew import extraire_ancre_grew, normaliser
    # `decalage` rend les indices uniques d'un discours au suivant.
    enonces, relations, decalage = [], [], 0
    # Conserve les décisions de résolution d'anaphores par discours.
    tables_anaphores: dict[str, dict] = {}
    for nom, phrases in discours.items():
        # Récupère la lecture éventuelle associée à ce discours.
        lecture = (lectures or {}).get(nom)
        phrases = appliquer_rattachements(phrases, lecture)
        # Normalise avant les anaphores, notamment pour reconnaître « il » impersonnel.
        phrases = normaliser(phrases)              # Grew, avant les anaphores (il impersonnel…)
        if anaphores or lecture is not None:
            # Résout les pronoms par les règles, puis remplace les décisions par celles du linguiste.
            table = resoudre(phrases) if anaphores else {}
            tables_anaphores[nom] = remplacer_anaphores(table, phrases, lecture)
            phrases = appliquer(phrases, tables_anaphores[nom])
        phrases = marquer_inseparables(phrases, lecture)               # LG9 (opération 5)
        # Grew produit les énoncés ; les latents sont intégrés ensuite avant les relations.
        ancres, normalisees, latents = extraire_ancre_grew(phrases, discours=nom, codage=version,
                                                           ensembles_1969=ensembles_1969)
        ancres = ajouter_latents(ancres, normalisees, _avec_latents(lecture, latents, nom), version)
        locales = relier(normalisees, ancres, version)
        # Décale énoncés et extrémités des relations pour éviter les doublons entre discours.
        enonces += [replace(e, indice=e.indice + decalage) for e, _ in ancres]
        relations += [replace(r, gauche=r.gauche + decalage, droit=r.droit + decalage) for r in locales]
        decalage += len(ancres)
    return Corpus(enonces, relations, version, tables_anaphores)


def corpus_depuis_tables(enonces: list[Enonce], relations: list[RelationBinaire]) -> Corpus:
    """Crée un corpus à partir d'énoncés et de relations déjà établis (I2).

    Vérifie que chaque énoncé a un indice unique et que chaque relation renvoie
    à des indices présents dans la liste. Cette entrée n'a pas besoin de Grew,
    Stanza ni du module du linguiste.
    """
    # Chaque indice doit désigner un seul énoncé dans tout le corpus.
    indices = [e.indice for e in enonces]
    if len(set(indices)) != len(indices):
        raise ValueError("deux énoncés portent le même numéro (I1 : numérotation sur tout le corpus)")
    # Vérifie que les deux extrémités de chaque relation pointent vers un énoncé existant.
    connus = set(indices)
    inconnus = {i for r in relations for i in (r.gauche, r.droit)} - connus
    if inconnus:
        raise ValueError(f"relations vers des énoncés inexistants : {sorted(inconnus)}")
    return Corpus(list(enonces), list(relations))


Corrections = dict[int, dict[str, str]]   # {numéro d'énoncé: {case: nouvelle valeur}}


def appliquer_corrections(corpus: Corpus, corrections: Corrections) -> Corpus:
    """Applique les corrections manuelles aux cases des énoncés, sans toucher aux relations (I6).

    Une valeur vide est convertie en `Ø`. Si des corrections sont fournies,
    une nouvelle instance du corpus est renvoyée ; les relations gardent leurs
    indices, car les numéros d'énoncés ne changent pas. Sans correction, le
    corpus original est renvoyé.
    """
    if not corrections:
        return corpus
    # Refuse les corrections visant un indice absent du corpus.
    connus = {e.indice for e in corpus.enonces}
    inconnus = set(corrections) - connus
    if inconnus:
        raise ValueError(f"corrections pour des énoncés inexistants : {sorted(inconnus)}")
    # Reconstruit chaque énoncé : seules les cases explicitement corrigées changent.
    enonces = []
    for e in corpus.enonces:
        cases = corrections.get(e.indice, {})
        for case in cases:
            if case not in CASES:
                raise ValueError(f"case inconnue : {case}")
        enonces.append(replace(e, **{c: (v.strip() or VIDE) for c, v in cases.items()}))
    return Corpus(enonces, corpus.relations, corpus.version, corpus.anaphores)


@dataclass
class Resultats:
    """Résultats des étapes d'analyse exécutées sur un corpus.

    Les chaînes et le coefficient ne sont renseignés que pour la version qui
    les utilise ; les domaines, relations entre domaines et hyperdomaines
    sont conservés pour l'affichage et l'export.
    """

    reglages: Reglages
    corpus: Corpus
    zones: list[Zone]
    chaines: list[Chaine] = field(default_factory=list)              # 1969 seulement
    domaines: dict[str, Domaine | Domaine1972] = field(default_factory=dict)  # "D1", "D2"…
    coefficient: float | None = None                                  # 1972 seulement
    relations_domaines: list[RelationDomaines] = field(default_factory=list)
    hyperdomaines: list[Hyperdomaine] = field(default_factory=list)

    @property
    def origines(self) -> dict[str, set[int]]:
        """Associe à chaque domaine l'ensemble de ses énoncés-origines."""
        return {nom: origines(d) for nom, d in self.domaines.items()}


def executer(corpus: Corpus, reglages: Reglages | None = None) -> Resultats:
    """Exécute les étapes 4 à 7 et rassemble leurs résultats.

    Si aucun réglage n'est fourni, utilise les valeurs par défaut de `Reglages`.
    Les étapes 5 et 7 suivent ensuite la version choisie (1969 ou 1972).
    """
    # Calcule les zones de similitude à partir des énoncés et relations du corpus.
    r = reglages or Reglages()
    zones = zones_de_similitude(corpus.enonces, corpus.relations, r.poids, r.borne, r.regle,
                                r.intermediaires, r.annulation, r.operateurs_exclus)
    res = Resultats(r, corpus, zones)

    # En 1969, les zones sont assemblées en chaînes puis en domaines.
    if r.version == "1969":
        res.chaines = chaines_de_similitude(zones)
        liste = domaines(res.chaines, {e.indice: e for e in corpus.enonces}, r.critere_homogeneite,
                         r.poids, r.borne, r.regle)
    else:
        # En 1972, les domaines sont regroupés par transitivité ; on calcule aussi le coefficient.
        liste = domaines_par_transitivite(zones)
        res.coefficient = coefficient_homogeneite(corpus.enonces, corpus.relations, zones, r.operateurs_exclus)
    # Attribue des identifiants lisibles aux domaines calculés.
    res.domaines = {f"D{i}": d for i, d in enumerate(liste, 1)}

    # Déduit les relations entre domaines à partir de leurs origines.
    dependances = Dependances(corpus.relations, r.operateurs_exclus)
    res.relations_domaines = tableau(res.origines, dependances, r.version)
    # Les hyperdomaines appartiennent à 1969 ; en 1972, leur calcul est une extension activable.
    if r.version == "1969" or r.hyperdomaines_1972:
        res.hyperdomaines = hyperdomaines(res.origines)
    return res
