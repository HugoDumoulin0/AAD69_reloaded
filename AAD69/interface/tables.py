"""Mise en tableaux des résultats (Python pur, sans Flask).

Utilisé par les onglets (affichage) ET par l'export (CSV) : ce qu'on voit à l'écran est
exactement ce qu'on télécharge. Chaque fonction renvoie une liste de dictionnaires
(une ligne = un dictionnaire) ; les pages HTML les affichent, l'export les écrit en CSV.
"""

from __future__ import annotations

from collections import Counter

from aad69.modele import CASES, OPERATEURS_1969, VIDE, Enonce
from aad69.pipeline import Resultats

# Annexe 2 du manuel (p. 54) : libellés des codes de connecteurs les plus fréquents.
LIBELLES_1972 = {
    "01": "δ1", "02": "δ2", "05": "IMP", "06": "PRG1", "07": "PRG2", "08": "SPE", "09": "CIRC",
    "11": "que", "12": "comme", "13": "si", "22": "quand", "40": "et", "47": "mais", "49": "ou",
    "60": "point", "63": "c.-à-d.", "71": "car", "72": "puisque", "73": "pour que", "74": "au point que",
    "80": "si", "85": "bien que", "99": "énoncé vide",
}

# Symboles courts pour la matrice des relations entre domaines (ligne x, colonne y).
SYMBOLES_MATRICE = {
    "ORIGINES_COMMUNES": ("⊕", "⊕"), "INCLUT": ("⊃", "⊂"), "INTERSECTION": ("∩", "∩"),
    "DEP1": ("⇒1", "⇐1"), "DEP2": ("⇒2", "⇐2"), "DEP3": ("→3", "←3"), "DEP4": ("→4", "←4"),
    "RECIPROQUE": ("—", "—"), "DISJOINTS": ("∥", "∥"),
    "IDORG": ("=", "="), "INCLU": ("⊂", "⊃"), "INTER": ("∩", "∩"),
    "DEPENDANCE_POSSIBLE": ("→?", "←?"), "DEPENDANCE_POSSIBLE_RECIPROQUE": ("↔?", "↔?"), "AUCUNE": ("", ""),
}

LEGENDE_MATRICE = {
    "1969": "⊕ origines communes · ⊃/⊂ inclusion · ∩ intersection · ⇒1 ⇒2 →3 →4 dépendance (degrés 1 à 4, "
            "la flèche part du domaine qui commande) · — réciproque · ∥ disjoints",
    "1972": "= IDORG · ⊂/⊃ INCLU (« x ⊂ y » : x INCLU y) · ∩ INTER · →? dépendance possible · "
            "↔? dépendance possible dans les deux sens · vide : aucune relation",
}


def operateur(code: str, version: str) -> str:
    """Convertit un code d'opérateur en libellé destiné à l'affichage.

    En 1969, renvoie le symbole (par exemple `δ2`) ; en 1972, ajoute le code
    numérique devant le libellé connu (par exemple `02 δ2`).
    """
    if version == "1969" or code in OPERATEURS_1969:
        return OPERATEURS_1969.get(code, code)
    return f"{code} {LIBELLES_1972[code]}" if code in LIBELLES_1972 else code


def resume(e: Enonce) -> str:
    """Produit un résumé lisible d'un énoncé avec ses cases nominales remplies."""
    return " ".join(x for x in (e.N1, e.V, e.PP, e.D2, e.N2_3) if x != VIDE) or "(vide)"


def _par_indice(res: Resultats) -> dict[int, Enonce]:
    """Prépare l'accès aux énoncés à partir de leur numéro."""
    return {e.indice: e for e in res.corpus.enonces}


def table_enonces(res: Resultats) -> list[dict]:
    """Prépare une ligne de tableau par énoncé, avec ses cases et son discours."""
    return [{"n°": e.indice, "discours": e.discours, **dict(zip(CASES, e.cases())), "source": e.source}
            for e in res.corpus.enonces]


def table_anaphores(res: Resultats) -> list[dict]:
    """Prépare une ligne par pronom résolu ou examiné (I7).

    Chaque ligne indique le discours et la phrase, le pronom, son antécédent,
    la règle appliquée, le statut et les candidats. Le résultat est vide si
    les anaphores n'ont pas été résolues ou si le corpus vient de tables.
    """
    lignes = []
    for discours, table in res.corpus.anaphores.items():
        for (phrase, mot), r in table.items():
            lignes.append({"discours": discours, "phrase": phrase, "mot": mot, "pronom": r.forme,
                           "antécédent": r.lemme if r.resolue else "",
                           "phrase de l'antécédent": r.antecedent[0] if r.antecedent else "",
                           "règle": r.regle, "statut": r.statut, "candidats": " | ".join(r.candidats)})
    return lignes


