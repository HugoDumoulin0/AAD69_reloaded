"""Dessin du graphe d'un discours en SVG (Python pur, sans Graphviz).

Comme les graphes du manuel (p. 40-41) : les énoncés sont des boîtes, les relations des flèches
étiquetées par leur opérateur. Disposition en couches de gauche à droite : un énoncé est placé
une colonne après le plus éloigné de ses prédécesseurs (plus long chemin depuis une source).
La relation d'ordre φα n'est pas une dépendance (décision R2) : elle ne compte pas pour la
disposition, et elle est dessinée en pointillés.
"""

from __future__ import annotations

from html import escape

from aad69.pipeline import Resultats

from .tables import operateur, resume

LARGEUR_CAR = 7.9   # largeur d'un caractère d'Anonymous Pro à 13 px
HAUTEUR = 30
ECART_X = 70
ECART_Y = 18
MARGE = 12


def _couches(noeuds: list[int], aretes: list[tuple[int, int]]) -> dict[int, int]:
    """Attribue une colonne à chaque nœud selon sa distance aux sources.

    La couche vaut la longueur du plus long chemin qui mène au nœud dans un
    graphe sans cycle. Un cycle inattendu est coupé pour arrêter le parcours.
    """
    # Pour chaque nœud, mémorise les nœuds qui le précèdent directement.
    entrants = {n: [] for n in noeuds}
    for a, b in aretes:
        entrants[b].append(a)
    couche: dict[int, int] = {}

    def calcul(n, pile=()):
        """Calcule récursivement la couche du nœud à partir de ses prédécesseurs."""
        # Réutilise la couche déjà calculée pour éviter de reparcourir le graphe.
        if n in couche:
            return couche[n]
        if n in pile:  # cycle (ne devrait pas arriver) : on coupe
            return 0
        couche[n] = 1 + max((calcul(p, pile + (n,)) for p in entrants[n]), default=-1)
        return couche[n]

    for n in noeuds:
        calcul(n)
    return couche


def graphe_svg(res: Resultats, discours: str) -> str:
    """Dessine les énoncés et relations d'un discours dans un fragment SVG."""
    v = res.reglages.version
    enonces = [e for e in res.corpus.enonces if e.discours == discours]
    if not enonces:
        return ""
    # Ne garde que les relations dont les deux énoncés appartiennent au discours.
    ids = {e.indice for e in enonces}
    rels = [r for r in res.corpus.relations if r.gauche in ids and r.droit in ids]
    couches = _couches([e.indice for e in enonces],
                       [(r.gauche, r.droit) for r in rels if r.operateur != "phi_alpha"])

    # Calcule les dimensions nécessaires à l'affichage des boîtes.
    textes = {e.indice: f"{e.indice}  {resume(e)}" for e in enonces}
    largeur = {i: len(t) * LARGEUR_CAR + 20 for i, t in textes.items()}
    colonnes: dict[int, list[int]] = {}
    for e in enonces:
        colonnes.setdefault(couches[e.indice], []).append(e.indice)
    x_col, x = {}, MARGE
    for c in sorted(colonnes):
        x_col[c] = x
        x += max(largeur[i] for i in colonnes[c]) + ECART_X
    # Place les nœuds de chaque couche dans une colonne, avec un espacement régulier.
    pos = {i: (x_col[c], MARGE + k * (HAUTEUR + ECART_Y)) for c, membres in colonnes.items()
           for k, i in enumerate(membres)}
    W = x - ECART_X + MARGE + 60  # place pour les arcs de droite
    H = MARGE * 2 + max(len(m) for m in colonnes.values()) * (HAUTEUR + ECART_Y) - ECART_Y

    l = [f'<svg class="graphe" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" role="img" '
         f'aria-label="Graphe du discours {escape(discours)}">',
         '<defs><marker id="pointe-' + v + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
         'markerHeight="7" orient="auto"><path d="M0 1L9 5L0 9" fill="none" stroke="currentColor" '
         'stroke-width="1.5"/></marker></defs>']
    # Dessine d'abord les flèches ; les relations d'ordre sont affichées en pointillés.
    for r in rels:
        (x1, y1), (x2, y2) = pos[r.gauche], pos[r.droit]
        x1 += largeur[r.gauche]
        y1 += HAUTEUR / 2
        y2 += HAUTEUR / 2
        classe = "arete ordre" if r.operateur == "phi_alpha" else "arete"
        if x2 <= x1:  # même colonne ou retour : arc sur la droite des boîtes
            x2 += largeur[r.droit]
            bord = max(x1, x2) + 28
            l.append(f'<path class="{classe}" d="M{x1:.0f} {y1:.0f} C{bord:.0f} {y1:.0f} {bord:.0f} {y2:.0f} {x2 + 2:.0f} {y2:.0f}" '
                     f'marker-end="url(#pointe-{v})"/>')
            l.append(f'<text class="op" x="{bord + 4:.0f}" y="{(y1 + y2) / 2 + 4:.0f}" text-anchor="start">'
                     f'{escape(operateur(r.operateur, v))}</text>')
            continue
        mx = (x1 + x2) / 2
        l.append(f'<path class="{classe}" d="M{x1:.0f} {y1:.0f} C{mx:.0f} {y1:.0f} {mx:.0f} {y2:.0f} {x2 - 2:.0f} {y2:.0f}" '
                 f'marker-end="url(#pointe-{v})"/>')
        # étiquette près de la pointe (t = 0,8 sur la courbe) : plusieurs flèches qui partent du même
        # énoncé ont ainsi des étiquettes séparées, chacune à hauteur de son énoncé d'arrivée.
        t = 0.8  # courbe de Bézier : points de contrôle (mx, y1) et (mx, y2)
        lx = (1 - t) ** 3 * x1 + 3 * (1 - t) * t * mx + t ** 3 * x2
        ly = y1 + (y2 - y1) * (3 * t * t - 2 * t ** 3)
        l.append(f'<text class="op" x="{lx - 14:.0f}" y="{ly - 5:.0f}">{escape(operateur(r.operateur, v))}</text>')
    # Ajoute les boîtes et leurs libellés au-dessus des flèches.
    for i, (x, y) in pos.items():
        l.append(f'<g class="noeud"><rect x="{x:.0f}" y="{y:.0f}" width="{largeur[i]:.0f}" height="{HAUTEUR}" rx="2"/>'
                 f'<text x="{x + 10:.0f}" y="{y + 19:.0f}">{escape(textes[i])}</text></g>')
    l.append("</svg>")
    return "\n".join(l)


