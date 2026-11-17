"""Étape 3 : Construire les relations binaires entre les énoncés.

Une relation relie un énoncé dominant à un énoncé dépendant : `Ei ψ Ej`.
Le module procède en deux temps : il détermine d'abord le type de chaque
lien (`Lien`), puis le traduit dans la notation demandée :

- codage 1969 : opérateurs de l'annexe I (p. 115), comme δ1, δ2, φ1…φ5, φα;
- codage 1972 : connecteurs numérotés de l'annexe 2 du manuel (p. 54).

En 1969, un lien dont le marqueur n'est pas attesté dans l'annexe I n'est pas
noté (la virgule n'y figure pas, pas plus que IMP ou PRG) : le module ne crée
pas d'opérateur pour ce que le livre n'a pas représenté.

Les liens sont repérés à partir des phrases et des ancrages produits à
l'étape 2. Ils peuvent marquer l'adjonction d'un adjectif ou d'un complément
à un nom, la dépendance entre propositions, la coordination, ou la structure
du discours entre phrases. Le module ajoute aussi les relations de saturation
prévues par la méthode.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conllu import Phrase
from .commun import Ancrage
from .modele import Enonce, RelationBinaire

# --- Types de liens avant leur conversion en notation 1969 ou 1972 -----------------------

# Adjonction à un nom : δ1 si le groupe nominal occupe la place de sujet, δ2 s'il est complément.
DETERMINATION_SUJET = "determination_sujet"
DETERMINATION_COMPLEMENT = "determination_complement"
# Liens entre les énoncés d'un même prédicat : complément circonstanciel ou argument supplémentaire.
COMPLEMENT_CIRCONSTANCIEL = "complement_circonstanciel"
COMPLEMENT_ARGUMENT = "complement_argument"
# Liens entre propositions ou variantes d'une coordination.
SUBORDINATION = "subordination"
COORDINATION = "coordination"
CONSEQUENCE = "consequence"
JONCTION = "jonction"  # IMP, QUE, PRG1, PRG2, repérés par Grew
# Autres liens : ponctuation, infinitif dépendant d'un nom, ordre ajouté par saturation.
ARRET = "arret"
INFINITIF_DU_NOM = "infinitif_du_nom"
ORDRE = "ordre"


@dataclass(frozen=True)
class Lien:
    """Lien neutre entre deux énoncés, avant conversion en code de relation.

    `gauche` est l'indice de l'énoncé dominant et `droit` celui de l'énoncé
    dépendant. `type` décrit leur lien ; `marqueur` conserve le mot qui le
    signale, comme « quand » ou « et ». `saturation` indique que le lien a
    été ajouté par les règles de saturation, et non repéré directement dans
    la phrase.
    """

    gauche: int
    type: str
    droit: int
    marqueur: str = ""
    saturation: bool = False


# --- Conversion des liens en opérateurs de 1969 (annexe I, p. 115) -----------------------

# Opérateurs attestés dans l'annexe I, p. 115 (φ1 = lorsque, φ2 = ., φ3 = et, φ4 = :,
# φ5 = si…que ; « quand » : même usage, annexe I, 1 φ1 4).
# NB : la virgule n'est pas notée en 1969 : aucun opérateur dans l'annexe I, on n'en
# crée pas. Le manuel de 1972 la note, lui : « 40 : et, VIRGULE » en coordination et
# 60 comme marque d'arrêt (annexe 2, p. 54).
PHI_1969 = {"lorsque": "phi1", "quand": "phi1", ".": "phi2", "et": "phi3", ":": "phi4", "si…que": "phi5"}


def notation_1969(lien: Lien) -> str | None:
    """Convertit un lien neutre en opérateur de 1969, ou renvoie `None`."""
    if lien.type == DETERMINATION_SUJET:
        return "d1"
    if lien.type == DETERMINATION_COMPLEMENT:
        return "d2"
    if lien.type == COMPLEMENT_CIRCONSTANCIEL:
        return "d1"      # annexe I : 20 δ1 21 (« lapin avoir dans U1 main »)
    if lien.type == COMPLEMENT_ARGUMENT:
        return "alpha"   # chap. II, p. 82 : Ève donne une pomme ∝ Ève donne à Adam ;
                         # α : opérateur de l'ensemble ψ (livre, pp. 94-95)
    if lien.type == INFINITIF_DU_NOM:
        return "phi6"    # annexe I : 32 φ6 34 (table des relations, p. 115) ; φ6
                         # n'est pas défini dans la liste des connexions (p. 115) ni
                         # dans l'annexe V ; d'après 32 (« Alice avoir une envie ») et
                         # 34 (« Alice manger les tartes »), il relie un énoncé de nom
                         # au prédicat que ce nom recouvre (« envie de manger ») ;
                         # l'équivalent 1972 est le connecteur 11 (que)
    if lien.type == ORDRE:
        return "phi_alpha"  # livre, pp. 60-61 : relation d'ordre entre les énoncés dominés
                           # directement par un même énoncé
    if lien.type == CONSEQUENCE:
        return "phi5"    # relation de conséquence (si…que, au point…que), annexe I, p. 115
    if lien.type == JONCTION:      # pas d'opérateur en 1969 : pas de notation
        # NB : IMP, PRG1, PRG2, SPE et que sont des connecteurs du manuel 1972
        # (annexe 2, p. 54 : 05, 06, 07, 08, 11) ; le livre de 1969 ne les note
        # pas
        return None
    # Un marqueur sans opérateur attesté dans l'annexe I (la virgule, « ou »,
    # le « que » de subordination…) n'est pas noté en 1969 : on ne crée rien.
    return PHI_1969.get(lien.marqueur)


# --- Conversion des liens en codes de 1972 (annexe 2, p. 54) ------------------------------

# Correspondance entre les mots de liaison et les connecteurs numérotés du manuel
# (annexe 2, p. 54).
# NB : « ni » → 40 est attesté par la remarque de la table (« ni A, ni B → NEG (A)
# et NEG (B) », p. 54) ; « ainsi que » n'y est pas imprimé tel quel : « ainsi » et
# « de même que » figurent sous 41 (que comparatif), mais pas la locution. Le code
# 40 pour « ainsi que » est un choix du programme, à valider avec Hugo.
CONNECTEURS_1972 = {
    "et": "40", "ou": "49", "mais": "47", "ni": "40",
    "puis": "23", "or": "70",
    "lorsque": "22", "quand": "22", "comme": "22", "pendant que": "20", "tandis que": "20",
    "avant que": "28", "après que": "29", "depuis que": "25", "dès que": "24",
    "que": "11", "si": "80", "parce que": "71", "car": "71", "puisque": "72",
    # préposition + infinitif = PREP + QUE (manuel § 3.14223, 3 ; annexe 2)
    "pour": "73", "afin de": "73", "de manière à": "73", "de façon à": "73", "sans": "83",
    "avant de": "28", "après": "29", "au lieu de": "49", "jusqu'à": "26",
    "pour que": "73", "afin que": "73", "bien que": "85", "quoique": "85",
    ".": "60", ";": "60", ",": "60",
    ":": "63",  "c'est-à-dire que": "63" 
}


def notation_1972(lien: Lien) -> str | None:
    """Convertit un lien neutre en code du manuel de 1972, ou renvoie `None`."""
    if lien.type == DETERMINATION_SUJET:
        return "01"
    if lien.type == DETERMINATION_COMPLEMENT:
        return "02"
    if lien.type == COMPLEMENT_CIRCONSTANCIEL:
        return "09"  # CIRC
    if lien.type == COMPLEMENT_ARGUMENT:
        return "08"  # SPE (annexe 2 : prédicats à n > 2 arguments ; manuel, p. 33 :
                     # (ARTHUR DONNER + U FLEUR) SPE (ARTHUR DONNER A CAMILLE))
    if lien.type == INFINITIF_DU_NOM:
        return "11"  # prédicat recouvert par une nominalisation (manuel, § 3.1425, p. 33 :
                     # « Pierre attend la venue de Jean » ; annexe 1, étape 7 : connecteurs 11 à 16)
    if lien.type == CONSEQUENCE:
        return "74"  # au point que
    if lien.type == ORDRE:
        return None  # pas de relation d'ordre en 1972
    if lien.type == JONCTION:      # annexe 1, étape 5 : IMP 05, QUE 11, PRG1 06, PRG2 07
        return {"IMP": "05", "QUE": "11", "PRG1": "06", "PRG2": "07"}[lien.marqueur]
    return CONNECTEURS_1972.get(lien.marqueur, f"?[{lien.marqueur}]")


# Fonction de conversion à utiliser selon le codage demandé.
NOTATIONS = {"1969": notation_1969, "1972": notation_1972}

# MOTS_DEGRE (« si appétissantes qu'… » -> conséquence) et PREPOSITIONS_CIRCONSTANCIELLES (E3-14) :
# listes dans lexique.py.
from .lexique import MOTS_DEGRE, PREPOSITIONS_CIRCONSTANCIELLES  # noqa: E402,F401


def _est_argument(phrase: Phrase, mot_id: int, pp: str) -> bool:
    """Indique si le complément est un argument du verbe plutôt que circonstanciel.

    Les compléments d'objet indirect, obliques argumentaux et agents du
    passif sont considérés comme arguments. Les prépositions circonstancielles
    et les mots « y » ou « où » ne le sont pas.
    """
    mot = phrase.mots.get(mot_id)
    if mot is None:
        return False
    if pp in PREPOSITIONS_CIRCONSTANCIELLES or mot.forme.lower() in ("y", "où"):
        return False
    return mot.relation in ("iobj", "obl:arg", "obl:agent")


# --- Construction des liens --------------------------------------------------------------

def _marqueur(phrase: Phrase, pred_id: int) -> str:
    """Renvoie le mot de liaison attaché au prédicat, y compris une locution.

    Les morceaux rattachés par `fixed` sont réunis, par exemple pour
    restituer « pendant que ».
    """
    marques = phrase.dependants(pred_id, {"mark", "cc"})
    if not marques:
        return ""
    m = marques[0]
    parties = [m] + phrase.dependants(m.id, {"fixed"})
    return " ".join(x.lemme.lower() for x in sorted(parties, key=lambda x: x.id))


def _ponctuation(phrase: Phrase, pred_id: int) -> str:
    """Renvoie « : » ou « ; » avant le prédicat, s'il y en a une."""
    for m in phrase.dependants(pred_id, {"punct"}):
        if m.forme in (":", ";") and m.id < pred_id:
            return m.forme
    return ""


