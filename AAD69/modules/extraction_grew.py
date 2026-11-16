"""
Ce transforme les phrases analysées par Stanza (arbres de dépendances, voir conllu.py) en énoncés
à 8 cases (F D1 N1 V ADV PP D2 N2/3, voir modele.py). Le travail est partagé en deux :

1. Grew (Bruno Guillaume, Inria ; <https://grew.fr>) applique des RÈGLES DE RÉÉCRITURE à l'arbre.
   Une règle = un motif à chercher dans l'arbre + des commandes (changer une relation, ajouter
   une arête, poser un trait). Les règles sont dans `grew/aad69.grs`, leurs listes de mots dans
   `grew/lexiques/*.lex`. Grew décide de la
   STRUCTURE : quels mots sont des prédicats, qui est sujet ou complément de quoi, quelle
   proposition dépend de quelle autre (IMP, QUE, PRG1, PRG2), quelle forme canonique donner à une
   clivée, un nom propre, un verbe support… Il écrit ces décisions dans l'arbre sous forme
   d'« arêtes profondes » (étiquettes E:suj, E:comp, E:PRG1…) et de traits (pred, S, sujet_vide…).
2. Ce module (Python) lit ce que Grew a écrit et REMPLIT LES 8 CASES : codage de F (forme.py),
   des déterminants (determinant.py), lemmes et prépositions (commun.py), ensembles A1… Il ne
   cherche pas lui-même les arguments dans l'arbre : il lit les arêtes E:.

Deux passes de règles
---------------------
    arbre de Stanza
      -> passe « normaliser » (`normaliser`) : il impersonnel, clivées, noms propres…
      -> anaphores (anaphores.py, linguiste.py(LLM))        <- doivent voir l'arbre déjà normalisé
      -> passe « main » (`extraire_ancre_grew`) : prédicats, syntagmes figés, modalités et
         complétives, énoncés latents, sujets vides, arguments
      -> assemblage des 8 cases (ce module) -> relations (relations.py)
Pourquoi deux passes : un « il » impersonnel (« il faut… ») doit être marqué AVANT la résolution
des anaphores, sinon il serait remplacé par un antécédent (« il faut » -> « ministre falloir »).

"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from .conllu import Mot, Phrase
from .determinant import adverbe, code_determinant
from .commun import (CATEGORIES_NOMINALES, Ancrage, Ensembles, _appartenances, _Terme, est_passif,
                         est_tete_de_locution, lemme_nominal, lemme_verbe, marqueur_coordination, membre_nie,
                         preposition)
from .forme import CODAGES, FormeVerbale, analyser_forme
from .lexique import NOMINALISATIONS, NOMS_LOCUTION
from .modele import VIDE, Enonce

REGLES = Path(__file__).resolve().parent / "grew" / "aad69.grs"
TRAITS_POUR_GREW = ("VerbForm", "Voice", "PronType", "Anaphore", "Preposition", "Number", "Gender", "Person",
                    "Tense", "Mood", "Reflex", "Polarity", "locution", "absorbe", "titre", "ellipse")

_grs = None


class GrewAbsent(RuntimeError):
    """Grew n'est pas installé : on le dit, on ne bascule pas en silence sur l'extraction Python."""

    def __init__(self):
        super().__init__(
            "L'extraction des énoncés utilise Grew, qui demande grewpy et son moteur "
            "grewpy_backend (installation : docs/grew.md).")


def grew_disponible() -> bool:
    """True si Grew est installé et que les règles se chargent (pour l'interface, les tests)."""
    try:
        _grew()
        return True
    except GrewAbsent:
        return False


def _grew():
    """Le système de règles, chargé une fois (le moteur grewpy_backend doit être dans le PATH)."""
    global _grs
    if _grs is None:
        chemins = [Path.home() / ".opam" / "grew" / "bin"]
        opam = shutil.which("opam")
        if opam:
            resultat = subprocess.run([opam, "var", "bin"], capture_output=True, text=True, check=False)
            if resultat.returncode == 0:
                chemins.append(Path(resultat.stdout.strip()))
        path_actuel = os.environ.get("PATH", "").split(os.pathsep)
        nouveaux = [str(chemin) for chemin in chemins
                    if chemin.is_dir() and str(chemin) not in path_actuel]
        if nouveaux:
            os.environ["PATH"] = os.pathsep.join([*nouveaux, os.environ.get("PATH", "")])
        if shutil.which("grewpy_backend") is None:
            raise GrewAbsent()
        try:
            import grewpy
        except ImportError as erreur:
            raise GrewAbsent() from erreur
        grewpy.set_config("ud")
        _grs = grewpy.GRS(str(REGLES))
    return _grs


# ---------------------------------------------------------------------------------------------
# Phrase <-> graphe Grew
# ---------------------------------------------------------------------------------------------
# Ces fonctions font l'aller-retour entre les objets `Phrase` de Python et les graphes CoNLL-U
# traités par Grew. Grew corrige l'arbre et ajoute des informations ; Python reconstruit ensuite
# la phrase et conserve à part les arêtes et les traits qui serviront à fabriquer les énoncés.

def _propre(valeur: str) -> str:
    """Adapte une valeur aux séparateurs réservés du format CoNLL-U utilisé par Grew.

    Les espaces deviennent `_`, `|` devient `+`, `=` devient `-` et une valeur
    vide devient `_`.
    """
    return str(valeur).replace(" ", "_").replace("|", "+").replace("=", "-") or "_"


def vers_conllu(phrase: Phrase) -> str:
    """Convertit une `Phrase` en texte CoNLL-U que Grew peut lire.

    Chaque mot devient une ligne avec son identifiant, sa forme, son lemme,
    sa catégorie, ses traits, sa tête et sa relation. Seuls les traits listés
    dans `TRAITS_POUR_GREW` sont transmis ; les autres restent dans l'objet
    Python. Par exemple, `Anaphore` est transmis, mais `Membres` ne l'est pas.
    La fonction ajoute aussi l'identifiant et le texte de la phrase.
    """
    lignes = [f"# sent_id = {phrase.sent_id}", f"# text = {phrase.texte}"]
    for m in sorted(phrase.mots.values(), key=lambda x: x.id):
        traits = "|".join(f"{k}={_propre(v)}" for k, v in sorted(m.traits.items()) if k in TRAITS_POUR_GREW) or "_"
        lignes.append("\t".join([str(m.id), _propre(m.forme), _propre(m.lemme), m.upos, "_", traits,
                                 str(m.tete), m.relation, "_", "_"]))
    return "\n".join(lignes) + "\n"


def _etiquette(arete: dict) -> str:
    """Recompose l'étiquette d'une relation à partir de ses morceaux Grew.

    Par exemple, `{"1": "obl", "2": "mod"}` devient `obl:mod`.
    """
    return ":".join(arete[k] for k in ("1", "2", "3") if k in arete)


def normaliser(phrases: list[Phrase]) -> list[Phrase]:
    """Applique à chaque phrase la passe Grew qui normalise l'arbre syntaxique.

    Cette passe est faite avant la résolution des anaphores. Elle ne renvoie
    que les phrases réécrites ; les arêtes et traits ajoutés par Grew sont
    récupérés plus tard par `reecrire`.
    """
    return [reecrire(p, "normaliser")[0] for p in phrases]


def reecrire(phrase: Phrase, strategie: str = "main") -> tuple[Phrase, dict[int, dict[str, list[int]]], dict[int, dict]]:
    """Applique une stratégie Grew et reconstruit les résultats sous forme Python.

    Renvoie un triplet :
    1. la phrase avec les catégories, têtes et relations corrigées ;
    2. les arêtes ajoutées par Grew, rangées par tête puis par étiquette ;
    3. les traits ajoutés par Grew, rangés par identifiant de mot.

    Les arêtes ordinaires mettent à jour l'arbre. Les arêtes marquées
    `enhanced=yes` sont conservées séparément pour l'assemblage des énoncés.
    Les traits Grew incluent notamment `pred`, `locution`, `S`, `copule` et
    `emphase`.

    Une règle peut supprimer des mots, par exemple dans une clivée. Ces mots
    ne figurent alors plus dans la phrase renvoyée. Si la tête d'un mot a été
    supprimée, ce mot est rattaché à la première tête encore présente au-dessus
    de lui dans l'arbre.
    """
    # Grew applique la stratégie demandée au graphe construit depuis la phrase.
    grs = _grew()
    import grewpy
    graphe = grs.run(grewpy.Graph(vers_conllu(phrase)), strategie)
    if len(graphe) != 1:
        raise RuntimeError(f"{phrase.sent_id} : les règles donnent {len(graphe)} graphes (attendu : 1)")
    graphe = graphe[0]
    # Les arêtes ordinaires décrivent l'arbre corrigé ; les arêtes E:* sont
    # des informations supplémentaires destinées à l'extraction des énoncés.
    tetes, profondes = {}, {}
    for tete, arete, dep in graphe.triples():
        t, d = int(tete), int(dep)
        if arete.get("enhanced") == "yes":
            profondes.setdefault(t, {}).setdefault("E:" + _etiquette(arete), []).append(d)
        else:
            tetes[d] = (t, _etiquette(arete))
    # Reconstruit la Phrase à partir des mots conservés dans le graphe Grew.
    mots, ajouts = {}, {}
    for i, m in phrase.mots.items():
        # Les règles peuvent supprimer certains mots, notamment les mots
        # grammaticaux d'une tournure clivée.
        if str(i) not in graphe.features:
            continue
        f = graphe.features[str(i)]
        tete, relation = tetes.get(i, (m.tete, m.relation))
        # Si la tête syntaxique a disparu, remonte jusqu'à une tête conservée.
        while tete and str(tete) not in graphe.features:
            tete = phrase.mots[tete].tete if tete in phrase.mots else 0
        traits = dict(m.traits)
        # Ces traits posés par Grew sont réutilisés lors des passes suivantes.
        for cle in ("locution", "absorbe", "titre", "ellipse"):
            if cle in f:
                traits[cle] = f[cle]
        lemme = f.get("lemma", m.lemme)
        # Grew remplace les espaces d'un lemme composé par `_` ; on les restaure.
        if lemme != _propre(m.lemme):
            lemme = lemme.replace("_", " ")
        else:
            lemme = m.lemme
        mots[i] = replace(m, upos=f.get("upos", m.upos), tete=tete, relation=relation, traits=traits, lemme=lemme)
        ajouts[i] = {k: f[k] for k in ("pred", "locution", "S", "sujet_vide", "objet_vide", "copule", "emphase",
                                       "fige")
                     if k in f}
    # Un ordre stable facilite l'assemblage et rend les sorties reproductibles.
    for t in profondes:
        for cle in profondes[t]:
            profondes[t][cle].sort()
    return Phrase(sent_id=phrase.sent_id, texte=phrase.texte, mots=mots), profondes, ajouts


# ---------------------------------------------------------------------------------------------
# Construire les énoncés : remplir leurs huit cases à partir des résultats de Grew
# ---------------------------------------------------------------------------------------------

def _membres(mot: Mot) -> list[str]:
    """Renvoie les membres d'un groupe porté par `mot`, ou son lemme seul.

    Par exemple, un pronom résolu « ils » peut porter les membres
    `enfants|parents` ; la fonction renvoie alors `['enfants', 'parents']`.
    """
    return mot.traits["Membres"].split("|") if mot.traits.get("Membres") else [lemme_nominal(mot)]


def _pp(phrase: Phrase, verbe: Mot, mot: Mot, tete_du_groupe: Mot, ajouts: dict) -> str:
    """Détermine la case PP du complément `mot`.

    Pour un terme coordonné, `tete_du_groupe` est le premier terme ; sa
    relation indique le rôle du groupe. La préposition est choisie ainsi :
    locution reconnue, préposition propre au membre, `*` pour un objet
    direct, ou préposition portée par le groupe. Un complément indirect
    sans préposition reçoit `à` ; `de` devant un verbe passif devient
    `de = par` (E16), annexe I).
    """
    locution = ajouts.get(mot.id, {}).get("locution") or mot.traits.get("locution")
    if locution:
        return f"{locution.lower()} de"
    relation = tete_du_groupe.relation if mot is not tete_du_groupe else mot.relation
    propre = preposition(phrase, mot)
    if mot is not tete_du_groupe and propre != VIDE:
        pp = propre
    elif relation == "obj" or relation.startswith("obj:") or relation == "xcomp":
        pp = "*"
    else:
        pp = preposition(phrase, tete_du_groupe)
        if pp == VIDE and tete_du_groupe.traits.get("Preposition"):
            pp = tete_du_groupe.traits["Preposition"]
        if pp == VIDE and relation == "iobj":          # « je vous propose », « il leur donne » : à
            pp = "à"
    if pp == "de" and est_passif(phrase, verbe):
        pp = "de = par"
    return pp


def _quantifie(profondes: dict, mot: Mot, phrase: Phrase) -> Mot:
    """Renvoie/ récupère le nom réellement compté par un nom de quantité, ou `mot` lui-même.

    Grew relie le nom de quantité à ce qu'il compte avec l'arête `E:quant`.
    Ainsi, dans « toutes sortes de quadrupèdes », la fonction renvoie
    « quadrupèdes » plutôt que « sortes » (annexe I).
    """
    q = profondes.get(mot.id, {}).get("E:quant")
    return phrase.mots[q[0]] if q else mot


def _d2(phrase: Phrase, porteur: Mot, tete_du_groupe: Mot, codage: str) -> str:
    """Trouve le déterminant du complément. Si un membre coordonné n’a pas le sien, il peut reprendre celui du premier membre.
    Le déterminant de la tête est repris quand le membre n'a ni déterminant
    ni numéral, comme « oiseaux » dans « de quadrupèdes et d'oiseaux ».
    """
    d = code_determinant(phrase, porteur, codage)
    if d == VIDE and porteur is not tete_du_groupe and not phrase.dependants(porteur.id, {"det", "nummod"}):
        return code_determinant(phrase, tete_du_groupe, codage)   # « de quadrupèdes et d'oiseaux »
    return d


def _en_ensemble(ensembles: Ensembles | None, codage: str) -> bool:
    """vérifie si le réglage demande de représenter une coordination par un symbole de groupe en 1969.

    En 1972, cette option ne s'applique pas : les termes sont dissociés,
    sauf si une décision les marque comme inséparables.
    """
    return ensembles is not None and ensembles.actifs and codage == "1969"


def _inseparable(phrase, ids) -> bool:
    """vérifie si le linguiste a marqué un groupe comme impossible à séparer, par exemple blanc et noir pour le drapeau.

    Exemple : « blanc et noir » forme une propriété unique. Le groupe est
    alors représenté par un ensemble en 1969 et par une propriété
    intermédiaire en 1972, quel que soit le réglage de coordination.
    """
    return any(phrase.mots[i].traits.get("Inseparable") for i in ids if i in phrase.mots)

#    énoncés construits à partir d’un prédicat 

def _enonces_du_predicat(phrase, p, profondes, ajouts, codage, ensembles: Ensembles | None = None) -> list[dict]:
    """Construit les lignes d'énoncés portées par un verbe ou un attribut.

    Les arêtes et traits de Grew indiquent le prédicat, ses sujets et ses
    compléments. La fonction les convertit en cases : `F`, `D1`, `N1`, `V`,
    `ADV`, `PP`, `D2` et `N2_3`. Elle produit une ligne pour chaque couple
    sujet-complément. Les sujets ou compléments coordonnés peuvent être
    dissociés ou réunis sous un symbole `A1`, selon le codage et le réglage.

    `S` représente une proposition sujet ou complétive ; `X` représente un
    sujet ou objet vide. Une coordination réunie en ensemble reçoit aussi
    des lignes d'appartenance. Enfin, un attribut adjectival avec son propre
    complément peut produire un énoncé supplémentaire (annexe I).

    Les dictionnaires renvoyés contiennent les cases et quelques repères
    internes (`_ancrage`, `_base`, `_hote`) utilisés ensuite pour numéroter
    les énoncés et relier les variantes.
    """
    coder = CODAGES[codage]
    aretes = profondes.get(p.id, {})
    if ajouts.get(p.id, {}).get("copule") == "implicite":     # « rendre obligatoire la prime »
        forme = FormeVerbale(copule=True)
        commun = dict(F=coder(forme), V="être", ADV=VIDE, source=f"{phrase.sent_id}:{p.id}")
    else:
        forme = analyser_forme(phrase, p)
        commun = dict(F=coder(forme), V=lemme_verbe(phrase, p), ADV=adverbe(phrase, p),
                      source=f"{phrase.sent_id}:{p.id}")

    # Prépare les sujets : déterminant, lemme, ID du mot, connecteur et négation.
    sujets = []
    for i in aretes.get("E:suj", []) + aretes.get("E:sujc", []):
        s = phrase.mots[i]
        coordonne = i in aretes.get("E:sujc", [])
        # Un sujet hérité d'un autre prédicat est déjà mentionné dans la phrase.
        herite = s.tete != p.id and not coordonne
        d1 = code_determinant(phrase, s, codage, deja_mentionne=herite)
        for k, lemme in enumerate(_membres(_quantifie(profondes, s, phrase))):
            marque = "" if not sujets and k == 0 else ("et" if k else marqueur_coordination(phrase, s))
            sujets.append((d1, lemme, s.id, marque, membre_nie(phrase, s) if sujets else False))
    app_sujet, symbole_sujet = [], ""
    ids_sujets = aretes.get("E:suj", [])[:1] + aretes.get("E:sujc", [])
    if ensembles is not None and sujets and ids_sujets and (
            _en_ensemble(ensembles, codage) or (len(ids_sujets) > 1 and _inseparable(phrase, ids_sujets))):
        ids = ids_sujets
        premier = phrase.mots[ids[0]]
        if len(ids) > 1:          # « le Roi et la Reine » -> R : ensemble (annexe I, 1-3)
            symbole_sujet, nouveau = ensembles.obtenir(f"{phrase.sent_id}#{premier.id}")
            app_sujet = [_Terme(code_determinant(phrase, phrase.mots[i], codage), lemme_nominal(phrase.mots[i]), i)
                         for i in ids] if nouveau else []
        elif premier.traits.get("Membres") and codage == "1969":      # « ils » = l'ensemble déjà posé
            symbole_sujet, nouveau = ensembles.obtenir(premier.traits.get("Ensemble") or f"{phrase.sent_id}#{premier.id}")
            app_sujet = [_Terme(VIDE, l, premier.id) for l in premier.traits["Membres"].split("|")] if nouveau else []
        if symbole_sujet:
            sujets = [(VIDE, symbole_sujet, premier.id, "", False)]
    if not sujets and ajouts.get(p.id, {}).get("S") == "N1":
        sujets = [(VIDE, "S", 0, "", False)]           # proposition sujet, impersonnel (1972, p.20, § 3.1413 et p.25, 3.14221)
    if not sujets and ajouts.get(p.id, {}).get("sujet_vide"):
        sujets = [(VIDE, "X", 0, "", False)]           # sujet non assigné (p.25, 3.14221) : X DÉCIDER)
    if not sujets:
        sujets = [(VIDE, VIDE, 0, "", False)]

    # Chaque groupe représente un complément et ses membres éventuels :
    # préposition, déterminant, lemme, ID, connecteur et indication de négation.
    groupes, appartenances_comp = [], {}
    if ajouts.get(p.id, {}).get("pred") == "attribut":
        d2 = code_determinant(phrase, p, codage) if p.upos in CATEGORIES_NOMINALES else VIDE
        pp = preposition(phrase, p)                     # « La parole est à Mme X » : PP = à
        groupe = [(pp if pp != VIDE else "*", d2, lemme_nominal(p), p.id, "", False)]
        for i in profondes.get(p.id, {}).get("E:attrc", []):
            y = phrase.mots[i]
            d = code_determinant(phrase, y, codage) if y.upos in CATEGORIES_NOMINALES else d2
            groupe.append(("*", d, lemme_nominal(y), y.id, marqueur_coordination(phrase, y), membre_nie(phrase, y)))
        if ensembles is not None and len(groupe) > 1 and _inseparable(phrase, [g[3] for g in groupe]):
            symbole, nouveau = ensembles.obtenir(f"{phrase.sent_id}#{p.id}")       # LG9 : « froide et sombre »
            appartenances_comp[0] = [_Terme(g[1], g[2], g[3]) for g in groupe] if nouveau else []
            groupe = [(groupe[0][0], VIDE, symbole, p.id, "", False)]
        groupes.append(groupe)
    else:
        tetes = [phrase.mots[i] for i in aretes.get("E:comp", [])]
        tetes.sort(key=lambda c: (not (c.relation == "obj" or c.relation.startswith("obj:")), c.id))
        autres = [phrase.mots[i] for i in aretes.get("E:compc", [])]
        for c in tetes:
            cible = _quantifie(profondes, c, phrase)
            groupe = []
            for k, lemme in enumerate(_membres(cible)):
                groupe.append((_pp(phrase, p, c, c, ajouts), code_determinant(phrase, c, codage), lemme, cible.id,
                               "et" if k else "", False))
            # Ajoute les membres coordonnés au complément ou au nom quantifié.
            for y in autres:
                racine = y
                while racine.relation == "conj" and racine.tete in phrase.mots and racine.tete not in (c.id, cible.id):
                    racine = phrase.mots[racine.tete]
                if racine.relation == "conj" and racine.tete in (c.id, cible.id):
                    # Dans « toutes sortes de quadrupèdes et d'oiseaux », « de »
                    # dépend de « sortes » : le second membre reprend la PP du groupe.
                    pp_y = groupe[0][0] if (cible is not c and racine.tete == cible.id) else _pp(phrase, p, y, c, ajouts)
                    groupe.append((pp_y, _d2(phrase, y, c, codage), lemme_nominal(y), y.id,
                                   marqueur_coordination(phrase, y), membre_nie(phrase, y)))
            inseparable = len(groupe) > 1 and _inseparable(phrase, [g[3] for g in groupe])
            if ensembles is not None and (inseparable or (_en_ensemble(ensembles, codage)
                                                          and (len(groupe) > 1 or cible.traits.get("Membres")))):
                # Un pronom peut déjà désigner un groupe coordonné.
                if cible.traits.get("Membres") and not inseparable:
                    cle = cible.traits.get("Ensemble") or f"{phrase.sent_id}#{cible.id}"
                    termes = [_Terme(VIDE, l, cible.id) for l in cible.traits["Membres"].split("|")]
                else:  # Crée un ensemble à partir des membres coordonnés du complément.
                    cle = f"{phrase.sent_id}#{cible.id}"
                    termes = [_Terme(code_determinant(phrase, c, codage) if g[3] == cible.id else g[1], g[2], g[3])
                              for g in groupe]
                symbole, nouveau = ensembles.obtenir(cle)
                appartenances_comp[len(groupes)] = termes if nouveau else []
                groupe = [(groupe[0][0], VIDE, symbole, cible.id, "", False)]
            groupes.append(groupe)
    # Une complétive en position de complément est représentée par S.
    if ajouts.get(p.id, {}).get("S") == "N2":
        groupes.insert(0, [("*", VIDE, "S", 0, "", False)])
    # X représente l'objet non exprimé d'une construction comme PRG2.
    if ajouts.get(p.id, {}).get("objet_vide") and not groupes:
        groupes.append([("*", VIDE, "X", 0, "", False)])
    if not groupes:
        groupes = [[(VIDE, VIDE, VIDE, 0, "", False)]]

    lignes, bases_sujet = [], {}
    for i_s, (d1, n1, id_s, marque_s, nie_s) in enumerate(sujets):
        for rang, groupe in enumerate(groupes):
            base_comp = 0
            for i_c, (pp, d2, n2, id_c, marque_c, nie_c) in enumerate(groupe):
                d = d1
                if rang > 0 and n1 != VIDE and d != VIDE:
                    d = "R" if codage == "1972" else VIDE
                ligne = dict(commun, D1=d, N1=n1, PP=pp if n2 != VIDE else VIDE, D2=d2, N2_3=n2,
                             _ancrage=Ancrage(phrase=phrase.sent_id, pred=p.id, n1=id_s, n2=id_c, rang=rang))
                if i_c == 0:
                    if i_s == 0:
                        bases_sujet[rang] = len(lignes)
                    else:
                        ligne["_base"], ligne["_marqueur"] = bases_sujet[rang], marque_s or "et"
                    base_comp = len(lignes)
                else:
                    ligne["_base"], ligne["_marqueur"] = base_comp, marque_c or "et"
                if nie_s or nie_c:
                    ligne["F"] = coder(replace(forme, polarite="negatif"))
                hote = len(lignes)
                lignes.append(ligne)
                # Place les énoncés d'appartenance juste après l'énoncé hôte.
                if i_s == 0 and i_c == 0 and rang == 0 and app_sujet:
                    lignes += _appartenances(phrase, app_sujet, symbole_sujet, codage, hote, "sujet")
                if i_s == 0 and i_c == 0 and appartenances_comp.get(rang):
                    place = "sujet" if pp in ("de = par", "par") and est_passif(phrase, p) else "complement"
                    lignes += _appartenances(phrase, appartenances_comp[rang], n2, codage, hote, place)
    # Un adjectif attribut avec complément produit aussi un énoncé nominalisé.
    if p.upos == "ADJ":
        for c in phrase.dependants(p.id, {"obl"}):
            pp = preposition(phrase, c)
            if pp != VIDE:
                lemme = lemme_nominal(p)
                lignes.append(dict(F=coder(FormeVerbale(copule=True)), D1=VIDE, N1=NOMINALISATIONS.get(lemme, lemme),
                                   V="E" if codage == "1972" else "ε", ADV=VIDE, PP=pp,
                                   D2=code_determinant(phrase, c, codage), N2_3=lemme_nominal(c),
                                   source=f"{phrase.sent_id}:{p.id}>{c.id}",
                                   _ancrage=Ancrage(phrase=phrase.sent_id, n1=p.id, nom=p.id, dep=c.id, n2=c.id)))
    return lignes

#  énoncés construits à partir d’un nom

def _enonces_du_nom(phrase, nom, profondes, codage, ensembles: Ensembles | None = None) -> list[dict]:
    """Construit les énoncés tirés des dépendants d'un nom.

    La fonction traite les adjectifs épithètes, les appositions et les
    compléments du nom. Elle tient compte des groupes coordonnés et des
    noms de quantité repérés par Grew. Le nom principal est considéré comme
    déjà mentionné dans un autre énoncé.
    """
    coder = CODAGES[codage]
    copule = "E" if codage == "1972" else "ε"
    base = dict(D1=code_determinant(phrase, nom, codage, deja_mentionne=True), N1=lemme_nominal(nom))
    quant = profondes.get(nom.id, {}).get("E:quant", [])
    lignes = []
    for dep in sorted(phrase.dependants(nom.id), key=lambda m: m.id):
        if dep.id in quant:
            continue
        source = f"{phrase.sent_id}:{nom.id}>{dep.id}"
        ancre = dict(phrase=phrase.sent_id, n1=nom.id, nom=nom.id, dep=dep.id)
        if dep.relation == "amod" and dep.upos == "ADJ" and dep.lemme.lower() not in ("tout", "autre"):
            obliques = phrase.dependants(dep.id, {"obl"})
            membres = [dep] + [y for y in phrase.mots.values() if y.relation == "conj" and y.tete == dep.id
                               and y.upos == "ADJ"]
            if not obliques and ensembles is not None and len(membres) > 1 and _inseparable(phrase, [m.id for m in membres]):
                # Une coordination inséparable devient un groupe intermédiaire.
                symbole, nouveau = ensembles.obtenir(f"{phrase.sent_id}#{dep.id}")
                hote = len(lignes)
                lignes.append(dict(base, F=coder(FormeVerbale(copule=True)), V=copule, PP="*", D2=VIDE,
                                   N2_3=symbole, source=source, _ancrage=Ancrage(**ancre)))
                if nouveau:
                    lignes += _appartenances(phrase, [_Terme(VIDE, lemme_nominal(m), m.id) for m in membres],
                                             symbole, codage, hote, "complement")
            elif not obliques:
                lignes.append(dict(base, F=coder(FormeVerbale(copule=True)), V=copule, PP="*", D2=VIDE,
                                   N2_3=lemme_nominal(dep), source=source, _ancrage=Ancrage(**ancre)))
                _coordonnes(phrase, dep, lignes, ancre, {"ADJ"}, lambda y: VIDE)    # « simple et claire »
            # Un adjectif avec complément (« debout devant eux ») donne un énoncé par complément.
            for obl in obliques:
                gouverneur = phrase.mots.get(nom.tete)
                forme = (replace(analyser_forme(phrase, gouverneur), voix="actif")
                         if gouverneur is not None and gouverneur.upos == "VERB" else FormeVerbale(copule=True))
                debut = len(lignes)
                if _en_ensemble(ensembles, codage) and obl.traits.get("Membres"):
                    symbole, _ = ensembles.obtenir(obl.traits.get("Ensemble") or f"{phrase.sent_id}#{obl.id}")
                    lignes.append(dict(base, F=coder(forme), V=f"être {lemme_nominal(dep)}", PP=preposition(phrase, obl),
                                       D2=VIDE, N2_3=symbole, source=source, _ancrage=Ancrage(**ancre, n2=obl.id)))
                    continue
                # Sinon, les membres du pronom sont émis séparément.
                for k, lemme in enumerate(_membres(obl)):
                    ligne = dict(base, F=coder(forme), V=f"être {lemme_nominal(dep)}", PP=preposition(phrase, obl),
                                 D2=code_determinant(phrase, obl, codage), N2_3=lemme, source=source,
                                 _ancrage=Ancrage(**ancre, n2=obl.id))
                    if k:
                        ligne["_base"], ligne["_marqueur"] = debut, "et"
                    lignes.append(ligne)
        elif dep.relation == "appos" and dep.upos in ("NOUN", "PROPN", "ADJ"):
            d2 = code_determinant(phrase, dep, codage) if dep.upos == "NOUN" else VIDE
            lignes.append(dict(base, F=coder(FormeVerbale(copule=True)), V=copule, PP="*", D2=d2,
                               N2_3=lemme_nominal(dep), source=source, _ancrage=Ancrage(**ancre, n2=dep.id)))
            _coordonnes(phrase, dep, lignes, ancre, {"NOUN", "PROPN", "ADJ"},
                        lambda y: code_determinant(phrase, y, codage) if y.upos == "NOUN" else VIDE)
        elif (dep.relation == "nmod" and dep.upos in CATEGORIES_NOMINALES
              and (phrase.dependants(dep.id, {"case"}) or dep.traits.get("Preposition"))):
            cible, pp = dep, preposition(phrase, dep)
            if pp == VIDE:
                pp = dep.traits["Preposition"]
            cible = _quantifie(profondes, dep, phrase)
            suite = [m for m in phrase.dependants(dep.id, {"nmod"}) if m.upos in CATEGORIES_NOMINALES]
            locution = dep.lemme.lower() in NOMS_LOCUTION and suite
            if locution:
                cible, pp = suite[0], NOMS_LOCUTION[dep.lemme.lower()]
            d2 = code_determinant(phrase, cible if (cible is dep or locution) else dep, codage)
            lignes.append(dict(base, F=coder(FormeVerbale(copule=True)), V=copule, PP=pp, D2=d2,
                               N2_3=lemme_nominal(cible), source=source, _ancrage=Ancrage(**ancre, n2=cible.id)))
            debut = len(lignes) - 1
            # Ajoute aussi les membres coordonnés du complément du nom.
            for y in sorted(phrase.mots.values(), key=lambda m: m.id):
                if y.relation == "conj" and y.tete == cible.id and y.upos in CATEGORIES_NOMINALES:
                    lignes.append(dict(lignes[debut], PP=preposition(phrase, y) if phrase.dependants(y.id, {"case"}) else pp,
                                       D2=_d2(phrase, y, dep, codage), N2_3=lemme_nominal(y),
                                       _ancrage=Ancrage(**ancre, n2=y.id), _base=debut,
                                       _marqueur=marqueur_coordination(phrase, y)))
    return lignes


def _coordonnes(phrase, dep, lignes, ancre, categories, determinant) -> None:
    """Ajoute une variante pour chaque élément coordonné à un dépendant du nom.

    Chaque variante reprend l'énoncé de base et lui est reliée par le
    connecteur porté par le membre (par exemple « et » : φ3 en 1969, `40`
    en 1972).
    """
    debut = len(lignes) - 1
    for y in sorted(phrase.mots.values(), key=lambda m: m.id):
        if y.relation == "conj" and y.tete == dep.id and y.upos in categories:
            lignes.append(dict(lignes[debut], D2=determinant(y), N2_3=lemme_nominal(y),
                               _ancrage=Ancrage(**dict(ancre, dep=y.id), n2=y.id) if "n2" not in ancre
                               else Ancrage(**ancre), _base=debut, _marqueur=marqueur_coordination(phrase, y)))


JONCTIONS = ("E:IMP", "E:QUE", "E:PRG1", "E:PRG2")


def _jonctions(profondes: dict) -> dict[int, tuple[str, int]]:
    """Associe chaque prédicat dépendant à sa jonction et au prédicat qui le gouverne.

    Les jonctions possibles sont `IMP`, `QUE`, `PRG1` et `PRG2` (manuel,
    § 3.1422). La clé du résultat est l'ID du prédicat dépendant.
    """
    sortie = {}
    for tete, aretes in profondes.items():
        for cle in JONCTIONS:
            for d in aretes.get(cle, []):
                sortie[d] = (cle[2:], tete)
    return sortie


def extraire_ancre_grew(phrases: list[Phrase], discours: str = "", codage: str = "1969",
                        ensembles_1969: bool = False):
    """Extrait les énoncés Grew et conserve les liens vers les phrases sources.

    Renvoie trois éléments :
    1. les paires `(énoncé, ancrage)` ;
    2. les phrases après réécriture par Grew, utilisées ensuite pour calculer
       les relations entre énoncés ;
    3. les triplets `(phrase, objet, lieu)` repérés pour les énoncés latents.

    Le pipeline normalise les phrases et résout les anaphores avant cet appel.
    La stratégie `main` est appliquée ensuite pour repérer les prédicats et
    leurs arguments. `ensembles_1969` choisit le traitement des coordinations
    par groupe en 1969.
    """
    # Un même registre attribue les symboles A1, A2… dans tout le discours.
    ensembles = Ensembles(actifs=ensembles_1969)
    resultat, normalisees, latents = [], [], []
    for phrase in phrases:
        norm, profondes, ajouts = reecrire(phrase)
        normalisees.append(norm)
        jonctions = _jonctions(profondes)
        lignes = []
        for mot in sorted(norm.mots.values(), key=lambda m: m.id):
            if ajouts.get(mot.id, {}).get("pred"):
                decalage = len(lignes)
                jonction = jonctions.get(mot.id)
                for ligne in _enonces_du_predicat(norm, mot, profondes, ajouts, codage, ensembles):
                    for cle in ("_base", "_hote"):
                        if cle in ligne:
                            ligne[cle] += decalage
                    if jonction:
                        ligne["_ancrage"] = replace(ligne["_ancrage"], jonction=jonction[0], hote_pred=jonction[1])
                    lignes.append(ligne)
            if mot.upos in CATEGORIES_NOMINALES and not est_tete_de_locution(norm, mot):
                decalage = len(lignes)
                for ligne in _enonces_du_nom(norm, mot, profondes, codage, ensembles):
                    for cle in ("_base", "_hote"):
                        if cle in ligne:
                            ligne[cle] += decalage
                    lignes.append(ligne)
        depart = len(resultat) + 1
        for i, ligne in enumerate(lignes):
            ancre = ligne.pop("_ancrage")
            if "_base" in ligne:
                ancre = replace(ancre, coord_de=depart + ligne.pop("_base"), coord_marqueur=ligne.pop("_marqueur"))
            if "_hote" in ligne:
                ancre = replace(ancre, hote=depart + ligne.pop("_hote"), place_hote=ligne.pop("_place"))
            resultat.append((Enonce(indice=depart + i, discours=discours, **ligne), ancre))
        # Grew signale séparément les couples objet-lieu des énoncés latents (G13).
        for objet, aretes in profondes.items():
            for lieu in aretes.get("E:latent", []):
                latents.append((phrase.sent_id, objet, lieu))
    return resultat, normalisees, latents


# --- Raccourcis pour extraire directement des phrases -------------------------------------------
# Ces fonctions servent aux tests et aux scripts. Elles appliquent Grew directement aux phrases
# reçues, sans les étapes du pipeline complet (anaphores, décisions du linguiste et ajouts latents).
# Le pipeline complet est `pipeline.corpus_depuis_discours`. Ici, le réglage par défaut reproduit
# les ensembles de l'annexe I en 1969 ; le pipeline suit le réglage `coordination_1969` (LG6).

def extraire_ancre(phrases: list[Phrase], discours: str = "", codage: str = "1969",
                   ensembles_1969: bool = True) -> list[tuple[Enonce, Ancrage]]:
    """Extrait les phrases et renvoie chaque énoncé avec son ancrage.

    Les indices commencent à 1. Pour calculer les relations, appeler
    `extraire_ancre_grew` : cette fonction renvoie aussi les phrases réécrites
    auxquelles les ancrages se rapportent.
    """
    return extraire_ancre_grew(phrases, discours, codage, ensembles_1969)[0]


def extraire(phrases: list[Phrase], discours: str = "", codage: str = "1969",
             ensembles_1969: bool = True) -> list[Enonce]:
    """Extrait une liste de phrases et renvoie les énoncés sans leurs ancrages."""
    return [e for e, _ in extraire_ancre(phrases, discours, codage, ensembles_1969)]


def extraire_phrase_ancree(phrase: Phrase, discours: str = "", indice_depart: int = 1,
                           codage: str = "1969") -> list[tuple[Enonce, Ancrage]]:
    """Extrait une phrase et renvoie ses énoncés avec leurs ancrages.

    `indice_depart` fixe le numéro du premier énoncé.
    """
    decalage = indice_depart - 1
    sortie = []
    for e, a in extraire_ancre([phrase], discours, codage):
        a = replace(a, coord_de=a.coord_de + decalage if a.coord_de else 0,
                    hote=a.hote + decalage if a.hote else 0)
        sortie.append((replace(e, indice=e.indice + decalage), a))
    return sortie


def extraire_phrase(phrase: Phrase, discours: str = "", indice_depart: int = 1,
                    codage: str = "1969") -> list[Enonce]:
    """Extrait une phrase et renvoie les énoncés sans leurs ancrages.

    `indice_depart` fixe le numéro du premier énoncé.
    """
    return [e for e, _ in extraire_phrase_ancree(phrase, discours, indice_depart, codage)]
