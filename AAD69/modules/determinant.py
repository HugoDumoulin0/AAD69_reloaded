"""Étape 2c — Codes des déterminants (cases D1 et D2) et case ADV.

À quoi sert ce module ?
---------------------
Dans un énoncé de Pêcheux, le déterminant n'est pas écrit en toutes lettres : il est remplacé par
un CODE qui dit comment le nom est déterminé. D1 est le code du déterminant de N1 (le sujet), D2
celui de N2/3 (le complément). « Le facteur perdit une lettre » donne D1 = L (défini singulier) et
D2 = U (indéfini singulier). Ce module calcule ces codes ; il remplit aussi la case ADV
(l'adverbe du verbe).

Il est appelé par l'extraction (extraction_grew.py) pour chaque nom qui va dans une case N1 ou
N2/3.

Les codes
---------
Ils sont calculés à partir des traits UD du déterminant (voir conllu.py : Definite = Def/Ind,
PronType = Dem, Number = Sing/Plur) :

| Déterminant              | Singulier | Pluriel | Source                                           |
|--------------------------|-----------|---------|--------------------------------------------------|
| défini (le, la, les)     | L         | LS      | 1969 p. 114 « fléchage » ; 1972 p. 20 (§ 3.1412) |
| indéfini (un, une, des)  | U         | DS      | 1969 p. 114 « extraction » ; 1972 p. 20           |
| tout, toute(s)           | TL        | TS      | 1969 p. 114 « balayage » — absent du tableau 1972 |
| démonstratif (ce, ces)   | C         | CS      | 1972 p. 20 (§ 3.1412)                            |
| nombre (deux soldats)    | lemme du nombre en MAJUSCULES ; seul DEUX est attesté (1969, énoncé 16, p. 117) — généralisation construite |
| pas de déterminant       | Ø         | Ø       | 1969 annexe I ; 1972 p. 20                       |

Nom déjà présent dans un autre énoncé (sujet hérité) : Ø en 1969, R en 1972
(1969 : « Ø valet encadrer », énoncé 16, p. 117 ; 1972 : « R METEO », p. 20).
Les autres déterminants (possessifs…) gardent leur lemme (« son », « notre »…) —
construit : Pêcheux n'atteste ni possessif ni nombre autre que DEUX.

Nom rétabli à la place d'une anaphore (anaphores.py, trait Anaphore) :
- relatif (« le chat qui dort ») : comme un sujet hérité, Ø en 1969, R en 1972 (AN4) ;
- pronom personnel (« Un enfant la trouva ») : L / LS en 1969 (annexe I, énoncés 31 et 34 :
  « Elles » -> « LS tarte », p. 117), R en 1972 (manuel § 3.1412, p. 20 : nom déjà
  déterminé) (AN5).
  NB : l'annexe I n'est pas cohérente sur ce point (énoncé 1 : « ils » -> R ; énoncés 21
  et 25 : « lapin » rétabli -> Ø, alors que les énoncés 20 et 23 donnent L). AN5 suit
  les énoncés 31 et 34.

U1 et U2 : « une main… l'autre (main) »
---------------------------------------
Quand un texte oppose « un X » et « l'autre X », on numérote les deux pour ne pas les confondre :
U2 pour « l'autre » (annexe I, énoncé 26 : « rouleau ε dans U2 main », p. 117), U1 pour le
premier « un X » quand le même nom revient plus loin sous « l'autre X » (énoncés 21 et 22 :
« dans U1 main », p. 117). Si « l'autre » est employé seul (« dans l'autre »), c'est
anaphores.py qui rétablit le nom et pose le trait Anaphore = Autre, qui donne aussi U2.
NB : pour la même main, l'annexe I écrit U (énoncé 25) puis U2 (énoncé 26) ; et l'énoncé 27
note « U2 table » sans paire « un/l'autre » — le livre ne l'explique pas. Le code suit
l'énoncé 26 ; l'énoncé 27 sortira « U table ».

Ordre des vérifications dans `code_determinant`
-----------------------------------------------
L'ordre compte : le premier cas qui s'applique donne le code.
1. anaphore rétablie (Autre, Prs, Rel) ;
2. nom déjà mentionné (sujet hérité) ;
3. « l'autre X » après « un X » : U2 ;
4. « tout » (avant le déterminant, parce que « tout le paquet » a aussi un « le ») ;
5. le déterminant : démonstratif, défini, indéfini, sinon son lemme ;
6. un nombre (nummod) ;
7. rien : Ø.
"""

