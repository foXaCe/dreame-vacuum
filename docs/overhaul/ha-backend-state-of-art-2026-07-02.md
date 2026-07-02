# État de l'art développement intégrations Home Assistant (backend Python) — 2026-07-02

Contexte : refactor de `dreame_vacuum` (fork Tasshack), iot_class `cloud_push`, integration_type `hub`,
plateformes vacuum/camera/sensor/binary_sensor/switch/select/number/button/time + diagnostics/repairs/
system_health/logbook/recorder. hacs.json `homeassistant >= 2023.6.0`, manifest `quality_scale: gold`.
Dépendances : DataUpdateCoordinator, config_flow, `paho-mqtt`, `requests` (sync), `pillow`/`numpy`.

---

## 1. Version HA stable actuelle et cadence

- **Version stable actuelle : Home Assistant Core 2026.7** — "Automations that speak your language",
  sortie le **1er juillet 2026**. (https://www.home-assistant.io/blog/2026/07/01/release-20267/)
- Cadence mensuelle inchangée (release le 1er jeudi/vendredi du mois, patchs `.1`, `.2`… ensuite).
- 3 dernières stables :
  1. **2026.7** (2026-07-01) — renommage massif de triggers/conditions "purpose-specific"
     (`battery.low`→`battery.became_low`, `vacuum.docked`→`vacuum.returned_to_dock`, etc.), timeline
     Activity/logbook refaite.
  2. **2026.6** (2026-06-03) — "Pick a card, any card" : nouveau card picker, migration de plusieurs
     checks Quality Scale de hassfest vers pylint (`parallel-updates`, `diagnostics`,
     `config-entry-unloading`, `reauthentication-flow`), renommage des comportements de triggers Labs
     (`any`→`each`, `last`→`all`), Bluetooth scanning mode par défaut passé à `Auto`.
  3. **2026.5** (2026-05-06) — "We're on the same frequency now" : support RF (radio-fréquence) pour
     stores/portails, nouveau dashboard Maintenance (suivi batteries), suppression des triggers/conditions
     `entered home`/`left home`/`is home`/`is not home` sur Person/Device Tracker.
- **Constat important** : depuis courant 2025, les *release notes* utilisateur (home-assistant.io/blog)
  ne contiennent plus de section "For developers" détaillée — elles renvoient systématiquement vers le
  **developer blog** (https://developers.home-assistant.io/blog/) pour tout ce qui concerne le
  développement d'intégrations. C'est désormais la source de vérité à surveiller en continu.

---

## 2. Dépréciations ACTIVES à corriger (avec version de retrait)

Classées par urgence pour ce refactor. **Beaucoup de délais sont déjà expirés** vu que hacs.json cible
encore HA 2023.6.0 — l'intégration tourne probablement déjà en mode dégradé/warnings sur une install à jour.

| # | Dépréciation | Déprécié depuis | Retrait prévu | Statut au 2026-07-02 | Action |
|---|---|---|---|---|---|
| 1 | `StateVacuumEntity` : constantes `STATE_*` pour l'état → **`VacuumActivity` enum** + propriété `activity` (au lieu de `state`) | 2025.1 | **2026.1** | **DÉJÀ RETIRÉ** (6 mois) | Urgent : si le code fixe encore `self._attr_state = STATE_CLEANING` ou équivalent, ça ne fonctionne plus du tout sur HA récent |
| 2 | `StateVacuumEntity` : constantes de feature flags → **`VacuumEntityFeature` enum** | 2024.10 (période "officielle"; dépréciation technique dès 2022.5 sans annonce propre) | 2025.10 | **DÉJÀ RETIRÉ** | Urgent : vérifier `SUPPORT_*` remplacés par `VacuumEntityFeature.*` |
| 3 | `StateVacuumEntity.battery_level` / `battery_icon` (properties) | **2025.8** | **2026.8** (dans ~1 mois) | ACTIF, retrait imminent | Remplacer par une entité `sensor` séparée `device_class: battery` (+ éventuellement un `binary_sensor` `device_class: charging`) |
| 4 | Camera : `frontend_stream_type` (property), `async_handle_web_rtc_offer`, `async_register_rtsp_to_web_rtc_provider` | 2024.12 | 2025.6 | **DÉJÀ RETIRÉ** | Si la plateforme camera fait du WebRTC (flux caméra embarquée du robot), migrer vers `async_handle_async_webrtc_offer` / `async_register_webrtc_provider`, utiliser le WS `camera/capabilities` côté frontend |
| 5 | `OptionsFlow` : assignation manuelle de `self.config_entry` dans `__init__` du flow / `OptionsFlowWithConfigEntry` | annoncé 2024.11 | avertissement jusqu'à **2025.12**, retrait non daté précisément mais **la fenêtre d'avertissement est déjà passée** | ACTIF — logge un warning demandant d'ouvrir une issue sur le repo custom si toujours assigné manuellement | Supprimer le paramètre `config_entry` du constructeur d'`OptionsFlowHandler`, utiliser `self.config_entry` / `self._config_entry_id` fournis nativement |
| 6 | Combiner un **config entry update listener** (`add_update_listener`) avec des méthodes de reload dans le config flow (`async_update_reload_and_abort`, `reload_on_update` implicite) | **2026.6** (ce mois-ci) | **2026.12** | TRÈS RÉCENT, ACTIF | Risque de reload en double / race condition. Choisir une seule stratégie : soit retirer le listener, soit `async_update_and_abort()`, soit `reload_on_update=False` sur `_abort_if_unique_id_configured()` |
| 7 | `quality_scale` déclaré comme clé dans `manifest.json` | changement de mécanisme depuis **2024.11.20** | pas un retrait à proprement parler pour les intégrations custom (non validé par hassfest hors core), mais c'est l'ancien pattern | À migrer par bonne pratique | Le nouveau modèle est un fichier **`quality_scale.yaml`** à la racine de l'intégration listant chaque règle avec statut (`done`/`exempt`+raison/`todo`). Pour une intégration custom ce fichier n'a pas d'effet runtime mais sert de checklist/preuve vis-à-vis de HACS et des reviewers |
| 8 | `FlowHandler.show_advanced_options` / `context['show_advanced_options']` | **2026.5** | **2027.6** | ACTIF, marge confortable | Remplacer le gating par "advanced mode" par une organisation en *sections* dans le config/options flow |
| 9 | `paho-mqtt` `CallbackAPIVersion.VERSION1` (API historique de callbacks) | dépréciée côté lib paho-mqtt (pas HA) | retrait prévu en **paho-mqtt 3.0** | À surveiller | Migrer les callbacks (`on_connect`, `on_message`, etc.) vers `CallbackAPIVersion.VERSION2`, plus cohérent MQTT 3.x/5.x |
| 10 | Détection des appels bloquants dans l'event loop (`requests`, `urllib`, `time.sleep`, I/O fichier sync) | renforcée depuis **2024.7** | pas une deadline unique — mais les logs `Detected blocking call to X inside the event loop by custom integration 'dreame_vacuum'` sont visibles par tous les utilisateurs et nourrissent les demandes HACS/quality-scale. Certains cas (import bloquant, sleep bloquant) sont déjà remontés comme quasi-erreurs bloquantes selon les composants internes | ACTIF EN PERMANENCE | `requests` est **structurellement incompatible** avec la règle Platinum `async-dependency` et dégrade l'expérience (warnings visibles, potentiel throttling futur). Tout appel `requests.get/post` doit passer par `hass.async_add_executor_job(...)` a minima, et à terme être remplacé par `aiohttp`/`httpx` async natif |

**Non trouvé de dépréciation spécifique 2024-2026 sur** : `DataUpdateCoordinator` (API stable, juste enrichie,
voir §3), `EntityDescription`/`_attr_has_entity_name` (pattern stable depuis 2023, toujours recommandé,
`has-entity-name` reste une règle Bronze obligatoire), `select`/`number`/`button`/`time`/`switch` platforms
(pas de breaking change identifié sur la période).

---

## 3. Nouvelles API à adopter (avec version d'introduction)

| API / pattern | Introduit en | Ce que ça apporte pour `dreame_vacuum` |
|---|---|---|
| **`ConfigEntry.runtime_data`** (ConfigEntry générique typé, `type MyConfigEntry = ConfigEntry[MyData]`) | 2024.4 (blog 2024-04-30), usage généralisé dès 2024.6-2024.8 | Remplace `hass.data[DOMAIN][entry.entry_id]`. C'est aussi la règle **Bronze `runtime-data`** — actuellement quasi-certainement non respectée vu le manifest `quality_scale: gold` déclaré avec une base HA 2023.6 |
| **`DataUpdateCoordinator._async_setup()`** | 2024.8 (blog 2024-08-05) | Hook async dédié appelé une fois via `async_config_entry_first_refresh()`, pour init unique (ex: découverte des appareils MQTT, fetch config initiale) sans polluer `_async_update_data` avec des flags `if not initialized` |
| **Helpers reauth/reconfigure** : `self._get_reauth_entry()`, `self._get_reconfigure_entry()`, `self._abort_if_unique_id_mismatch()`, `async_update_reload_and_abort(..., data_updates=...)` | 2024.10-2024.11 (blog 2024-10-21, 2024-11-04) | Pattern standard pour la règle Silver `reauthentication-flow` et Gold `reconfiguration-flow`. Entries doivent être liées via `entry_id` et récupérées localement à chaque step, pas cachées en attribut de classe |
| **OptionsFlow natif** : `self.config_entry` fourni automatiquement, `self._config_entry_id` | 2024.11 (blog 2024-11-12) | Supprimer le paramètre `config_entry` du `__init__` de l'OptionsFlowHandler |
| **Config Subentries** (`ConfigSubentryFlow`) | 2025.2 (blog 2025-02-16), ajustements 2025-03-24 | Pertinent si un compte cloud Dreame gère plusieurs robots/hubs — permettrait de modéliser chaque robot comme sous-entrée plutôt qu'un flot config unique |
| **`service.async_register_platform_entity_service`** appelé depuis `async_setup` de l'intégration (plus depuis le platform setup) | 2025.9 (blog 2025-09-25) | Remplace `platform.async_register_entity_service` historique ; découple l'enregistrement des services (actions) du timing de setup des plateformes — pertinent pour les actions custom vacuum (ex: `go_to`, `clean_zone`, `clean_segment`) |
| **Description placeholders pour traductions d'actions de service** | 2025.11 (blog 2025-11-27) | Permet des messages d'erreur/traductions d'actions plus riches — aligné avec la règle Gold `exception-translations` |
| **DataUpdateCoordinator "Retry-After"** | 2025.11 (blog 2025-11-17) | Le coordinator respecte un `retry_after` renvoyé par l'API cloud lors d'un throttle — utile pour l'API cloud Dreame |
| **Coordinator retriggering** | 2025.10 (blog 2025-10-05) | Permet de forcer un refresh coordonné depuis un event MQTT push sans dupliquer la logique |
| **Terminologie "services → actions"**, icônes via `icons.json` (depuis 2024.2, schéma étendu 2024-08-27) | 2024.7 (services→actions), 2024.2/2024.8 (icons.json) | `services.yaml` reste le nom de fichier technique mais toute la doc/UX parle d'"actions" ; les icônes d'entités/services doivent passer par `icons.json` plutôt que la property `icon` codée en dur |
| **`prek`** remplace `pre-commit` comme runner de hooks | 2026.1 (blog 2026-01-13) | Déjà fait côté ce repo (commit `81794d8` "adopt prek as the pre-commit hook runner", `f4ee2d5` "migrate to prek-only") — rien à faire |
| **Quality Scale : migration de checks hassfest → pylint** (`parallel-updates`, `diagnostics`, `config-entry-unloading`, `reauthentication-flow`) | 2026.6 | Pour du custom (hors core), hassfest/pylint core ne s'appliquent pas directement, mais les mêmes règles de style doivent être répliquées manuellement / via `quality_scale.yaml` en checklist |

---

## 4. Règles Quality Scale du jour (liste complète des identifiants, par palier)

Source : https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/ (état au 2026-07-02)

### 🥉 Bronze
1. `action-setup` — Les actions de service sont enregistrées dans `async_setup`
2. `appropriate-polling` — Intervalle de polling approprié (si intégration à polling)
3. `brands` — Assets de branding disponibles
4. `common-modules` — Patterns communs dans des modules communs
5. `config-flow-test-coverage` — Couverture de test complète du config flow
6. `config-flow` — Configurable via l'UI
7. `dependency-transparency` — Transparence des dépendances
8. `docs-actions` — Doc décrit les actions de service fournies
9. `docs-triggers` — Doc décrit les triggers fournis
10. `docs-conditions` — Doc décrit les conditions fournies
11. `docs-high-level-description` — Description haut niveau de la marque/produit/service
12. `docs-installation-instructions` — Instructions d'installation pas-à-pas + prérequis
13. `docs-removal-instructions` — Instructions de suppression
14. `entity-event-setup` — Abonnement aux events dans les bonnes méthodes de cycle de vie
15. `entity-unique-id` — Entités avec unique ID
16. `has-entity-name` — Entités avec `has_entity_name = True`
17. `runtime-data` — Usage de `ConfigEntry.runtime_data`
18. `test-before-configure` — Test de connexion dans le config flow
19. `test-before-setup` — Vérification à l'init que le setup est possible
20. `unique-config-entry` — Empêche le double setup du même device/service

### 🥈 Silver
1. `action-exceptions` — Les actions lèvent des exceptions en cas d'échec
2. `config-entry-unloading` — Support du unload du config entry
3. `docs-configuration-parameters` — Doc décrit toutes les options de config
4. `docs-installation-parameters` — Doc décrit tous les paramètres d'installation
5. `entity-unavailable` — Entité marquée indisponible si pertinent
6. `integration-owner` — Un owner d'intégration désigné
7. `log-when-unavailable` — Log une fois à la perte de connexion, une fois à la reconnexion
8. `parallel-updates` — `PARALLEL_UPDATES` spécifié
9. `reauthentication-flow` — Réauthentification disponible via l'UI
10. `test-coverage` — >95% de couverture de test sur tous les modules

### 🥇 Gold
1. `devices` — Crée des devices
2. `diagnostics` — Implémente les diagnostics
3. `discovery-update-info` — Utilise les infos de discovery pour mettre à jour les infos réseau
4. `discovery` — Devices découvrables
5. `docs-data-update` — Doc décrit comment les données sont mises à jour
6. `docs-examples` — Doc fournit des exemples d'automatisation
7. `docs-known-limitations` — Doc décrit les limitations connues
8. `docs-supported-devices` — Doc décrit devices supportés/non supportés
9. `docs-supported-functions` — Doc décrit fonctionnalités/entités supportées
10. `docs-troubleshooting` — Doc fournit infos de dépannage
11. `docs-use-cases` — Doc décrit les cas d'usage
12. `dynamic-devices` — Devices ajoutés après le setup initial de l'intégration
13. `entity-category` — Entités avec `EntityCategory` approprié
14. `entity-device-class` — Entités avec device class quand possible
15. `entity-disabled-by-default` — Entités peu utiles/bruyantes désactivées par défaut
16. `entity-translations` — Noms d'entités traduits
17. `exception-translations` — Messages d'exception traduisibles
18. `icon-translations` — Icônes via traductions (`icons.json`)
19. `reconfiguration-flow` — Flow de reconfiguration disponible
20. `repair-issues` — Repair issues / repair flows utilisés quand une intervention est nécessaire
21. `stale-devices` — Suppression des devices obsolètes

### 🏆 Platinum
1. `async-dependency` — La dépendance externe est async
2. `inject-websession` — La dépendance supporte l'injection d'une websession
3. `strict-typing` — Typage strict (mypy)

**Point critique pour ce refactor** : `paho-mqtt` (thread-based, non-asyncio natif) et `requests` (100%
sync) rendent `async-dependency` et `inject-websession` **non atteignables tels quels**. Pour viser
Platinum il faudrait soit un wrapper asyncio-natif autour de paho-mqtt (ou migrer vers une lib MQTT async
type `aiomqtt`), soit au minimum isoler tous les appels bloquants dans l'executor et documenter
l'exemption dans `quality_scale.yaml` avec justification. `quality_scale: gold` déclaré dans le manifest
actuel est donc probablement **non tenable en l'état** tant que `requests` reste sur le chemin critique
(cf. règle Gold implicite de stabilité/robustesse — pas listée nommément mais couverte par
`action-exceptions`, `entity-unavailable`, `log-when-unavailable`).

---

## 5. Points spécifiques vacuum / camera / mqtt / requests-sync

### Vacuum
- **Obligatoire dès maintenant** (fenêtres déjà expirées) : propriété `activity` retournant un
  `VacuumActivity` (pas `state`), et `VacuumEntityFeature` pour les feature flags. Si le fork n'a pas
  encore été migré, c'est la priorité n°1 — l'entité vacuum est probablement cassée ou en fallback dégradé
  sur toute install HA ≥ 2026.1.
- `battery_level`/`battery_icon` sur l'entité vacuum : à sortir vers un `sensor` `device_class: battery`
  dédié + `binary_sensor` `device_class: charging` avant **2026.8** (dans ~1 mois). C'est un changement
  d'UX visible (l'indicateur batterie quitte la carte vacuum pour devenir une entité séparée) — à
  documenter dans le changelog utilisateur du fork.
- Pas de nouvelle contrainte identifiée sur `map_data`/coordonnées de carte, actions `clean_zone`/`clean_segment`/`go_to` au-delà du pattern générique "services → actions" et `async_register_platform_entity_service`.

### Camera
- Si `dreame_vacuum` expose un flux caméra embarquée (certains robots ont une caméra), toute logique
  WebRTC doit être sur `async_handle_async_webrtc_offer` / `async_register_webrtc_provider`
  (les anciennes méthodes sont retirées depuis 2025.6).
- Le rendu de carte (pillow/numpy) via `camera.Image` / `async_camera_image` doit rester **dans
  l'executor** (`hass.async_add_executor_job`) — Pillow/numpy sont CPU-bound et synchrones, donc jamais
  d'appel direct dans une coroutine du event loop.

### MQTT (paho-mqtt)
- Vérifier la version de `paho-mqtt` épinglée dans `manifest.json` → `requirements`. Si `< 2.0`,
  planifier la migration `CallbackAPIVersion.VERSION1` → `VERSION2` (retrait prévu en paho-mqtt 3.0,
  côté lib externe, pas HA).
- Paho-mqtt fonctionne avec sa propre boucle réseau en thread — s'assurer que tous les callbacks
  (`on_message`, `on_connect`, etc.) qui touchent l'état HA passent bien par
  `hass.loop.call_soon_threadsafe(...)` ou `async_add_executor_job`, jamais d'appel direct à des
  coroutines/`hass.states` depuis le thread paho.
- C'est ce pattern (dépendance non-async) qui bloque structurellement la règle Platinum
  `async-dependency` (cf. §4).

### `requests` (sync)
- Incompatible avec les bonnes pratiques asyncio de HA depuis toujours, mais la détection des appels
  bloquants dans l'event loop s'est **renforcée depuis 2024.7** (logs `Detected blocking call to X
  inside the event loop by custom integration 'dreame_vacuum'` visibles par tous les utilisateurs dans
  leurs logs HA — mauvais pour la réputation/HACS).
- Recommandation minimale immédiate : englober tout appel `requests.*` dans
  `await hass.async_add_executor_job(...)`.
- Recommandation cible : migrer vers `aiohttp` (déjà une dépendance systématique de HA, réutilisable via
  `aiohttp_client.async_get_clientsession(hass)`) ou `httpx.AsyncClient`, ce qui débloque aussi
  `inject-websession` (Platinum) et simplifie les tests (mock de session).

### Divers pertinents (hub / multi-device)
- `integration_type: hub` + potentiellement plusieurs robots par compte cloud → évaluer **Config
  Subentries** (2025.2) pour modéliser chaque robot, au lieu d'un unique config entry monolithique.
- `hacs.json` : `homeassistant >= 2023.6.0` est très en retard par rapport à toutes les API listées
  ci-dessus (runtime_data 2024.4, coordinator `_async_setup` 2024.8, reauth/reconfigure helpers
  2024.10-11, OptionsFlow natif 2024.11, subentries 2025.2, service registration API 2025.9). Si le
  refactor adopte ces patterns, il faut remonter le minimum HA en conséquence (au minimum
  2024.11/2025.1, idéalement une version 2025.x-2026.x récente) — sinon le fork ne sera plus installable
  correctement sur les anciennes versions déclarées compatibles.

---

## 6. Sources (URLs)

Developer blog (index + pagination) :
- https://developers.home-assistant.io/blog/
- https://developers.home-assistant.io/blog/page/2 … page/11

Quality Scale :
- https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/
- https://developers.home-assistant.io/blog/2024/11/20/integration-quality-scale
- https://www.home-assistant.io/docs/quality_scale/
- https://github.com/home-assistant/architecture/blob/master/adr/0022-integration-quality-scale.md

Vacuum :
- https://developers.home-assistant.io/blog/2024/12/08/new-vacuum-state-property
- https://developers.home-assistant.io/blog/2024/09/23/feature-flag-constants-vacuum-deprecation
- https://developers.home-assistant.io/blog/2025/07/02/vacuum-battery-properties-deprecated

Camera :
- https://developers.home-assistant.io/blog/2024/11/26/camera-deprecations

Config flow / OptionsFlow / reauth-reconfigure :
- https://developers.home-assistant.io/blog/2024/11/12/options-flow
- https://developers.home-assistant.io/blog/2024/11/04/reauth-reconfigure-entry-id
- https://developers.home-assistant.io/blog/2024/10/21/reauth-reconfigure-helpers
- https://developers.home-assistant.io/blog/2025/02/16/config-subentries
- https://developers.home-assistant.io/blog/2025/03/24/config-subentry-flow-changes
- https://developers.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods
- https://developers.home-assistant.io/blog/2026/05/26/advanced-mode-config-flow-deprecation

Coordinator / ConfigEntry :
- https://developers.home-assistant.io/blog/2024/04/30/store-runtime-data-inside-config-entry/
- https://developers.home-assistant.io/blog/2024/08/05/coordinator_async_setup
- https://developers.home-assistant.io/blog/2025/10/05/coordinator-retrigger
- https://developers.home-assistant.io/blog/2025/11/17/retry-after-update-failed

Services/actions, traductions, icônes :
- https://developers.home-assistant.io/blog/2024/07/16/service-actions
- https://developers.home-assistant.io/blog/2024/01/19/icon-translations/
- https://developers.home-assistant.io/blog/2024/08/27/changed-icon-translations-schema
- https://developers.home-assistant.io/blog/2024/08/27/entity-service-schema-validation
- https://developers.home-assistant.io/blog/2025/09/25/entity-services-api-changes
- https://developers.home-assistant.io/blog/2025/11/27/service-translation-placeholders

Blocking calls / async best practices :
- https://developers.home-assistant.io/docs/asyncio_blocking_operations/
- https://community.home-assistant.io/t/blocking-call-inside-event-loop/575796

MQTT / paho-mqtt :
- https://github.com/home-assistant/core/pull/137613 (Upgrade paho-mqtt API to v2)
- https://pypi.org/project/paho-mqtt/

Outillage dev :
- https://developers.home-assistant.io/blog/2026/01/13/replace-pre-commit-with-prek

Release notes HA (stable) :
- https://www.home-assistant.io/blog/2026/07/01/release-20267/ (2026.7, courante)
- https://www.home-assistant.io/blog/2026/06/03/release-20266/ (2026.6)
- https://www.home-assistant.io/blog/2026/05/06/release-20265/ (2026.5)
- https://www.home-assistant.io/changelogs/core-2026.6/
- https://www.home-assistant.io/changelogs/core-2026.5/
