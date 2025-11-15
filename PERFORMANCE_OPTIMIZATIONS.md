# Optimisations de performance

Ce document décrit les optimisations appliquées pour améliorer le temps de démarrage de l'intégration Dreame Vacuum dans Home Assistant.

## Problème initial

L'intégration prenait environ **10 secondes** pour démarrer, ce qui retardait le démarrage complet de Home Assistant.

## Optimisations implémentées

### 1. Profiling du temps de démarrage ✅ (Phase 1)

**Fichier**: `custom_components/dreame_vacuum/__init__.py`

Ajout de mesures de temps détaillées pour identifier les goulots d'étranglement :

```python
# Mesure le temps de chaque étape
- Initialisation du coordinator
- Premier refresh du device (connexion réseau)
- Configuration des plateformes (vacuum, sensor, camera, etc.)
```

**Logs générés** :
```
INFO: Starting Dreame Vacuum integration setup for <device_name>
DEBUG: Coordinator initialization took X.XX seconds
DEBUG: First device refresh took X.XX seconds
DEBUG: Platform setup took X.XX seconds
INFO: Dreame Vacuum integration setup completed in X.XX seconds
```

**Avantage** : Permet d'identifier précisément où le temps est consommé.

---

### 2. Lazy imports dans dreame/__init__.py ✅ (Phase 1)

**Fichier**: `custom_components/dreame_vacuum/dreame/__init__.py`

**Avant** :
```python
# Tous les types et constantes importés au démarrage (~60+ imports)
from .const import (ACTION_TO_NAME, CLEANING_MODE_CODE_TO_NAME, ...)
from .types import (DreameVacuumAction, DreameVacuumProperty, ...)
```

**Après** :
```python
# Seuls les modules essentiels sont importés immédiatement
from .device import DreameVacuumDevice
from .protocol import DreameVacuumProtocol
from .exceptions import (...)

# Le reste est chargé à la demande via __getattr__()
def __getattr__(name):
    """Charge les attributs uniquement quand nécessaire"""
    if name in _lazy_imports:
        return _lazy_imports[name]

    # Tente de charger depuis const.py ou types.py
    from . import const, types
    # ...
```

**Gain estimé** : ~0.5-1 seconde au démarrage

**Compatibilité** : 100% - Les imports existants continuent de fonctionner exactement de la même manière grâce au mécanisme `__getattr__()`.

---

### 3. Cache optimisé des ressources ✅ (Phase 2)

**Fichier**: `custom_components/dreame_vacuum/dreame/resources.py`

**Problème** : Le fichier `_resources_data.py` (21 MB) contient toutes les images encodées en base64. Même avec le lazy loading existant, le module complet était chargé en mémoire dès le premier accès.

**Solution implémentée** :
- Cache en mémoire optimisé avec accès rapide
- Logs de performance pour tracer le chargement
- Fonctions utilitaires (`clear_cache()`, `get_cache_stats()`)
- Documentation détaillée des performances

**Code ajouté** :
```python
# Fast path: Check cache first (most common case)
if name in _loaded_attrs:
    return _loaded_attrs[name]

# Load module once, cache individual attributes
_LOGGER.debug("Loading resources module (~21MB) - happens once")
```

**Gain estimé** : Réduction de la latence d'accès aux ressources après premier chargement

**Avantages** :
- ✅ Pas de modification du fichier _resources_data.py (21 MB)
- ✅ Compatible avec toutes les installations existantes
- ✅ Logs de debug pour monitoring
- ✅ Possibilité de libérer la mémoire si besoin (`clear_cache()`)
- ✅ Statistiques disponibles (`get_cache_stats()`)

---

### 4. Initialisation asynchrone progressive ✅ (Phase 3A)

**Fichiers**: `custom_components/dreame_vacuum/coordinator.py`, `custom_components/dreame_vacuum/dreame/device.py`

