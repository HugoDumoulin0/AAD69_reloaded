"""Les listes de mots utilisées par les règles.

À quoi sert ce module ?,

Certaines règles dépendent du mot lui-même, pas seulement de sa catégorie ou de sa place dans
l'arbre. Par exemple, « au milieu de la salle » doit donner PP = « au milieu de », mais
« au bout de la salle » ne le donnera que si « bout » est dans la liste NOMS_LOCUTION. Ces listes
décrivent le français ; elles sont toutes ici.

On les a regroupées pour trois raisons : les voir d'un coup d'œil, savoir d'où vient chaque mot, et pouvoir les
compléter sans toucher aux règles. Les modules qui les utilisent les importent d'ici (et les
ré-exportent sous le même nom, pour ne rien casser).

"""

#  Étape 2 : extraction des énoncés
# Utilisées par extraction.py (et, pour NOMS_LOCUTION et NOMINALISATIONS, par extraction_grew.py).

# Noms qui forment une locution prépositionnelle avec « de » : « au milieu de la salle »
# -> PP = « au milieu de », N2/3 = salle (et non : N2/3 = milieu, puis « milieu ε de salle »).
# Clé : le nom ; valeur : la préposition complète qui va dans la case PP.
# Annexe I (p.117), énoncé 28 (« au milieu de ») ; les autres : construit.
NOMS_LOCUTION = {
    "milieu": "au milieu de", "cours": "au cours de", "côté": "à côté de",
    "bord": "au bord de", "lieu": "au lieu de", "face": "en face de", "fond": "au fond de",
}

# Noms de quantité, qui jouent le rôle d'un déterminant : dans « toutes sortes de quadrupèdes »,
# le terme de l'énoncé est « quadrupède », pas « sorte » (E2-17).
# Annexe I (p.117), énoncés 9-11 (« foule », « sorte ») ; les autres : construit.
NOMS_QUANTITE = {"sorte", "espèce", "genre", "foule", "multitude", "nombre", "quantité", "tas",
                 "plupart", "série", "masse"}

# Nominalisation d'un adjectif attribut qui a son propre complément (E2-21) : livre, p. 80,
# « Napoléon était avide de gloire » -> « (avide -> avidité) ε de gloire », « pour pouvoir
# appliquer la règle d'adjonction ». L'adjectif devient un nom, qui peut alors être N1 d'un
# énoncé à copule. Clé : l'adjectif ; valeur : le nom.
# Seul « avide » vient du livre ; le reste est construit (adjectifs courants à complément). Un
# adjectif absent de la liste garde sa forme (E2-21).
NOMINALISATIONS = {
    "avide": "avidité", "fier": "fierté", "jaloux": "jalousie", "capable": "capacité",
    "certain": "certitude", "conscient": "conscience", "content": "contentement",
    "curieux": "curiosité", "digne": "dignité", "fidèle": "fidélité", "fou": "folie",
    "heureux": "bonheur", "libre": "liberté", "plein": "plénitude", "responsable": "responsabilité",
    "sûr": "sûreté", "utile": "utilité", "proche": "proximité", "différent": "différence",
    "semblable": "similitude", "généreux": "générosité", "prudent": "prudence",
    "sensible": "sensibilité", "amoureux": "amour", "désireux": "désir", "riche": "richesse",
    "coupable": "culpabilité", "dépendant": "dépendance", "indépendant": "indépendance",
}

# Pronoms dont le contenu est « vidé » : manuel 1972, (p.20), § 3.1413, « Dans le cas où le contenu d'un terme
# est vidé (cas de certains pronoms), on représente par X la place de ce terme vidé »
# (« Celui qui soutient cette opinion est stupide » : N1 = X). E2-22.
# MARQUE_TERME_VIDE est ce qu'on écrit dans la case à la place du pronom.
PRONOMS_VIDES = {"celui", "celle", "ceux", "celles"}
MARQUE_TERME_VIDE = "X"

# Première personne : manuel (p.32), § 3.1423, « André et moi sommes allés au meeting »se décompose en deux énoncés liés par le connecteur :
#  (ANDRÉ ALLER A L MEETING) et (EGO ALLER A L MEETING)
MARQUE_EGO = "EGO"


