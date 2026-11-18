"""État de l'interface : le corpus chargé, la version affichée, les réglages, les noms des hyperdomaines.

L'interface est une application LOCALE, pour une personne à la fois : l'état est gardé en
mémoire dans un objet `Etat` attaché à l'application Flask (une instance par application,
ce qui permet aux tests de repartir de zéro).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from aad69.comparaison import Poids
from aad69.conllu import Phrase, lire_conllu
from aad69.modele import CASES, Enonce, RelationBinaire
from aad69.pipeline import (Corpus, Resultats, appliquer_corrections, corpus_depuis_discours, corpus_depuis_tables,
                            executer, LINGUISTE_DISPONIBLE)
from aad69.reference import charger_enonces, charger_relations
from aad69.reglages import Reglages

if TYPE_CHECKING:
    from aad69.linguiste import Lecture

ETATS_LISIBLES = {"a_verifier": "à vérifier", "acceptee": "acceptée", "refusee": "refusée",
                  "corrigee": "modifiée par l'analyste"}

RACINE = Path(__file__).resolve().parents[2]
REF = RACINE / "tests" / "reference"

EXEMPLES = {
    "annexe3": ("Annexe III, Jeanne d'Arc",
                "Les 18 énoncés du domaine (φ2, δ2) du livre, répartis en 6 récits, donnés en tables. "
                "Résultat attendu : 30 zones, 15 chaînes, 1 domaine de 18 énoncés en 1969 ; 2 domaines en 1972."),
    "phrases": ("Phrases de test",
                "Deux petits discours en CoNLL-U, écrits pour les tests des étapes 2 et 3. "
                "Montre la chaîne complète depuis l'analyse syntaxique."),
    "alice": ("Alice, annexe I",
              "Le texte d'Alice analysé par Stanza. Un seul discours : on voit les énoncés et les relations, "
              "mais aucune comparaison n'est possible (il faut au moins deux discours, D7)."),
}

VERSIONS_AFFICHABLES = {"les-deux": ("1969", "1972"), "1969": ("1969",), "1972": ("1972",)}


def _poids_depuis(r: dict) -> Poids:
    """Reconstruit les poids à partir des valeurs du formulaire."""
    livre = Poids()
    return Poids(identiques={c: int(r.get(f"poids_id_{c}", livre.identiques[c])) for c in CASES},
                 vides={c: (None if livre.vides[c] is None else int(r.get(f"poids_vide_{c}", livre.vides[c])))
                        for c in CASES},
                 copules=int(r.get("poids_copules", livre.copules)))


@dataclass
class Etat:
    """État en mémoire d'une session de l'interface.

    Contient le corpus chargé, les réglages, les corrections manuelles et les
    résultats déjà calculés. Chaque application Flask possède son propre objet.
    """

    source: str = ""
    phrases: dict[str, list[Phrase]] | None = None
    tables: tuple[list[Enonce], list[RelationBinaire]] | None = None
    conllu: dict[str, str] = field(default_factory=dict)
    textes_bruts: dict[str, str] = field(default_factory=dict)
    version_affichee: str = "les-deux"
    reglages: dict = field(default_factory=dict)          # valeurs du formulaire ; vide = réglages du livre
    noms_hyper: dict[str, dict[int, str]] = field(default_factory=dict)
    corrections: dict[str, dict[int, dict[str, str]]] = field(default_factory=dict)  # version -> n° -> case -> valeur (I6)
    message: tuple[str, str] | None = None                # (genre, texte) affiché une fois
    lectures: dict[str, Lecture] = field(default_factory=dict)  # discours -> lecture du linguiste LLM (LG5)
    linguiste_tente: bool = False
    _resultats_cache: dict[str, Resultats] = field(default_factory=dict, init=False, repr=False)

    def invalider_calcul(self):
        """Efface les résultats mémorisés après une modification des entrées."""
        self._resultats_cache.clear()

    # --- corpus -----------------------------------------------------------------------------
    @property
    def a_un_corpus(self) -> bool:
        """Indique si un corpus de phrases ou des tableaux sont chargés."""
        return self.phrases is not None or self.tables is not None

    def charger_phrases(self, discours: dict[str, list[Phrase]], source: str, conllu: dict[str, str] | None = None,
                        textes_bruts: dict[str, str] | None = None):
        """Enregistre des phrases analysées et réinitialise les données liées à l'ancien corpus."""
        self.invalider_calcul()
        self.phrases, self.tables, self.conllu, self.source = discours, None, conllu or {}, source
        self.textes_bruts = textes_bruts or {}
        self.noms_hyper, self.corrections, self.lectures = {}, {}, {}
        self.linguiste_tente = False

    def charger_tables(self, enonces: list[Enonce], relations: list[RelationBinaire], source: str):
        """Enregistre des énoncés et relations déjà construits, après validation de leurs indices."""
        corpus_depuis_tables(enonces, relations)  # vérifie les numéros (I1) : lève ValueError sinon
        self.invalider_calcul()
        self.phrases, self.tables, self.conllu, self.source = None, (enonces, relations), {}, source
        self.textes_bruts = {}
        self.noms_hyper, self.corrections, self.lectures = {}, {}, {}
        self.linguiste_tente = False

    def charger_exemple(self, cle: str):
        """Charge l'un des exemples intégrés : annexe III, phrases de test ou Alice."""
        nom = EXEMPLES[cle][0]
        if cle == "annexe3":
            self.charger_tables(charger_enonces(REF / "enonces_jeanne_annexeIII.csv"),
                                charger_relations(REF / "relations_jeanne_annexeIII.csv"), nom)
        elif cle == "phrases":
            self.charger_phrases({"A": lire_conllu(REF / "phrases_test_2a.conllu"),
                                  "B": lire_conllu(REF / "phrases_test_3.conllu")}, nom)
        else:
            self.charger_phrases({"alice": lire_conllu(REF / "alice_livre.conllu")}, nom)

    def discours(self) -> list[tuple[str, int, str]]:
        """Renvoie, pour chaque discours, son nom, sa taille et un extrait de texte.

        La taille compte les énoncés pour les tableaux, et les phrases pour les
        entrées CoNLL-U.
        """
        if self.tables is not None:
            compte: dict[str, int] = {}
            for e in self.tables[0]:
                compte[e.discours] = compte.get(e.discours, 0) + 1
            return [(d, n, "") for d, n in compte.items()]
        return [(d, len(p), p[0].texte if p else "") for d, p in (self.phrases or {}).items()]

    # --- réglages et calcul ---------------------------------------------------------------------
    @property
    def versions(self) -> tuple[str, ...]:
        """Renvoie les versions à calculer selon le choix affiché dans l'interface."""
        return VERSIONS_AFFICHABLES[self.version_affichee]

    def reglages_pour(self, version: str) -> Reglages:
        """Construit les réglages complets pour une version à partir du formulaire."""
        r = self.reglages
        livre = Reglages()
        # Les champs absents du formulaire reprennent les valeurs par défaut du livre.
        return Reglages(
            version=version, poids=_poids_depuis(r),
            borne=float(r.get("borne", livre.borne)),
            regle=r.get("regle", livre.regle),
            intermediaires=r.get("intermediaires", "oui" if livre.intermediaires else "non") == "oui",
            annulation=r.get("annulation", "oui" if livre.annulation else "non") == "oui",
            exclure_phi_alpha=r.get("exclure_phi_alpha", "oui" if livre.exclure_phi_alpha else "non") == "oui",
            critere_homogeneite=r.get("critere_homogeneite", livre.critere_homogeneite),
            hyperdomaines_1972=r.get("hyperdomaines_1972", "oui" if livre.hyperdomaines_1972 else "non") == "oui",
            resoudre_anaphores=r.get("resoudre_anaphores", "oui" if livre.resoudre_anaphores else "non") == "oui",
            coordination_1969=r.get("coordination_1969", livre.coordination_1969),
        )

    def corpus_brut(self, version: str) -> Corpus:
        """Renvoie le corpus avant les corrections manuelles, pour la version demandée."""
        if self.tables is not None:
            # Les tableaux sont déjà extraits : seule leur validation est nécessaire.
            return corpus_depuis_tables(*self.tables)
        reglages = self.reglages_pour(version)
        return corpus_depuis_discours(self.phrases, version, reglages.resoudre_anaphores, self.lectures or None,
                                      ensembles_1969=reglages.coordination_1969 == "ensemble")

    def calculer(self) -> dict[str, Resultats]:
        """Calcule les résultats des versions affichées et applique les corrections manuelles.

        Les résultats sont gardés en cache jusqu'à ce qu'une entrée, un réglage
        ou une correction change.
        """
        resultats = {}
        for version in self.versions:
            if version not in self._resultats_cache:
                # Construit le corpus brut, applique les corrections, puis exécute les étapes 4 à 7.
                corpus = appliquer_corrections(self.corpus_brut(version), self.corrections.get(version, {}))
                self._resultats_cache[version] = executer(corpus, self.reglages_pour(version))
            resultats[version] = self._resultats_cache[version]
        return resultats

    # --- linguiste LLM (LG5) ------------------------------------------------------------------------
    def lancer_linguiste(self, cache=None) -> tuple[int, int]:
        """Demande une lecture LLM pour chaque discours et enregistre les réponses.

        Renvoie le nombre de décisions produites et le nombre d'éléments rejetés
        pendant leur validation.
        """
        self.linguiste_tente = True
        if not LINGUISTE_DISPONIBLE:
            raise RuntimeError("Partie LLM indisponible : linguiste.py n'est pas publié.")
        try:
            from aad69.linguiste import lire_discours
            from aad69.mistral import CACHE_PAR_DEFAUT
        except ModuleNotFoundError as erreur:
            if erreur.name and erreur.name.endswith((".linguiste", ".mistral")):
                raise RuntimeError(f"Partie LLM indisponible : {erreur.name} n'est pas publié.") from erreur
            raise
        try:
            from dotenv import load_dotenv
            load_dotenv(RACINE / ".env", override=False)
        except ImportError:
            pass
        lectures = {nom: lire_discours(nom, phrases, cache=cache or CACHE_PAR_DEFAUT)
                    for nom, phrases in (self.phrases or {}).items()}
        self.lectures = lectures
        self.invalider_calcul()
        return (sum(len(l.decisions) for l in lectures.values()), sum(len(l.rejets) for l in lectures.values()))

    def lignes_linguiste(self) -> list[dict]:
        """Prépare les lignes d'export pour les décisions et éléments rejetés du LLM."""
        if not self.lectures:
            return []
        from aad69.linguiste import decrire
        lignes = []
        for nom, lecture in self.lectures.items():
            phrases = (self.phrases or {}).get(nom, [])
            for d in lecture.decisions:
                statut = ("oui" if d.acceptee else "non (refusée)") if d.verifiee else "en attente"
                lignes.append({"discours": nom, "phrase": d.sent_id, "type": d.type, "décision": decrire(d, phrases),
                               "raison": d.raison, "état": ETATS_LISIBLES[d.etat], "source": d.source,
                               "acceptée": statut, "vérifiée": "oui" if d.verifiee else "non",
                               "modifiée": "oui" if d.modifiee else "non",
                               "proposition du LLM": d.proposition,
                               "modèle": lecture.modele, "consigne": lecture.consigne})
            for r in lecture.rejets:
                lignes.append({"discours": nom, "phrase": "", "type": "écartée", "décision": r.element,
                               "raison": r.motif, "état": "écartée par la validation", "source": "llm",
                               "acceptée": "non", "vérifiée": "oui", "modifiée": "non",
                               "proposition du LLM": "",
                               "modèle": lecture.modele, "consigne": lecture.consigne})
        return lignes

    @property
    def decisions_a_verifier(self) -> int:
        """Compte les décisions du linguiste qui attendent une vérification."""
        return sum(len(l.a_verifier) for l in self.lectures.values())

    def _lecture(self, discours: str) -> tuple[Lecture, list[Phrase]]:
        """Retrouve la lecture et les phrases d'un discours, ou signale l'absence de lecture."""
        if not LINGUISTE_DISPONIBLE:
            raise RuntimeError("Partie LLM indisponible : linguiste.py n'est pas publié.")
        from aad69.linguiste import Invalide
        if discours not in self.lectures:
            raise Invalide("discours sans lecture")
        return self.lectures[discours], (self.phrases or {}).get(discours, [])

    def decider(self, discours: str, cle: str, action: str):
        """Accepte, refuse ou remet à vérifier une décision du linguiste."""
        if not LINGUISTE_DISPONIBLE:
            raise RuntimeError("Partie LLM indisponible : linguiste.py n'est pas publié.")
        from aad69.linguiste import changer_etat
        etats = {"accepter": "acceptee", "refuser": "refusee", "remettre": "a_verifier"}
        decision = changer_etat(self._lecture(discours)[0], cle, etats.get(action, action))
        self.invalider_calcul()
        return decision

    def choisir_decision(self, discours: str, cle: str, acceptee: bool) -> bool:
        """Accepte ou refuse une suggestion et renvoie son état après modification."""
        decision = self.decider(discours, cle, "accepter" if acceptee else "refuser")
        return decision.acceptee

    def tout_accepter(self, discours: str | None = None) -> int:
        """Accepte toutes les décisions en attente, pour un discours ou pour tous."""
        n = 0
        for nom, lecture in self.lectures.items():
            if discours in (None, nom):
                for i, d in enumerate(lecture.decisions):
                    if d.etat == "a_verifier":
                        lecture.decisions[i] = replace(d, etat="acceptee")
                        n += 1
        if n:
            self.invalider_calcul()
        return n

    def modifier_decision(self, discours: str, cle: str, **valeurs):
        """Corrige une décision du linguiste puis invalide les résultats en cache."""
        if not LINGUISTE_DISPONIBLE:
            raise RuntimeError("Partie LLM indisponible : linguiste.py n'est pas publié.")
        from aad69.linguiste import Invalide, modifier
        lecture, phrases = self._lecture(discours)
        if "antecedents" in valeurs and valeurs["antecedents"] is not None:
            # Convertit les choix reçus du formulaire en clés (identifiant de phrase, numéro du mot).
            antecedents = []
            for valeur in valeurs["antecedents"]:
                if isinstance(valeur, str):
                    try:
                        sent_id, mot = valeur.rsplit("|", 1)
                        antecedents.append((sent_id, int(mot)))
                    except ValueError as erreur:
                        raise Invalide("antécédent invalide") from erreur
                else:
                    antecedents.append(valeur)
            valeurs["antecedents"] = antecedents
        decision = modifier(lecture, phrases, cle, **valeurs)
        self.invalider_calcul()
        return decision

    def ajouter_decision(self, discours: str, sent_id: str, mot: int, antecedents):
        """Ajoute une décision d'anaphore manuelle à la lecture du discours."""
        if not LINGUISTE_DISPONIBLE:
            raise RuntimeError("Partie LLM indisponible : linguiste.py n'est pas publié.")
        from aad69.linguiste import ajouter
        lecture, phrases = self._lecture(discours)
        decision = ajouter(lecture, phrases, sent_id, mot, antecedents)
        self.invalider_calcul()
        return decision

    # --- corrections à la main (I6) ---------------------------------------------------------------
    def corriger(self, version: str, indice: int, valeurs: dict[str, str]):
        """Enregistre les cases modifiées par rapport à l'extraction automatique."""
        original = {e.indice: e for e in self.corpus_brut(version).enonces}[indice]
        # Les valeurs identiques à l'extraction sont retirées du journal des corrections.
        changees = {c: (v.strip() or "Ø") for c, v in valeurs.items()
                    if c in CASES and (v.strip() or "Ø") != getattr(original, c)}
        par_version = self.corrections.setdefault(version, {})
        if changees:
            par_version[indice] = changees
        else:
            par_version.pop(indice, None)
        self.invalider_calcul()

    def annuler_correction(self, version: str, indice: int):
        """Supprime les corrections manuelles d'un énoncé pour une version."""
        self.corrections.get(version, {}).pop(indice, None)
        self.invalider_calcul()

    def lignes_corrections(self) -> list[dict]:
        """Prépare une ligne d'export par case corrigée, avec valeur automatique et valeur retenue."""
        lignes = []
        for version, par_indice in self.corrections.items():
            # Recalcule les valeurs d'origine pour documenter ce qui a été changé.
            brut = {e.indice: e for e in self.corpus_brut(version).enonces}
            for indice, cases in sorted(par_indice.items()):
                for case, valeur in cases.items():
                    lignes.append({"version": version, "énoncé": indice, "case": case,
                                   "extraction automatique": getattr(brut[indice], case), "valeur retenue": valeur})
        return lignes

    def dire(self, genre: str, texte: str):
        """Enregistre un message à afficher une fois à l'utilisateur."""
        self.message = (genre, texte)

    def lire_message(self) -> tuple[str, str] | None:
        """Renvoie le message courant, puis le retire de l'état."""
        m, self.message = self.message, None
        return m
