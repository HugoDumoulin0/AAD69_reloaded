"""Analyse syntaxique du corpus : texte brut français -> CoNLL-U via Stanza.

Couche d'outillage en amont de l'AAD 69 : ce module ne contient aucune
règle du livre (1969). Il produit les données brutes, lemmes, UPOS,
dépendances au format CoNLL-U (celui du projet Universal Dependencies) ;
conllu.py relit ce format, et les modules aval (lexique, forme,
déterminant…) appliquent ensuite Pêcheux sur ces données.

Pourquoi un texte CoNLL-U plutôt que des objets en mémoire : l'analyse
Stanza est coûteuse (modèle neuronal). analyser_texte renvoie le texte
CoNLL-U à côté des phrases : sauvegardé une fois, il se relit avec
lire_conllu_texte (conllu.py) sans jamais recharger le modèle.
"""
from __future__ import annotations

from .conllu import Phrase, lire_conllu_texte

_PIPELINE = None


def stanza_disponible() -> bool:
    """Vrai si la bibliothèque stanza est installée, sans l'importer.

    find_spec teste la présence du paquet sans l'exécuter : importer
    stanza (et torch) coûterait plusieurs secondes… pour échouer.
    Sert à afficher « stanza n'est pas installé » à la place d'un
    ImportError brut venu de la première analyse.
    """
    import importlib.util
    return importlib.util.find_spec("stanza") is not None


def conllu_depuis_doc(doc, prefixe: str, version_stanza: str = "") -> str:
    """Document Stanza -> texte CoNLL-U (# sent_id : prefixe-1, prefixe-2…).

    Mots contractés (Stanza : « multi-word tokens ») : Stanza donne le
    token visible « du » ET ses mots « de »/« le » avec leurs lemmes.
    Le CoNLL-U exige les deux niveaux : une ligne « plage » (3-4 du)
    puis une ligne par mot (3 de, 4 le). Sans la ligne plage, le fichier
    est invalide pour tout lecteur CoNLL-U strict ; sans les lignes de
    mots, on perd les lemmes « de »/« le » qu'utilisent les modules aval.

    Détails : token.id de Stanza est une liste (["3", "4"] pour « du »),
    d'où id[0]-id[-1] ; les 8 « _ » portent la ligne plage aux 10
    colonnes exigées ; rstrip évite l'espace final de « # generator »
    quand version_stanza est vide.
    """
    lignes = [f"# generator = stanza {version_stanza}".rstrip()]
    for i, phrase in enumerate(doc.sentences, start=1):
        lignes += [f"# sent_id = {prefixe}-{i}", f"# text = {phrase.text}"]
        for token in phrase.tokens:
            if len(token.words) > 1:  # mot contracté (du = de + le) : ligne « plage » puis les mots
                lignes.append(f"{token.id[0]}-{token.id[-1]}\t{token.text}" + "\t_" * 8)
            for mot in token.words:
                lignes.append("\t".join([
                    str(mot.id), mot.text, mot.lemma or "_", mot.upos or "_", mot.xpos or "_",
                    mot.feats or "_", str(mot.head), mot.deprel or "_", "_", "_"]))
        lignes.append("")  # ligne vide obligatoire après chaque phrase : c'est elle qui les sépare
    return "\n".join(lignes) + "\n"


def analyser_texte(texte: str, prefixe: str) -> tuple[str, list[Phrase]]:
    """Texte brut -> (texte CoNLL-U, phrases). Modèle français chargé une seule fois.

    Le chargement du modèle neuronal de Stanza prend plusieurs dizaines de
    secondes : la globale _PIPELINE le garde en mémoire pour tout le
    processus. Conséquence : première analyse lente, suivantes immédiates
    — d'où l'intérêt de sauvegarder le CoNLL-U renvoyé.

    Contournement torch : depuis torch 2.6, torch.load refuse par défaut
    les fichiers « non sûrs » (weights_only=True par défaut), et le
    chargement des modèles Stanza échoue (UnpicklingError). On remplace
    donc torch.load par une version qui force weights_only=False,
    uniquement le temps de créer le Pipeline, puis on restaure l'original
    dans le finally : le reste du programme garde un torch.load normal.

    Exemple : analyser_texte("Alice mange une pomme.", "alice") ->
    # sent_id = alice-1 ; lemmes Alice / manger / un / pomme.
    """
    global _PIPELINE
    import stanza
    if _PIPELINE is None:
        import torch

        torch_load = torch.load

        def torch_load_stanza(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return torch_load(*args, **kwargs)

        try:
            torch.load = torch_load_stanza
            _PIPELINE = stanza.Pipeline("fr", processors="tokenize,mwt,pos,lemma,depparse")
        finally:
            torch.load = torch_load
    conllu = conllu_depuis_doc(_PIPELINE(texte), prefixe, stanza.__version__)
    return conllu, lire_conllu_texte(conllu)
