"""Étape 2b — La forme de l'énoncé (case F).

À quoi sert ce module
---------------------
La case F d'un énoncé code la forme du verbe : voix (actif / passif), négation, interrogation,
mode et temps. « Le facteur perdit la lettre » : passé simple, actif, affirmatif. Les deux
versions ne l'écrivent pas de la même façon :
- 1969 : F1 (passé simple) … F5 (passif) ;
- 1972 : un code à 4 chiffres, ici 0004.
Ce module calcule ce code ; il est appelé par l'extraction (extraction.py et extraction_grew.py)
pour chaque prédicat.

Deux temps pour coder la forme
----------
On procède en deux temps, pour ne pas choisir trop tôt entre 1969 et 1972 :

1. `analyser_forme` décrit la forme du verbe de façon NEUTRE, à partir des traits UD
   (voix, polarité, interrogation, mode, temps), dans un objet `FormeVerbale` ;
2. deux fonctions traduisent cette description dans l'une ou l'autre notation :
   - `codage_1969` : F1 … F5 (Pêcheux 1969, annexe I, p. 114) ;
   - `codage_1972` : code à 4 chiffres (Haroche & Pêcheux 1972, p. 18).
`CODAGES` (en fin de fichier) donne la bonne fonction selon la version : CODAGES["1972"](forme).

Ainsi, une même analyse sert aux deux versions, et une correction de l'analyse (le passé simple
mal lu par Stanza, par exemple) vaut pour les deux.

Ce que l'on ne traite pas dans F : modalités adverbiales et aspect (annexe IV : voir
lexique.py, ADVERBES_MODALITE_ASPECT), emphase.

Pouvoir / devoir ne sont pas codés dans F : l'extraction Grew en fait deux énoncés
reliés par PRG1 — « (JULES POUVOIR 0 0) + (JULES VENIR A PARIS) » (manuel 1972,
§ 3.1422221, p. 27 et 28 ; « devoir » est dans la liste PRG1, § 3.14223, p. 29), la
modalité étant « extérieure à la ligne B du tableau ». C'est le traitement de 1972 :
la même propriété — le référent de N° identique à celui de N — y motive le découpage
en deux énoncés, la modalité devenant la jonction entre eux, hors de F. En 1969, au
contraire, la modalité du possible et du nécessaire est une marque de l'énoncé dans
F, sans découpage : « Je peux venir demain » = « Je viens demain + modalité du
possible » (livre 1969, p. 75) ; le livre précise que la transformation T₁
(rétablissement des propositions latentes) ne s'applique pas à pouvoir / devoir, le
sujet sous-entendu de l'infinitif étant le même que celui du verbe porteur de la
modalité — c'est ce qui les distingue de « vouloir », qui admet « Je veux que tu… ».

*L'implémentation suit pour l'instant 1972 dans les deux versions (PRG1 partout) ;
codage_1969 n'a donc pas de forme de modalité. Qu'en pensez-vous ?*
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .conllu import Mot, Phrase
from .modele import VIDE

# Reconnaître les deux sortes d'auxiliaires : celui de temps (« a perdu »,
# aux:tense — ou « aux » selon l'analyseur) donne le mot qui porte le temps ;
# celui du passif (« fut perdue », aux:pass) marque la voix.
RELATIONS_AUX_TEMPS = {"aux:tense", "aux"}
RELATIONS_AUX_PASSIF = {"aux:pass"}
from .lexique import ADVERBES_NEGATION as LEMMES_NEGATION, VERBES_ETRE 

# Traduction des traits UD en noms de temps et de mode. Deux tables de
# temps, parce que le même trait Tense change de sens selon le porteur :
# « perd » (Pres) = présent, mais le « a » de « a perdu » (Pres) = passé
# composé. C'est analyser_forme (étape 3) qui choisit la table.
TEMPS_SIMPLE = {"Pres": "present", "Imp": "imparfait", "Fut": "futur", "Past": "passe_simple"}
TEMPS_COMPOSE = {"Pres": "passe_compose", "Imp": "plus_que_parfait", "Fut": "futur_anterieur", "Past": "passe_anterieur"}
MODE = {"Ind": "indicatif", "Cnd": "conditionnel", "Sub": "subjonctif", "Imp": "imperatif"}


@dataclass(frozen=True)
class FormeVerbale:
    """La forme du verbe, sans notation de 1969 ni de 1972 (voir le docstring du module).

    Un énoncé à copule n'a pas de verbe : sa case V est ε en 1969, E en 1972
    (« le Lapin Blanc » -> « lapin ε blanc », annexe I, p. 117). Il n'y a donc
    rien à analyser : `copule` n'est jamais posé par `analyser_forme` (qui lit
    les traits d'un verbe), mais par l'extraction (sous-étape 2d), qui crée
    directement FormeVerbale(copule=True) — les autres champs gardent leurs
    valeurs par défaut. Les deux codages en tirent le reste : F4 en 1969
    (les 17 énoncés à copule de l'annexe I sont tous F4), 0000 en 1972
    (« R METEO E Ø + Ø NATIONAL », manuel, p. 20).
    """

    voix: str = "actif"           # actif | passif
    polarite: str = "affirmatif"  # affirmatif | negatif
    interrogatif: bool = False
    mode: str | None = None       # indicatif | conditionnel | subjonctif | imperatif | infinitif | participe
    temps: str | None = None      # present | imparfait | futur | passe_simple | passe_compose | …
    copule: bool = False          # énoncé à copule (sous-étape 2d)


def _dependants(phrase: Phrase, mot: Mot, relations: set[str]) -> list[Mot]:
    """Les mots qui dépendent de `mot` (leur chef) et qui portent l'une des
    étiquettes demandées, écrite au mot près.

    Dans l'arbre de Stanza, chaque mot porte une étiquette vers son chef :
    dans « la lettre fut perdue », « fut » dépend de « perdue » avec
    l'étiquette aux:pass — un auxiliaire (base « aux ») du passif
    (sous-type « pass »). Une même base cache des rôles opposés :
    aux:tense (temps), aux:pass (passif), aux (sans précision).

    Différence avec Phrase.dependants, qui cherche en large : là, demander
    « aux » attrape aussi « aux:pass » et « aux:tense ». Ici, « aux » ne
    retourne que les « aux » tout courts. Sans cette égalité stricte,
    RELATIONS_AUX_TEMPS (qui contient le « aux » nu) attraperait « fut »
    dans « fut perdue » : l'auxiliaire du passif serait pris pour un
    auxiliaire de temps, et l'énoncé deviendrait passé antérieur au lieu
    de passé simple passif.
    """
    return [m for m in phrase.mots.values() if m.tete == mot.id and m.relation in relations]


def _participe_passif_seul(phrase: Phrase, verbe: Mot, aux_temps: list[Mot]) -> bool:
    """E2-24 : un participe passé employé sans auxiliaire (« une foule […], composée de… ») est un
    passif, sauf pour les verbes qui se conjuguent avec « être » (« arrivé à Paris »). Sert quand
    l'analyseur ne donne pas le trait Voice=Pass (annexe I, énoncé 9 : « composer », F5).

    Attesté deux fois dans l'annexe I (livre 1969, p. 117) : énoncés 9 (« composer ») et
    27 (« était posé »), tous deux F5 — aucun des deux n'est un verbe qui se conjugue avec
    « être » : l'exception VERBES_ETRE est construite (décision E2-24).

    Conditions, toutes nécessaires : participe passé ; ni auxiliaire ni copule ; employé comme
    épithète, subordonnée, ou coordonné (acl, advcl, conj, amod) ; verbe absent de VERBES_ETRE.
    """
    return (verbe.traits.get("VerbForm") == "Part" and verbe.traits.get("Tense") == "Past"
            and not aux_temps and not _dependants(phrase, verbe, RELATIONS_AUX_PASSIF)
            and not _dependants(phrase, verbe, {"cop"})
            and verbe.relation.split(":")[0] in {"acl", "advcl", "conj", "amod"}
            and verbe.lemme.lower() not in VERBES_ETRE)


TERMINAISONS_PASSE_SIMPLE_ER = ("a", "as", "âmes", "âtes", "èrent")


def _passe_simple_en_er(verbe: Mot) -> bool:
    """Stanza analyse parfois au présent un passé simple rare (« Le facteur égara la
    lettre » : Tense=Pres). Pour un verbe en -er, une forme en -a, -as, -âmes, -âtes, -èrent ne
    peut pas être un présent (le présent finit en -e, -es, -ons, -ez, -ent). « aller » est exclu
    (« il va », « tu vas » sont des présents)."""
    lemme, forme = verbe.lemme.lower(), verbe.forme.lower()
    return (lemme.endswith("er") and lemme != "aller" and verbe.traits.get("Mood", "Ind") == "Ind"
            and forme.endswith(TERMINAISONS_PASSE_SIMPLE_ER))


def analyser_forme(phrase: Phrase, verbe: Mot) -> FormeVerbale:
    """Décrit la forme de `verbe` (voix, polarité, interrogation, mode, temps), sans notation.

    Étapes :
    1. la voix : passif s'il y a un auxiliaire de passif (« fut perdue »), le trait Voice=Pass, ou
       un participe passif employé seul (E2-24, l'annexe I) ;
    2. cas particulier : un participe coordonné à un verbe, sans auxiliaire (« était enchaîné et
       encadré ») prend le temps et le mode de ce verbe ;
    3. le mot qui porte le temps et le mode : le premier auxiliaire, sinon la copule, sinon le
       verbe lui-même (« a perdu » : c'est « a » qui dit le temps) ;
    4. mode et temps, d'après les traits de ce mot (correction E2-26 du passé simple) ;
    5. la négation : « ne… pas » qui dépend du verbe (le repli par lemme exige un « ne » dans
       la phrase : « elle mangea plus de tartes » n'est pas une négation) ;
    6. l'interrogation : le verbe principal d'une phrase qui finit par « ? ».
    """
    # 1. voix
    aux_temps = _dependants(phrase, verbe, RELATIONS_AUX_TEMPS)
    aux_passif = _dependants(phrase, verbe, RELATIONS_AUX_PASSIF)
    est_passif = (bool(aux_passif) or verbe.traits.get("Voice") == "Pass"
                  or _participe_passif_seul(phrase, verbe, aux_temps))

    # 2. Participe sans auxiliaire, coordonné à un verbe (« était enchaîné et encadré ») :
    # il partage le temps et le mode de ce verbe. Attesté : énoncés 14 et 16 de l'annexe I,
    # tous deux F5 (livre 1969, p. 117).
    if not aux_temps and not aux_passif and verbe.relation == "conj" and verbe.traits.get("VerbForm") == "Part":
        tete = phrase.mots[verbe.tete]
        if tete.upos == "VERB":
            forme_tete = analyser_forme(phrase, tete)
            return replace(forme_tete, voix="passif" if est_passif else forme_tete.voix)

    # 3. Le verbe qui porte le temps et le mode : le premier auxiliaire s'il y en a un.
    # Avec un auxiliaire de temps, on lit les temps composés (« a perdu » = passé composé).
    if aux_temps:
        porteur, table_temps = aux_temps[0], TEMPS_COMPOSE
    elif aux_passif:
        porteur, table_temps = aux_passif[0], TEMPS_SIMPLE
    elif copules := _dependants(phrase, verbe, {"cop"}):
        porteur, table_temps = copules[0], TEMPS_SIMPLE  # « Elles étaient appétissantes »
    else:
        porteur, table_temps = verbe, TEMPS_SIMPLE

    # 4. mode et temps
    forme_verbale = porteur.traits.get("VerbForm")
    if forme_verbale == "Inf":
        mode, temps = "infinitif", None
    elif forme_verbale == "Part":
        mode, temps = "participe", None
    else:
        mode = MODE.get(porteur.traits.get("Mood"), "indicatif")   # sans trait Mood : indicatif
        temps = table_temps.get(porteur.traits.get("Tense"))
        if temps == "present" and _passe_simple_en_er(porteur):
            temps = "passe_simple"

    # 5. négation : signifiant discontinu « ne...pas/jamais/plus... » (annexe IV, p. 130 :
    # les particules « ne sont ni positives ni négatives par elles-mêmes »). Le repli par
    # lemme exige un « ne » dans la phrase.
    ne_dans_phrase = any(p.lemme.lower() == "ne" for p in phrase.mots.values())
    negatif = any(
        m.traits.get("Polarity") == "Neg"
        or (m.lemme in LEMMES_NEGATION and ne_dans_phrase)
        for m in _dependants(phrase, verbe, {"advmod"})
    )
    # 6. interrogation : seulement le verbe racine, et seulement si la dernière ponctuation est « ? »
    derniers = [m for m in phrase.mots.values() if m.upos == "PUNCT"]
    interrogatif = verbe.tete == 0 and bool(derniers) and derniers[-1].forme == "?"

    return FormeVerbale(
        voix="passif" if est_passif else "actif",
        polarite="negatif" if negatif else "affirmatif",
        interrogatif=interrogatif,
        mode=mode,
        temps=temps,
    )


def codage_1969(f: FormeVerbale) -> str:
    """F1 passé simple, F2 imparfait, F3 subjonctif (et infinitif), F4 copule, F5 passif.

    Le tableau « Formes de F » (p. 114): passé simple
    (F1) et imparfait (F2) sous « actif, indicatif passé » ; « passif ou
    réfléchi » (F5) ; subjonctif (F3) ; copule (F4). L'ordre des tests suit
    ce tableau : la voix se lit avant le temps, donc un passif est F5 quel
    que soit son temps (énoncé 14 : « était enchaîné », imparfait).

    Pêcheux précise que ces formes ne valent que pour l'exemple d'Alice
    (p. 113). Le code traduit cette réserve ainsi : les temps absents de
    la table donnent VIDE (présent, futur, conditionnel) ; la négation,
    absente elle aussi, n'est pas encore codée en 1969 — l'énoncé garde
    la forme de sa version affirmative (« il ne perdait pas » -> F2).

    Qu'en pensez vous de ces decisions si dessous ?

    - Infinitif : absent du tableau Formes de F (p.114).
      F3-infinitif repose uniquement sur NOTRE TRANSCRIPTION de l'annexe I (énoncé 34 :
      « manger », F3) ;

    - Pronominal : le tableau met « passif ou réfléchi » en F5,
      mais l'annexe I code « se tenait » F2 (énoncé 18) : le livre se
      contredit d'une page à l'autre. On suit l'annexe I : le pronominal
      prend le temps du verbe, jamais F5.
    """
    if f.copule:
        return "F4"
    if f.voix == "passif":
        return "F5"
    if f.mode in ("subjonctif", "infinitif"):
        return "F3"
    if f.mode == "indicatif" and f.temps == "passe_simple":
        return "F1"
    if f.mode == "indicatif" and f.temps == "imparfait":
        return "F2"
    return VIDE


# Tableau du manuel 1972, p. 18 : chiffres du mode (3e chiffre) et du temps (4e chiffre).
CODE_MODE_1972 = {"indicatif": "0", "conditionnel": "1", "subjonctif": "2", "imperatif": "3"}
CODE_TEMPS_1972 = {
    "present": "0", "imparfait": "1", "futur": "2", "passe_compose": "3",
    "passe_simple": "4", "futur_anterieur": "5", "plus_que_parfait": "6",
}


def codage_1972(f: FormeVerbale) -> str:
    """Code à 4 chiffres : voix, affirmation/négation/interrogation, mode, temps (manuel 1972, p. 18).

    1er chiffre, voix : 0 actif, 1 passif.
    2e chiffre, statut : 0 affirmatif, 1 négatif, 2 interrogatif, 3 interrogatif et négatif.
    3e chiffre, mode : CODE_MODE_1972. 4e chiffre, temps : CODE_TEMPS_1972.
    Exemples : « Le facteur perdit la lettre » -> 0004 ; « La lettre ne fut pas perdue » -> 1104.

    Un « x » marque une valeur absente du tableau de 1972 (infinitif, participe, passé antérieur).

    Qu'en pensez vous ?
    """
    if f.copule:
        return "0000"  # copule implicite : « R METEO E Ø * Ø NATIONAL » (manuel 1972, p. 20)
    voix = "1" if f.voix == "passif" else "0"
    statut = {(False, False): "0", (True, False): "1", (False, True): "2", (True, True): "3"}[
        (f.polarite == "negatif", f.interrogatif)       # (négatif ?, interrogatif ?)
    ]
    mode = CODE_MODE_1972.get(f.mode, "x")
    temps = CODE_TEMPS_1972.get(f.temps, "x")
    return voix + statut + mode + temps


# La fonction de codage selon la version : CODAGES[codage](forme).
CODAGES = {"1969": codage_1969, "1972": codage_1972}