from __future__ import annotations

from .conllu import Mot, Phrase
from .modele import VIDE

# Adverbes qui ne vont pas dans la case ADV (annexe IV, p. 128 sqq
# les adverbes, p. 130) : listes dans lexique.py.
# Ré-exportées ici sous le même nom (d'où le noqa : importées mais pas toutes utilisées ici).
from .lexique import ADVERBES_DEGRE, ADVERBES_LIEU_TEMPS, ADVERBES_MODALITE_ASPECT, ADVERBES_NEGATION  # noqa: E402,F401


# --- U1 / U2 : « un X … l'autre X » ------------------------------------------------------------

def _porte_autre(phrase: Phrase, nom: Mot) -> bool:
    """Le nom est-il « l'autre X » ? Il a parmi ses dépendants « autre » ET un article défini."""
    enfants = phrase.dependants(nom.id)
    return (any(m.lemme.lower() == "autre" for m in enfants)
            and any(m.relation == "det" and
                    (m.traits.get("Definite") == "Def" or m.lemme == "le") for m in enfants))


def _precede_de_un(phrase: Phrase, nom: Mot) -> bool:
    """Le même nom (même lemme) apparaît-il plus tôt dans la phrase avec « un / une » (indéfini
    singulier) ? Sert à reconnaître la paire « une main… l'autre main »."""
    return any(m.id < nom.id and m.lemme.lower() == nom.lemme.lower()
               and any(d.relation == "det" and d.traits.get("Definite") == "Ind"
                       and d.traits.get("Number", "Sing") == "Sing"
                       for d in phrase.dependants(m.id))
               for m in phrase.mots.values())


def _suivi_de_l_autre(phrase: Phrase, nom: Mot) -> bool:
    """Le même nom apparaît-il plus loin dans la phrase sous la forme « l'autre X » ?"""
    return any(m.id > nom.id and m.lemme.lower() == nom.lemme.lower() and _porte_autre(phrase, m)
               for m in phrase.mots.values())


def _nombre(det: Mot, nom: Mot) -> str:
    """Singulier ou pluriel : le trait Number du déterminant, à défaut celui du nom, à défaut
    singulier (quand aucun des deux n'a le trait)."""
    return det.traits.get("Number") or nom.traits.get("Number") or "Sing"


# --- D1, D2 -----------------------------------------------------------------------------------

