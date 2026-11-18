# AAD69 — premier prototype

Ce dépôt présente un premier prototype de réimplémentation de l’algorithme
d’analyse automatique du discours proposé par Michel Pêcheux en 1969. Le
programme est développé progressivement.

Il offre deux parcours : fournir des tableaux CSV d’énoncés et de relations
déjà établis, ou partir de textes. Dans le second parcours, Stanza analyse les
phrases, Grew applique les règles d’extraction du projet, puis le linguiste LLM
peut proposer des décisions à vérifier. Les résultats s’utilisent dans une
interface web locale.

## Installation

Il faut Python 3.10 ou une version plus récente. Depuis la racine du dépôt,
créez et activez un environnement virtuel.

**Windows (PowerShell)**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS et Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Installez les dépendances Python déclarées dans `pyproject.toml` :

```bash
python -m pip install -e ".[interface,analyse,grew,llm]"
```

Pour analyser des textes, téléchargez une fois le modèle français de Stanza :

```bash
python -c "import stanza; stanza.download('fr')"
```

Grew nécessite aussi un moteur natif installé avec opam. Installez opam si
nécessaire :

**Debian ou Ubuntu**

```bash
sudo apt install opam
```

**macOS avec Homebrew**

```bash
brew install opam
```

Puis initialise opam une première fois :

```bash
opam init
eval "$(opam env)"
```

Sous Windows, exécute ces commandes dans un environnement Linux WSL.

Si opam propose de modifier `~/.profile`, vous pouvez accepter pour charger son
environnement automatiquement dans les prochains terminaux. Sinon, lancez
`eval "$(opam env)"` dans chaque nouveau terminal avant d’utiliser Grew.

Ajoutez ensuite le dépôt de paquets Grew et installez le moteur :

```bash
opam remote add grew https://opam.grew.fr
opam install grewpy_backend "conll<1.20"
```

La limite `"conll<1.20"` évite un problème de compilation de `conll` 1.20 avec
OCaml 4.14. Le paquet Python `grewpy`, lui, est installé avec les dépendances
du projet indiquées plus haut.

## Lancer l’application

Depuis la racine du dépôt, lancez :

```bash
python AAD69/interface/app.py
```

Ouvrez ensuite <http://127.0.0.1:5000> dans votre navigateur.

## Linguiste LLM

L’analyse par Stanza et Grew fonctionne sans clé d’API. Pour utiliser les
suggestions du linguiste LLM, créez à la racine du dépôt un fichier `.env` avec
votre clé API Mistral :

```dotenv
MISTRAL_API_KEY=votre_cle_api
```

Le fichier `.env` est ignoré par Git : ne publiez pas votre clé. Les textes
soumis au linguiste sont envoyés à l’API Mistral ; n’utilisez que des textes
non confidentiels.

## NB

Ce code a été co-écrit avec Claude Code.
