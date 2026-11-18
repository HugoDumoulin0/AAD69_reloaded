"""Interface AAD69 (Flask). Elle AFFICHE les résultats de aad69.pipeline ; elle ne calcule rien.

Lancement, depuis le dossier du projet :
    python AAD69/interface/app.py

Organisation :
- etat.py        corpus chargé, réglages, calcul (appelle aad69.pipeline) ;
- tables.py      mise en tableaux (partagée avec l'export) ; graphe_svg.py : graphes des discours ;
- export.py      zip de l'analyse ;
- templates/     une page par étape (base.html = bandeau, procédure, panneau des réglages) ;
- static/        style.css, app.js, polices embarquées.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent
MODULES = CODE_ROOT / "modules"
for chemin in (CODE_ROOT, MODULES):
    if str(chemin) not in sys.path:
        sys.path.insert(0, str(chemin))

from flask import Flask, Response, abort, redirect, render_template, request, url_for  # noqa: E402

from aad69.analyse import analyser_texte, stanza_disponible  # noqa: E402
from aad69.comparaison import proximite, vecteur_pi  # noqa: E402
from aad69.conllu import lire_conllu_texte  # noqa: E402
from aad69.extraction_grew import GrewAbsent  # noqa: E402
from aad69.modele import CASES  # noqa: E402
from aad69.reference import charger_enonces_texte, charger_relations_texte  # noqa: E402
from aad69.reglages import CATALOGUE, Reglages  # noqa: E402
from aad69.pipeline import LINGUISTE_DISPONIBLE, executer  # noqa: E402
from interface import tables  # noqa: E402
from interface.etat import EXEMPLES, Etat  # noqa: E402
from interface.export import zip_resultats  # noqa: E402
from interface.graphe_svg import dendrogramme_svg, graphe_svg  # noqa: E402
from interface.propositions import construire_propositions  # noqa: E402
from aad69.regroupements import LIENS, borne_valide, regrouper, score_maximum  # noqa: E402
from dataclasses import replace as _remplacer  # noqa: E402

# Les étapes de la procédure, dans l'ordre (c'est une vraie séquence : elles sont numérotées).
ETAPES = [
    ("corpus", "Corpus"), ("linguiste", "Linguiste"), ("propositions", "Propositions"),
    ("enonces", "Énoncés"), ("relations", "Relations"), ("comparaison", "Comparaison"),
    ("domaines", "Domaines"), ("regroupements", "Regroupements"),
    ("entre-domaines", "Entre domaines"), ("hyperdomaines", "Hyperdomaines"),
    ("journal", "Journal"),
]
CASES_CHECKBOX = ("intermediaires", "annulation", "exclure_phi_alpha", "hyperdomaines_1972", "resoudre_anaphores")


def _nom_propre(nom: str) -> str:
    """Nettoie un nom de fichier pour en faire un identifiant de discours."""
    return re.sub(r"[^\w-]+", "-", nom.strip()).strip("-") or "discours"


def _nombre(x, decimales: int = 2) -> str:
    """Formate les nombres selon les usages français, avec une virgule décimale."""
    if isinstance(x, float) and not x.is_integer():
        return f"{x:.{decimales}f}".replace(".", ",")
    return str(int(x)) if isinstance(x, float) else str(x)


def _compteurs(resultats) -> dict[str, str]:
    """Prépare les nombres affichés à côté des étapes du parcours.

    Si les versions 1969 et 1972 donnent des nombres différents, les deux
    valeurs sont affichées séparées par une barre verticale.
    """
    def val(f):
        """Applique une mesure à chaque version et assemble les valeurs obtenues."""
        valeurs = [str(f(r)) for r in resultats.values()]
        return valeurs[0] if len(set(valeurs)) == 1 else " | ".join(valeurs)
    return {
        "enonces": val(lambda r: len(r.corpus.enonces)), "relations": val(lambda r: len(r.corpus.relations)),
        "comparaison": val(lambda r: len(r.zones)), "domaines": val(lambda r: len(r.domaines)),
        "hyperdomaines": val(lambda r: len(r.hyperdomaines)),
    }


def _statuts_etapes(e: Etat, resultats) -> dict[str, str]:
    """Détermine si chaque étape est prête, vide, en attente ou indisponible."""
    if not e.a_un_corpus:
        return {cle: "non calculé" for cle, _ in ETAPES}

    statuts = {"corpus": "prêt", "journal": "prêt",
               "propositions": "prêt" if e.phrases else "non disponible",
               "linguiste": ("non disponible" if not LINGUISTE_DISPONIBLE else
                             "prêt" if e.lectures else "erreur" if e.linguiste_tente else "à lancer")}
    # Associe chaque étape calculée à la mesure qui permet de déterminer son statut.
    mesures = {
        "enonces": lambda r: len(r.corpus.enonces),
        "relations": lambda r: len(r.corpus.relations),
        "comparaison": lambda r: len(r.zones),
        "domaines": lambda r: len(r.domaines),
        "regroupements": lambda r: len(r.corpus.relations),
        "entre-domaines": lambda r: len(r.domaines),
        "hyperdomaines": lambda r: len(r.hyperdomaines),
    }
    if not resultats:
        statuts.update({etape: "à venir" for etape in mesures})
        return statuts
    for etape, mesurer in mesures.items():
        statuts[etape] = "prêt" if any(mesurer(r) for r in resultats.values()) else "vide"
    return statuts


def _resume_corpus(e: Etat) -> dict[str, int | str]:
    """Prépare les informations de résumé du corpus pour les gabarits HTML."""
    discours = e.discours()
    return {
        "discours": len(discours),
        "phrases_ou_enonces": sum(n for _, n, _ in discours),
        "source": e.source or "Aucun corpus",
        "conllu": bool(e.conllu),
    }


def creer_app(mode_developpement: bool = False) -> Flask:
    """Crée l'application Flask et enregistre ses pages et actions.

    L'objet `Etat` est propre à cette instance. Le mode développement ajoute
    l'accès aux corpus d'exemple.
    """
    app = Flask(__name__)
    app.extensions["aad69"] = Etat()
    app.config["AAD69_MODE_DEVELOPPEMENT"] = mode_developpement
    app.jinja_env.filters["nombre"] = _nombre

    @app.errorhandler(GrewAbsent)
    def grew_indisponible(erreur):
        """Affiche la page d'aide lorsque le moteur Grew n'est pas installé."""
        return render_template("grew_absent.html", erreur=str(erreur)), 503

    def etat() -> Etat:
        """Renvoie l'état associé à l'application courante."""
        return app.extensions["aad69"]

    def page(gabarit: str, etape: str, **contexte):
        """Prépare les données communes puis affiche le gabarit d'une étape."""
        e = etat()
        # Calcule les résultats uniquement pour les pages qui les affichent.
        resultats = e.calculer() if e.a_un_corpus and etape != "corpus" else {}
        r0 = e.reglages_pour(e.versions[0]) if e.a_un_corpus else Reglages()
        compteurs = _compteurs(resultats) if resultats else {}
        # Les étapes du linguiste et des propositions n'ont de sens qu'avec des phrases.
        parcours = [
            item for item in ETAPES
            if (e.phrases or item[0] not in {"linguiste", "propositions"})
            and (LINGUISTE_DISPONIBLE or item[0] != "linguiste")
        ]
        position = next((i for i, (cle, _) in enumerate(parcours) if cle == etape), -1)
        precedente = parcours[position - 1] if position > 0 else None
        suivante = parcours[position + 1] if 0 <= position < len(parcours) - 1 else None
        if e.a_un_corpus:
            compteurs["corpus"] = str(len(e.discours()))
        compteurs.update(contexte.pop("compteurs_extra", {}))
        return render_template(
            gabarit, etape=etape, etapes=parcours, etat=e, resultats=resultats, compteurs=compteurs,
            etape_precedente=precedente, etape_suivante=suivante,
            statuts=_statuts_etapes(e, resultats),
            ecarts=r0.ecarts(), r=r0, livre=Reglages(coordination_1969="ensemble"),
            catalogue=CATALOGUE, cases=CASES,
            message=e.lire_message(), exemples=EXEMPLES if mode_developpement else {},
            mode_developpement=mode_developpement, tables=tables, resume=_resume_corpus(e), **contexte)

    def exige_corpus(vue):
        """Protège une route : si aucun corpus n'est chargé, renvoie vers son chargement."""
        def enveloppe(*a, **k):
            """Vérifie la présence du corpus avant d'appeler la route protégée."""
            if not etat().a_un_corpus:
                etat().dire("info", "Chargez d'abord un corpus.")
                return redirect(url_for("corpus"))
            return vue(*a, **k)
        enveloppe.__name__ = vue.__name__
        return enveloppe

    def retour():
        """Renvoie l'utilisateur vers la page demandée, ou vers le corpus par défaut."""
        return redirect(request.form.get("retour") or request.referrer or url_for("corpus"))

    @app.post("/corpus/reset")
    def corpus_reinitialiser():
        """Vide les données de la session et revient à l'écran de chargement."""
        e = etat()
        e.invalider_calcul()
        e.phrases, e.tables, e.conllu, e.textes_bruts, e.source = None, None, {}, {}, ""
        e.noms_hyper, e.corrections, e.lectures = {}, {}, {}
        e.dire("info", "Corpus réinitialisé. Vous pouvez en charger un nouveau.")
        return redirect(url_for("corpus"))

    # --- 1. Corpus -----------------------------------------------------------------------------
    @app.get("/")
    def accueil():
        """Redirige la page d'accueil vers l'étape de chargement du corpus."""
        return redirect(url_for("corpus"))

    @app.get("/corpus")
    def corpus():
        """Affiche le formulaire de chargement adapté au format choisi."""
        mode_defaut = "textes" if LINGUISTE_DISPONIBLE else "tables"
        mode = request.args.get("mode", mode_defaut)
        modes = {"textes", "conllu", "tables"} if LINGUISTE_DISPONIBLE else {"tables"}
        if app.config["AAD69_MODE_DEVELOPPEMENT"]:
            modes.add("exemples")
        if mode not in modes:
            return abort(404)
        try:
            nb_textes = int(request.args.get("n", 2))
        except ValueError:
            nb_textes = 2
        return page("corpus.html", "corpus", mode=mode, modifier=request.args.get("modifier") == "1",
                    stanza=stanza_disponible(),
                    nb_textes=max(2, min(20, nb_textes)))

    @app.post("/corpus/exemple")
    def corpus_exemple():
        """Charge un corpus intégré, uniquement en mode développement."""
        if not app.config["AAD69_MODE_DEVELOPPEMENT"]:
            return abort(404)
        cle = request.form["exemple"]
        if cle not in EXEMPLES:
            return abort(404)
        etat().charger_exemple(cle)
        etat().dire("ok", f"Corpus chargé : {EXEMPLES[cle][0]}.")
        return redirect(url_for("corpus"))

    @app.post("/corpus/conllu")
    def corpus_conllu():
        """Lit les fichiers CoNLL-U déposés et charge leurs phrases dans l'état."""
        if not LINGUISTE_DISPONIBLE:
            etat().dire("info", "Le chargement CoNLL-U est désactivé dans cette version ; utilisez les tables CSV.")
            return redirect(url_for("corpus", mode="tables"))
        fichiers = [f for f in request.files.getlist("fichiers") if f.filename]
        if not fichiers:
            etat().dire("erreur", "Aucun fichier choisi.")
            return redirect(url_for("corpus", mode="conllu"))
        discours, textes = {}, {}
        for f in fichiers:
            nom = _nom_propre(Path(f.filename).stem)
            if nom in discours:
                etat().dire("erreur", f"Deux fichiers donnent le même nom de discours : {nom}.")
                return redirect(url_for("corpus", mode="conllu"))
            textes[nom] = f.read().decode("utf-8")
            discours[nom] = lire_conllu_texte(textes[nom])
        etat().charger_phrases(discours, f"{len(discours)} fichiers CoNLL-U", textes)
        etat().dire("ok", f"{len(discours)} discours chargés.")
        return redirect(url_for("corpus"))

    @app.post("/corpus/tables")
    def corpus_tables():
        """Lit les deux CSV déposés et charge les énoncés avec leurs relations."""
        fe, fr = request.files.get("enonces"), request.files.get("relations")
        if not (fe and fe.filename and fr and fr.filename):
            etat().dire("erreur", "Il faut les deux fichiers : énoncés et relations.")
            return redirect(url_for("corpus", mode="tables"))
        try:
            etat().charger_tables(charger_enonces_texte(fe.read().decode("utf-8")),
                                  charger_relations_texte(fr.read().decode("utf-8")),
                                  f"tables {fe.filename} et {fr.filename}")
        except (ValueError, KeyError) as erreur:
            etat().dire("erreur", f"Tables refusées : {erreur}")
            return redirect(url_for("corpus", mode="tables"))
        etat().dire("ok", "Tables chargées.")
        return redirect(url_for("corpus"))

    @app.post("/corpus/textes")
    def corpus_textes():
        """Analyse les textes avec Stanza puis charge les phrases obtenues."""
        if not LINGUISTE_DISPONIBLE:
            etat().dire("info", "L'analyse de textes est désactivée dans cette version ; utilisez les tables CSV.")
            return redirect(url_for("corpus", mode="tables"))
        if not stanza_disponible():
            etat().dire("erreur", "Stanza n'est pas installé ou le modèle français n'est pas disponible. "
                        "Installez les dépendances puis lance : python -c \"import stanza; stanza.download('fr')\".")
            return redirect(url_for("corpus", mode="textes",
                                    **({"modifier": "1"} if etat().a_un_corpus else {})))

        remplis = {}
        for fichier in request.files.getlist("fichiers"):
            if not fichier or not fichier.filename:
                continue
            nom = _nom_propre(Path(fichier.filename).stem) or "discours"
            texte = fichier.read().decode("utf-8", errors="replace")
            if not texte.strip():
                continue
            if nom in remplis:
                etat().dire("erreur", f"Deux discours portent le même nom : {nom}. Renommez l'un des fichiers.")
                return redirect(url_for("corpus", mode="textes",
                                        **({"modifier": "1"} if etat().a_un_corpus else {})))
            remplis[nom] = texte

        noms = request.form.getlist("nom")
        textes = request.form.getlist("texte")
        for nom, texte in zip(noms, textes):
            if not texte or not texte.strip():
                continue
            nom = _nom_propre(nom) or "discours"
            if nom in remplis:
                etat().dire("erreur", f"Deux discours portent le même nom : {nom}. Utilisez des titres différents.")
                return redirect(url_for("corpus", mode="textes",
                                        **({"modifier": "1"} if etat().a_un_corpus else {})))
            remplis[nom] = texte

        if not remplis:
            etat().dire("erreur", "Aucun texte exploitable : ajoutez au moins un discours non vide.")
            return redirect(url_for("corpus", mode="textes",
                                    **({"modifier": "1"} if etat().a_un_corpus else {})))

        try:
            analyses = {nom: analyser_texte(t, nom) for nom, t in remplis.items()}
        except Exception as erreur:  # pragma: no cover - dépend de Stanza et du modèle
            etat().dire("erreur", "L'analyse Stanza a échoué : "
                        f"{erreur}. Vérifiez que le modèle français 'fr' est bien installé.")
            return redirect(url_for("corpus", mode="textes",
                                    **({"modifier": "1"} if etat().a_un_corpus else {})))

        etat().charger_phrases({n: ph for n, (_, ph) in analyses.items()},
                               f"{len(remplis)} textes analysés par Stanza",
                               {n: c for n, (c, _) in analyses.items()}, remplis)
        etat().dire("ok", f"{len(remplis)} textes analysés et chargés.")
        return redirect(url_for("corpus"))

    @app.get("/corpus/<nom>.conllu")
    def corpus_telecharger(nom):
        """Télécharge le fichier CoNLL-U d'un discours chargé."""
        texte = etat().conllu.get(nom)
        if texte is None:
            return Response("Inconnu", 404)
        return Response(texte, mimetype="text/plain",
                        headers={"Content-Disposition": f'attachment; filename="{nom}.conllu"'})

    # --- Lecture du linguiste LLM (LG5) ----------------------------------------------------------
    @app.get("/linguiste")
    @exige_corpus
    def linguiste():
        """Affiche les lectures du linguiste et les décisions à vérifier."""
        if not LINGUISTE_DISPONIBLE:
            etat().dire("info", "Partie linguiste indisponible dans cette installation.")
            return redirect(url_for("corpus"))
        try:
            from aad69.mistral import ErreurMistral
        except ModuleNotFoundError as erreur:
            if erreur.name and erreur.name.endswith(".mistral"):
                etat().dire("info", "Module Mistral indisponible dans cette installation.")
                return redirect(url_for("corpus"))
            raise
        from aad69.linguiste import RELATIONS_PERMISES, decrire, phrase_lue
        e = etat()
        if e.phrases and not e.linguiste_tente:
            e.linguiste_tente = True
            try:
                n, rejets = e.lancer_linguiste()
            except (ErreurMistral, RuntimeError) as erreur:
                e.dire("erreur", f"Lecture impossible : {erreur}")
            else:
                e.dire("ok", f"Lecture faite : {n} suggestion{'s' if n > 1 else ''} appliquée{'s' if n > 1 else ''} par défaut"
                       + (f", {rejets} réponse{'s' if rejets > 1 else ''} écartée{'s' if rejets > 1 else ''} par la validation" if rejets else "")
                       + ". Tu peux refuser ou modifier chaque suggestion.")
        blocs = []
        for nom, phrases in (e.phrases or {}).items():
            lecture = e.lectures.get(nom)
            antecedents = [
                {"cle": f"{p.sent_id}|{m.id}", "forme": m.forme, "phrase": p.texte}
                for p in phrases for m in sorted(p.mots.values(), key=lambda mot: mot.id)
                if m.upos in ("NOUN", "PROPN")
            ]
            lignes = []
            for p in phrases:
                decisions = [d for d in (lecture.decisions if lecture else []) if d.sent_id == p.sent_id]
                tetes = [{"id": 0, "forme": "mot principal"}] + [
                    {"id": m.id, "forme": m.forme}
                    for m in sorted(p.mots.values(), key=lambda mot: mot.id) if m.upos != "PUNCT"
                ]
                lieux = [
                    {"id": m.id, "forme": m.forme, "preposition": " ".join(
                        case.forme for case in p.dependants(m.id, {"case"}))}
                    for m in sorted(p.mots.values(), key=lambda mot: mot.id)
                    if m.upos in ("NOUN", "PROPN", "PRON") and p.dependants(m.id, {"case"})
                ]
                lignes.append({
                    "phrase": p, "lue": phrase_lue(p, lecture, phrases) if lecture else "",
                    "decisions": [(d, decrire(d, phrases)) for d in decisions],
                    "antecedents": antecedents, "tetes": tetes, "lieux": lieux,
                })
            blocs.append({"nom": nom, "lecture": lecture, "lignes": lignes})
        return page("linguiste.html", "linguiste", blocs=blocs,
                    relations_permises=sorted(RELATIONS_PERMISES))

    @app.post("/linguiste/lancer")
    def linguiste_lancer():
        """Lance la lecture LLM des phrases du corpus."""
        if not LINGUISTE_DISPONIBLE:
            etat().dire("info", "Partie linguiste indisponible dans cette installation.")
            return redirect(url_for("corpus"))
        try:
            from aad69.mistral import ErreurMistral
        except ModuleNotFoundError as erreur:
            if erreur.name and erreur.name.endswith(".mistral"):
                etat().dire("info", "Module Mistral indisponible dans cette installation.")
                return redirect(url_for("corpus"))
            raise
        if not etat().phrases:
            etat().dire("erreur", "Le linguiste lit des phrases : chargez un corpus de textes ou de CoNLL-U.")
            return redirect(url_for("linguiste"))
        try:
            n, rejets = etat().lancer_linguiste()
        except (ErreurMistral, RuntimeError) as erreur:
            etat().linguiste_tente = True
            etat().dire("erreur", f"Lecture impossible : {erreur}")
            return redirect(url_for("linguiste"))
        etat().dire("ok", f"Lecture faite : {n} suggestion{'s' if n > 1 else ''} appliquée{'s' if n > 1 else ''} par défaut"
                    + (f", {rejets} réponse{'s' if rejets > 1 else ''} écartée{'s' if rejets > 1 else ''} par la validation" if rejets else "")
                    + ". Tu peux refuser ou modifier chaque suggestion.")
        return redirect(url_for("linguiste"))

    @app.post("/linguiste/decision")
    def linguiste_decision():
        """Enregistre l'acceptation ou le refus d'une décision proposée."""
        if not LINGUISTE_DISPONIBLE:
            etat().dire("info", "Partie linguiste indisponible dans cette installation.")
            return redirect(url_for("corpus"))
        choix = request.form.get("choix")
        if choix not in ("accepter", "refuser"):
            etat().dire("erreur", "Choix invalide : accepte ou refuse explicitement la suggestion.")
            return redirect(url_for("linguiste"))
        acceptee = etat().choisir_decision(
            request.form.get("discours", ""), request.form.get("cle", ""), choix == "accepter")
        if acceptee is not None:
            etat().dire("ok", "Suggestion acceptée et appliquée." if acceptee
                        else "Suggestion refusée : les règles seules sont appliquées.")
        return redirect(url_for("linguiste") + "#" + request.form.get("ancre", ""))

    @app.post("/linguiste/corriger")
    def linguiste_corriger():
        """Enregistre une correction manuelle d'une décision du linguiste."""
        if not LINGUISTE_DISPONIBLE:
            etat().dire("info", "Partie linguiste indisponible dans cette installation.")
            return redirect(url_for("corpus"))
        discours, cle = request.form.get("discours", ""), request.form.get("cle", "")
        try:
            etat().modifier_decision(
                discours, cle,
                antecedents=request.form.getlist("antecedents"),
                tete=request.form.get("tete"),
                relation=request.form.get("relation"),
                complement=request.form.get("complement", ""),
                raison=request.form.get("raison", "").strip(),
            )
        except ValueError as erreur:
            etat().dire("erreur", f"Correction non appliquée : {erreur}")
        else:
            etat().dire("ok", "Correction enregistrée et validée ; elle sera appliquée aux étapes suivantes.")
        return redirect(url_for("linguiste") + "#" + request.form.get("ancre", ""))

    # --- Vue consultative des propositions ------------------------------------------------------
    @app.get("/propositions")
    @exige_corpus
    def propositions():
        """Affiche les propositions et leurs dépendances dans les phrases chargées."""
        e = etat()
        blocs = [
            {"nom": nom, "phrases": construire_propositions(phrases, e.lectures.get(nom))}
            for nom, phrases in (e.phrases or {}).items()
        ]
        return page("propositions.html", "propositions", blocs=blocs)

    # --- 2 à 8 -----------------------------------------------------------------------------------
    @app.get("/enonces")
    @exige_corpus
    def enonces():
        """Affiche la table des énoncés, avec un filtre facultatif par discours."""
        return page("enonces.html", "enonces", filtre=request.args.get("discours", ""))

    @app.get("/enonces/<version>/<int:indice>")
    @exige_corpus
    def enonce_corriger(version, indice):
        """Affiche le formulaire de correction d'un énoncé et sa phrase d'origine."""
        brut = {e.indice: e for e in etat().corpus_brut(version).enonces}
        if version not in ("1969", "1972") or indice not in brut:
            return Response("Énoncé inconnu", 404)
        correction = etat().corrections.get(version, {}).get(indice, {})
        e = brut[indice]
        phrase = ""  # la phrase d'où vient l'énoncé (source = « id-de-phrase:id-du-mot »)
        if etat().phrases and e.source:
            sid = e.source.rsplit(":", 1)[0]
            phrase = next((p.texte for p in etat().phrases.get(e.discours, []) if p.sent_id == sid), "")
        return page("corriger.html", "enonces", version=version, original=e, correction=correction, phrase=phrase)

    @app.post("/enonces/<version>/<int:indice>")
    @exige_corpus
    def enonce_enregistrer(version, indice):
        """Enregistre ou annule la correction manuelle d'un énoncé."""
        if request.form.get("action") == "annuler":
            etat().annuler_correction(version, indice)
            etat().dire("ok", f"Correction de l'énoncé {indice} ({version}) annulée.")
        else:
            etat().corriger(version, indice, {c: request.form.get(c, "") for c in CASES})
            etat().dire("ok", f"Énoncé {indice} ({version}) enregistré. Toutes les étapes sont recalculées.")
        return redirect(url_for("enonces", discours=request.form.get("discours", "")) + f"#e{version}-{indice}")

    @app.get("/relations")
    @exige_corpus
    def relations():
        """Affiche les relations du discours choisi sous forme de graphe."""
        e = etat()
        noms = [d for d, _, _ in e.discours()]
        choisi = request.args.get("discours") or (noms[0] if noms else "")
        graphes = {v: graphe_svg(res, choisi) for v, res in e.calculer().items()}
        return page("relations.html", "relations", discours=noms, choisi=choisi, graphes=graphes)

    @app.get("/comparaison")
    @exige_corpus
    def comparaison():
        """Affiche les cases identiques, le vecteur π et la proximité de deux énoncés."""
        details = {}
        for v, res in etat().calculer().items():
            par = {x.indice: x for x in res.corpus.enonces}
            ids = list(par)
            if len(ids) < 2:
                continue
            a = int(request.args.get("a", ids[0]))
            b = int(request.args.get("b", ids[1]))
            if a in par and b in par:
                details[v] = {"a": par[a], "b": par[b], "pi": vecteur_pi(par[a], par[b]),
                              "p": proximite(par[a], par[b], res.reglages.poids), "max": res.reglages.poids.maximum()}
        return page("comparaison.html", "comparaison", details=details,
                    a=request.args.get("a", ""), b=request.args.get("b", ""))

    @app.get("/domaines")
    @exige_corpus
    def domaines():
        """Affiche les domaines calculés à l'étape 5."""
        return page("domaines.html", "domaines")

    @app.get("/regroupements")
    @exige_corpus
    def regroupements():
        """Affiche le dendrogramme et les groupes à la borne choisie."""
        lien = request.args.get("lien", "simple")
        if lien not in LIENS:
            lien = "simple"
        calculs = {}
        for version, res in etat().calculer().items():
            r = res.reglages
            s_max = score_maximum(r.poids, r.regle)
            borne = borne_valide(request.args.get("borne", r.borne), r.borne, s_max)
            reference = res if borne == r.borne else executer(res.corpus, _remplacer(r, borne=borne))
            reg = regrouper(
                res.corpus.enonces,
                res.corpus.relations,
                lien,
                borne,
                r.poids,
                r.intermediaires,
                r.annulation,
                r.operateurs_exclus,
                domaines_aad=reference.domaines,
                regle=r.regle,
            )
            calculs[version] = {"reg": reg, "svg": dendrogramme_svg(reference, reg), "ref": reference}

        nombres = [str(len(c["reg"].groupes)) for c in calculs.values()]
        compteur = nombres[0] if len(set(nombres)) <= 1 else " | ".join(nombres)
        premier = next(iter(calculs.values()))["reg"] if calculs else None
        return page(
            "regroupements.html",
            "regroupements",
            calculs=calculs,
            lien=lien,
            liens=LIENS,
            borne=premier.borne if premier else 28,
            s_max=premier.s_max if premier else 56,
            compteurs_extra={"regroupements": compteur} if compteur else {},
        )

    @app.get("/entre-domaines")
    @exige_corpus
    def entre_domaines():
        """Affiche les relations entre les domaines calculés."""
        return page("entre_domaines.html", "entre-domaines")

    @app.get("/hyperdomaines")
    @exige_corpus
    def hyperdomaines():
        """Affiche les hyperdomaines et leurs noms éventuels."""
        return page("hyperdomaines.html", "hyperdomaines")

    @app.post("/hyperdomaines/noms")
    @exige_corpus
    def hyperdomaines_noms():
        """Enregistre les noms d'hyperdomaines saisis par l'analyste."""
        for cle, valeur in request.form.items():
            m = re.fullmatch(r"nom_(\d{4})_(\d+)", cle)
            if m:
                etat().noms_hyper.setdefault(m[1], {})[int(m[2])] = valeur.strip()
        etat().dire("ok", "Noms enregistrés. Ils seront repris dans l'export.")
        return redirect(url_for("hyperdomaines"))

    @app.get("/journal")
    @exige_corpus
    def journal():
        """Affiche le journal des réglages et des corrections de l'analyse."""
        return page("journal.html", "journal")

    @app.get("/export.zip")
    @exige_corpus
    def export():
        """Télécharge l'archive ZIP des tables, réglages et traces de l'analyse."""
        e = etat()
        donnees = zip_resultats(e.calculer(), e.noms_hyper, e.source, e.lignes_corrections(), e.lignes_linguiste())
        nom = f"aad69_{datetime.now():%Y%m%d_%H%M}.zip"
        return Response(donnees, mimetype="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{nom}"'})

    # --- version et réglages -------------------------------------------------------------------
    @app.post("/version")
    def version():
        """Change la version affichée : 1969, 1972 ou les deux."""
        if request.form.get("version") in ("les-deux", "1969", "1972"):
            etat().version_affichee = request.form["version"]
        return retour()

    @app.post("/reglages")
    def reglages():
        """Enregistre les réglages du formulaire après validation."""
        valeurs = {k: v for k, v in request.form.items() if k != "retour"}
        for k in CASES_CHECKBOX:
            valeurs[k] = "oui" if k in request.form else "non"
        try:
            etat().reglages = valeurs
            etat().reglages_pour("1969")  # vérifie les valeurs
        except ValueError as erreur:
            etat().reglages = {}
            etat().invalider_calcul()
            etat().dire("erreur", f"Réglages refusés : {erreur}")
            return retour()
        etat().invalider_calcul()
        n = len(etat().reglages_pour("1969").ecarts())
        etat().dire("ok", "Réglages du livre appliqués." if n == 0 else f"Réglages appliqués : {n} écart(s) au livre.")
        return retour()

    @app.post("/reglages/livre")
    def reglages_livre():
        """Rétablit les réglages par défaut du livre."""
        etat().reglages = {}
        etat().invalider_calcul()
        etat().dire("ok", "Réglages par défaut rétablis.")
        return retour()

    return app


if __name__ == "__main__":
    mode_developpement = os.environ.get("AAD69_MODE_DEVELOPPEMENT") == "1"
    creer_app(mode_developpement=mode_developpement).run(debug=False, port=5000)
