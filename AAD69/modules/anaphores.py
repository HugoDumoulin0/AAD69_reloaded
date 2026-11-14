"""Retrouver les noms auxquels renvoient les pronoms (1972, p. 17).

Après l'analyse syntaxique par Stanza, ce module cherche l'antécédent de
chaque pronom. Quand il en trouve un, il remplace le lemme du pronom par
celui de cet antécédent. Ainsi, « Un enfant la trouva » peut être extrait
comme « enfant trouver * L lettre » : la forme « la » reste visible, mais
son lemme devient « lettre ».

Le module traite deux types d'anaphores : celles qu'on peut résoudre dans
la phrase, grâce à son arbre syntaxique, et celles qui nécessitent de
consulter les phrases précédentes. Dans les deux cas, le résultat est une
`Resolution`.

1. Dans la phrase : les pronoms relatifs
----------------------------------------
Pour un relatif, l'antécédent est le nom auquel la proposition relative
est rattachée dans l'arbre syntaxique (relation `acl:relcl`). 

2. Dans le discours : les pronoms personnels
---------------------------------------------
Pour les pronoms de troisième personne (`il`, `elle`, `ils`, `elles`,
`le`, `la`, `les`, `lui`, `leur`, `eux`, ainsi que `y` et `en`), le module
parcourt les phrases dans l'ordre et garde en mémoire les noms et les
pronoms déjà résolus. Pour chaque pronom, il procède ainsi :

1. Il cherche les noms ou pronoms déjà résolus qui apparaissent avant lui,
   dans la même phrase ou dans les `PORTEE` phrases précédentes au maximum.
2. Il écarte les candidats qui désignent un co-argument du même verbe.
   Cette vérification se fait par entité : dans « Elle le remercia »,
   « le » ne renvoie pas à « elle » ; dans « Il lui sourit », « lui » ne
   renvoie pas au garçon désigné par « Il ». Le sujet transmis par une
   coordination est également pris en compte : dans « Le garçon prit le
   livre et le lut », « le » ne renvoie pas au garçon, sujet de « lut ».
   Un groupe coordonné compte comme une seule entité ; ses membres ne sont
   donc pas considérés séparément comme co-arguments.
3. Il conserve les candidats dont le genre et le nombre sont compatibles
   avec le pronom. Ces informations viennent des traits UD de Stanza ; un
   trait manquant ne suffit pas à exclure un candidat.
4. Il retient d'abord les candidats de la phrase la plus proche. S'ils
   désignent une seule entité, le pronom est résolu par proximité. Sinon,
   pour les pronoms personnels, un sujet unique puis une entité reprise
   unique peuvent départager les candidats. Pour `y` et `en`,
   un candidat unique qui n'est pas sujet peut les départager.
   Si aucun critère ne suffit, le pronom est marqué ambigu : son lemme
   n'est pas remplacé et une correction manuelle est nécessaire.

Les noms coordonnés peuvent former une entité plurielle, comme « le Roi et
la Reine ». Pour un pronom pluriel, le groupe est préféré à chacun
de ses membres pris séparément. Un pronom résolu peut ensuite servir
 lui-même d'antécédent, en conservant l'entité et les traits de genre et
de nombre de son antécédent (par exemple, « lui » ne porte pas de genre).

Limites actuelles : `là` n'est pas traité. « Il » impersonnel (relation
`expl:subj`) et « se » (relations `expl:*`) sont ignorés, car ils ne sont
pas considérés comme des anaphores. Un « qui » interrogatif
(`PronType=Int`) n'est pas traité comme un relatif. Enfin, un pronom
réfléchi non clitique, comme « Le garçon garda la lettre pour lui », reste
« sans candidat » : son antécédent est écarté parce qu'il est co-argument.

"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace

from .conllu import Mot, Phrase
from .extraction import lemme_nominal, nom_quantifie, sujet

# Nombre maximal de phrases précédentes où chercher un antécédent.
PORTEE = 2

# Pronoms personnels de troisième personne traités par le résolveur.
PRONOMS_PERSONNELS = {"il", "elle", "ils", "elles", "le", "la", "les", "lui", "leur", "eux"}

# Pronoms relatifs traités dans leur phrase.
RELATIFS = {"qui", "que", "lequel", "laquelle", "lesquels", "lesquelles"}

# Prépositions ajoutées par défaut lors du rétablissement des relatifs.
# Pour « où », le manuel donne « se plaignent dans la Météorologie » (1972, p. 17).
# La préposition réellement attendue peut dépendre du verbe.
RELATIFS_PREPOSITIONNELS = {"dont": "de", "où": "à"}

# Prépositions rétablies par défaut pour les pronoms adverbiaux.
PRONOMS_ADVERBIAUX = {"y": "à", "en": "de"}

# Relations syntaxiques UD qui marquent un sujet actif ou passif.
SUJETS = {"nsubj", "nsubj:pass"}

# Catégories UD considérées comme des noms dans la recherche d'antécédents.
NOMINAUX = {"NOUN", "PROPN"}

Cle = tuple[str, int]  # (sent_id, id du mot)


@dataclass
class Resolution:
    """Informations sur la résolution d'un pronom.

    `statut` indique le résultat :
    - « résolue » : un antécédent a été trouvé ;
    - « ambiguë » : plusieurs antécédents restent possibles ;
    - « sans candidat » : aucun antécédent n'a été trouvé.

    `regle` précise la règle utilisée. `antecedent` contient l'identifiant du
    mot retenu quand la résolution a réussi. Les autres champs décrivent le
    pronom et les informations utiles à son remplacement.
    """

    pronom: Cle
    forme: str
    statut: str
    regle: str
    antecedent: Cle | None = None
    lemme: str = ""
    upos: str = "NOUN"
    candidats: list[str] = field(default_factory=list)
    membres: tuple[str, ...] = ()
    ensemble: str = ""
    nombre: str | None = None
    preposition: str = ""

    @property
    def resolue(self) -> bool:
        """Indique si un antécédent a été trouvé."""
        return self.statut == "résolue"


@dataclass
class _Mention:
    """Une expression déjà rencontrée qui peut servir d'antécédent.

    `cle` identifie le mot dans le discours. `lemme`, `upos`, `genre` et
    `nombre` décrivent cette mention ; `relation` et `tete` indiquent son
    lien syntaxique. `phrase` est son rang dans le discours et sert à
    mesurer la proximité avec le pronom à résoudre.

    `pronom` vaut True si cette mention vient d'un pronom déjà résolu.
    `membres` et `ensemble` identifient un groupe coordonné, par exemple
    « le Roi et la Reine ».
    """

    cle: Cle
    lemme: str
    upos: str
    genre: str | None
    nombre: str | None
    relation: str
    tete: int
    phrase: int
    pronom: bool = False
    membres: tuple[str, ...] = ()
    ensemble: str = ""


def _est_pronom_personnel(m: Mot) -> bool:
    """Indique si `m` est un pronom personnel de troisième personne traité ici.

    La forme ou le lemme doit appartenir à `PRONOMS_PERSONNELS`. Les pronoms
    impersonnels (`expl`), réfléchis et de première ou deuxième personne sont
    exclus : ils ne désignent pas un antécédent nominal dans ce traitement.
    """
    return (m.upos == "PRON" and (m.lemme.lower() in PRONOMS_PERSONNELS or m.forme.lower() in PRONOMS_PERSONNELS)
            and not m.relation.startswith("expl") and m.traits.get("Person", "3") == "3"
            and m.traits.get("Reflex") != "Yes")


def _est_relatif(m: Mot) -> bool:
    """Indique si `m` est un pronom relatif traité dans sa phrase.

    Stanza peut analyser certains relatifs, comme « dont » et « où », comme
    des pronoms ou des adverbes : les deux catégories sont donc vérifiées.
    Quand le trait `PronType` est présent, il permet de distinguer un relatif
    (`Rel`) d'un interrogatif (`Int`). En son absence, la fonction s'appuie
    sur les listes de relatifs connues.
    """
    if m.upos not in ("PRON", "ADV"):
        return False
    if m.lemme.lower() in RELATIFS_PREPOSITIONNELS or m.forme.lower() in RELATIFS_PREPOSITIONNELS:
        return m.traits.get("PronType", "Rel") == "Rel"
    if m.upos != "PRON":
        return False
    if "PronType" in m.traits:
        return m.traits["PronType"] == "Rel"
    return m.lemme.lower() in RELATIFS


def _est_pronom_adverbial(m: Mot) -> bool:
    """Indique si `m` est le pronom adverbial « y » ou « en ».

    Ces pronoms sont rétablis respectivement comme « à + antécédent » et
    « de + antécédent ». Les mots liés par `expl`, `fixed` ou `case` sont
    exclus : dans ces emplois, « y » ou « en » n'est pas traité comme une
    anaphore.
    """
    return (m.upos in ("PRON", "ADV") and m.forme.lower() in PRONOMS_ADVERBIAUX
            and not m.relation.startswith("expl") and m.relation not in ("fixed", "case"))


def _ellipse_autre(phrase: Phrase, mot: Mot) -> Mot | None:
    """Cherche l'antécédent de « autre » employé seul, comme dans « l'autre ».

    La fonction renvoie le nom commun indéfini (`Definite=Ind`) le plus
    proche qui précède `mot` dans la phrase. Ce nom fournit le lemme à
    rétablir. Renvoie `None` si `mot` n'est pas le pronom « autre » ou si
    aucun nom correspondant n'a été trouvé.
    """
    if mot.lemme.lower() != "autre" or mot.upos != "PRON":
        return None
    for nom in sorted(phrase.mots.values(), key=lambda x: -x.id):
        if nom.id < mot.id and nom.upos == "NOUN" and any(
                det.relation == "det" and det.traits.get("Definite") == "Ind"
                for det in phrase.dependants(nom.id)):
            return nom
    return None


def _nombre(m: Mot) -> str | None:
    """Renvoie le nombre du mot, ou `None` si on ne peut pas le déterminer.

    Pour un nom propre, le nombre est considéré singulier quand Stanza ne
    fournit pas le trait UD `Number`.
    """
    return m.traits.get("Number") or ("Sing" if m.upos == "PROPN" else None)


def _genre(phrase: Phrase, m: Mot) -> str | None:
    """Renvoie le genre du nom, en privilégiant celui de son déterminant.

    Le déterminant aide notamment pour les noms qui ont la même forme au
    masculin et au féminin, comme « artiste » dans « une artiste ».
    """
    for determinant in phrase.dependants(m.id, {"det"}):
        if determinant.traits.get("Gender"):
            return determinant.traits["Gender"]
    return m.traits.get("Gender")


def _fonction(phrase: Phrase, m: Mot) -> str:
    """Renvoie la relation syntaxique du mot ou de la tête de sa coordination.

    Un membre introduit par `conj` hérite ici de la relation du premier
    membre du groupe, par exemple de son rôle de sujet ou de complément.
    """
    courant = m
    profondeur = 0
    while courant.relation == "conj" and courant.tete in phrase.mots and profondeur < 5:
        courant = phrase.mots[courant.tete]
        profondeur += 1
    return courant.relation


def _groupes_coordonnes(phrase: Phrase) -> dict[int, list[Mot]]:
    """Repère les groupes de noms coordonnés dans la phrase.

    Le résultat associe l'ID du dernier membre de chaque groupe à la liste
    de ses membres, dans l'ordre de la phrase. Les groupes à un seul nom
    ne sont pas inclus.
    """
    groupes = {}
    for tete in phrase.mots.values():
        if tete.upos not in NOMINAUX or tete.relation == "conj":
            continue
        membres, a_voir = [tete], [tete.id]
        while a_voir:
            identifiant = a_voir.pop()
            conjoints = [m for m in phrase.mots.values()
                         if m.tete == identifiant and m.relation == "conj" and m.upos in NOMINAUX]
            membres.extend(conjoints)
            a_voir.extend(m.id for m in conjoints)
        if len(membres) > 1:
            groupes[max(m.id for m in membres)] = sorted(membres, key=lambda m: m.id)
    return groupes


def _s_accorde(m: _Mention, pronom: Mot) -> bool:
    """Vérifie si le genre et le nombre de la mention conviennent au pronom.

    Une différence exclut la mention seulement si les deux côtés ont une
    valeur connue pour ce trait. Une information manquante, par exemple le
    genre de « lui », ne suffit donc pas à écarter un candidat.
    """
    for trait, valeur in (("Gender", m.genre), ("Number", m.nombre)):
        voulu = pronom.traits.get(trait)
        if voulu and valeur and voulu != valeur:
            return False
    return True


def _entites_co_arguments(phrase: Phrase, m: Mot, resultats: dict[Cle, Resolution]) -> set[str]:
    """Renvoie les entités à écarter parmi les antécédents possibles de `m`.

    Ce sont les autres participants du même verbe, dont le sujet. Si l'un
    d'eux est un pronom déjà résolu, on écarte l'entité de son antécédent.
    Si c'est un membre d'un groupe coordonné, on écarte le groupe et ses
    membres. Renvoie un ensemble vide si la tête syntaxique de `m` manque.
    """
    if m.tete not in phrase.mots:
        return set()
    verbe = phrase.mots[m.tete]
    autres = [x for x in phrase.mots.values() if x.tete == m.tete and x.id != m.id]
    s = sujet(phrase, verbe)
    if s is not None and s.id != m.id:
        autres.append(s)
    groupes = _groupes_coordonnes(phrase)
    groupe_par_membre = {
        membre.id: membres
        for membres in groupes.values()
        for membre in membres
    }
    entites = set()
    for x in autres:
        r = resultats.get((phrase.sent_id, x.id))
        if r is not None and r.resolue:
            entites.add(r.lemme)
            entites.update(r.membres)
        elif x.upos in NOMINAUX:
            entites.add(x.lemme)
        membres = groupe_par_membre.get(x.id)
        if membres:
            entites.update(membre.lemme for membre in membres)
            entites.add(" et ".join(lemme_nominal(membre) for membre in membres))
    return entites


def resoudre(phrases: list[Phrase], portee: int = PORTEE) -> dict[Cle, Resolution]:
    """Cherche les antécédents des pronoms dans un discours ordonné.

    Les phrases doivent être fournies dans leur ordre de lecture. La
    fonction traite les relatifs, les pronoms personnels et adverbiaux,
    ainsi que l'ellipse « l'autre ». Elle garde les noms rencontrés en
    mémoire ; un pronom résolu peut ensuite servir à son tour de mention.

    Renvoie un dictionnaire associant chaque pronom traité, identifié par
    `(identifiant de phrase, ID du mot)`, à son résultat `Resolution`.
    `portee` règle le nombre maximal de phrases précédentes considérées.
    """
    resultats: dict[Cle, Resolution] = {}
    mentions: list[_Mention] = []

    for rang, phrase in enumerate(phrases):
        groupes = _groupes_coordonnes(phrase)
        for m in sorted(phrase.mots.values(), key=lambda x: x.id):
            cle = (phrase.sent_id, m.id)

            if _est_relatif(m) and m.tete in phrase.mots:
                verbe = phrase.mots[m.tete]
                for _ in range(3):  # le relatif peut être à plusieurs verbes de sa phrase (coordination)
                    if verbe.relation == "acl:relcl" or verbe.tete not in phrase.mots:
                        break
                    verbe = phrase.mots[verbe.tete]
                if verbe.relation == "acl:relcl" and verbe.tete in phrase.mots:
                    nom = phrase.mots[verbe.tete]
                    entite = resultats.get((phrase.sent_id, nom.id))
                    lemme = entite.lemme if entite and entite.resolue else nom.lemme
                    prep = RELATIFS_PREPOSITIONNELS.get(m.lemme.lower()) or \
                        RELATIFS_PREPOSITIONNELS.get(m.forme.lower(), "")
                    resultats[cle] = Resolution(cle, m.forme, "résolue", "relatif (acl:relcl)",
                                                (phrase.sent_id, nom.id), lemme, nom.upos,
                                                nombre=_nombre(nom), preposition=prep)
                elif m.lemme.lower() not in RELATIFS_PREPOSITIONNELS and \
                        m.forme.lower() not in RELATIFS_PREPOSITIONNELS:
                    resultats[cle] = Resolution(cle, m.forme, "sans candidat", "relatif sans acl:relcl")
                continue

            nom_autre = _ellipse_autre(phrase, m)
            if nom_autre is not None:
                resultats[cle] = Resolution(cle, m.forme, "résolue", "ellipse (l'autre)",
                                            (phrase.sent_id, nom_autre.id), nom_autre.lemme, nom_autre.upos,
                                            nombre=_nombre(nom_autre))
                continue

            adverbial = _est_pronom_adverbial(m)
            if _est_pronom_personnel(m) or adverbial:
                exclues = _entites_co_arguments(phrase, m, resultats)
                candidats = [c for c in mentions
                             if rang - c.phrase <= portee
                             and not (c.phrase == rang and c.tete == m.tete)
                             and c.lemme not in exclues
                             and (adverbial or _s_accorde(c, m))]
                res, choisi = None, None
                for distance in range(portee + 1):
                    proches = [c for c in candidats if rang - c.phrase == distance]
                    if not proches:
                        continue
                    # Pronom pluriel : l'entité de groupe (« le Roi et la Reine ») est
                    # préférée à ses mentions individuelles.
                    if not adverbial and m.traits.get("Number") == "Plur":
                        groupes_pluriels = [c for c in proches if c.membres and c.nombre == "Plur"]
                        membres_groupes = {lemme for groupe in groupes_pluriels for lemme in groupe.membres}
                        if groupes_pluriels:
                            proches = [c for c in proches
                                       if c.membres or c.lemme not in membres_groupes]
                    entites = {c.lemme for c in proches}
                    if len(entites) == 1:
                        choisi = proches[-1]
                        res = Resolution(cle, m.forme, "résolue", "proximité", choisi.cle,
                                         choisi.lemme, choisi.upos, membres=choisi.membres)
                    else:
                        if adverbial:
                            sujets = {c.lemme: c for c in proches if c.relation not in SUJETS}
                        else:
                            sujets = {c.lemme: c for c in proches if c.relation in SUJETS}
                        reprises = {} if adverbial else {c.lemme: c for c in proches if c.pronom}
                        if len(sujets) == 1:
                            (c,) = sujets.values()
                            choisi = c
                            res = Resolution(cle, m.forme, "résolue",
                                             "préférence non-sujet" if adverbial else "préférence sujet",
                                             c.cle, c.lemme, c.upos, membres=c.membres)
                        elif len(reprises) == 1:
                            (c,) = reprises.values()
                            choisi = c
                            res = Resolution(cle, m.forme, "résolue", "continuité", c.cle, c.lemme, c.upos,
                                             membres=c.membres)
                        else:
                            res = Resolution(cle, m.forme, "ambiguë", "plusieurs candidats",
                                             candidats=sorted(entites))
                    break
                resultats[cle] = res or Resolution(cle, m.forme, "sans candidat", "aucun nom accordé")
                if choisi is not None:
                    res.ensemble, res.nombre = choisi.ensemble, choisi.nombre
                    if adverbial:
                        res.preposition = "" if m.relation == "obj" else PRONOMS_ADVERBIAUX[m.forme.lower()]
                    mentions.append(_Mention(cle, res.lemme, res.upos,
                                             m.traits.get("Gender") or choisi.genre,
                                             m.traits.get("Number") or choisi.nombre,
                                             m.relation, m.tete, rang, pronom=True, membres=res.membres,
                                             ensemble=res.ensemble))
                continue

            if m.upos in NOMINAUX and nom_quantifie(phrase, m) is None:
                mentions.append(_Mention(cle, m.lemme, m.upos, _genre(phrase, m),
                                         _nombre(m), _fonction(phrase, m), m.tete, rang))
            if m.id in groupes:
                membres = groupes[m.id]
                tete = membres[0]
                genres = [m.traits.get("Gender") for m in membres]
                genre = ("Masc" if "Masc" in genres else "Fem" if all(g == "Fem" for g in genres) else None)
                lemmes = tuple(lemme_nominal(x) for x in membres)
                mentions.append(_Mention((phrase.sent_id, tete.id),
                                         " et ".join(lemmes),
                                         "NOUN", genre, "Plur", tete.relation, tete.tete, rang,
                                         membres=lemmes, ensemble=f"{phrase.sent_id}#{tete.id}"))
    return resultats


def appliquer(phrases: list[Phrase], resolutions: dict[Cle, Resolution]) -> list[Phrase]:
    """Renvoie une copie des phrases avec les résolutions appliquées.

    Pour un pronom résolu, remplace le lemme et ajoute les traits qui
    décrivent son antécédent. Pour un pronom non résolu, garde sa forme
    comme lemme. Les phrases d'origine ne sont pas modifiées.
    """
    nouvelles = []
    for phrase in phrases:
        p = copy.deepcopy(phrase)
        for mot_id, m in p.mots.items():
            r = resolutions.get((p.sent_id, mot_id))
            if r and not r.resolue:
                # Éviter le lemme de Stanza, variable selon les versions, pour un pronom non rétabli.
                p.mots[mot_id] = replace(m, lemme=m.forme.lower())
                continue
            if r and r.resolue:
                traits = {k: v for k, v in m.traits.items() if k in ("Number", "Gender")}
                if "Number" not in traits and r.nombre:
                    traits["Number"] = r.nombre
                traits["Anaphore"] = ("Rel" if r.regle.startswith("relatif")
                                      else "Autre" if r.regle.startswith("ellipse") else "Prs")
                if r.membres:
                    traits["Membres"] = "|".join(r.membres)
                if r.ensemble:
                    traits["Ensemble"] = r.ensemble
                if r.preposition:
                    traits["Preposition"] = r.preposition
                p.mots[mot_id] = Mot(id=m.id, forme=m.forme, lemme=r.lemme, upos=r.upos, traits=traits,
                                     tete=m.tete, relation=m.relation)
        nouvelles.append(p)
    return nouvelles