def table_relations(res: Resultats) -> list[dict]:
    """Prépare une ligne d'affichage pour chaque relation du corpus."""
    p = _par_indice(res)
    v = res.reglages.version
    lignes = []
    for r in res.corpus.relations:
        destination = p[r.droit]
        # Signale à vérifier les relations « à » dont la destination peut être un lieu ou un destinataire.
        a_verifier = (
            "Lieu ou destinataire ?"
            if r.operateur in {"alpha", "08"} and destination.PP == "à"
            else ""
        )
        lignes.append({
            "gauche": r.gauche,
            "opérateur": operateur(r.operateur, v),
            "droit": r.droit,
            "discours": p[r.gauche].discours,
            "énoncé gauche": resume(p[r.gauche]),
            "énoncé droit": resume(destination),
            "saturation": "oui" if r.saturation else "",
            "variante": r.variante or "",
            "à vérifier": a_verifier,
        })
    return lignes


def table_zones(res: Resultats) -> list[dict]:
    """Prépare une ligne par zone, avec les couples comparés et leurs scores."""
    v = res.reglages.version
    return [{"gauches (Ei/Ej)": f"{z.gauche[0]}/{z.gauche[1]}", "opérateur": operateur(z.operateur, v),
             "droites (Ek/Em)": f"{z.droite[0]}/{z.droite[1]}", "P1": z.P1, "P2": z.P2, "score": z.score}
            for z in res.zones]


def table_chaines(res: Resultats) -> list[dict]:
    """Prépare une ligne par chaîne de similitude (version 1969)."""
    v = res.reglages.version
    return [{"groupe opérateur": "(" + ", ".join(operateur(o, v) for o in c.operateurs) + ")",
             "couples": " ".join(f"({a}/{b})" for a, b in c.couples),
             "séquences": "  |  ".join("-".join(map(str, s)) for s in c.sequences())}
            for c in res.chaines]


def table_domaines(res: Resultats) -> list[dict]:
    """Prépare les lignes détaillées des domaines.

    En 1969, chaque ligne présente un énoncé et sa position dans le domaine ;
    en 1972, chaque ligne présente une relation.
    """
    p = _par_indice(res)
    v = res.reglages.version
    lignes = []
    for nom, d in res.domaines.items():
        if v == "1969":
            groupe = "(" + ", ".join(operateur(o, v) for o in d.groupe) + ")"
            for k, position in enumerate(d.positions, 1):
                for i in sorted(position):
                    lignes.append({"domaine": nom, "groupe": groupe, "position": k, "énoncé": i,
                                   "discours": p[i].discours, **dict(zip(CASES, p[i].cases()))})
        else:
            for r in d.relations:
                lignes.append({"domaine": nom, "connecteur": operateur(d.connecteur, v),
                               "gauche": r.gauche, "énoncé gauche": resume(p[r.gauche]),
                               "droit": r.droit, "énoncé droit": resume(p[r.droit]),
                               "discours": p[r.gauche].discours})
    return lignes


def synthese_domaines(res: Resultats) -> list[dict]:
    """Résume chaque domaine sur une ligne, à la manière de l'annexe III (p. 125).

    En 1969, les résumés d'énoncés sont regroupés par position dans les chaînes.
    En 1972, les énoncés à gauche et à droite des relations sont présentés séparément.
    """
    p = _par_indice(res)
    v = res.reglages.version
    lignes = []
    for nom, d in res.domaines.items():
        if v == "1969":
            colonnes = [" | ".join(sorted({resume(p[i]) for i in pos})) for pos in d.positions]
            lignes.append({"domaine": nom, "groupe": "(" + ", ".join(operateur(o, v) for o in d.groupe) + ")",
                           "chaînes": len(d.chaines), "énoncés": len(d.enonces()),
                           "synthèse": "  ⟶  ".join(f"[{c}]" for c in colonnes)})
        else:
            gauches = " | ".join(sorted({resume(p[i]) for i in d.gauches}))
            droites = " | ".join(sorted({resume(p[i]) for i in d.droites}))
            lignes.append({"domaine": nom, "connecteur": operateur(d.connecteur, v),
                           "relations": len(d.relations),
                           "synthèse": f"[{gauches}]  ⟶  [{droites}]"})
    return lignes


def table_relations_domaines(res: Resultats) -> list[dict]:
    """Prépare une ligne par relation entre deux domaines, avec son symbole."""
    return [{"domaine x": r.x, "relation": r.type, "symbole": SYMBOLES_MATRICE[r.type][0], "domaine y": r.y}
            for r in res.relations_domaines]


