# Guide de contribution

Merci de votre intérêt pour contribuer au projet Dreame Vacuum !

## Configuration de l'environnement de développement

### Prérequis

- Python 3.13 ou supérieur (3.14 pour mypy, comme en CI)
- Git  
- Home Assistant (pour les tests)

### Installation

1. Clonez le dépôt :
```bash
git clone https://github.com/foXaCe/dreame-vacuum.git
cd dreame-vacuum
```

2. Installez le runner de hooks **prek** (drop-in Rust de pre-commit) et activez-le :
```bash
pipx install prek   # ou : uv tool install prek / brew install j178/prek/prek
prek install
```

3. Installez la stack de développement complète (tests + qualité + libs runtime) :
```bash
pip install -r requirements-dev.txt
```
> `requirements_test.txt` (inclus) épingle `pytest-homeassistant-custom-component`,
> qui impose les versions Home Assistant compatibles ; les libs runtime restent
> volontairement non épinglées (Home Assistant décide).

## Outils de qualité de code

### Ruff

Ruff est utilisé pour le linting et le formatage du code.

**Vérifier le code :**
```bash
ruff check custom_components/dreame_vacuum
```

**Corriger automatiquement :**
```bash
ruff check custom_components/dreame_vacuum --fix
```

**Formater le code :**
```bash
ruff format custom_components/dreame_vacuum
```

### Pre-commit (via prek)

Les hooks définis dans `.pre-commit-config.yaml` s'exécutent automatiquement à chaque commit, via [prek](https://github.com/j178/prek) — un drop-in Rust de `pre-commit`, ~10× plus rapide (même fichier de config). La version Python historique reste compatible (`pipx install pre-commit`) si vous préférez.

**Exécuter manuellement :**
```bash
prek run --all-files
```

## Tests et vérifications

La CI applique cinq portes de qualité. Avant d'ouvrir une Pull Request, exécutez-les
localement :

**Tests unitaires (avec couverture) :**
```bash
pytest tests/ --cov=custom_components/dreame_vacuum
```
≈ 4 000 tests, ~30 s. La couverture doit rester ≥ 95 % — c'est un plancher qui ne
fait que monter, jamais redescendre.

**Lint :**
```bash
ruff check custom_components/ tests/
```

**Formatage :**
```bash
ruff format --check custom_components/ tests/
```

**Typage statique :**
```bash
mypy custom_components/dreame_vacuum
```
Mode ratchet : seuls les modules listés explicitement dans `pyproject.toml
[tool.mypy]` sont vérifiés strictement ; le reste du package est temporairement
ignoré. On étend cette liste au fil du nettoyage, on ne la réduit jamais.

**Analyse de sécurité :**
```bash
bandit -c pyproject.toml -r custom_components/
```

## Standards de code

- Longueur de ligne : 120 caractères
- Doubles quotes pour les chaînes
- Imports organisés automatiquement par ruff

## Contribution

1. Fork le dépôt
2. Créez une branche : `git checkout -b feature/ma-fonctionnalite`
3. Committez : `git commit -m "feat: description"`
4. Push : `git push origin feature/ma-fonctionnalite`
5. Ouvrez une Pull Request

## Gestion des dépendances

Les mises à jour de dépendances sont gérées automatiquement par **Renovate**
(et non Dependabot). Les PR sont ouvertes par `@renovate[bot]` ; le
[dashboard Renovate](https://github.com/foXaCe/dreame-vacuum/issues?q=is%3Aissue+is%3Aopen+author%3Aapp%2Frenovate) liste
toutes les mises à jour en attente.

Le plancher `python-miio>=0.5.12` du manifest est volontairement gelé : 0.5.12
(juillet 2022) est la dernière release stable publiée sur PyPI. L'upstream
GitHub reste actif mais ne release plus ; `dreame/miio_patch.py` porte le
contournement d'un fix upstream non publié. Ne tentez pas de bump cette
dépendance.

Merci ! 🎉
