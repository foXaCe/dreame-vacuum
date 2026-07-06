# Home Assistant backend — état de l'art (2026-07-06)

Sources : `developers.home-assistant.io/blog`, `developers.home-assistant.io/docs/core/integration-quality-scale/rules`, `home-assistant.io/blog` (release notes), `home-assistant/core` sur GitHub (branche `dev` et tag `2026.7.1`). Toutes les dates/versions citées sont vérifiées sur les billets officiels ou le code source de core.

Contexte cible : `dreame_vacuum`, integration_type `hub`, iot_class `cloud_push`, plateformes `vacuum`, `camera`, `binary_sensor`, `button`, `number`, `select`, `sensor`, `switch`, `time`. Environnement de dev local pinné sur **HA Core 2026.2.3 / Python 3.13.2** — soit 5 releases mineures de retard sur le courant.

---

## 1. Version HA courante + Python minimal

- **Version stable courante : Home Assistant Core 2026.7** (billet "2026.7: Automations that speak your language", publié le 1ᵉʳ juillet 2026, patch en cours `2026.7.1` du 3 juillet 2026).
- Cycle récent : 2026.5 (6 mai) → 2026.6 (3 juin) → 2026.7 (1ᵉʳ juillet). Une release mineure par mois, patches hebdomadaires (visée le vendredi).
- **Python minimal requis par HA Core 2026.7 : `>=3.14.2`** (`pyproject.toml` du tag `2026.7.1` : `requires-python = ">=3.14.2"` ; `homeassistant/const.py` : `REQUIRED_PYTHON_VER = (3, 14, 2)`).
- Rappel : l'environnement de dev local de l'intégration est encore sur HA 2026.2 (Python 3.13.2 minimum à cette époque) — l'écart de 5 mois de core couvre plusieurs dépréciations/durcissements listés ci-dessous.

---

## 2. Dépréciations ACTIVES à corriger (avec version de retrait prévue)

Ces dépréciations sont **encore en période de grâce** aujourd'hui (2026-07-06) mais ont une date de retrait annoncée — à traiter avant l'échéance.