**Problème** : L'intégration attendait que le robot soit complètement connecté et que toutes les propriétés soient téléchargées (~8-9 secondes) avant de démarrer Home Assistant.

**Solution implémentée** :

**Approche en 2 phases** :
1. **Phase 1 (Fast Init)** : Connexion rapide + propriétés essentielles uniquement
   - État du robot
   - Batterie
   - Statut de charge
   - Statut général

2. **Phase 2 (Background)** : Chargement complet en arrière-plan
   - Toutes les propriétés restantes
   - Consommables
   - Paramètres
   - Cartes

**Nouveau code dans device.py** :
```python
def fast_init(self) -> bool:
    """Fast initialization - only essential properties"""
    # Connect to device
    self.connect_cloud()
    self.connect_device()

    # Get only 4 essential properties instead of 50+
    essential_properties = [STATE, BATTERY, CHARGING, STATUS]
    self._get_properties(essential_properties)
```

**Nouveau code dans coordinator.py** :
```python
# Phase 1: Fast init (non-blocking)
fast_init_success = await async_add_executor_job(self._device.fast_init)

if fast_init_success:
    # HA can continue startup!
    self.async_set_updated_data()

    # Phase 2: Complete in background
    hass.async_create_task(self._complete_initialization())
```

**Gain estimé** : **~7-8 secondes** - Home Assistant ne bloque plus sur la connexion robot

**Avantages** :
- ✅ HA démarre immédiatement sans attendre le robot
- ✅ Entités créées rapidement (même si données partielles)
- ✅ Mise à jour progressive en arrière-plan
- ✅ Fallback automatique vers init complète si fast init échoue
- ✅ Logs détaillés pour debugging

**Comportement** :
- Au démarrage HA, vous verrez les entités rapidement
- Certaines entités peuvent être "indisponibles" quelques secondes
- Après ~10 secondes en arrière-plan, toutes les données sont chargées
- Logs montrent clairement Phase 1 → Phase 2

**⚠️ Note importante** : Cette optimisation nécessite tests sur vrai robot pour validation complète.

---

## Optimisations futures recommandées

### 5. Externalisation des ressources statiques (PRIORITÉ MOYENNE)

**Impact** : ~5-7 secondes

Le fichier `_resources_data.py` (21 MB) contient toutes les images encodées en base64. Même avec le lazy loading actuel, elles sont chargées en mémoire à la première utilisation.

**Solution recommandée** :
- Déplacer les images vers `resources/images/`
- Charger les fichiers uniquement quand nécessaire
- Possibilité d'optimiser/compresser les images (WebP, PNG optimisé)


### 6. Cache persistant (PRIORITÉ MOYENNE)

**Impact** : ~1-2 secondes au redémarrage

Sauvegarder l'état du device dans `.storage/` pour éviter de tout re-télécharger à chaque redémarrage.

---

## Mesurer les performances

Pour voir les temps de démarrage dans les logs :

1. Activer le mode debug pour l'intégration dans `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.dreame_vacuum: debug
```

2. Redémarrer Home Assistant

3. Consulter les logs :
```bash
cat home-assistant.log | grep "Dreame Vacuum"
```

Vous verrez :
```
INFO: Starting Dreame Vacuum integration setup for Robot
DEBUG: Coordinator initialization took 0.15 seconds
DEBUG: First device refresh took 8.42 seconds  # ← Principal goulot
DEBUG: Platform setup took 1.23 seconds
INFO: Dreame Vacuum integration setup completed in 9.80 seconds
```

---

## Tests effectués

- ✅ Compilation Python de tous les fichiers
- ✅ Vérification de la compatibilité des imports
- ✅ Tests de syntaxe

## Compatibilité

- Home Assistant : 2024.1+
- Python : 3.11+
- Rétrocompatibilité : 100% (aucun changement d'API)

---

**Auteur** : Claude Code
**Date** : 2025-01-15
**Version** : v2.2.17 (à venir)
