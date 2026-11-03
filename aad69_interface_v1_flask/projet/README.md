# AAD69 — première étape

Ce dossier contient le début du programme AAD69. Pour le moment, il contient
notamment `aad69/modele.py`, qui définit la forme des énoncés et des relations.
Ce fichier ne lance pas encore une application : il pose les structures de
données qui seront utilisées par les étapes suivantes.

## Préparer l'environnement

Il faut installer **Python 3.10 ou une version plus récente**. Aucune
bibliothèque supplémentaire n'est nécessaire pour cette étape.

Ouvrez un terminal dans le dossier `projet` — celui où se trouve ce README —
puis créez un environnement virtuel :

```bash
python -m venv .venv
```

Si la commande `python` n'est pas reconnue, utilisez `py -3` sous Windows ou
`python3` sous macOS/Linux.

Activez ensuite cet environnement.

**Windows (PowerShell) :**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS ou Linux :**

```bash
source .venv/bin/activate
```

Quand l'environnement est activé, son nom (`.venv`) apparaît généralement au
début de la ligne du terminal. Il n'y a pas de commande `pip install` à lancer
pour cette étape.

## Vérifier le modèle

Dans le même terminal, toujours depuis le dossier `projet`, exécutez :

```bash
python -c "from aad69.modele import Enonce; print(Enonce(1))"
```

Si vous avez utilisé `py -3` ou `python3` pour créer l'environnement, remplacez
également `python` par cette commande ici.

Si une ligne commençant par `Enonce(` s'affiche sans erreur, le modèle est
accessible et fonctionne. Pour quitter l'environnement virtuel, exécutez :

```bash
deactivate
```
