# Guide de contribution

Merci de votre intérêt pour contribuer au projet Dreame Vacuum !

## Configuration de l'environnement de développement

### Prérequis

- Python 3.11 ou supérieur
- Git  
- Home Assistant (pour les tests)

### Installation

1. Clonez le dépôt :
\`\`\`bash
git clone https://github.com/foXaCe/dreame-vacuum.git
cd dreame-vacuum
\`\`\`

2. Installez le runner de hooks **prek** (drop-in Rust de pre-commit) et activez-le :
\`\`\`bash
pipx install prek   # ou : uv tool install prek / brew install j178/prek/prek
prek install
\`\`\`

## Outils de qualité de code

### Ruff

Ruff est utilisé pour le linting et le formatage du code.

**Vérifier le code :**
\`\`\`bash
ruff check custom_components/dreame_vacuum
\`\`\`

**Corriger automatiquement :**
\`\`\`bash
ruff check custom_components/dreame_vacuum --fix
\`\`\`

**Formater le code :**
\`\`\`bash
ruff format custom_components/dreame_vacuum
\`\`\`

### Pre-commit (via prek)

Les hooks définis dans `.pre-commit-config.yaml` s'exécutent automatiquement à chaque commit, via [prek](https://github.com/j178/prek) — un drop-in Rust de `pre-commit`, ~10× plus rapide (même fichier de config). La version Python historique reste compatible (`pipx install pre-commit`) si vous préférez.

**Exécuter manuellement :**
\`\`\`bash
prek run --all-files
\`\`\`

## Standards de code

- Longueur de ligne : 120 caractères
- Doubles quotes pour les chaînes
- Imports organisés automatiquement par ruff

## Contribution

1. Fork le dépôt
2. Créez une branche : \`git checkout -b feature/ma-fonctionnalite\`
3. Committez : \`git commit -m "feat: description"\`
4. Push : \`git push origin feature/ma-fonctionnalite\`
5. Ouvrez une Pull Request

## Gestion des dépendances

Les mises à jour de dépendances sont gérées automatiquement par **Renovate**
(et non Dependabot). Les PR sont ouvertes par `@renovate[bot]` ; le
[dashboard Renovate](https://github.com/foXaCe/dreame-vacuum/issues?q=is%3Aissue+is%3Aopen+author%3Aapp%2Frenovate) liste
toutes les mises à jour en attente.

Merci ! 🎉
