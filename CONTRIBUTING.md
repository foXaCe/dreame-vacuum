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

2. Installez les hooks pre-commit :
\`\`\`bash
pre-commit install
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

### Pre-commit

Les hooks pre-commit s'exécutent automatiquement à chaque commit.

**Exécuter manuellement :**
\`\`\`bash
pre-commit run --all-files
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

Merci ! 🎉