| Dépréciation | Déprécié depuis | Retrait prévu | Détail |
|---|---|---|---|
| **`battery_level` / `battery_icon`** overridés directement sur `StateVacuumEntity` | 2025.8 | **2026.8** (~1 mois) | Remplacer par un capteur séparé `device_class: battery` (+ éventuellement un binary_sensor `charging`). Exemption : plateforme `template`. Source : code `homeassistant/components/vacuum/__init__.py` (`breaks_in_ha_version="2026.8"`), billet 2025-07-02. |
| Feature flag `BATTERY` sur `VacuumEntityFeature` | idem | 2026.8 | Le simple fait de déclarer `VacuumEntityFeature.BATTERY` déclenche un `report_usage` déprécié dans `state_attributes` (voir `_report_deprecated_battery_feature`). À retirer en même temps que les propriétés battery. |
| `hass` en argument des helpers de service (`verify_domain_control`, `extract_entity_ids`, `async_extract_entities`, `async_extract_entity_ids`, `async_extract_config_entry_ids`) | 2025.1 (PR core #133062) | **2026.10** | `ServiceCall.hass` existe désormais ; supprimer le paramètre `hass` des appels/décorateurs. Billet 2025-09-22. |
| `DeviceEntry.suggested_area` (lecture) | 2025.8 (PR core #149730) | **2026.9** | Utiliser `DeviceEntry.area_id`. `suggested_area` en écriture dans `DeviceInfo`/`async_get_or_create` reste supporté pour l'instant. |
| Config entry listener **combiné** avec les méthodes de reload dans un config flow (`async_update_reload_and_abort`, `_abort_if_unique_id_configured(reload_on_update=True)` + un listener enregistré par ailleurs) | 2026.6 | **2026.12** (erreur dure) | Solutions : retirer le listener et ne garder que le reload du config flow, ou `async_update_and_abort()`, ou `reload_on_update=False`. Billet 2026-05-07. |
| `FlowHandler.show_advanced_options` (mode avancé) | 2026.6 | **2027.6** | Retourne désormais toujours `True`. Remplacer toute logique conditionnée par l'advanced mode par des sections UI groupées. Billet 2026-05-26. |
| Entity ID avec domaine non concordant (`entity_id` fixé manuellement avec un préfixe ≠ domaine de la plateforme) | 2026.4 | **2027.5** | Ne plus fixer `entity_id` manuellement ; laisser HA le générer. Billet 2026-04-07. |
| `home_assistant_start` flag de `async_initialize_triggers` | 2026.6 (30/06) | **2027.8** | Sans effet depuis 2026.6 ; ne concerne que les intégrations qui définissent des triggers personnalisés. |
| `TemperatureConverter.convert_interval` | 2025.11 | non annoncé | Remplacer par `TemperatureDeltaConverter.convert`. Non applicable si aucune conversion d'intervalle de température n'est faite (peu probable pour un aspirateur, sauf capteur de température de batterie). |
| Ancien style condition/script (callable direct plutôt que classes `async_check`/`async_unload`) | 2026.5 | **2027.1** | Ne concerne que les intégrations qui *fournissent ou instancient* des `Condition`/`Script` personnalisés (pas le cas des intégrations "device" classiques). |

### Déjà dans le passé — dates de retrait dépassées (si le code n'a pas été mis à jour, il est **déjà cassé** sur 2026.7)

| Élément retiré | Retrait effectif | Remplacement |
|---|---|---|
| `@bind_hass`, `hass.components` | **2025.3** (repoussé depuis 2024.9) | Import direct + passage explicite de `hass` |
| `hass.helpers` | **2025.5** (repoussé depuis 2024.11) | Import direct depuis `homeassistant.helpers.*` |
| `async_add_hass_job` | 2025.5 | `async_run_hass_job` |
| `async_run_job` / `async_add_job` (async) | 2025.4 | `hass.async_create_task` / `entry.async_create_background_task` / `async_add_executor_job` |
| `hass.config_entries.async_forward_entry_setup` (singulier) | 2025.6 | `async_forward_entry_setups` (pluriel, doit être `await`-é) |
| Camera : `frontend_stream_type`, `async_handle_web_rtc_offer`, `async_register_rtsp_to_web_rtc_provider` | 2025.6 | `async_handle_async_webrtc_offer`, `async_register_webrtc_provider`, websocket `camera/capabilities` |
| Constantes de feature flag `SUPPORT_*` sur `StateVacuumEntity` (pré-`VacuumEntityFeature`) | **2025.10** | `VacuumEntityFeature` (IntFlag) |
| Constantes d'état caméra (`STATE_IDLE`, `STATE_RECORDING`, etc.) | **2025.10** | `CameraState` (StrEnum) |
| Schéma vol. personnalisé sur un entity service sans passer par `cv.make_entity_service_schema` | **2025.10** (dur) | Toujours dériver le schéma de `cv.make_entity_service_schema` |
| `Template.hass` non fourni à la création manuelle d'un objet `Template` | **2025.10** (dur) | Toujours passer `hass` au constructeur `Template(...)` |
| Constantes `STATE_*` de `StateVacuumEntity` (état brut au lieu de l'enum) | **2026.1** | `VacuumActivity` (StrEnum) — cf. §6 |
| Import `Dhcp/Ssdp/Usb/ZeroconfServiceInfo` depuis `homeassistant.components.*` | **2026.2** | `homeassistant.helpers.service_info.{dhcp,ssdp,usb,zeroconf}` |
| `OptionsFlowWithConfigEntry` argument `config_entry` au constructeur / attribut `self.config_entry` fixé manuellement | ~2025.12 | `OptionsFlow.config_entry` fourni nativement par la classe parente |
| Reauth/reconfigure flow démarré sans lien à un config entry | 2025.12 | `entry.async_start_reauth(hass)` / lever `ConfigEntryAuthFailed` |
| `homeassistant.backports.enum.StrEnum`, `backports.functools.cached_property`, alias `typing.ContextType/EventType/HomeAssistantType/ServiceCallType` | déprécié 2024.4 (HA ne supporte plus que Python ≥3.13/3.14) | `enum.StrEnum`, `functools.cached_property`, `homeassistant.core.{Context,Event,HomeAssistant,ServiceCall}` |

---

## 3. Nouvelles API à adopter

### `ConfigEntry.runtime_data` (depuis 2024.4, Bronze `runtime-data`)
```python
type MyConfigEntry = ConfigEntry[MyData]

@dataclass
class MyData:
    client: MyClient

async def async_setup_entry(hass: HomeAssistant, entry: MyConfigEntry) -> bool:
    entry.runtime_data = MyData(client=MyClient(...))
    return True
```
Remplace `hass.data[DOMAIN][entry.entry_id]`. Nettoyage automatique au unload.

### Coordinator `_async_setup` (depuis 2024.8)
```python
class MyCoordinator(DataUpdateCoordinator[MyDataType]):
    async def _async_setup(self) -> None:
        """Appelé une seule fois avant le premier refresh (via async_config_entry_first_refresh)."""
        self.prereq_data = await self.my_api.get_initial_data()
```
Gère nativement `ConfigEntryError` / `ConfigEntryAuthFailed`.

### Coordinator `retry_after` (depuis 2025.11)
```python
raise UpdateFailed(retry_after=60) from err   # ex: HTTP 429 / Retry-After
```
Retarde le prochain refresh de N secondes puis reprend la cadence normale. Ignoré pendant `async_config_entry_first_refresh` (c'est `ConfigEntryNotReady` qui gère le retry initial).

### Coordinator : re-déclenchement pendant une update en cours (depuis 2025.10)
Comportement automatique — une demande de refresh reçue pendant une update en cours est désormais mise en file au lieu d'être ignorée. Permet de déclencher un refresh *depuis* `_async_update_data` (ex. reconnexion après perte de connexion cloud).

### Entity services enregistrés depuis `async_setup` (depuis 2025.9)
```python
# platform.py, dans async_setup_entry -> ne plus faire platform.async_register_entity_service()
# component-level : dans le module vacuum/__init__.py de core (async_setup)
service.async_register_platform_entity_service(...)
```
Objectif : l'enregistrement des services ne dépend plus du setup de la plateforme.
*(Constaté : `dreame_vacuum/services.py` utilise déjà `async_register_platform_entity_service` — conforme.)*

### Reauth / reconfigure helpers modernes (depuis 2024.10-11)
- `self._get_reauth_entry()` / `self._get_reconfigure_entry()`
- `self._abort_if_unique_id_mismatch()`
- `entry.async_start_reauth(hass)` pour déclencher un reauth hors config flow
- `async_update_reload_and_abort(..., data_updates=...)` plutôt que `data=...`

### OptionsFlow simplifié (depuis 2024.11, Bronze indirect)
```python
class OptionsFlowHandler(OptionsFlow):
    def __init__(self) -> None:
        self._conf_app_id: str | None = None
    # self.config_entry est fourni par la classe parente, ne plus le stocker soi-même
```

### Config entry unload simplifié (depuis 2025.2/2025.3)
```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not hass.config_entries.async_loaded_entries(DOMAIN):
        # dernier entry déchargé : libérer les ressources partagées
        ...
```
Nouveaux états `ConfigEntryState.UNLOAD_IN_PROGRESS` et `FAILED_UNLOAD` (si `async_unload_entry` retourne `False`).

### Config subentries (depuis 2025.2)
Pour un `integration_type: hub` avec plusieurs comptes/appareils enfants, les *config subentries* (créées/éditées via des subentry flows) sont le pattern recommandé plutôt qu'une ConfigEntry par appareil ou un flou dans `options`.

### `HassKey` / `HassEntryKey` (depuis 2024.5)
```python
MY_KEY: HassKey["MyData"] = HassKey(DOMAIN)
hass.data[MY_KEY] = MyData(...)   # type inféré par mypy
```
Uniquement utile pour des données **globales** partagées entre entries ; pour les données par-entry, préférer `runtime_data`.

### OAuth2 helper — nouvelles exceptions (depuis 2026.3, si applicable)
`OAuth2TokenRequestTransientError` / `OAuth2TokenRequestReauthError` / `OAuth2TokenRequestError` remontent proprement dans le DataUpdateCoordinator (`ConfigEntryAuthFailed` ou `UpdateFailed` selon le cas). **Non applicable** si l'authentification cloud Dreame/Xiaomi n'utilise pas le helper OAuth2 générique de HA (authentification par identifiants propriétaires).

### Traductions de service actions — placeholders (depuis 2025.11)
Les actions de service personnalisées peuvent désormais fournir des `description_placeholders` (ex. pour insérer une URL dynamique dans la doc traduite d'une action).

### Boutons "Identify" → catégorie diagnostic (depuis 2025.11, obligatoire)
Tout bouton avec `device_class: identify` doit avoir `entity_category: diagnostic`.

---

## 4. Règles Quality Scale (état courant, page mise à jour le 21/05/2025)

**Total : 54 règles** — Bronze 20, Silver 10, Gold 21, Platinum 3.

### Bronze (20)
- `action-setup` — Les actions de service sont enregistrées dans `async_setup`
- `appropriate-polling` — Intervalle de polling approprié pour une intégration à polling
- `brands` — Assets de branding disponibles
- `common-modules` — Regrouper les patterns communs dans des modules dédiés
- `config-flow-test-coverage` — Couverture de tests complète du config flow
- `config-flow` — L'intégration doit pouvoir être configurée via l'UI
- `dependency-transparency` — Transparence de la dépendance (source buildable/auditable)
- `docs-actions` — La doc décrit les actions de service fournies
- `docs-triggers` — La doc décrit les triggers fournis
- `docs-conditions` — La doc décrit les conditions fournies
- `docs-high-level-description` — Description haut niveau de la marque/produit/service
- `docs-installation-instructions` — Instructions d'installation pas-à-pas
- `docs-removal-instructions` — Instructions de désinstallation
- `entity-event-setup` — Abonnement aux events dans le bon cycle de vie
- `entity-unique-id` — Les entités ont un unique ID
- `has-entity-name` — Les entités utilisent `has_entity_name = True`
- `runtime-data` — Utilisation de `ConfigEntry.runtime_data`
- `test-before-configure` — Test de connexion dans le config flow
- `test-before-setup` — Vérification de bon fonctionnement à l'initialisation
- `unique-config-entry` — Empêcher la configuration en double d'un même appareil/service

### Silver (10)
- `action-exceptions` — Les actions lèvent des exceptions en cas d'échec
- `config-entry-unloading` — Support du déchargement de la config entry
- `docs-configuration-parameters` — Doc de toutes les options de configuration
- `docs-installation-parameters` — Doc de tous les paramètres d'installation
- `entity-unavailable` — Marquer une entité indisponible si pertinent
- `integration-owner` — L'intégration a un owner (codeowner)
- `log-when-unavailable` — Log unique lors de la perte/reprise de connexion
- `parallel-updates` — `PARALLEL_UPDATES` spécifié
- `reauthentication-flow` — Réauthentification disponible via l'UI
- `test-coverage` — >95% de couverture de tests sur tous les modules

### Gold (21)
- `devices` — L'intégration crée des devices
- `diagnostics` — Implémente les diagnostics
- `discovery-update-info` — Mise à jour des infos réseau via discovery
- `discovery` — Les appareils peuvent être découverts
- `docs-data-update` — Doc explique comment les données sont mises à jour
- `docs-examples` — Exemples d'automatisation dans la doc
- `docs-known-limitations` — Doc des limitations connues (≠ bugs)
- `docs-supported-devices` — Doc des appareils supportés/non supportés
- `docs-supported-functions` — Doc des fonctionnalités/entités/plateformes supportées
- `docs-troubleshooting` — Doc de dépannage
- `docs-use-cases` — Doc des cas d'usage
- `dynamic-devices` — Appareils ajoutés après le setup initial
- `entity-category` — `EntityCategory` approprié sur les entités
- `entity-device-class` — Device class utilisée quand pertinent
- `entity-disabled-by-default` — Désactivation par défaut des entités peu utiles/bruyantes
- `entity-translations` — Noms d'entités traduits
- `exception-translations` — Messages d'exception traduisibles
- `icon-translations` — Icônes traduites
- `reconfiguration-flow` — Flow de reconfiguration disponible
- `repair-issues` — Repair issues/flows utilisés quand une intervention est nécessaire
- `stale-devices` — Suppression des devices obsolètes

### Platinum (3)
- `async-dependency` — La dépendance externe est asynchrone
- `inject-websession` — La dépendance supporte l'injection d'une websession HA
- `strict-typing` — Typage strict (mypy)

*Note : le manifest de `dreame_vacuum` déclare déjà `"quality_scale": "gold"` et le repo contient `quality_scale.yaml`, `repairs.py`, `system_health.py`, `diagnostics.py`, `recorder.py`, `logbook.py` — une vérification ligne-à-ligne des 51 règles Bronze→Gold (l'intégration dépend de `requests`/`paho-mqtt`/`python-miio`, tous **synchrones**, donc Platinum `async-dependency`/`inject-websession` sont structurellement hors de portée sans réécriture du client) est du ressort de la phase d'audit, pas de cette recherche.*

---

## 5. Changements backward-incompatible récents (2026.5 / 2026.6 / 2026.7) pertinents vacuum/camera/cloud_push

### 2026.5
- Nouvelle plateforme entity **Infrared** et **Radio Frequency** (non applicable).
- Suppression des triggers/conditions Person/Device Tracker "entered home"/"left home"/"is home" (remplacement cross-domaine à venir) — non applicable à `dreame_vacuum`.
- **Rien de spécifique vacuum/camera en backward-incompatible**, mais gros ajout *feature* : cf. §6.

### 2026.6
- **Suppression de la syntaxe legacy des `template:` platform-keyed** (`vacuum:`, `sensor:`, etc. sous forme d'ancienne syntaxe de plateforme) — dépréciée 2025.12, retirée 2026.6. Concerne les utilisateurs de `template` vacuum, pas `dreame_vacuum` directement, mais peut affecter des exemples de doc/blueprint fournis avec l'intégration.
- Mode de scan Bluetooth par défaut passé à `Auto` (Bluetooth/ESPHome/Shelly) — non applicable (pas de Bluetooth dans `dreame_vacuum`).

### 2026.7
- **Renommage de triggers/conditions "purpose-specific"**, dont **`vacuum.docked` → `vacuum.returned_to_dock`** — impact uniquement les automatisations utilisateur qui utilisaient l'ancien trigger nommé, pas le code de l'intégration elle-même (mais à mentionner dans le changelog/doc utilisateur si `dreame_vacuum` documentait ce trigger).
- Suppression de l'attribut `requires_api_password` de l'annonce zeroconf/mDNS (`_home-assistant._tcp`) — non applicable.
- Rien de plus impactant côté vacuum/camera cette release.

### Fonctionnalité majeure (pas un breaking change, mais un ajout d'API à fort impact) : **Clean by area / segments** — landé en HA Core **2026.3** (PR core [#149315](https://github.com/home-assistant/core/pull/149315), mergée le 18/02/2026), exposé côté UI dans **2026.5** ("A modern more-info dialog for vacuums and lawn mowers")
Voir détail complet en §6 — c'est le changement le plus significatif pour une intégration vacuum avec cleaning par pièce/segment comme `dreame_vacuum`.

---

## 6. Points spécifiques par plateforme

### Vacuum (`StateVacuumEntity`)

- **`VacuumActivity` (StrEnum)** est l'API état officielle depuis 2025.1, obligatoire depuis 2026.1 (les anciennes constantes d'état sont retirées). Valeurs : `CLEANING`, `DOCKED`, `IDLE`, `PAUSED`, `RETURNING`, `ERROR`.
  ```python
  from homeassistant.components.vacuum import VacuumActivity

  @property
  def activity(self) -> VacuumActivity | None:
      return VacuumActivity.CLEANING if self.device.is_cleaning() else VacuumActivity.DOCKED
  ```
- **`battery_level`/`battery_icon`** : dépréciés depuis 2025.8, cassent en **2026.8**. Migrer vers un `sensor.battery` séparé lié au même device (+ éventuellement `binary_sensor` charging). Ne plus déclarer `VacuumEntityFeature.BATTERY`.
- **Nouvelle fonctionnalité core majeure : "Clean by area"** (`VacuumEntityFeature.CLEAN_AREA = 16384`, code source `homeassistant/components/vacuum/__init__.py` sur `dev`) :
  - Nouvelle méthode à implémenter : `async def async_get_segments(self) -> list[Segment]` — retourne la liste des segments/pièces nettoyables (`Segment(id, name, group=None)`, dataclass `slots=True`).
  - Nouvelles méthodes : `clean_segments(self, segment_ids: list[str], **kwargs)` (sync) / `async_clean_segments(...)` (async, wrapper par défaut via executor).
  - Nouveau service core **`vacuum.clean_area`** (remplace le besoin d'un service `send_command`/`clean_segment` custom) : prend `cleaning_area_id` (liste d'*area_id* HA), résout via `registry_entry.options["vacuum"]["area_mapping"]` (mapping zone HA → segment IDs, configuré côté UI/frontend) puis appelle `async_clean_segments` pour chaque entité concernée.
  - `last_seen_segments` (property) + `async_create_segments_issue()` : à appeler quand les segments rapportés par l'aspirateur changent par rapport au dernier mapping enregistré → crée une repair issue `segments_changed` que le frontend résout en réaffichant le dialogue de mapping.
  - Ce mécanisme alimente directement le nouveau **more-info dialog "Clean by area"** (2026.5) et l'action Google Assistant "nettoyer une pièce spécifique" (2026.7).
  - **Constat sur le repo actuel** : `custom_components/dreame_vacuum/vacuum.py` implémente déjà `async_get_segments`, `async_clean_segments` et référence `CLEAN_AREA_ENTITY_FEATURE` via `getattr(VacuumEntityFeature, "CLEAN_AREA", 0)` (fallback pour compat HA < 2026.3) — l'adoption semble déjà largement faite ; à vérifier lors de l'audit : présence de `async_create_segments_issue()` pour la gestion du repair issue `segments_changed`.
- Le renommage automation-trigger `vacuum.docked` → `vacuum.returned_to_dock` (2026.7) est un changement de clé de trigger user-facing, sans impact code.
- `VacuumEntityFeature.TURN_ON/TURN_OFF/STATUS` restent marqués "Deprecated, not supported by StateVacuumEntity" dans le code (vestiges de l'ancien modèle `VacuumEntity` non-state) — ne pas les utiliser.

### Camera

- Dépréciations 2024.11/2024.12 (retirées 2025.6) : `frontend_stream_type`, `async_handle_web_rtc_offer`, `async_register_rtsp_to_web_rtc_provider` → `async_handle_async_webrtc_offer` / `async_register_webrtc_provider` / websocket `camera/capabilities`. **Non applicable** si la caméra de `dreame_vacuum` est une caméra "image statique" (rendu de carte) sans flux WebRTC — à confirmer en phase d'audit (constat rapide : `camera.py` ne référence aucune des méthodes WebRTC dépréciées ni actuelles, donc probablement hors sujet).
- Constantes d'état caméra (`STATE_IDLE`, etc.) retirées en 2025.10 → `CameraState` (StrEnum). Impact quasi nul car la propriété `state` de `Camera` n'est normalement pas surchargée directement.
- Aucun changement camera-spécifique dans les release notes 2026.5/6/7.

### Select / Switch / Number

- Aucune dépréciation ou nouvelle API spécifique à ces domaines identifiée dans le blog développeur 2024–2026. Ce sont des plateformes stables ; les seules règles qui s'appliquent sont génériques (Quality Scale : `entity-category`, `entity-translations`, `entity-disabled-by-default`, etc.).
- Rappel général applicable à toutes les entités : boutons `device_class: identify` → `entity_category: diagnostic` obligatoire depuis 2025.11.

### Services (actions)

- **Nouveau pattern d'enregistrement recommandé** (2025.9) : `service.async_register_platform_entity_service(...)` appelé depuis `async_setup` du module de plateforme, plutôt que `platform.async_register_entity_service(...)` appelé pendant le setup de plateforme (évite une dépendance au setup pour le chargement des services). *(déjà utilisé dans `dreame_vacuum/services.py`)*.
- Schéma de service : si un schéma voluptuous **custom** (pas généré par `cv.make_entity_service_schema`) est enregistré, HA lève une erreur dure depuis 2025.10 — toujours dériver de `cv.make_entity_service_schema`.
- `hass` en paramètre des helpers d'extraction de service (`async_extract_entities`, etc.) déprécié depuis 2025.1, retiré en **2026.10** — utiliser `ServiceCall.hass`.
- Terminologie "Services" → "Actions" (2024.8, cosmétique/doc uniquement, aucun impact fonctionnel).
- Nouveau depuis 2025.11 : `description_placeholders` pour les traductions de description d'action (permet d'insérer des valeurs dynamiques dans les messages traduits d'une action de service).

### Notify

- La plateforme `notify` en tant qu'**entity platform** (`notify.send_message`) existe depuis 2024.4/2024.5 (avec support de `title` depuis mai 2024) et est le pattern *recommandé* pour toute nouvelle intégration notify — remplace le vieux service `notify.notify` avec des `targets`. **Non applicable à `dreame_vacuum`** (pas de plateforme `notify` dans ce hub), sauf si une future fonctionnalité de notification (ex. alerte "poubelle pleine"/"erreur") devait être ajoutée : dans ce cas, utiliser directement l'entity platform moderne plutôt qu'un service `notify.notify` legacy.

---

## 7. Hors périmètre pour ce backend (frontend-only, non pertinent)

Le repo `dreame_vacuum` est un backend pur (aucun `www/`, aucune carte Lovelace custom). Les billets suivants du blog développeur concernent uniquement le frontend et **n'ont aucun impact** sur ce projet : `format-entity-name-helper`, `frontend-context-groups-decorators`, `browse-media-source-root-class`, `custom-card-suggestions`, `registering-custom-dashboard-strategies`, `frontend-component-updates-2026.{4,5,6,7}`, `frontend-lazy-context`, `frontend-dialogs`.