def construire_liens(phrases: list[Phrase], ancres: list[tuple[Enonce, Ancrage]]) -> list[Lien]:
    """Repère les liens neutres entre les énoncés et ajoute les liens de saturation.

    Les ancrages indiquent quels mots remplissent les places de sujet et de
    complément. La fonction les indexe d'abord, puis construit les liens :

    1. adjonctions d'adjectifs, de relatives et de compléments du nom ;
    2. liens entre plusieurs énoncés du même prédicat ;
    3. liens entre ensembles et énoncés d'appartenance, et entre variantes
       coordonnées ;
    4. liens entre propositions dans une phrase et entre phrases ;
    5. liens ajoutés par saturation du sujet partagé ou par ordre.

    Le résultat est dédoublonné et ne contient pas de lien d'un énoncé vers
    lui-même. La conversion en codes 1969 ou 1972 est faite ensuite par
    `relier`.
    """
    par_phrase = {p.sent_id: p for p in phrases}
    pp_de = {e.indice: e.PP for e, _ in ancres}

    # Index des énoncés par prédicat et des mots qui apparaissent en position de sujet ou complément.
    principal: dict[tuple[str, int], int] = {}
    suivants: dict[tuple[str, int], list[tuple[int, Ancrage]]] = {}
    en_n1: dict[tuple[str, int], list[int]] = {}
    en_n2: dict[tuple[str, int], list[int]] = {}
    du_nom: list[tuple[int, Ancrage]] = []
    variantes: list[tuple[int, Ancrage]] = []
    appartenances: list[tuple[int, Ancrage]] = []
    for e, a in ancres:
        if a.hote:
            appartenances.append((e.indice, a))
            if a.n1 and (a.phrase, a.n1) not in en_n1:
                en_n1.setdefault((a.phrase, a.n1), []).append(e.indice)
            continue
        if a.coord_de:
            variantes.append((e.indice, a))
            if a.pred and a.rang == 0 and a.n1:
                en_n1.setdefault((a.phrase, a.n1), []).append(e.indice)
        elif a.pred:
            if a.rang == 0:
                principal[(a.phrase, a.pred)] = e.indice
                if a.n1:
                    en_n1.setdefault((a.phrase, a.n1), []).append(e.indice)
            else:
                suivants.setdefault((a.phrase, a.pred), []).append((e.indice, a))
        else:
            du_nom.append((e.indice, a))
        if a.n2:
            en_n2.setdefault((a.phrase, a.n2), []).append(e.indice)

    def ancre_du_mot(phrase: Phrase, mot_id: int, profondeur: int = 0) -> tuple[int, str] | None:
        """Trouve l'énoncé où le mot apparaît comme sujet ou complément.

        Si le mot est un membre coordonné, la recherche remonte à la tête
        du groupe nominal. Renvoie l'indice de l'énoncé et sa place, ou
        `None` si le mot n'est ancré dans aucun énoncé.
        """
        cle = (phrase.sent_id, mot_id)
        if cle in en_n1:
            return en_n1[cle][0], "sujet"
        if cle in en_n2:
            return en_n2[cle][0], "complement"
        mot = phrase.mots.get(mot_id)
        if mot and mot.relation == "conj" and mot.tete and profondeur < 5:
            return ancre_du_mot(phrase, mot.tete, profondeur + 1)
        return None

    def adjonction(phrase: Phrase, nom_id: int, droit: int) -> Lien | None:
        """Relie un énoncé issu d'un nom à celui où ce nom est sujet ou complément."""
        trouve = ancre_du_mot(phrase, nom_id)
        if trouve is None or trouve[0] == droit:
            return None
        gauche, place = trouve
        return Lien(gauche, DETERMINATION_SUJET if place == "sujet" else DETERMINATION_COMPLEMENT, droit)

    liens: list[Lien] = []

    # 1. Énoncés tirés d'un nom : l'énoncé principal détermine l'énoncé d'adjectif ou de complément.
    for indice, a in du_nom:
        # Un nom déverbal peut recouvrir un prédicat (« la venue de Jean ») : lien de type QUE (LG11).
        if a.recouvre:
            trouve = ancre_du_mot(par_phrase[a.phrase], a.recouvre)
            if trouve and trouve[0] != indice:
                liens.append(Lien(trouve[0], INFINITIF_DU_NOM, indice, "que"))
            continue
        lien = adjonction(par_phrase[a.phrase], a.nom, indice)
        if lien:
            liens.append(lien)
        # Un énoncé latent dépend aussi de l'énoncé qui décrit son lieu.
        if a.latent:
            lien = adjonction(par_phrase[a.phrase], a.dep, indice)
            if lien:
                liens.append(lien)

    # 2. Pour un prédicat à plusieurs compléments, relie le premier énoncé aux suivants.
    for (sid, pred), autres in suivants.items():
        phrase = par_phrase[sid]
        for indice, a in autres:
            obligatoire = _est_argument(phrase, a.n2, pp_de[indice])
            liens.append(Lien(principal[(sid, pred)],
                              COMPLEMENT_ARGUMENT if obligatoire else COMPLEMENT_CIRCONSTANCIEL, indice))

    # 3. Un énoncé qui porte le symbole d'un ensemble domine ses énoncés d'appartenance.
    for indice, a in appartenances:
        liens.append(Lien(a.hote,
                          DETERMINATION_SUJET if a.place_hote == "sujet" else DETERMINATION_COMPLEMENT,
                          indice))

    # 4. Relie les énoncés créés en dissociant une coordination, puis leurs compléments éventuels.
    par_pred_n1: dict[tuple[str, int, int], int] = {}
    for e, a in ancres:
        if a.pred and a.rang == 0 and a.n1:
            par_pred_n1.setdefault((a.phrase, a.pred, a.n1), e.indice)
    for indice, a in variantes:
        liens.append(Lien(a.coord_de, COORDINATION, indice, a.coord_marqueur or "et"))
        if a.pred and a.rang > 0:
            premier = par_pred_n1.get((a.phrase, a.pred, a.n1))
            if premier and premier != a.coord_de:
                obligatoire = _est_argument(par_phrase[a.phrase], a.n2, pp_de[indice])
                liens.append(Lien(premier,
                                  COMPLEMENT_ARGUMENT if obligatoire else COMPLEMENT_CIRCONSTANCIEL,
                                  indice))

    # 5. Repère les relations entre propositions dans une même phrase.
    ancrage_de = {e.indice: a for e, a in ancres}
    for (sid, pred), droit in principal.items():
        phrase = par_phrase[sid]
        mot = phrase.mots[pred]
        a_droit = ancrage_de[droit]
        # Grew a déjà indiqué le type de jonction et le prédicat qui la gouverne.
        if a_droit.jonction and (sid, a_droit.hote_pred) in principal:
            liens.append(Lien(principal[(sid, a_droit.hote_pred)], JONCTION, droit, a_droit.jonction))
            continue
        if mot.tete == 0:
            continue
        relation = mot.relation.split(":")[0]
        forme = mot.traits.get("VerbForm")
        tete = phrase.mots[mot.tete]

        if relation in ("acl", "advcl") and forme == "Part" and not _marqueur(phrase, pred):
            # Un participe sans marqueur peut qualifier un nom : il lui est adjoint.
            nom_id = mot.tete if relation == "acl" else (tete and _sujet_id(phrase, tete.id))
            if nom_id:
                lien = adjonction(phrase, nom_id, droit)
                if lien:
                    liens.append(lien)
            continue
        if mot.relation == "acl:relcl":
            lien = adjonction(phrase, mot.tete, droit)
            if lien:
                liens.append(lien)
            continue
        if relation == "acl" and forme == "Inf":
            trouve = ancre_du_mot(phrase, mot.tete)
            if trouve:
                liens.append(Lien(trouve[0], INFINITIF_DU_NOM, droit, _marqueur(phrase, pred)))
            continue

        # Remonte jusqu'au prédicat principal et repère la construction de conséquence éventuelle.
        degre = tete.lemme.lower() in MOTS_DEGRE
        while (sid, tete.id) not in principal and tete.tete != 0:
            tete = phrase.mots[tete.tete]
        if (sid, tete.id) not in principal:
            continue
        gauche = principal[(sid, tete.id)]
        marqueur = _marqueur(phrase, pred)
        if degre and marqueur == "que":
            liens.append(Lien(gauche, CONSEQUENCE, droit, "si…que"))
        elif relation == "conj":
            liens.append(Lien(gauche, COORDINATION, droit, marqueur or ","))
        elif relation == "parataxis":
            liens.append(Lien(gauche, ARRET, droit, _ponctuation(phrase, pred) or ","))
        elif relation in ("advcl", "ccomp") and marqueur:
            liens.append(Lien(gauche, SUBORDINATION, droit, marqueur))

    # 6. Les variantes coordonnées héritent de certains liens de leur énoncé de base.
    base_de = {indice: a.coord_de for indice, a in variantes}
    derives: dict[int, list[int]] = {}
    for indice, base in base_de.items():
        racine = base
        while racine in base_de:
            racine = base_de[racine]
        derives.setdefault(racine, []).append(indice)
    for lien in list(liens):
        if lien.type in (DETERMINATION_SUJET, DETERMINATION_COMPLEMENT, SUBORDINATION,
                         CONSEQUENCE, INFINITIF_DU_NOM, ARRET, JONCTION):
            for variante in derives.get(lien.droit, []):
                liens.append(Lien(lien.gauche, lien.type, variante, lien.marqueur))

    # 7. Relie l'énoncé principal de la première phrase à l'énoncé principal
    #    de chaque phrase suivante (annexe I : 1 φ2 7, 1 φ2 17, 1 φ2 18).
    racines = []
    for p in phrases:
        racine = next((m.id for m in p.mots.values() if m.tete == 0), None)
        if racine is not None and (p.sent_id, racine) in principal:
            racines.append(principal[(p.sent_id, racine)])
    for droit in racines[1:]:
        liens.append(Lien(racines[0], ARRET, droit, "."))

    # 8. Saturation du sujet partagé : un prédicat coordonné reçoit aussi les liens de détermination
    #    du sujet commun.
    coordonnes: dict[int, list[int]] = {}
    for lien in liens:
        if lien.type == COORDINATION:
            coordonnes.setdefault(lien.gauche, []).append(lien.droit)
    for lien in list(liens):
        if lien.type == DETERMINATION_SUJET:
            for autre in coordonnes.get(lien.gauche, []):
                if _meme_sujet(ancres, lien.gauche, autre):
                    liens.append(Lien(autre, DETERMINATION_SUJET, lien.droit, saturation=True))

    # 9. Saturation par l'ordre : ajoute un lien entre énoncés qui ont le même énoncé dominant.
    dependants: dict[int, list[int]] = {}
    for lien in liens:
        dependants.setdefault(lien.gauche, []).append(lien.droit)
    for gauche, droits in dependants.items():
        droits = sorted(set(droits))
        for x, y in zip(droits, droits[1:]):
            liens.append(Lien(x, ORDRE, y, saturation=True))

    # Supprime les doublons et les liens réflexifs, en conservant l'ordre de création.
    vus, uniques = set(), []
    for lien in liens:
        cle = (lien.gauche, lien.type, lien.droit)
        if cle not in vus and lien.gauche != lien.droit:
            vus.add(cle)
            uniques.append(lien)
    return uniques


