"""Appel à l'API de Mistral, avec un cache des réponses.

Utilisé par le linguiste LLM (aad69/reecriture.py). Python pur (urllib) : rien à installer.

- La clé est lue dans la variable d'environnement MISTRAL_API_KEY ; elle n'est jamais écrite
  dans le code, le cache ni les journaux.
- Le modèle se choisit par MISTRAL_MODEL (défaut : mistral-large-4) ou par l'argument `modele`.
- Température 0 et réponse en JSON.
- Cache (facultatif) : une requête identique déjà posée n'est pas renvoyée, on relit la réponse
  gardée ; relancer donne donc le même résultat, sans nouvel appel ni nouveau coût.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.mistral.ai/v1/chat/completions"
MODELE_PAR_DEFAUT = "mistral-large-4"
CACHE_PAR_DEFAUT = Path.home() / ".cache" / "aad69" / "linguiste_llm.json"


# Regroupe les erreurs liées à l'appel Mistral pour que l'interface puisse les afficher clairement.
class ErreurMistral(RuntimeError):
    """Clé absente, API injoignable, réponse tronquée ou illisible : message en clair."""


# Produit une empreinte stable de la requête, utilisée comme clé dans le cache.
def _cle(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# Lit le cache s'il existe ; un fichier absent ou illisible est traité comme un cache vide.
def _lire_cache(chemin: Path | None) -> dict:
    if chemin is None or not Path(chemin).is_file():
        return {}
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# Envoie une requête au modèle et renvoie le texte produit ainsi que le nom du modèle utilisé.
def appeler(consigne: str, question: str, *, modele: str | None = None, cle_api: str | None = None,
            delai: float = 300, max_jetons: int = 16000, cache: Path | None = None) -> tuple[str, str]:
    """Envoie (consigne système, question) et renvoie (texte de la réponse, modèle qui a répondu)."""
    # L'argument modele remplace la variable d'environnement, qui remplace le modèle par défaut.
    nom = modele or os.environ.get("MISTRAL_MODEL", MODELE_PAR_DEFAUT)
    # Demande une réponse JSON stable pour que le module linguiste puisse la lire et la valider.
    payload = {
        "model": nom,
        "messages": [{"role": "system", "content": consigne}, {"role": "user", "content": question}],
        "temperature": 0, "top_p": 1, "reasoning_effort": os.environ.get("MISTRAL_REASONING", "low"),
        "max_tokens": max_jetons,
        "response_format": {"type": "json_object"},
    }
    # Si cette requête a déjà été faite, réutilise sa réponse sans appeler l'API.
    empreinte = _cle(payload)
    memoire = _lire_cache(cache)
    if empreinte in memoire:
        return memoire[empreinte]["contenu"], memoire[empreinte]["modele"]

    # La clé peut être fournie directement ou lue dans l'environnement ; elle n'entre pas dans le cache.
    cle = cle_api or os.environ.get("MISTRAL_API_KEY")
    if not cle:
        raise ErreurMistral("Clé Mistral absente : définir la variable MISTRAL_API_KEY.")
    requete = urllib.request.Request(
        URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
    # Convertit les problèmes réseau et les réponses HTTP invalides en erreurs compréhensibles.
    try:
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            resultat = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:500].replace(cle, "***")
        except OSError:
            detail = ""
        exc.close()
        raise ErreurMistral(f"L'API Mistral a répondu avec le statut HTTP {exc.code} "
                            f"(modèle demandé : {nom}). Détail : {detail}") from None
    except urllib.error.URLError as exc:
        raise ErreurMistral(f"Impossible de joindre l'API Mistral : {exc.reason}") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ErreurMistral("La réponse de l'API Mistral n'est pas du JSON.") from None
    # Extrait le texte de la première réponse et signale les formats incomplets ou tronqués.
    try:
        choix = resultat["choices"][0]
        if choix.get("finish_reason") == "length":
            raise ErreurMistral("Réponse tronquée : texte trop long pour une seule requête.")
        contenu = choix["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ErreurMistral("La réponse de l'API Mistral n'a pas le format attendu.") from None
    if isinstance(contenu, list):   # certains modèles renvoient des blocs de texte
        contenu = "".join(b.get("text", "") for b in contenu if isinstance(b, dict))
    nom_effectif = resultat.get("model", nom)
    # Enregistre la réponse uniquement si un chemin de cache a été demandé.
    if cache is not None:
        memoire[empreinte] = {"modele": nom_effectif, "contenu": contenu}
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        Path(cache).write_text(json.dumps(memoire, ensure_ascii=False, indent=1), encoding="utf-8")
    return contenu, nom_effectif
