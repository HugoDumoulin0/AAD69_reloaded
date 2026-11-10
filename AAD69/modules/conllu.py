"""Lecture de l'analyse syntaxique (sortie de Stanza) : étape 1 du programme.

Ce module fait une seule chose : il lit un fichier CoNLL-U et le range dans deux objets Python,
`Phrase` et `Mot`. Toutes les étapes suivantes (extraction des énoncés, anaphores, relations)
partent de ces objets. Aucune analyse linguistique n'est faite ici.

Le format CoNLL-U
-----------------
C'est le format standard des arbres de dépendances (Universal Dependencies, UD). Stanza le produit.
- Une ligne par mot, 10 colonnes séparées par des tabulations :
  ID (numéro du mot dans la phrase), FORM (le mot tel qu'il est écrit), LEMMA (sa forme de
  dictionnaire), UPOS (sa catégorie : NOUN, VERB, ADJ…), XPOS (catégorie propre à la langue),
  FEATS (ses traits : genre, nombre, temps…), HEAD (le numéro du mot dont il dépend : sa
  « tête » ; 0 pour la racine de la phrase), DEPREL (le nom de la relation avec sa tête : nsubj
  = sujet, obj = objet, obl = complément prépositionnel…), DEPS, MISC.
- Une ligne vide sépare deux phrases.
- Les lignes qui commencent par « # » sont des commentaires ; on y lit l'identifiant de la phrase
  (« # sent_id = … ») et son texte (« # text = … »).

Exemple (« Le facteur perdit la lettre. ») :
    1  Le       le       DET   …  2  det
    2  facteur  facteur  NOUN  …  3  nsubj     <- « facteur » dépend de « perdit » : sujet
    3  perdit   perdre   VERB  …  0  root      <- racine de la phrase
    4  la       le       DET   …  5  det
    5  lettre   lettre   NOUN  …  3  obj       <- « lettre » dépend de « perdit » : objet

Ce qu'on garde et ce qu'on ignore
---------------------------------
On garde les colonnes ID, FORM, LEMMA, UPOS, FEATS, HEAD, DEPREL. XPOS, DEPS et MISC ne servent
à aucune règle.

On ignore deux sortes de lignes :
- les lignes « plage » des mots contractés (« 2-3  du ») : CoNLL-U écrit « du » sur une ligne,
  puis « de » (2) et « le » (3) sur deux lignes. On garde « de » + « le », ce qui sépare la
  préposition et le déterminant, comme Pêcheux le fait dans les énoncés (PP et D2 sont deux
  cases différentes) ;
- les nœuds vides (identifiants décimaux comme « 8.1 »), qu'UD ajoute pour des mots
  sous-entendus ; aucune règle ne les utilise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Mot:
    """Un mot de la phrase, c'est-à-dire une ligne CoNLL-U.

    - `id` : son numéro dans la phrase (colonne ID), à partir de 1 ;
    - `forme` : le mot tel qu'il est écrit (« perdit ») ;
    - `lemme` : sa forme de dictionnaire (« perdre ») ; c'est le lemme qui va dans les énoncés ;
    - `upos` : sa catégorie UD (NOUN, VERB, ADJ, PRON, DET, ADP…) ;
    - `traits` : ses traits morphologiques, sous forme de dictionnaire
      (« Gender=Fem|Number=Sing » -> {"Gender": "Fem", "Number": "Sing"}) ; d'autres modules y
      ajoutent leurs propres marques (anaphore rétablie, terme inséparable…) ;
    - `tete` : le numéro du mot dont il dépend ; 0 = c'est la racine de la phrase ;
    - `relation` : le nom de la relation avec sa tête (nsubj, obj, obl:mod…).

    `frozen=True` : un mot ne se modifie pas après la lecture. Pour corriger un mot (par exemple
    quand le linguiste change son rattachement), on crée un nouveau `Mot`.
    """

    id: int
    forme: str
    lemme: str
    upos: str
    traits: dict
    tete: int
    relation: str


@dataclass
class Phrase:
    """Une phrase : son identifiant, son texte, et ses mots rangés par numéro.

    `mots` est un dictionnaire {numéro: Mot}, pour retrouver directement un mot par son numéro
    (la tête d'un mot, par exemple : `phrase.mots[mot.tete]`).
    """

    sent_id: str
    texte: str
    mots: dict[int, Mot] = field(default_factory=dict)

    def dependants(self, tete: int, relations: set[str] | None = None) -> list[Mot]:
        """Les mots qui dépendent directement du mot numéro `tete`, dans l'ordre de la phrase.

        C'est l'opération de base de toutes les règles : « le sujet de ce verbe », « les
        déterminants de ce nom »… Dans l'exemple du docstring du module, `dependants(3)` donne
        « facteur » et « lettre », et `dependants(3, {"obj"})` donne « lettre ».

        `relations` filtre sur la relation ; sans filtre, on a tous les dépendants. Le filtre
        accepte aussi les sous-types UD (la partie après « : ») : « obl » trouve aussi
        « obl:mod », « obl:agent »… ; « obl:mod » ne trouve que « obl:mod ».
        """
        resultat = []
        for mot in self.mots.values():
            if mot.tete != tete:
                continue
            if relations is None or mot.relation in relations or mot.relation.split(":")[0] in relations:
                resultat.append(mot)
        return resultat


def _lire_traits(texte: str) -> dict:
    """La colonne FEATS en dictionnaire : « Gender=Fem|Number=Sing » -> {"Gender": "Fem", …} ;
    « _ » (aucun trait) -> {}. Une paire sans « = » lève ValueError (traitée par l'appelant)."""
    if texte == "_":
        return {}
    return dict(paire.split("=", 1) for paire in texte.split("|"))


def lire_conllu(chemin: str | Path) -> list[Phrase]:
    """Lit un fichier CoNLL-U et renvoie ses phrases dans l'ordre du fichier.
    Le travail est fait par `lire_conllu_texte` ; cette fonction ne fait qu'ouvrir le fichier."""
    with open(chemin, encoding="utf-8") as f:
        return lire_conllu_texte(f.read())


class ErreurConllu(ValueError):
    """Fichier CoNLL-U mal formé. Le message donne le numéro de la ligne fautive, pour qu'on puisse
    corriger le fichier à la main."""


def _entier(valeur: str, colonne: str, numero: int) -> int:
    """Convertit une colonne numérique (ID ou HEAD) en entier, ou lève ErreurConllu avec la ligne.
    `from None` : on cache l'erreur Python d'origine, notre message suffit."""
    try:
        return int(valeur)
    except ValueError:
        raise ErreurConllu(f"Ligne {numero} : {colonne} « {valeur} » n'est pas un nombre entier.") from None


def _verifier_tetes(phrase: Phrase, lignes: dict[int, int]) -> None:
    """Vérifie que chaque mot a une tête qui existe dans la phrase (ou 0, la racine).

    On ne peut le faire qu'une fois la phrase entièrement lue : une tête peut se trouver plus loin
    dans la phrase que le mot qui en dépend. `lignes` ({numéro du mot: numéro de ligne dans le
    fichier}) sert seulement à donner la bonne ligne dans le message d'erreur.
    """
    for mot in phrase.mots.values():
        if mot.tete != 0 and mot.tete not in phrase.mots:
            raise ErreurConllu(f"Ligne {lignes[mot.id]} (phrase {phrase.sent_id}) : le mot {mot.id} « {mot.forme} » "
                               f"a pour tête {mot.tete}, qui n'existe pas dans la phrase.")


def lire_conllu_texte(texte: str) -> list[Phrase]:
    """Lit du CoNLL-U donné sous forme de texte (par exemple un fichier déposé dans l'interface).

    Comment : on lit ligne par ligne. Une ligne vide termine la phrase en cours ; une ligne « # »
    donne l'identifiant ou le texte de la phrase ; toute autre ligne est un mot.

    Un fichier mal formé lève `ErreurConllu`, avec le numéro de la ligne :
    - moins de 8 colonnes (souvent des espaces au lieu de tabulations) ;
    - identifiant ou tête qui n'est pas un nombre ;
    - traits illisibles ;
    - tête absente de la phrase ;
    - identifiant répété dans la phrase.

    Deux tolérances :
    - une phrase sans « # sent_id » reçoit s1, s2… (pratique pour les petits fichiers écrits à la
      main) ;
    - un bloc qui n'a que des commentaires est ignoré.
    """
    phrases: list[Phrase] = []
    courante: Phrase | None = None           # la phrase en cours de lecture
    lignes_mots: dict[int, int] = {}         # numéro du mot -> numéro de ligne (pour les messages)

    def terminer() -> None:
        """Ferme la phrase en cours : vérifie les têtes et l'ajoute au résultat (si elle a des mots)."""
        if courante is not None and courante.mots:
            _verifier_tetes(courante, lignes_mots)
            phrases.append(courante)

    for numero, ligne in enumerate(texte.splitlines(), start=1):
        ligne = ligne.rstrip("\n")
        if not ligne.strip():                                    # ligne vide : fin de phrase
            terminer()
            courante, lignes_mots = None, {}
            continue
        if courante is None:                                     # première ligne d'une phrase
            courante = Phrase(sent_id=f"s{len(phrases) + 1}", texte="")
        if ligne.startswith("#"):                                # commentaire : sent_id ou text
            cle, _, valeur = ligne[1:].partition("=")
            if cle.strip() == "sent_id":
                courante.sent_id = valeur.strip()
            elif cle.strip() == "text":
                courante.texte = valeur.strip()
            continue
        colonnes = ligne.split("\t")
        if len(colonnes) < 8:
            raise ErreurConllu(f"Ligne {numero} : {len(colonnes)} colonne(s) au lieu de 10 "
                               "(séparateur attendu : tabulation).")
        if "-" in colonnes[0] or "." in colonnes[0]:              # « 2-3 du » ou nœud vide « 8.1 »
            continue
        ident = _entier(colonnes[0], "l'identifiant", numero)
        if ident in courante.mots:
            raise ErreurConllu(f"Ligne {numero} : l'identifiant {ident} est déjà utilisé dans la phrase.")
        try:
            traits = _lire_traits(colonnes[5])
        except ValueError:
            raise ErreurConllu(f"Ligne {numero} : traits illisibles « {colonnes[5]} » (attendu : Cle=Valeur|…).") from None
        mot = Mot(                                                # colonnes 0 à 7 : ID … DEPREL
            id=ident, forme=colonnes[1], lemme=colonnes[2], upos=colonnes[3],
            traits=traits, tete=_entier(colonnes[6], "la tête", numero), relation=colonnes[7],
        )
        courante.mots[mot.id] = mot
        lignes_mots[mot.id] = numero
    terminer()  # la dernière phrase, si le fichier ne finit pas par une ligne vide
    return phrases