def _meme_sujet(ancres: list[tuple[Enonce, Ancrage]], i: int, j: int) -> bool:
    """Indique si deux énoncés ont le même mot ancré en position de sujet."""
    par_indice = {e.indice: a for e, a in ancres}
    return bool(par_indice[i].n1) and (par_indice[i].phrase, par_indice[i].n1) == (par_indice[j].phrase, par_indice[j].n1)


def _sujet_id(phrase: Phrase, pred_id: int) -> int:
    """Renvoie l'ID du nom ou du pronom sujet du prédicat, ou `0` s'il n'en a pas."""
    for m in phrase.dependants(pred_id, {"nsubj", "nsubj:pass"}):
        if m.upos in ("NOUN", "PROPN", "PRON"):
            return m.id
    return 0


def relier(phrases: list[Phrase], ancres: list[tuple[Enonce, Ancrage]], codage: str = "1969") -> list[RelationBinaire]:
    """Construit les relations binaires dans la notation demandée.

    `construire_liens` repère les liens sans dépendre du codage. Cette
    fonction les convertit ensuite en opérateurs de 1969 ou en codes de
    1972 et renvoie les `RelationBinaire` correspondantes.
    """
    noter = NOTATIONS[codage]
    relations = []
    for lien in construire_liens(phrases, ancres):
        code = noter(lien)
        if code is not None:
            relations.append(RelationBinaire(lien.gauche, code, lien.droit, saturation=lien.saturation))
    return relations
