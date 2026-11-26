# AAD69 — code applicatif

Ce dossier contient les modules du programme et l'interface web locale :

```text
AAD69/
├── modules/
│   └── *.py         modules de calcul
└── interface/       application web locale
```

## Première étape : modèle, lecture CoNLL-U et lexique

Les modules `modules/modele.py`, `modules/conllu.py` et `modules/lexique.py`
définissent les structures de données, la lecture de fichiers CoNLL-U et les
listes de mots(dictionnair) utilisées par le programme. Ils ne lancent pas une application
à eux seuls.

Il faut Python **3.10 ou une version plus récente**. Pour ces trois modules,
aucune bibliothèque supplémentaire n'est nécessaire.

Ouvrez un terminal à la racine du dépôt, c'est-à-dire le dossier qui contient
`AAD69/`, puis créez un environnement virtuel. Placez-le dans votre dossier
personnel pour qu'il ne soit pas ajouté par erreur au dépôt.

**Windows (PowerShell) :**

```powershell
py -3 -m venv "$env:USERPROFILE\aad69-env"
& "$env:USERPROFILE\aad69-env\Scripts\Activate.ps1"
```

**macOS ou Linux :**

```bash
python3 -m venv "$HOME/aad69-env"
source "$HOME/aad69-env/bin/activate"
```

Il n'y a pas de commande `pip install` à lancer pour cette étape. Pour vérifier
que le modèle peut être utilisé, toujours depuis la racine du dépôt, exécutez :

```bash
python -c "import sys; sys.path.insert(0, 'AAD69/modules'); from modele import Enonce; print(Enonce(1))"
```

Si une ligne commençant par `Enonce(` s'affiche sans erreur, le modèle est
accessible. Si vous avez utilisé `python3` pour créer l'environnement, utilisez
également `python3` dans cette commande. Pour quitter l'environnement virtuel :

```bash
deactivate
```

