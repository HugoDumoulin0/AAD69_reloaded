"""le module de réglages. il contient les réglages par défaut du livre.

`Reglages()` sans argument donne les RÉGLAGES DU LIVRE : ceux qui reproduisent les exemples
de Pêcheux (annexe III, manuel p. 51). 
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from .comparaison import Poids

VERSIONS = ("1969", "1972")


@dataclass(frozen=True)
class Reglage:
    """Métadonnées qui expliquent un réglage dans l'interface et le journal.

    `nom` identifie le réglage dans le code ; `libelle` est son nom affiché ;
    `decisions` renvoie aux décisions qui le justifient ; `explication` en
    décrit le sens et la valeur par défaut.
    """

    nom: str
    libelle: str
    decisions: str      # codes du journal, ex. "D1, C2"
    explication: str    # ce que dit Pêcheux / pourquoi cette valeur par défaut


CATALOGUE = {r.nom: r for r in [
    Reglage("poids", "Poids des cases (p)", "D2, D5",
            "Pondérations « provisoires » de la p. 92. Deux cases vides valent 1 (sauf F, N1, V) ; "
            "deux copules ε/ε valent 2 ; « * » compte comme un terme (poids de PP)."),
    Reglage("borne", "Borne pα", "D4",
            "Annexe III : 28, « la demi-somme des poids maximum de deux couples d'énoncés »."),
    Reglage("regle", "Somme ou moyenne", "D1, C2",
            "Le chap. II écrit la moyenne (P1+P2)/2 > pα, mais l'annexe III calcule la somme "
            "(13 + 20 = 33 > 28). Seule la somme reproduit le livre."),
    Reglage("intermediaires", "Alg. 2 (énoncés intermédiaires)", "D3",
            "Programmé, mais l'annexe III dit l'avoir « négligé » : désactivé par défaut."),
    Reglage("annulation", "Annulation de la différence répétée", "D6",
            "Remarque 1, p. 97 : une même opposition n'est pas comptée deux fois."),
    Reglage("exclure_phi_alpha", "Exclure φα (relation d'ordre)", "D8, R2",
            "φα marque un ordre, pas une dépendance : il ne forme ni zone ni dépendance."),
    Reglage("critere_homogeneite", "Homogénéité des chaînes (1969)", "C3",
            "« alg5 » : Alg. 4-5 du chapitre II ; « sequence_commune » : critère manuel de l'annexe III."),
    Reglage("resoudre_anaphores", "Rétablir les anaphores", "AN1",
            "Manuel § 3.12 : les pronoms sont remplacés par les termes qu'ils représentent avant la "
            "décomposition en énoncés (relatifs dans la phrase ; il, elle, le, la, lui… entre les phrases)."),
    Reglage("coordination_1969", "Termes coordonnés en 1969", "LG6, E2-15",
            "« séparée » (choix de l'équipe, 04/11) : un énoncé par terme, comme en 1972 (manuel § 3.1423), "
            "pour unifier les deux versions. « ensemble » : un symbole A1 et des énoncés d'appartenance "
            "ε3, comme l'annexe I. La différence est à discuter avec Hugo."),
    Reglage("hyperdomaines_1972", "Hyperdomaines en 1972", "H2",
            "Notion du livre, absente du manuel : calculée en 1972 comme extension."),
]}


def _poids_du_livre() -> Poids:
    """Crée les poids par défaut correspondant aux valeurs du livre."""
    return Poids()


@dataclass(frozen=True)
class Reglages:
    """Ensemble des choix qui pilotent l'analyse du corpus.

    Les valeurs par défaut reproduisent les réglages du livre, sauf les choix
    d'équipe décrits dans le docstring du module. Les valeurs sont vérifiées
    à la création de l'objet.
    """

    version: str = "1969"
    poids: Poids = field(default_factory=_poids_du_livre)
    borne: float = 28
    regle: str = "somme"
    intermediaires: bool = False
    annulation: bool = True
    exclure_phi_alpha: bool = True
    critere_homogeneite: str = "alg5"
    hyperdomaines_1972: bool = True
    resoudre_anaphores: bool = True
    coordination_1969: str = "separee"      # LG6 : « separee » ou « ensemble » (annexe I)

    def __post_init__(self):
        # Vérifie les choix qui doivent appartenir à une liste autorisée.
        if self.coordination_1969 not in ("separee", "ensemble"):
            raise ValueError("coordination_1969 doit valoir 'separee' ou 'ensemble'")
        if self.version not in VERSIONS:
            raise ValueError(f"version doit valoir {VERSIONS}")
        if self.regle not in ("somme", "moyenne"):
            raise ValueError("regle doit valoir 'somme' ou 'moyenne'")
        if self.critere_homogeneite not in ("alg5", "sequence_commune"):
            raise ValueError("critere_homogeneite doit valoir 'alg5' ou 'sequence_commune'")

    @property
    def operateurs_exclus(self) -> frozenset[str]:
        """Renvoie l'ensemble des opérateurs à ignorer pendant l'analyse."""
        # φα est exclu si l'option est active ; sinon aucun opérateur n'est écarté.
        return frozenset({"phi_alpha"}) if self.exclure_phi_alpha else frozenset()

    def ecarts(self) -> list[tuple[Reglage, object, object]]:
        """Liste les réglages dont la valeur diffère de celle du livre.

        Chaque ligne contient la description du réglage, sa valeur de référence
        et sa valeur actuelle. La version elle-même n'est pas un écart ; le choix
        de coordination n'est pas comparé au livre pour la version 1972.
        """
        # Construit la référence avec les paramètres du livre pour la version choisie.
        livre = Reglages(version=self.version, coordination_1969="ensemble")
        # Ne conserve que les champs différents de leur valeur de référence.
        return [(CATALOGUE[f.name], getattr(livre, f.name), getattr(self, f.name))
                for f in fields(self) if f.name != "version"
                and not (self.version == "1972" and f.name == "coordination_1969")
                and getattr(self, f.name) != getattr(livre, f.name)]