# VOIX — participe passé employé seul
# ---------------------------------------------------------------------------
#   - en 1972, la voix est la ligne A du code de F : 0 = actif, 1 =
#     passif ; exemple codé « 2006 Jean avait été attaqué par un
#     voleur » (manuel 1972, p. 18) ; le passif se transcrit par PAR :
#     « (L BASTILLE PRENDRE PAR L PEULEPLE) » (manuel 1972, p. 34,
#     § 3.1425) ;
#   - l'annexe I du livre 1969 reçoit un participe passé employé seul
#     comme un passif : énoncé 9 « foule composer de = par Ø K », codé
#     F5, où « de = par » glose « de » comme l'agent du passif
#     (livre 1969, p. 117). La voix y l'emporte sur le temps : énoncé 14
#     « était enchaîné » → F5, malgré l'imparfait.
#
# Ce que le texte laisse ouvert :
#   Pêcheux ne traite nulle part le participe passé employé seul d'un
#   verbe qui se conjugue avec être. Le seul exemple attesté du
#   participe seul (« composer », énoncé 9) n'est pas un verbe en être,
#   et « participe » n'apparaît dans le livre 1969 qu'à la p. 130, à
#   propos du mode. L'énoncé 9 ne permet donc pas de décider si
#   « arrivé à Paris » serait un passif.
#
# Décision d'implémentation :
#   Un participe passé employé seul est reçu comme un passif (F5),
#   SAUF pour les verbes qui se conjuguent avec être : « arrivé à
#   Paris » reste actif, « invité à Paris » est passif. Raison : ces
#   verbes (aller, arriver, naître, mourir, rester, tomber, retourner,
#   devenir, passer...) décrivent un procès dont le sujet reste l'agent ;
#   l'auxiliaire être y est un choix de conjugaison du français, pas une
#   marque de voix. La règle vit dans la liste ci-dessous : tout ajout
#   ou retrait se fait là, et nulle part ailleurs.

VERBES_ETRE = {
    "aller", "venir", "arriver", "partir", "entrer", "sortir", "monter", "descendre", "tomber",
    "naître", "mourir", "rester", "retourner", "devenir", "revenir", "parvenir", "passer", "décéder",
    "intervenir", "survenir", "rentrer", "repartir", "redevenir",
}

# case ADV (1969, annexe IV, p. 128 à p. 130) :
# détermination dans F
# négation, modalité et aspect -> F (opérateurs portant sur la totalité de l'énoncé) ;
# localisation spatio-temporelle -> N2 (circonstants). 
# Le degré est absorbé : rien dans aucune case (énoncé 31, p. 117 : « si » absent

# Utilisées par determinant.py (case ADV) et, pour la négation, par forme.py.


ADVERBES_NEGATION = {"ne", "pas", "jamais", "plus", "point", "guère"}       # -> F (polarité)

# -> F, opérateurs portant sur tout l'énoncé (annexe IV, p. 130 : M1
# oui/non, M2 probablement/certainement, M3 malheureusement, M4
# obstinément/volontairement ; aspect duratif : encore, toujours).
# Construits : peut-être, sûrement, heureusement, souvent, déjà.
# NB : pas enregistrées/implémentées
ADVERBES_MODALITE_ASPECT = {                                                
    "peut-être", "probablement", "certainement", "sûrement", "malheureusement", "heureusement",
    "encore", "toujours", "déjà", "souvent", "volontairement", "obstinément", "oui", "non",
}

# Absorbées : aucune case dans la p. 117.  « Elles étaient si appétissantes qu'Alice eut une envie folle de les manger » (p. 113)
# -> énoncé 31 « LS tarte être * appétissant » (p. 117) : le « si » de
# ne figure dans aucune des 8 cases.
ADVERBES_DEGRE = {"si", "très", "trop", "tellement", "tant", "aussi", "moins", "assez", "fort"}  # portent sur l'adjectif

# -> N2/3, circonstants
ADVERBES_LIEU_TEMPS = {"ici", "là", "hier", "demain", "aujourd'hui", "maintenant", "alors", "ailleurs"}  # -> N2/3


# Un mot de degré devant « que » marque une conséquence : « si appétissantes qu'… » -> φ5
# annexe I, p. 115 ; l'énoncé 31 (p. 117) en fournit le contexte. 
# Précédence : utilisé ici seulement devant « que » ; sinon, degré @ADVERBES_DEGRE
MOTS_DEGRE = {"si", "tellement", "tant", "trop"}

# Une préposition de lieu ou de temps indique un complément circonstanciel, même si Stanza l'analyse comme complément du verbe
# (obl:arg). 
# Pêcheux enregistre ces prépositions dans la case PP de l'énoncé (annexe I, p. 117) sans jamais distinguer argument du
# verbe et circonstanciel ; E3-14 montre ce ce que le texte laisse ouvert.
PREPOSITIONS_CIRCONSTANCIELLES = {
    "dans", "sur", "sous", "près de", "loin de", "autour de", "devant", "derrière", "chez", "vers", "entre",
    "parmi", "contre", "hors de", "au milieu de", "au bord de", "au fond de", "à côté de", "en face de",
    "pendant", "avant", "après", "depuis", "durant", "dès", "jusqu'à",
}