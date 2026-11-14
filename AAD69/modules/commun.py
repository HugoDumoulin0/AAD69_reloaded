"""Fonctions partagées pour lire les arbres syntaxiques et décrire leurs énoncés.

Ce module regroupe des fonctionnalités utilisées à plusieurs endroits du projet. Il ne réalise pas
l'extraction des énoncés : les règles d'extraction sont dans `extraction_grew.py`.


Utilisateurs principaux
-----------------------
- `extraction_grew.py` assemble les huit cases d'un énoncé à partir des résultats de Grew.
- `anaphores.py` et `linguiste.py` utilisent les outils de lecture des arbres, des lemmes, des
  sujets et des coordinations.
- `relations.py` utilise les ancrages (lien entre un énoncé extrait et les mots précis de la phrase dont il provient.) pour relier les énoncés à leur arbre syntaxique.
- `interface/propositions.py` utilise les prédicats, les sujets et les prépositions pour afficher
  les propositions.

Les fonctions précisent leurs appelants et leur rôle dans les commentaires placés près de leur
définition.

Notions utilisées
-----------------
Les fonctionnalités s'appuient sur les arbres de dépendances produits par Stanza et représentés par
`Phrase` dans `conllu.py` :
- La tête d'un mot est le mot auquel il est rattaché. Les dépendants d'un mot sont ceux qui lui
  sont rattachés ; `Phrase.dependants` permet de les obtenir.
- Les étiquettes de dépendance suivent Universal Dependencies : `nsubj` (sujet), `obj` (objet),
  `obl` (complément prépositionnel), `case` (préposition), `cop` (copule), `conj` (mot coordonné),
  `cc` (conjonction de coordination), `aux` (auxiliaire), `nmod` (complément du nom), etc.
- Un prédicat est le mot qui porte le contenu de l'énoncé : généralement un verbe, ou un adjectif
  accompagné d'une copule. Dans « Elles étaient appétissantes », le prédicat est « appétissantes ».
- Un ancrage relie un énoncé à un ou plusieurs mots de son arbre syntaxique.

Organisation du module
----------------------
1. Étiquettes de dépendance et catégories grammaticales utilisées par les outils.
2. Lecture du prédicat, du lemme, de la préposition et du sujet.
3. Ancrage d'un énoncé dans l'arbre (`Ancrage`).
4. Noms de quantité et constructions passives.
5. Coordination : membres, connecteur et négation.
6. Ensembles A1, A2… et énoncés d'appartenance (1969 : ε3 ; 1972 : CONTENIR).
7. Locutions prépositionnelles.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .conllu import Mot, Phrase
from .forme import CODAGES, FormeVerbale
from .lexique import MARQUE_EGO, MARQUE_TERME_VIDE, NOMS_LOCUTION, NOMS_QUANTITE, PRONOMS_VIDES
from .modele import VIDE


# --- 1. Relations et catégories -------------------------------------------------------------------
"""
Cette section regroupe les étiquettes syntaxiques et les catégories de mots
utilisées par les fonctions du module pour lire l'arbre de la phrase.
Elle précise quelles relations signalent un sujet, quand un verbe reprend
le sujet de son verbe tête et quelles catégories peuvent être reconnues
comme sujet ou comme nom dans l'analyse fournie par Stanza.
"""
# Relations UD du sujet : actif (« Le facteur perdit ») et passif (« La lettre fut perdue »).
RELATIONS_SUJET = {"nsubj", "nsubj:pass"}

# Relations par lesquelles un prédicat sans sujet reprend celui de sa tête (voir `sujet`).
RELATIONS_SUJET_HERITE = {"conj", "xcomp"}

# Relations du pronom d'un verbe pronominal (voir `lemme_verbe`).
RELATIONS_PRONOMINAL = {"expl:pv", "expl:pass", "expl:comp"}  # « se » : se tenir, se vendre…

# Pronoms réfléchis, par lemme et par forme (Stanza lemmatise parfois mal « me », voir lemme_verbe).
PRONOMS_REFLECHIS = {"se", "soi", "me", "te", "nous", "vous", "lui"}

# Formes de pronoms réfléchis que Stanza peut rattacher au verbe.
FORMES_REFLECHIES = {"se", "s'", "me", "m'", "te", "t'", "nous", "vous"}

# Catégories UD admises pour un sujet. Les numéraux sont inclus pour couvrir
# certaines analyses, même si un sujet est normalement nominal.
CATEGORIES_SUJET = {"NOUN", "PROPN", "PRON", "NUM"}

# Catégories UD des noms qui peuvent recevoir un déterminant codé (D1 ou D2).
CATEGORIES_NOMINALES = {"NOUN", "PROPN"}

# Les listes de mots (locutions, noms de quantité, nominalisations…) sont dans aad69/lexique.py.

# Relations UD qui identifient un auxiliaire ou une copule, à distinguer d'un verbe plein.
RELATIONS_AUXILIAIRE = {"aux", "aux:pass", "aux:tense", "aux:caus", "cop"}


# --- 2. Lire l'arbre ------------------------------------------------------------------------------

def verbes_etiquetes_aux(phrase: Phrase) -> Phrase:
    """Corrige l'étiquette AUX de certains emplois pleins de « être » et « avoir ».

    Stanza peut étiqueter AUX un « être » ou un « avoir » qui est pourtant
    la tête de sa proposition et possède ses propres dépendants. Ces mots
    sont alors réétiquetés VERB. Les auxiliaires et les
    copules, identifiés par leur relation syntaxique, ne sont pas modifiés.
    Renvoie la phrase d'origine si aucune correction n'est nécessaire.

    Utilisée par : interface/propositions.py.
    """
    changes = {i: replace(m, upos="VERB") for i, m in phrase.mots.items()
               if m.upos == "AUX" and m.relation not in RELATIONS_AUXILIAIRE
               and phrase.dependants(m.id, {"nsubj", "nsubj:pass", "obj", "obl"})}
    if not changes:
        return phrase
    return Phrase(sent_id=phrase.sent_id, texte=phrase.texte, mots={**phrase.mots, **changes})


def est_predicat(mot: Mot, phrase: Phrase | None = None) -> bool:
    """Indique si le mot porte un prédicat : un verbe ou un attribut avec copule.

    Utilisée par : `membres_coordonnes` et `sujet` (ci-dessous), interface/propositions.py.
    """
    if mot.upos == "VERB":
        return True
    return phrase is not None and bool(phrase.dependants(mot.id, {"cop"}))


def lemme_nominal(mot: Mot) -> str:
    """Renvoie la forme utilisée pour un terme nominal dans les énoncés.

    Les noms communs et adjectifs sont mis en minuscules ; les noms propres
    gardent leur casse. Certains pronoms sont remplacés par les marques du
    manuel : `X` pour le terme vidé (« celui qui… », § 3.1413, pp. 20-21, E2-22)
    et `EGO` pour la première personne du singulier : « André et moi sommes
    allés au meeting » -> (EGO ALLER A L MEETING) (§ 3.1423, p. 32, E2-23).

    NB, fidélité à 1969 : le livre (1969) utilise X sans le définir (annexe I, énoncés 4-6,
    pp. 116-117 : « ils », référent hors du texte, -> (X ARRIVER) ; puis « Alice ε2 à X »,
    « L griffon ε3 à X »). Ce cas n'est pas extrait : un pronom sans candidat dans sa phrase peut
    avoir son référent plus loin dans le discours, et le programme ne peut pas distinguer cette
    anaphore d'un référent réellement hors du corpus (« Il était une fois » en ouverture de
    texte). Le X implémenté suit le manuel (1972, § 3.1413, pp. 20-21), appliqué aux deux
    codages ; le X « hors corpus » du livre reste au linguiste : trait posé à la main, comme
    `Inseparable` (LG9).

    Utilisée par : extraction_grew.py (cases N1 et N2/3), anaphores.py, linguiste.py.
    """
    if mot.upos == "PRON":
        if mot.lemme.lower() in PRONOMS_VIDES or mot.forme.lower() in PRONOMS_VIDES:
            return MARQUE_TERME_VIDE
        if (mot.traits.get("Person") == "1" and mot.traits.get("Number") == "Sing"
                and mot.traits.get("Reflex") != "Yes"):
            return MARQUE_EGO
    return mot.lemme.lower() if mot.upos in ("NOUN", "ADJ") else mot.lemme


def lemme_verbe(phrase: Phrase, verbe: Mot) -> str:
    """Renvoie le lemme du prédicat (case V), en rétablissant la copule ou le réfléchi.

    - attribut avec copule (« Elles étaient appétissantes ») : le lemme de la copule, « être »
      (annexe I, énoncé 31 : « LS tarte être * appétissant », F2) ;
    - verbe pronominal (« se tenait ») : « se » + lemme, « se tenir » (annexe I, énoncé 18).

    Utilisée par : extraction_grew.py (case V).
    """
    copules = phrase.dependants(verbe.id, {"cop"})
    if verbe.upos != "VERB" and copules:
        return copules[0].lemme
    # Lemme ou forme : Stanza 1.15 lemmatise « me » en « moi » (comme « Elle » en « lui »).
    if any(m.lemme.lower() in PRONOMS_REFLECHIS or m.forme.lower() in FORMES_REFLECHIES
           for m in phrase.dependants(verbe.id, RELATIONS_PRONOMINAL)):
        return f"se {verbe.lemme}"
    return verbe.lemme


def preposition(phrase: Phrase, nom: Mot) -> str:
    """Renvoie la préposition liée au nom (case PP), ou `VIDE` s'il n'en a pas.

    Les mots liés par `fixed` sont réunis pour restituer les locutions,
    comme « près de » (annexe I, énoncé 17 : « valet être debout près de L roi »).

    Utilisée par : extraction_grew.py, linguiste.py, interface/propositions.py.
    """
    cases = phrase.dependants(nom.id, {"case"})
    if not cases:
        return VIDE
    tete = cases[0]
    parties = [tete] + phrase.dependants(tete.id, {"fixed"})
    return " ".join(m.lemme for m in sorted(parties, key=lambda m: m.id))


def sujet(phrase: Phrase, verbe: Mot, profondeur: int = 0) -> Mot | None:
    """Renvoie le sujet direct du prédicat, ou le sujet transmis par sa tête.

    Si le prédicat n'a pas de sujet direct, le sujet peut être repris de son
    verbe tête (coordination, infinitif complément ou participe détaché).
    Un participe qui modifie un nom prend ce nom pour sujet ; un infinitif
    qui modifie un nom peut hériter du sujet du prédicat auquel ce nom se
    rattache. `profondeur` limite le nombre de remontées dans l'arbre.

    Exemples : « Il trouva la lettre et la porta » : « porta » (conj) prend le sujet de « trouva » ;
    « une foule composée de… » : « composée » (acl, participe) a pour sujet « foule ».

    Utilisée par : anaphores.py (l'antécédent d'un pronom n'est pas un autre argument du même
    verbe, sujet compris : « Le facteur le vit » : « le » ≠ facteur), interface/propositions.py. Dans l'extraction, ce sont les règles
    Grew `sujet_*` qui trouvent le sujet.
    """
    directs = [m for m in phrase.dependants(verbe.id, RELATIONS_SUJET) if m.upos in CATEGORIES_SUJET]
    if directs:
        return directs[0]
    if profondeur > 5 or verbe.tete == 0:
        return None
    tete = phrase.mots[verbe.tete]
    forme = verbe.traits.get("VerbForm")
    relation = verbe.relation.split(":")[0]
    if relation in RELATIONS_SUJET_HERITE and est_predicat(tete, phrase):
        return sujet(phrase, tete, profondeur + 1)
    if relation == "advcl" and forme == "Part" and est_predicat(tete, phrase):
        return sujet(phrase, tete, profondeur + 1)
    if relation == "acl" and forme == "Part":
        return tete
    if relation == "acl" and forme == "Inf" and tete.tete != 0 and est_predicat(phrase.mots[tete.tete], phrase):
        return sujet(phrase, phrase.mots[tete.tete], profondeur + 1)
    return None


# --- 3. L'ancrage d'un énoncé ---------------------------------------------------------------------

@dataclass(frozen=True)
class Ancrage:
    """Repères reliant un énoncé extrait aux mots de sa phrase.

    Un énoncé ne garde que des lemmes et des codes ; pour relier les énoncés entre eux (étape 3),
    il faut savoir de quels mots de l'arbre il vient. L'ancrage le garde. La valeur `0` signifie
    qu'il n'y a pas de mot associé à ce repère.

    - `phrase` : identifiant de la phrase (sent_id) ;
    - `pred` : le prédicat ; `n1` et `n2` : les mots des cases N1 et N2/3 ;
    - `nom`, `dep` : pour un énoncé tiré d'un nom (« une grande foule » -> foule ε grand), le nom et
      son adjectif ou complément ;
    - `rang` : la place de l'énoncé parmi ceux d'un même prédicat (0 = le premier) ;
    - `coord_de`, `coord_marqueur` : pour un terme coordonné, le numéro de l'énoncé du premier
      terme et le connecteur (« et », « ou »…) ;
    - `hote`, `place_hote` : pour un énoncé d'appartenance (« roi ε3 à A1 »), le numéro de l'énoncé
      où figure le symbole A1, et la place du symbole dans cet énoncé (sujet ou complément) ;
    - `latent` : énoncé latent (LG8, règle Grew G13) : `nom` = l'objet, `dep` = le lieu ;
    - `recouvre` : prédicat rétabli d'une nominalisation (LG11) : le nom déverbal ;
    - `jonction`, `hote_pred` : énoncé qui dépend d'un autre par IMP, QUE, PRG1 ou PRG2 (manuel
      § 3.1422, règles Grew), et le prédicat dont il dépend.

    Utilisée par : extraction_grew.py (crée les ancrages), relations.py (les lit), linguiste.py.
    """

    phrase: str
    pred: int = 0
    n1: int = 0
    n2: int = 0
    nom: int = 0
    dep: int = 0
    rang: int = 0
    coord_de: int = 0
    coord_marqueur: str = ""
    hote: int = 0
    place_hote: str = ""
    latent: bool = False      # énoncé latent rétabli par le linguiste 
    recouvre: int = 0         # prédicat rétabli d'une nominalisation
    jonction: str = ""        # IMP | QUE | PRG1 | PRG2 : énoncé modalisé / complétive (manuel § 3.1422, Grew)
    hote_pred: int = 0        # le prédicat modalisant (ou qui porte S)


# --- 4. Noms de quantité, passif ------------------------------------------------------------------

def nom_quantifie(phrase: Phrase, mot: Mot) -> Mot | None:
    """Repère le nom sans déterminant qui complète un nom de quantité avec « de ».

    « toutes sortes de poissons » : pour « sortes », renvoie « poissons » (E2-17 ; liste
    NOMS_QUANTITE de lexique.py). Attesté : « toutes sortes de quadrupèdes et d'oiseaux » ->
    les énoncés portent TS quadrupède et TS oiseau (annexe I, énoncés 10-11). Renvoie None
    si `mot` n'est pas un nom de quantité.

    Utilisée par : anaphores.py (un nom de quantité n'est pas un antécédent possible : c'est le
    nom compté qui l'est). Dans l'extraction, c'est la règle Grew `nom_quantifie`.
    """
    if mot.upos != "NOUN" or mot.lemme.lower() not in NOMS_QUANTITE:
        return None
    for nom in phrase.dependants(mot.id, {"nmod"}):
        if (nom.upos in CATEGORIES_NOMINALES and not phrase.dependants(nom.id, {"det"})
                and any(c.lemme.lower() == "de" for c in phrase.dependants(nom.id, {"case"}))):
            return nom
    return None


def est_passif(phrase: Phrase, verbe: Mot) -> bool:
    """Indique si le verbe est à la voix passive, d'après ses traits ou son auxiliaire.

    Utilisée par : extraction_grew.py (« de » d'un passif -> PP = « de = par », E2-18 ; attesté :
    annexe I, énoncés 9 « foule composer de = par K » et 16 « encadrer de = par DEUX soldat »).
    """
    return verbe.traits.get("Voice") == "Pass" or bool(phrase.dependants(verbe.id, {"aux:pass"}))


# --- 5. Coordination ------------------------------------------------------------------------------

# Catégories des termes qu'on peut coordonner dans une case (pas les verbes : deux verbes
# coordonnés donnent deux énoncés — manuel, § 3.1423, rem. 1, p. 32 : un seul verbe à un mode
# personnel par proposition).
CATEGORIES_COORDONNABLES = {"NOUN", "PROPN", "PRON", "ADJ", "NUM"}

# Négation portée par un seul terme coordonné : « Pierre et pas Marcel ».
NEGATIONS_DE_MEMBRE = {"pas", "non", "jamais", "point"}


def membres_coordonnes(phrase: Phrase, mot: Mot) -> list[Mot]:
    """Renvoie le mot et les termes nominaux coordonnés avec lui.

    La recherche suit les relations `conj` et laisse de côté les prédicats
    coordonnés. Les membres sont renvoyés dans l'ordre de la phrase.
    « le roi et la reine » : pour « roi », renvoie [roi, reine].

    Utilisée par : linguiste.py (opération 5, termes inséparables).
    """
    membres, a_voir = [mot], [mot.id]
    while a_voir:
        identifiant = a_voir.pop()
        for conjoint in phrase.mots.values():
            if (conjoint.tete == identifiant and conjoint.relation == "conj"
                    and conjoint.upos in CATEGORIES_COORDONNABLES
                    and not est_predicat(conjoint, phrase)):
                membres.append(conjoint)
                a_voir.append(conjoint.id)
    return sorted(membres, key=lambda membre: membre.id)


def marqueur_coordination(phrase: Phrase, membre: Mot) -> str:
    """Renvoie le connecteur de coordination associé au terme, ou « et » par défaut.

    Le connecteur choisit la relation entre les énoncés des deux termes (étape 3 : « et » -> φ3
    en 1969, p. 115 ; 40 en 1972, Annexe 2 « Tableau des connecteurs » : « 40 : et, VIRGULE »,
    pp. 54-55). Les locutions sont reconstituées (« ainsi que », remarque 2, p.32 du § 3.1423).

    Utilisée par : extraction_grew.py.
    """
    famille = [membre] + [x for x in phrase.mots.values()
                          if x.tete == membre.tete and x.relation == "conj"]
    for terme in famille:
        connecteurs = phrase.dependants(terme.id, {"cc"})
        if connecteurs:
            cc = connecteurs[0]
            parties = [cc] + phrase.dependants(cc.id, {"fixed"})
            return " ".join(x.lemme.lower() for x in sorted(parties, key=lambda x: x.id))
    return "et"


def membre_nie(phrase: Phrase, membre: Mot) -> bool:
    """Indique si un marqueur de négation dépend du terme coordonné (« et pas Marcel ») : l'énoncé
    de ce terme est alors négatif (F).

    Attesté : « Jeanne aime Albert et pas Marcel » -> (JEANNE AIMER + ALBERT) et
    NEG (JEANNE AIMER + MARCEL) (manuel, § 3.1423, p. 32).

    Utilisée par : extraction_grew.py.
    """
    return any(x.lemme.lower() in NEGATIONS_DE_MEMBRE or x.traits.get("Polarity") == "Neg"
               for x in phrase.dependants(membre.id, {"advmod"}))


# --- 6. Ensembles A1, A2… -------------------------------------------------------------------------

@dataclass
class Ensembles:
    """Attribue et mémorise les symboles A1, A2… des groupes coordonnés.

    En 1969, des termes coordonnés peuvent former un ensemble (annexe I : « le Roi et la Reine »
    -> R ; E2-15) : l'énoncé porte un symbole, et chaque membre donne un énoncé d'appartenance
    (voir `_appartenances`). Le livre écrit R, X, K (attestés : énoncés 1-3, 4-6 et 9-12 de
    l'annexe I) ; nous écrivons A1, A2… parce que R, L, U… sont déjà des codes de déterminants.

    NB : l'écart de notation n'est pas décoratif. X a deux emplois dans les ouvrages : symbole
    de groupe (1969, annexe I, énoncés 4-6) et terme vidé (1972, § 3.1413, p. 20, E2-22) ; une
    sortie contenant à la fois (X ARRIVER) et (Ø X ETRE Ø + Ø STUPIDE) serait ambiguë. R est la
    marque de reprise (1972, p. 20 : « R METEO E Ø + Ø NATIONAL »). Et l'annexe I n'a que trois
    groupes : une lettre par groupe ne survit pas à un discours entier ; A1, A2… est inépuisable.
    A1, A2… reste un choix du programme (aucun livre ne le mentionne) ; la lettre A suit le
    manuel : le symbole intermédiaire du drapeau est A (1972, § 3.1423, p. 33 : « A CONTENIR +
    D BLANC »).

    Un seul objet `Ensembles` sert pour tout un discours : le même groupe garde le même symbole,
    même quand un pronom le reprend plus loin (« ils »). `obtenir(cle)` renvoie le symbole
    du groupe et True si le groupe est nouveau (il faut alors écrire ses énoncés d'appartenance).

    `actifs` : réglage `coordination_1969` ; False = termes séparés en 1969 aussi. Un
    groupe jugé inséparable par l'analyste reçoit un symbole même quand `actifs` est False.

    Utilisée par : extraction_grew.py.
    """
    compteur: int = 0
    symboles: dict[str, str] = field(default_factory=dict)
    actifs: bool = True       # False : en 1969 aussi, les termes coordonnés sont séparés (LG6)

    def obtenir(self, cle: str) -> tuple[str, bool]:
        if cle in self.symboles:
            return self.symboles[cle], False
        self.compteur += 1
        self.symboles[cle] = f"A{self.compteur}"
        return self.symboles[cle], True


@dataclass
class _Terme:
    """Un terme prêt à remplir les cases d'un énoncé extrait : déterminant (`d`), lemme, numéro
    du mot (`ident`), et, pour un terme coordonné, sa préposition, son connecteur et sa négation.

    Utilisée par : extraction_grew.py (membres d'un ensemble, passés à `_appartenances`).
    """
    d: str
    lemme: str
    ident: int
    pp: str = ""
    marqueur: str = ""
    nie: bool = False


def _appartenances(phrase: Phrase, membres: list[_Terme], symbole: str, codage: str,
                   hote: int, place: str) -> list[dict]:
    """Crée les énoncés qui relient les membres à un symbole de groupe.

    - 1969 : un énoncé d'appartenance par membre, « roi ε3 à A1 » (attesté : annexe I, énoncés 2-3,
      « L roi ε3 à R ») ;
    - 1972 : propriété intermédiaire, « A1 CONTENIR roi » (attesté : § 3.1423, p. 33 —
      « L DRAPEAU ETRE + A / A CONTENIR + D BLANC / A CONTENIR + D NOIR »).
    `hote` : numéro (dans la phrase) de l'énoncé qui porte le symbole ; `place` : « sujet » ou
    « complement ». Ils sont gardés dans l'ancrage (`hote`, `place_hote`) pour l'étape 3.

    Renvoie des lignes (dictionnaires de cases), que extraction_grew.py transforme en énoncés.
    Utilisée par : extraction_grew.py.
    """
    coder = CODAGES[codage]
    if codage == "1972":   # propriété intermédiaire : « A CONTENIR + D BLANC » (manuel § 3.1423, p. 33)
        return [
            dict(F=coder(FormeVerbale(copule=True)), D1=VIDE, N1=symbole, V="contenir", ADV=VIDE,
                 PP="*", D2=membre.d, N2_3=membre.lemme, source=f"{phrase.sent_id}:{membre.ident}",
                 _ancrage=Ancrage(phrase=phrase.sent_id, n2=membre.ident), _hote=hote, _place=place)
            for membre in membres
        ]
    return [
        dict(F=coder(FormeVerbale(copule=True)), D1=membre.d, N1=membre.lemme, V="ε3", ADV=VIDE,
             PP="à", D2=VIDE, N2_3=symbole, source=f"{phrase.sent_id}:{membre.ident}",
             _ancrage=Ancrage(phrase=phrase.sent_id, n1=membre.ident), _hote=hote, _place=place)
        for membre in membres
    ]


# --- 7. Locutions prépositionnelles ---------------------------------------------------------------

def est_tete_de_locution(phrase: Phrase, mot: Mot) -> bool:
    """Indique si le mot fait partie d'une locution prépositionnelle connue.

    « au milieu de la salle » : « milieu » (liste NOMS_LOCUTION de lexique.py) n'est pas un
    terme ; avec « de », il forme la préposition « au milieu de ». On ne tire donc pas d'énoncé
    « milieu ε de salle ». Attesté : annexe I, énoncé 28 — « table ε * au milieu de L salle »
    (p. 117) : « au milieu de » figure tel quel dans la case PP.

    Utilisée par : extraction_grew.py.
    """
    return (mot.relation == "nmod" and mot.lemme.lower() in NOMS_LOCUTION
            and any(m.upos in CATEGORIES_NOMINALES for m in phrase.dependants(mot.id, {"nmod"})))