def matrice_relations_domaines(res: Resultats) -> list[dict]:
    """Construit la matrice des relations entre domaines (tableau p. 127)."""
    noms = list(res.domaines)
    cases = {(a, b): "" for a in noms for b in noms}
    for r in res.relations_domaines:
        direct, inverse = SYMBOLES_MATRICE[r.type]
        cases[(r.x, r.y)], cases[(r.y, r.x)] = direct, inverse
    return [{"": a, **{b: ("·" if a == b else cases[(a, b)]) for b in noms}} for a in noms]


def table_hyperdomaines(res: Resultats, noms: dict[int, str] | None = None) -> list[dict]:
    """Prépare une ligne par hyperdomaine, avec les domaines et le nom donné par l'analyste."""
    noms = noms or {}
    return [{"hyperdomaine": f"H{h.numero}", "domaines": ", ".join(h.domaines),
             "origine commune à tous": ("— (domaine seul)" if len(h.domaines) == 1 else
                                        ", ".join(map(str, sorted(h.origine_commune))) or "AUCUNE"),
             "nom (analyste)": noms.get(h.numero, "")} for h in res.hyperdomaines]


def paradigmes(res: Resultats) -> list[dict]:
    """Présente chaque domaine sous forme de colonnes, comme chez Pêcheux.

    Les positions sont séparées par les opérateurs. Dans chaque colonne, les
    résumés d'énoncés identiques sont regroupés avec leur nombre (« J aller ×3 »).
    Cette présentation suit l'annexe III (p. 125) et le manuel (p. 52).

    Renvoie, par domaine : nom, titre, colonnes = [[(texte, nombre), …], …], operateurs = [ψ1, ψ2…].
    """
    p = _par_indice(res)
    v = res.reglages.version

    def colonne(indices) -> list[tuple[str, int]]:
        # Compte les résumés identiques, puis place les plus fréquents en premier.
        compte = Counter(resume(p[i]) for i in indices)
        return sorted(compte.items(), key=lambda t: (-t[1], t[0]))

    sortie = []
    for nom, d in res.domaines.items():
        if v == "1969":
            ops = [operateur(o, v) for o in d.groupe]
            titre = f"({', '.join(ops)}), {len(d.chaines)} chaînes, {len(d.enonces())} énoncés"
            colonnes = [colonne(pos) for pos in d.positions]
        else:
            ops = [operateur(d.connecteur, v)]
            titre = f"connecteur {ops[0]}, {len(d.relations)} relations"
            colonnes = [colonne(d.gauches), colonne(d.droites)]
        sortie.append({"nom": nom, "titre": titre, "colonnes": colonnes, "operateurs": ops})
    return sortie


def paradigmes_groupes(res: Resultats, reg) -> list[dict]:
    """Présente chaque groupe de classification hiérarchique en deux colonnes."""
    p = _par_indice(res)
    version = res.reglages.version

    def colonne(indices) -> list[tuple[str, int]]:
        # Regroupe les mêmes résumés d'énoncé et compte leurs occurrences.
        compte = Counter(resume(p[i]) for i in indices)
        return sorted(compte.items(), key=lambda t: (-t[1], t[0]))

    return [
        {
            "nom": nom,
            "titre": f"{len(domaine.relations)} relations",
            "operateurs": [operateur(domaine.connecteur, version)],
            "colonnes": [colonne(domaine.gauches), colonne(domaine.droites)],
            "classe": f"groupe-cah-{(int(nom[1:]) - 1) % 8 + 1}",
        }
        for nom, domaine in reg.domaines.items()
    ]


def table_regroupements(res: Resultats) -> list[dict]:
    """Recalcule et prépare les groupes CAH pour les trois types de lien.

    Chaque ligne indique le lien utilisé, la borne, le groupe et les deux
    relations qui le composent. Les réglages sont repris de l'analyse affichée.
    """
    from aad69.regroupements import LIENS, regrouper

    reglages = res.reglages
    par_indice = _par_indice(res)
    lignes = []
    # Produit les groupes séparément pour le lien simple, moyen et complet.
    for lien in LIENS:
        resultat = regrouper(
            res.corpus.enonces,
            res.corpus.relations,
            lien,
            reglages.borne,
            reglages.poids,
            reglages.intermediaires,
            reglages.annulation,
            reglages.operateurs_exclus,
            regle=reglages.regle,
        )
        # Une ligne de sortie est créée pour chaque relation de chaque groupe.
        for nom, domaine in resultat.domaines.items():
            for relation in domaine.relations:
                lignes.append(
                    {
                        "lien": lien,
                        "borne": reglages.borne,
                        "groupe": nom,
                        "connecteur": operateur(relation.operateur, reglages.version),
                        "énoncé gauche": f"{relation.gauche} {resume(par_indice[relation.gauche])}",
                        "énoncé droit": f"{relation.droit} {resume(par_indice[relation.droit])}",
                    }
                )
    return lignes