def dendrogramme_svg(res: Resultats, reg) -> str:
    """Dessine le dendrogramme et la ligne qui marque la borne de coupe.

    Renvoie une chaîne vide s'il n'y a pas de fusion à afficher ou si l'échelle
    de distance ne permet pas de construire le graphique.
    """
    from aad69.regroupements import seuil_de_la_borne

    dendrogramme = reg.dendrogramme
    if not dendrogramme.fusions or dendrogramme.s_max <= 0:
        return ""

    version = res.reglages.version
    par_indice = {e.indice: e for e in res.corpus.enonces}
    n = len(dendrogramme.feuilles)
    enfants = {f.nouveau: (f.a, f.b) for f in dendrogramme.fusions}
    # Les racines sont les groupes fusionnés qui ne sont eux-mêmes enfants d'aucune fusion.
    racines = set(enfants) - {x for paire in enfants.values() for x in paire}
    ordre: list[int] = []

    def parcours(i: int) -> None:
        # Parcourt l'arbre de gauche à droite pour fixer l'ordre vertical des feuilles.
        if i < n:
            ordre.append(i)
        else:
            for enfant in enfants[i]:
                parcours(enfant)

    for racine in sorted(racines):
        parcours(racine)

    # Associe chaque relation à son groupe après la coupe choisie.
    groupes = dendrogramme.groupes(seuil_de_la_borne(reg.borne, dendrogramme.s_max))
    numero_groupe = {
        relation: i for i, groupe in enumerate(groupes, 1) for relation in groupe
    }
    groupe_feuille = {
        i: numero_groupe.get(relation)
        for i, relation in enumerate(dendrogramme.feuilles)
    }

    def feuilles_sous(noeud: int) -> list[int]:
        # Retrouve toutes les feuilles contenues dans un groupe fusionné.
        if noeud < n:
            return [noeud]
        a, b = enfants[noeud]
        return feuilles_sous(a) + feuilles_sous(b)

    # Prépare les libellés, l'espacement des feuilles et l'échelle horizontale.
    pas, largeur_arbre = 24, 360
    etiquettes = {
        i: f"E{dendrogramme.feuilles[i].gauche} {operateur(dendrogramme.feuilles[i].operateur, version)} "
           f"E{dendrogramme.feuilles[i].droit}"
        for i in ordre
    }
    largeur_texte = max((len(t) for t in etiquettes.values()), default=0) * LARGEUR_CAR * 0.75 + 16
    seuil = seuil_de_la_borne(reg.borne, dendrogramme.s_max)
    d_max = min(
        dendrogramme.s_max,
        max(max(f.distance for f in dendrogramme.fusions), seuil) + 4,
    )
    if d_max <= 0:
        return ""

    x_feuilles = MARGE + largeur_texte
    largeur, hauteur = x_feuilles + largeur_arbre + 12, MARGE * 2 + len(ordre) * pas + 26

    def x_de(distance: float) -> float:
        # Convertit une distance en position horizontale dans le graphique.
        return x_feuilles + distance / d_max * largeur_arbre

    y = {i: MARGE + k * pas + pas / 2 for k, i in enumerate(ordre)}
    x = {i: x_feuilles for i in ordre}
    lignes = [
        f'<svg class="dendrogramme" viewBox="0 0 {largeur:.0f} {hauteur:.0f}" '
        f'width="{largeur:.0f}" height="{hauteur:.0f}" role="img" '
        f'aria-label="Arbre des rapprochements, lien {escape(reg.lien)}, coupe à la borne {reg.borne:g}">'
    ]
    # Dessine chaque fusion en reliant les positions de ses deux groupes enfants.
    for fusion in dendrogramme.fusions:
        xa, xb, xf = x[fusion.a], x[fusion.b], x_de(fusion.distance)
        y[fusion.nouveau] = (y[fusion.a] + y[fusion.b]) / 2
        x[fusion.nouveau] = xf
        descendance = feuilles_sous(fusion.nouveau)
        identifiants_groupes = {groupe_feuille[i] for i in descendance}
        meme_groupe = len(identifiants_groupes) == 1 and None not in identifiants_groupes
        identifiant = next(iter(identifiants_groupes)) if meme_groupe else None
        couleur = (identifiant - 1) % 8 + 1 if identifiant else None
        classe = f"branche groupe-{couleur}" if couleur else "branche hors-groupe"
        lignes.append(
            f'<path class="{classe}" d="M{xa:.1f} {y[fusion.a]:.1f}H{xf:.1f}'
            f'V{y[fusion.b]:.1f}H{xb:.1f}"/>'
        )
    # Écrit les étiquettes des relations de départ à gauche de l'arbre.
    for i in ordre:
        relation = dendrogramme.feuilles[i]
        texte_complet = (
            f"{resume(par_indice[relation.gauche])} → {resume(par_indice[relation.droit])}"
        )
        identifiant = groupe_feuille[i]
        couleur = (identifiant - 1) % 8 + 1 if identifiant else None
        classe = f"feuille groupe-{couleur}" if couleur else "feuille hors-groupe"
        lignes.append(
            f'<text class="{classe}" x="{x_feuilles - 8:.0f}" y="{y[i] + 4:.0f}" text-anchor="end">'
            f'<title>{escape(texte_complet)}</title>{escape(etiquettes[i])}</text>'
        )
    # Trace la limite de coupe et gradue l'axe des distances.
    x_coupe = x_de(seuil)
    bas = MARGE + len(ordre) * pas
    lignes.append(
        f'<line class="coupe" x1="{x_coupe:.1f}" y1="{MARGE - 4}" '
        f'x2="{x_coupe:.1f}" y2="{bas:.0f}"/>'
    )
    lignes.append(
        f'<text class="coupe" x="{x_coupe:.1f}" y="{bas + 16:.0f}" '
        f'text-anchor="middle">limite {reg.borne:g}</text>'
    )
    pas_axe = 7 if d_max > 28 else 4
    for distance in range(0, int(d_max) + 1, pas_axe):
        if abs(x_de(distance) - x_coupe) > 30:
            lignes.append(
                f'<text class="axe" x="{x_de(distance):.1f}" y="{bas + 16:.0f}" '
                f'text-anchor="middle">{distance}</text>'
            )
    lignes.append("</svg>")
    return "\n".join(lignes)
