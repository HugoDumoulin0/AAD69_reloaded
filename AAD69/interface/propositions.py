"""Construit les repères de propositions affichés à partir des arbres CoNLL-U.

Ce module prépare des informations de consultation pour l'interface ; il ne
modifie ni le corpus d'origine ni les règles qui produisent les énoncés.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aad69.conllu import Mot, Phrase
from aad69.commun import est_predicat, preposition, sujet as extraire_sujet, verbes_etiquetes_aux
from aad69.pipeline import LINGUISTE_DISPONIBLE

if TYPE_CHECKING:
    from aad69.linguiste import Lecture

if LINGUISTE_DISPONIBLE:
    from aad69.linguiste import appliquer_rattachements
else:
    def appliquer_rattachements(phrases, lecture):
        """Sans module linguiste, conserve les phrases non corrigées."""
        if lecture is not None:
            raise RuntimeError("Partie linguiste indisponible dans cette installation.")
        return phrases

RELATIONS_COMPLEMENTS = {"obj", "iobj", "obl", "nmod"}

NOMS_RELATIONS = {
    "acl": "relative / dépendance adjectivale",
    "acl:relcl": "relative",
    "advcl": "circonstancielle",
    "ccomp": "complétive",
    "conj": "coordination",
    "parataxis": "juxtaposition",
    "xcomp": "infinitive dépendante",
}


def _etiquette(mot: Mot, sent_id: str, decisions: set[tuple[str, int]]) -> dict[str, str | int | bool]:
    """Prépare les informations d'affichage d'un mot et signale s'il a été corrigé."""
    return {
        "id": mot.id,
        "forme": mot.forme,
        "lemme": mot.lemme,
        "relation": mot.relation,
        "corrige_par_linguiste": (sent_id, mot.id) in decisions,
    }


def construire_propositions(phrases: list[Phrase], lecture: Lecture | None = None) -> list[dict]:
    """Décrit les propositions repérées dans chaque phrase pour la page de consultation.

    Pour chaque prédicat, associe son sujet, ses compléments, les autres
    prédicats dont il dépend et les éventuelles corrections du linguiste.
    """
    resultat = []
    # Seules les corrections de rattachement acceptées sont marquées dans l'affichage.
    decisions_linguiste = {
        (d.sent_id, d.mot) for d in (lecture.decisions if lecture else [])
        if d.type == "rattachement" and d.appliquee
    }

    # Applique les rattachements à une copie de travail pour représenter la lecture retenue.
    phrases_corrigees = appliquer_rattachements(phrases, lecture)
    for phrase in phrases_corrigees:
        # Traite les verbes étiquetés comme auxiliaires, puis repère les prédicats de la phrase.
        phrase = verbes_etiquetes_aux(phrase)
        predicats = [m for m in phrase.mots.values() if est_predicat(m, phrase)]
        ids_predicats = {m.id for m in predicats}
        propositions = []

        for predicat in predicats:
            # Récupère le sujet et indique s'il dépend d'un prédicat précédent par coordination.
            sujet_ = extraire_sujet(phrase, predicat)
            sujet_affiche = None
            if sujet_ is not None:
                sujet_affiche = _etiquette(sujet_, phrase.sent_id, decisions_linguiste)
                sujet_affiche["heritage"] = sujet_.tete != predicat.id

            # Distingue les compléments du prédicat des autres prédicats qui lui sont liés.
            complements = []
            liees = []
            for dependance in phrase.dependants(predicat.id):
                relation = dependance.relation.split(":")[0]
                if dependance.id in ids_predicats and dependance.id != predicat.id:
                    liees.append({
                        **_etiquette(dependance, phrase.sent_id, decisions_linguiste),
                        "type": NOMS_RELATIONS.get(dependance.relation, NOMS_RELATIONS.get(relation, relation)),
                    })
                elif relation in RELATIONS_COMPLEMENTS:
                    pp = preposition(phrase, dependance) if relation in {"obl", "nmod"} else ""
                    complements.append({
                        **_etiquette(dependance, phrase.sent_id, decisions_linguiste),
                        "type": {"obj": "objet", "iobj": "complément indirect",
                                 "obl": "complément prépositionnel", "nmod": "dépendance nominale"}[relation],
                        "preposition": pp if pp != "Ø" else "",
                    })

            # Remonte l'arbre jusqu'au prédicat parent le plus proche.
            tete = phrase.mots.get(predicat.tete)
            parent = None
            courant = tete
            while courant is not None:
                if courant.id in ids_predicats:
                    parent = _etiquette(courant, phrase.sent_id, decisions_linguiste)
                    break
                courant = phrase.mots.get(courant.tete) if courant.tete else None

            # Assemble les informations qui seront affichées pour ce prédicat.
            mode = predicat.traits.get("VerbForm", "")
            propositions.append({
                "mot": _etiquette(predicat, phrase.sent_id, decisions_linguiste),
                "type": "prédicat verbal" if predicat.upos == "VERB" else "prédicat à copule",
                "mode": mode,
                "relation": predicat.relation,
                "parent": parent,
                "tete_syntaxique": _etiquette(tete, phrase.sent_id, decisions_linguiste)
                if tete and parent is None else None,
                "sujet": sujet_affiche,
                "complements": complements,
                "propositions_liees": liees,
            })

        resultat.append({"phrase": phrase, "propositions": propositions})
    return resultat