def code_determinant(phrase: Phrase, nom: Mot, codage: str = "1969", deja_mentionne: bool = False) -> str:
    """Le code du déterminant de `nom` (case D1 si le nom est N1, D2 s'il est N2/3).

    - `codage` : "1969" (livre) ou "1972" (manuel) ; les deux diffèrent pour un nom déjà
      mentionné (Ø / R) et pour une anaphore pronominale (L / R).
    - `deja_mentionne` : True quand l'extraction sait que ce nom a déjà été posé dans un autre
      énoncé (sujet repris par un verbe coordonné, par exemple).

    Les cas sont vérifiés dans l'ordre donné dans le docstring du module.
    """
    # 1. nom rétabli à la place d'une anaphore (trait posé par anaphores.py)
    anaphore = nom.traits.get("Anaphore")
    if anaphore == "Autre":                    # « dans l'autre » -> U2 main
        return "U2"
    if anaphore == "Prs":                      # pronom personnel : L / LS en 1969, R en 1972 (AN5)
        return "R" if codage == "1972" else ("LS" if nom.traits.get("Number") == "Plur" else "L")
    if anaphore == "Rel":                      # relatif : comme un nom déjà mentionné (AN4)
        deja_mentionne = True
    # 2. nom déjà présent dans un autre énoncé
    if deja_mentionne:
        return "R" if codage == "1972" else VIDE
    # 3. « l'autre X » après « un X »
    if _porte_autre(phrase, nom) and _precede_de_un(phrase, nom):
        return "U2"

    enfants = [m for m in phrase.mots.values() if m.tete == nom.id]
    # 4. « tout » : avant le déterminant, car « tout le paquet » a aussi « le ».
    # Stanza analyse parfois « tout » comme adjectif (amod) à côté de « le ».
    if any(m.lemme == "tout" for m in enfants if m.relation in ("det", "amod")):
        tout = next(m for m in enfants if m.lemme == "tout")
        return "TS" if _nombre(tout, nom) == "Plur" else "TL"

    # 5. le déterminant (le premier, s'il y en a plusieurs)
    dets = [m for m in enfants if m.relation == "det"]
    if dets:
        det = dets[0]
        pluriel = _nombre(det, nom) == "Plur"
        # Les traits UD d'abord ; le lemme seulement si les traits manquent (autre analyseur).
        if det.traits.get("PronType") == "Dem" or det.lemme == "ce":
            return "CS" if pluriel else "C"
        if det.traits.get("Definite") == "Def" or (not det.traits and det.lemme == "le"):
            return "LS" if pluriel else "L"
        if det.traits.get("Definite") == "Ind" or (not det.traits and det.lemme == "un"):
            if not pluriel and _suivi_de_l_autre(phrase, nom):     # « une main… l'autre main » : U1
                return "U1"
            return "DS" if pluriel else "U"
        return det.lemme                       # possessif et autres : le lemme tel quel

    # 6. un nombre : « deux soldats » -> DEUX
    nombres = [m for m in enfants if m.relation == "nummod"]
    if nombres:
        return nombres[0].lemme.upper()
    # 7. pas de déterminant
    return VIDE


# --- ADV --------------------------------------------------------------------------------------

def nom_de_locution_adverbiale(phrase: Phrase, adv: Mot) -> Mot | None:
    """Si l'adverbe est construit avec « de » + nom (« près du Roi », « loin du village »),
    renvoie ce nom ; sinon None.

    Un tel adverbe n'est pas un adverbe de manière : avec son nom, il forme un complément de lieu
    (PP = « près de », N2/3 = roi, E2-14). Il ne va donc pas dans la case ADV (voir `adverbe`).
    """
    if adv.upos != "ADV":
        return None
    for mot in phrase.mots.values():
        if (mot.tete == adv.id and mot.upos in ("NOUN", "PROPN", "PRON")
                and mot.relation.split(":")[0] in ("obl", "nmod")
                and any(c.lemme.lower() == "de" for c in phrase.dependants(mot.id, {"case"}))):
            return mot
    return None


def adverbe(phrase: Phrase, verbe: Mot) -> str:
    """L'adverbe du verbe qui va dans la case ADV (« Alice mangea lentement » -> lentement), ou Ø.

    On prend le premier adverbe (advmod, ADV) du verbe, sauf :
    - ceux des listes de lexique.py, qui vont ailleurs (annexe IV) : négation (-> F), modalité et
      aspect (-> F), lieu et temps (-> N2/3), degré (portent sur un adjectif) ;
    - tout adverbe marqué négatif par Stanza (Polarity = Neg) ;
    - les adverbes construits avec « de » + nom (« près du Roi »), voir `nom_de_locution_adverbiale`.
    """
    exclus = ADVERBES_NEGATION | ADVERBES_MODALITE_ASPECT | ADVERBES_LIEU_TEMPS | ADVERBES_DEGRE
    for m in phrase.mots.values():
        if m.tete == verbe.id and m.relation == "advmod" and m.upos == "ADV" \
                and nom_de_locution_adverbiale(phrase, m) is None \
                and m.traits.get("Polarity") != "Neg" and m.lemme.lower() not in exclus:
            return m.lemme
    return VIDE