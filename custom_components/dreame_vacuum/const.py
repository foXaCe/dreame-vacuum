"""Constants for Dreame Vacuum integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, Final

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .coordinator import DreameVacuumDataUpdateCoordinator

DOMAIN = "dreame_vacuum"
LOGGER = logging.getLogger(__package__)

# Config entry version — used by both __init__.py and config_flow.py
CONFIG_ENTRY_VERSION: Final = 1


@dataclass(slots=True)
class DreameVacuumRuntimeData:
    """Runtime data stored on the config entry."""

    coordinator: DreameVacuumDataUpdateCoordinator


# Type alias for config entry with runtime data.
# At type-check time we use the subscripted form so ``entry.runtime_data`` is
# resolved to ``DreameVacuumRuntimeData``. At runtime we keep the bare alias,
# because ConfigEntry is not subscriptable on Python 3.11 (HA's min-supported).
if TYPE_CHECKING:
    DreameVacuumConfigEntry = ConfigEntry[DreameVacuumRuntimeData]
else:
    DreameVacuumConfigEntry = ConfigEntry

UNIT_MINUTES: Final = "min"
UNIT_HOURS: Final = "h"
UNIT_PERCENT: Final = "%"
UNIT_DAYS: Final = "d"
UNIT_AREA: Final = "m²"
UNIT_TIMES: Final = "x"

CONF_NOTIFY: Final = "notify"
CONF_COLOR_SCHEME: Final = "color_scheme"
CONF_ICON_SET: Final = "icon_set"
CONF_COUNTRY: Final = "country"
CONF_MAC: Final = "mac"
CONF_DID: Final = "did"
CONF_AUTH_KEY: Final = "auth_key"
CONF_MAP_OBJECTS: Final = "map_objects"
CONF_HIDDEN_MAP_OBJECTS: Final = "hidden_map_objects"
CONF_PREFER_CLOUD: Final = "prefer_cloud"
CONF_LOW_RESOLUTION: Final = "low_resolution"
CONF_SQUARE: Final = "square"
CONF_VECTOR_ROOMS: Final = "vector_rooms"
CONF_MAP_SCALE: Final = "map_scale"
# Render-resolution multiplier for the interactive map PNG (1/2/3). Default 2
# keeps the map crisp under the card's pinch-zoom; memory/CPU grow with the
# square of the factor, so low-memory hosts can drop to 1.
DEFAULT_MAP_SCALE: Final = 2
CONF_ACCOUNT_TYPE: Final = "account_type"
CONF_VERSION: Final = "version"
# TOFU-pinned MQTT broker cert fingerprints, persisted so a Home Assistant
# restart does not silently re-trust whatever certificate is presented at
# reconnect. Shape: {"host:port": "<sha256 hex>"}.
CONF_MQTT_FINGERPRINTS: Final = "mqtt_fingerprints"

CONTENT_TYPE: Final = "image/png"

MAP_OBJECTS: Final = {
    "color": "Room Colors",
    "icon": "Room Icons",
    "name": "Room Names",
    "name_background": "Room Name Background",
    "order": "Room Order",
    "suction_level": "Room Suction Level",
    "water_volume": "Room Water Volume",
    "cleaning_times": "Room Cleaning Times",
    "cleaning_mode": "Room Cleaning Mode",
    "mopping_mode": "Room Mopping Mode",
    "path": "Path",
    "no_go": "No Go Zones",
    "no_mop": "No Mop Zones",
    "virtual_wall": "Virtual Walls",
    "pathway": "Virtual Thresholds",
    "active_area": "Active Areas",
    "active_point": "Active Points",
    "charger": "Charger Icon",
    "robot": "Robot Icon",
    "cleaning_direction": "Cleaning Direction",
    "obstacle": "AI Obstacle",
    "pet": "Pet",
    "carpet": "Carpet Area",
    "material": "Floor Material",
    "low_lying_area": "Low-Lying Areas",
    "furniture": "Furniture",
    "ramp": "Ramp",
    "curtain": "Curtain",
    "cruise_point": "Cruise Points",
}
NOTIFICATION: Final = {
    "cleanup_completed": "Cleanup Completed",
    "consumable": "Consumable",
    "information": "Information",
    "warning": "Warning",
    "error": "Error",
}

NOTIFICATION_TRANSLATIONS: Final = {
    "fr": {
        "cleanup_completed": "Nettoyage terminé",
        "consumable": "Consommable",
        "information": "Information",
        "warning": "Avertissement",
        "error": "Erreur",
    }
}


def get_notification_labels(language: str | None = None) -> dict[str, str]:
    """Get translated notification labels based on language."""
    if language and language in NOTIFICATION_TRANSLATIONS:
        return NOTIFICATION_TRANSLATIONS[language]
    return NOTIFICATION


FAN_SPEED_SILENT: Final = "Silent"
FAN_SPEED_STANDARD: Final = "Standard"
FAN_SPEED_STRONG: Final = "Strong"
FAN_SPEED_TURBO: Final = "Turbo"

SERVICE_CLEAN_ZONE: Final = "vacuum_clean_zone"
SERVICE_CLEAN_SEGMENT: Final = "vacuum_clean_segment"
SERVICE_CLEAN_SPOT: Final = "vacuum_clean_spot"
SERVICE_GOTO: Final = "vacuum_goto"
SERVICE_FOLLOW_PATH: Final = "vacuum_follow_path"
SERVICE_START_SHORTCUT: Final = "vacuum_start_shortcut"
SERVICE_REQUEST_MAP: Final = "vacuum_request_map"
SERVICE_SELECT_MAP: Final = "vacuum_select_map"
SERVICE_DELETE_MAP: Final = "vacuum_delete_map"
SERVICE_SET_RESTRICTED_ZONE: Final = "vacuum_set_restricted_zone"
SERVICE_SET_CARPET_AREA: Final = "vacuum_set_carpet_area"
SERVICE_SET_VIRTUAL_THRESHOLD: Final = "vacuum_set_virtual_threshold"
SERVICE_SET_PREDEFINED_POINTS: Final = "vacuum_set_predefined_points"
SERVICE_MOVE_REMOTE_CONTROL_STEP: Final = "vacuum_remote_control_move_step"
SERVICE_RENAME_MAP: Final = "vacuum_rename_map"
SERVICE_RESTORE_MAP: Final = "vacuum_restore_map"
SERVICE_RESTORE_MAP_FROM_FILE: Final = "vacuum_restore_map_from_file"
SERVICE_BACKUP_MAP: Final = "vacuum_backup_map"
SERVICE_SAVE_TEMPORARY_MAP: Final = "vacuum_save_temporary_map"
SERVICE_DISCARD_TEMPORARY_MAP: Final = "vacuum_discard_temporary_map"
SERVICE_REPLACE_TEMPORARY_MAP: Final = "vacuum_replace_temporary_map"
SERVICE_MERGE_SEGMENTS: Final = "vacuum_merge_segments"
SERVICE_SPLIT_SEGMENTS: Final = "vacuum_split_segments"
SERVICE_RENAME_SEGMENT: Final = "vacuum_rename_segment"
SERVICE_SET_CLEANING_SEQUENCE: Final = "vacuum_set_cleaning_sequence"
SERVICE_SET_CUSTOM_CLEANING: Final = "vacuum_set_custom_cleaning"
SERVICE_SET_CUSTOM_CARPET_CLEANING: Final = "vacuum_set_custom_carpet_cleaning"
SERVICE_INSTALL_VOICE_PACK: Final = "vacuum_install_voice_pack"
SERVICE_RESET_CONSUMABLE: Final = "vacuum_reset_consumable"
SERVICE_RENAME_SHORTCUT: Final = "vacuum_rename_shortcut"
SERVICE_SET_DND_TASK: Final = "vacuum_set_dnd_task"
SERVICE_DELETE_DND_TASK: Final = "vacuum_delete_dnd_task"
SERVICE_SET_OBSTACLE_IGNORE: Final = "vacuum_set_obstacle_ignore"
SERVICE_SET_ROUTER_POSITION: Final = "vacuum_set_router_position"
SERVICE_SET_PROPERTY: Final = "vacuum_set_property"
SERVICE_CALL_ACTION: Final = "vacuum_call_action"
SERVICE_DELETE_SCHEDULE: Final = "vacuum_delete_schedule"
SERVICE_SET_SCHEDULE: Final = "vacuum_set_schedule"

SERVICE_SELECT_NEXT: Final = "select_select_next"
SERVICE_SELECT_PREVIOUS: Final = "select_select_previous"
SERVICE_SELECT_FIRST: Final = "select_select_first"
SERVICE_SELECT_LAST: Final = "select_select_last"

INPUT_ROTATION: Final = "rotation"
INPUT_VELOCITY: Final = "velocity"
INPUT_MAP_ID: Final = "map_id"
INPUT_MAP_NAME: Final = "map_name"
INPUT_FILE_URL: Final = "file_url"
INPUT_RECOVERY_MAP_INDEX: Final = "recovery_map_index"
INPUT_WALL_ARRAY: Final = "walls"
INPUT_ZONE: Final = "zone"
INPUT_ZONE_ARRAY: Final = "zones"
INPUT_CARPET_ARRAY: Final = "carpets"
INPUT_IGNORED_CARPET_ARRAY: Final = "ignored_carpets"
INPUT_VIRTUAL_THRESHOLD_ARRAY: Final = "virtual_thresholds"
INPUT_REPEATS: Final = "repeats"
INPUT_CLEANING_MODE: Final = "cleaning_mode"
INPUT_CUSTOM_MOPPING_ROUTE: Final = "custom_mopping_route"
INPUT_CLEANING_ROUTE: Final = "cleaning_route"
INPUT_WETNESS_LEVEL: Final = "wetness_level"
INPUT_SEGMENTS_ARRAY: Final = "segments"
INPUT_SEGMENT: Final = "segment"
INPUT_SEGMENT_ID: Final = "segment_id"
INPUT_SEGMENT_NAME: Final = "segment_name"
INPUT_LINE: Final = "line"
INPUT_SUCTION_LEVEL: Final = "suction_level"
INPUT_MOP_MODE: Final = "mop_mode"
INPUT_MOP_ARRAY: Final = "no_mops"
INPUT_LANGUAGE_ID: Final = "lang_id"
INPUT_DELAY: Final = "delay"
INPUT_URL: Final = "url"
INPUT_MD5: Final = "md5"
INPUT_SIZE: Final = "size"
INPUT_CLEANING_SEQUENCE: Final = "cleaning_sequence"
INPUT_WATER_VOLUME: Final = "water_volume"
INPUT_CONSUMABLE: Final = "consumable"
INPUT_CYCLE: Final = "cycle"
INPUT_POINTS: Final = "points"
INPUT_SHORTCUT_ID: Final = "shortcut_id"
INPUT_SHORTCUT_NAME: Final = "shortcut_name"
INPUT_TASK_ID: Final = "task_id"
INPUT_ENABLED: Final = "enabled"
INPUT_START: Final = "start"
INPUT_END: Final = "end"
# Raw device weekday bitmask (see docs/dev/dnd-tasks-design.md): the
# bit-to-day mapping is unconfirmed on a live device, so this is never
# decoded into weekday names — only 127 (all 7 bits set) is known to mean
# "all days". Passed through opaquely end-to-end.
INPUT_WEEKDAY_MASK: Final = "weekday_mask"
INPUT_X: Final = "x"
INPUT_Y: Final = "y"
INPUT_OBSTACLE_IGNORED: Final = "obstacle_ignored"
INPUT_KEY: Final = "key"
INPUT_VALUE: Final = "value"
INPUT_ID: Final = "id"
INPUT_TYPE: Final = "type"
INPUT_CARPET_CLEANING: Final = "carpet_cleaning"
INPUT_CARPET_SETTINGS: Final = "carpet_settings"
INPUT_SCHEDULE_ID: Final = "schedule_id"
INPUT_TIME: Final = "time"
INPUT_ONCE: Final = "once"
INPUT_OPTIONS: Final = "options"

CONSUMABLE_MAIN_BRUSH = "main_brush"
CONSUMABLE_SIDE_BRUSH = "side_brush"
CONSUMABLE_FILTER = "filter"
CONSUMABLE_TANK_FILTER = "tank_filter"
CONSUMABLE_SENSOR = "sensor"
CONSUMABLE_MOP_PAD = "mop_pad"
CONSUMABLE_SILVER_ION = "silver_ion"
CONSUMABLE_DETERGENT = "detergent"
CONSUMABLE_SQUEEGEE = "squeegee"
CONSUMABLE_ONBOARD_DIRTY_WATER_TANK = "onboard_dirty_water_tank"
CONSUMABLE_DIRTY_WATER_TANK = "dirty_water_tank"
CONSUMABLE_DEODORIZER = "deodorizer"
CONSUMABLE_WHEEL = "wheel"
CONSUMABLE_SCALE_INHIBITOR = "scale_inhibitor"

NOTIFICATION_ID_DUST_COLLECTION: Final = "dust_collection"
NOTIFICATION_ID_CLEANING_PAUSED: Final = "cleaning_paused"
NOTIFICATION_ID_REPLACE_MAIN_BRUSH: Final = "replace_main_brush"
NOTIFICATION_ID_REPLACE_SIDE_BRUSH: Final = "replace_side_brush"
NOTIFICATION_ID_REPLACE_FILTER: Final = "replace_filter"
NOTIFICATION_ID_REPLACE_TANK_FILTER: Final = "replace_tank_filter"
NOTIFICATION_ID_CLEAN_SENSOR: Final = "clean_sensor"
NOTIFICATION_ID_REPLACE_MOP: Final = "replace_mop"
NOTIFICATION_ID_SILVER_ION: Final = "silver_ion"
NOTIFICATION_ID_REPLACE_DETERGENT: Final = "replace_detergent"
NOTIFICATION_ID_REPLACE_SQUEEGEE: Final = "replace_squeegee"
NOTIFICATION_ID_CLEAN_ONBOARD_DIRTY_WATER_TANK: Final = "clean_onboard_dirty_water_tank"
NOTIFICATION_ID_CLEAN_DIRTY_WATER_TANK: Final = "clean_dirty_water_tank"
NOTIFICATION_ID_REPLACE_DEODORIZER: Final = "replace_deodorizer"
NOTIFICATION_ID_CLEAN_WHEEL: Final = "clean_wheel"
NOTIFICATION_ID_REPLACE_SCALE_INHIBITOR: Final = "replace_scale_inhibitor"
NOTIFICATION_ID_CLEANUP_COMPLETED: Final = "cleanup_completed"
NOTIFICATION_ID_WARNING: Final = "warning"
NOTIFICATION_ID_ERROR: Final = "error"
NOTIFICATION_ID_INFORMATION: Final = "information"
NOTIFICATION_ID_CONSUMABLE: Final = "consumable"
NOTIFICATION_ID_REPLACE_TEMPORARY_MAP: Final = "replace_temporary_map"
NOTIFICATION_ID_LOW_WATER: Final = "low_water"
NOTIFICATION_ID_DRAINAGE_STATUS: Final = "drainage_status"

NOTIFICATION_CLEANUP_COMPLETED: Final = "### Cleanup completed"
NOTIFICATION_DUST_COLLECTION_NOT_PERFORMED: Final = "### Dust collecting (Auto-empty) task not performed\nThe robot will not perform auto-empty tasks during the DND period."
NOTIFICATION_RESUME_CLEANING: Final = "### Resume Cleaning Mode\nThe robot will automatically resume unfinished cleaning tasks after charging its battery to 80%."
NOTIFICATION_RESUME_CLEANING_NOT_PERFORMED: Final = (
    "### The robot is in the DND period\nRobot will resume cleaning after the DND period ends."
)
NOTIFICATION_REPLACE_MAP: Final = "### A new map has been generated\nYou need to save or discard map before using it."
NOTIFICATION_REPLACE_MULTI_MAP: Final = "### A new map has been generated\nMulti-floor maps that can be saved have reached the upper limit. You need to replace or discard map before using it."
NOTIFICATION_DRAINAGE_COMPLETED: Final = "### Drainage completed"
NOTIFICATION_DRAINAGE_FAILED: Final = "### Drainage failed"
NOTIFICATION_MESSAGES_TRANSLATIONS: Final = {
    "fr": {
        "cleanup_completed": "### Nettoyage terminé",
        "dust_collection_not_performed": (
            "### Tâche de vidage automatique non effectuée\nLe robot n'effectuera pas de vidage automatique pendant la période Ne Pas Déranger."
        ),
        "resume_cleaning": (
            "### Mode Reprise du nettoyage\nLe robot reprendra automatiquement les tâches de nettoyage inachevées après avoir chargé sa batterie à 80%."
        ),
        "resume_cleaning_not_performed": (
            "### Le robot est en période Ne Pas Déranger\nLe robot reprendra le nettoyage après la fin de la période Ne Pas Déranger."
        ),
        "resume_cleaning_timer": "\n## Le nettoyage démarrera dans {hour} heure(s) et {minute} minute(s)",
        "replace_map": "### Une nouvelle carte a été générée\nVous devez enregistrer ou supprimer la carte avant de l'utiliser.",
        "replace_multi_map": (
            "### Une nouvelle carte a été générée\nLe nombre maximum de cartes multi-étages pouvant être enregistrées est atteint. Vous devez remplacer ou supprimer une carte avant de l'utiliser."
        ),
        "drainage_completed": "### Vidange terminée",
        "drainage_failed": "### Vidange échouée",
    }
}


def get_notification_message(language: str, key: str, **kwargs: Any) -> str:
    """Get translated notification message based on language."""
    if language and language in NOTIFICATION_MESSAGES_TRANSLATIONS:
        translations = NOTIFICATION_MESSAGES_TRANSLATIONS[language]
        if key in translations:
            message = translations[key]
            if kwargs:
                return message.format(**kwargs)
            return message

    # Fallback to English
    messages = {
        "cleanup_completed": NOTIFICATION_CLEANUP_COMPLETED,
        "dust_collection_not_performed": NOTIFICATION_DUST_COLLECTION_NOT_PERFORMED,
        "resume_cleaning": NOTIFICATION_RESUME_CLEANING,
        "resume_cleaning_not_performed": NOTIFICATION_RESUME_CLEANING_NOT_PERFORMED,
        "resume_cleaning_timer": "\n## Cleaning will start in {hour} hour(s) and {minute} minutes(s)",
        "replace_map": NOTIFICATION_REPLACE_MAP,
        "replace_multi_map": NOTIFICATION_REPLACE_MULTI_MAP,
        "drainage_completed": NOTIFICATION_DRAINAGE_COMPLETED,
        "drainage_failed": NOTIFICATION_DRAINAGE_FAILED,
    }

    if key in messages:
        message = messages[key]
        if kwargs:
            return message.format(**kwargs)
        return message

    return ""


# Translation dictionaries for error descriptions, warnings and consumables
DESCRIPTION_TRANSLATIONS: Final = {
    "fr": {
        # Error descriptions
        "No error": "Aucune erreur",
        "Wheels are suspended": "Les roues sont suspendues",
        "Please reposition the robot and restart.": "Veuillez repositionner le robot et redémarrer.",
        "Cliff sensor error": "Erreur du capteur de chute",
        "Please wipe the cliff sensor and start the cleanup away from the stairs.": "Veuillez essuyer le capteur de chute et démarrer le nettoyage loin des escaliers.",
        "Collision sensor is stuck": "Le capteur de collision est coincé",
        "Please clean and gently tap the collision sensor.": "Veuillez nettoyer et tapoter doucement le capteur de collision.",
        "Robot is tilted": "Le robot est incliné",
        "Please move the robot to a level surface and start again.": "Veuillez déplacer le robot sur une surface plane et redémarrer.",
        "Optical flow sensor error": "Erreur du capteur optique de flux",
        "Please try to restart the vacuum-mop.": "Veuillez essayer de redémarrer l'aspirateur-serpillière.",
        "Dust bin not installed": "Le bac à poussière n'est pas installé",
        "Please install the dust bin and filter.": "Veuillez installer le bac à poussière et le filtre.",
        "Water tank not installed": "Le réservoir d'eau n'est pas installé",
        "Please install the water tank.": "Veuillez installer le réservoir d'eau.",
        "Water tank is empty": "Le réservoir d'eau est vide",
        "Please will up the water tank": "Veuillez remplir le réservoir d'eau",
        "The filter not dry or blocked": "Le filtre n'est pas sec ou est obstrué",
        "Please check whether the filter has dried or needs to be cleaned.": "Veuillez vérifier si le filtre est sec ou doit être nettoyé.",
        "The main brush wrapped": "La brosse principale est entravée",
        "Please remove the main brush and clean its bristles and bearings.": "Veuillez retirer la brosse principale et nettoyer ses poils et ses roulements.",
        # Low water warnings
        "No warning": "Pas d'avertissement",
        "Please check the clean water tank.": "Veuillez vérifier le réservoir d'eau propre.",
        "Please fill the clean water tank.": "Veuillez remplir le réservoir d'eau propre.",
        "The water in the clean water tank is about to be used up. Check and fill the clean water tank promptly.": "L'eau du réservoir d'eau propre est sur le point d'être épuisée. Vérifiez et remplissez le réservoir d'eau propre rapidement.",
        "Mop pad has been cleaned. Detected that the water in the clean water tank is insufficient, please fill the clean water tank and empty the used water tank.": "Le tampon de la serpillière a été nettoyé. Détecté que l'eau dans le réservoir d'eau propre est insuffisante, veuillez remplir le réservoir d'eau propre et vider le réservoir d'eau usée.",
        "Low water level in the clean water tank.": "Niveau d'eau bas dans le réservoir d'eau propre.",
        "Robot has switched to Vacuuming Mode.": "Le robot est passé en mode Aspiration.",
        "About to run out of water": "Sur le point de manquer d'eau",
        "The clean water tank is not installed.": "Le réservoir d'eau propre n'est pas installé.",
        # Consumable descriptions
        "Main brush must be replaced": "La brosse principale doit être remplacée",
        "The main brush is worn out. Please replace it in time and reset the counter.": "La brosse principale est usée. Veuillez la remplacer à temps et réinitialiser le compteur.",
        "Main brush needs to be replaced soon": "La brosse principale doit être remplacée bientôt",
        "The main brush is nearly worn out. Please replace it in time.": "La brosse principale est presque usée. Veuillez la remplacer à temps.",
        "Side brush must be replaced": "La brosse latérale doit être remplacée",
        "The side brush is worn out. Please replace it and reset the counter.": "La brosse latérale est usée. Veuillez la remplacer et réinitialiser le compteur.",
        "Side brush needs to be replaced soon": "La brosse latérale doit être remplacée bientôt",
        "The side brush is nearly worn out. Please replace it as soon as possible.": "La brosse latérale est presque usée. Veuillez la remplacer dès que possible.",
        "Filter must be replaced": "Le filtre doit être remplacé",
        "The filter is worn out. Please replace it in time and reset the counter.": "Le filtre est usé. Veuillez le remplacer à temps et réinitialiser le compteur.",
        "Filter needs to be replaced soon": "Le filtre doit être remplacé bientôt",
        "The filter is nearly worn out. Please replace it in time.": "Le filtre est presque usé. Veuillez le remplacer à temps.",
        "Sensors must be cleaned": "Les capteurs doivent être nettoyés",
        "Please clean the sensors and reset the counter": "Veuillez nettoyer les capteurs et réinitialiser le compteur",
        "Tank filter must be replaced": "Le filtre du réservoir doit être remplacé",
        "The tank filter is worn out. Please replace it in time and reset the counter.": "Le filtre du réservoir est usé. Veuillez le remplacer à temps et réinitialiser le compteur.",
        "Tank filter needs to be replaced soon": "Le filtre du réservoir doit être remplacé bientôt",
        "The tank filter is nearly worn out. Please replace it in time.": "Le filtre du réservoir est presque usé. Veuillez le remplacer à temps.",
        "Mop Pad Worn Out": "Tampon de la serpillière usé",
        "Please replace the mop pad and reset the counter.": "Veuillez remplacer le tampon de la serpillière et réinitialiser le compteur.",
        "Mop Pad Nearly Worn Out": "Tampon de la serpillière presque usé",
        "Please replace the mop pad timely.": "Veuillez remplacer le tampon de la serpillière à temps.",
        "Silver Ion Sterilizer Deteriorated": "Stérilisateur à ions d'argent détérioré",
        "Please replace the silver ion sterilizer and reset the counter.": "Veuillez remplacer le stérilisateur à ions d'argent et réinitialiser le compteur.",
        "Silver Ion Sterilizer Near to Deterioration": "Stérilisateur à ions d'argent proche de la détérioration",
        "Please replace the silver ion sterilizer timely.": "Veuillez remplacer le stérilisateur à ions d'argent à temps.",
        "The detergent is used up": "Le détergent est épuisé",
        "Please replace the detergent cartridge it and reset the counter.": "Veuillez remplacer la cartouche de détergent et réinitialiser le compteur.",
        "The detergent is about to be used up": "Le détergent est sur le point d'être épuisé",
        "The detergent is about to be used up, please replace it in time.": "Le détergent est sur le point d'être épuisé, veuillez le remplacer à temps.",
        "Squeegee Worn Out": "Raclette usée",
        "Please replace the squeegee and reset the counter.": "Veuillez remplacer la raclette et réinitialiser le compteur.",
        "Squeegee Nearly Worn Out": "Raclette presque usée",
        "Please replace the squeegee timely.": "Veuillez remplacer la raclette à temps.",
        "Onboard dirty water tank needs to be cleaned": "Le réservoir d'eau sale embarqué doit être nettoyé",
        "Please clean the onboard dirty water tank and reset the counter.": "Veuillez nettoyer le réservoir d'eau sale embarqué et réinitialiser le compteur.",
        "Dirty water tank needs to be cleaned": "Le réservoir d'eau sale doit être nettoyé",
        "Please clean the dirty water tank and reset the counter.": "Veuillez nettoyer le réservoir d'eau sale et réinitialiser le compteur.",
        "Used water tank deodorizer has been exhausted.": "Le désodorisant du réservoir d'eau usée est épuisé.",
        "Used water tank deodorizer has been exhausted. Please replace it.": "Le désodorisant du réservoir d'eau usée est épuisé. Veuillez le remplacer.",
        "Used water tank deodorizer is running out.": "Le désodorisant du réservoir d'eau usée est presque vide.",
        "Used water tank deodorizer is running out. Please replace it.": "Le désodorisant du réservoir d'eau usée est presque vide. Veuillez le remplacer.",
        "Omnidirectional wheel needs to be cleaned": "La roue omnidirectionnelle doit être nettoyée",
        "Please omnidirectional wheel and reset the counter.": "Veuillez nettoyer la roue omnidirectionnelle et réinitialiser le compteur.",
        "Scale inhibitor has been exhausted": "L'inhibiteur de tartre est épuisé",
        "Please replace the scale inhibitor and reset the counter.": "Veuillez remplacer l'inhibiteur de tartre et réinitialiser le compteur.",
        "Scale inhibitor is running out": "L'inhibiteur de tartre est presque vide",
        "Please replace the scale inhibitor timely.": "Veuillez remplacer l'inhibiteur de tartre à temps.",
        # Error descriptions - Side brush
        "The side brush wrapped": "La brosse latérale est entravée",
        "Please remove and clean the side brush.": "Veuillez retirer et nettoyer la brosse latérale.",
        # Error descriptions - Wheels and movement
        "The robot is stuck, or its left wheel may be blocked by foreign objects": "Le robot est coincé, ou sa roue gauche peut être bloquée par des objets étrangers",
        "The robot is stuck, or its right wheel may be blocked by foreign objects": "Le robot est coincé, ou sa roue droite peut être bloquée par des objets étrangers",
        "Check whether there is any object stuck in the main wheels and start the robot in a new position.": "Vérifiez s'il y a un objet coincé dans les roues principales et redémarrez le robot dans une nouvelle position.",
        "The robot is stuck, or cannot turn": "Le robot est coincé ou ne peut pas tourner",
        "The robot is stuck, or cannot go forward": "Le robot est coincé ou ne peut pas avancer",
        "The robot may be blocked or stuck.": "Le robot est peut-être bloqué ou coincé.",
        "Left wheel may be blocked by foreign objects": "La roue gauche peut être bloquée par des objets étrangers",
        "Right wheel may be blocked by foreign objects": "La roue droite peut être bloquée par des objets étrangers",
        # Error descriptions - Battery and charging
        "Cannot find base": "Impossible de trouver la base",
        "Please check whether the power cord is plugged in correctly.": "Veuillez vérifier si le cordon d'alimentation est correctement branché.",
        "Low battery": "Batterie faible",
        "Battery level is too low. Please charge.": "Le niveau de batterie est trop bas. Veuillez recharger.",
        "Charging error": "Erreur de charge",
        "Please use a dry cloth to wipe charging contacts of the robot and auto-empty base.": "Veuillez utiliser un chiffon sec pour essuyer les contacts de charge du robot et de la base d'auto-vidage.",
        "The charging dock is not powered on": "La station de charge n'est pas alimentée",
        "The charging dock is not powered on. Please check whether the power cord is plugged in correctly.": "La station de charge n'est pas alimentée. Veuillez vérifier si le cordon d'alimentation est correctement branché.",
        "Battery temperature error": "Erreur de température de la batterie",
        "Please wait until the battery temperature returns to normal.": "Veuillez attendre que la température de la batterie revienne à la normale.",
        "Low battery. Robot will shut down soon.": "Batterie faible. Le robot va bientôt s'éteindre.",
        # Error descriptions - Sensors
        "Internal error": "Erreur interne",
        "Visual positioning sensor error": "Erreur du capteur de positionnement visuel",
        "Please clean the visual positioning sensor.": "Veuillez nettoyer le capteur de positionnement visuel.",
        "Move sensor error": "Erreur du capteur de mouvement",
        "Optical sensor error": "Erreur du capteur optique",
        "Please wipe the optical sensor clean and restart.": "Veuillez essuyer le capteur optique et redémarrer.",
        "Infrared shielding error": "Erreur de blindage infrarouge",
        "Fan speed sensor error": "Erreur du capteur de vitesse du ventilateur",
        "Accelerometer error": "Erreur de l'accéléromètre",
        "Gyro error": "Erreur du gyroscope",
        "Left magnet sensor error": "Erreur du capteur magnétique gauche",
        "Right magnet sensor error": "Erreur du capteur magnétique droit",
        "Flow sensor error": "Erreur du capteur de flux",
        "Infrared error": "Erreur infrarouge",
        "Camera error": "Erreur de la caméra",
        "Strong magnetic field detected": "Champ magnétique puissant détecté",
        "Strong magnetic field detected. Please start away from the virtual wall.": "Champ magnétique puissant détecté. Veuillez démarrer loin du mur virtuel.",
        "Laser distance sensor error": "Erreur du capteur de distance laser",
        "Please check whether the laser distance sensor has any jammed items": "Veuillez vérifier si le capteur de distance laser a des éléments coincés",
        "Laser distance sensor bumper error": "Erreur du pare-chocs du capteur de distance laser",
        "Please check whether the laser distance sensor bumper is jammed": "Veuillez vérifier si le pare-chocs du capteur de distance laser est coincé",
        "Please check whether the filter has dried or needs to be cleaned": "Veuillez vérifier si le filtre est sec ou doit être nettoyé",
        "Edge sensor error": "Erreur du capteur de bord",
        "Edge sensor error. Please check and clean it.": "Erreur du capteur de bord. Veuillez le vérifier et le nettoyer.",
        "The 3D obstacle avoidance sensor is malfunctioning.": "Le capteur d'évitement d'obstacles 3D est défaillant.",
        "Please try to clean the 3D obstacle avoidance sensor.": "Veuillez essayer de nettoyer le capteur d'évitement d'obstacles 3D.",
        "The ultrasonic sensor is malfunctioning.": "Le capteur ultrasonique est défaillant.",
        "Please restart the robot and try it again.": "Veuillez redémarrer le robot et réessayer.",
        # Error descriptions - Water pump
        "Water pump error": "Erreur de la pompe à eau",
        "RTC error": "Erreur RTC",
        # Error descriptions - Navigation
        "Please start the robot in non-carpet area.": "Veuillez démarrer le robot dans une zone sans tapis.",
        "A carpet is detected under the robot when it is mopping. Please move the robot to another place and restart it.": "Un tapis a été détecté sous le robot pendant le lavage. Veuillez déplacer le robot ailleurs et le redémarrer.",
        "No-Go zone or virtual wall detected.": "Zone interdite ou mur virtuel détecté.",
        "Please move the robot away from the area and restart.": "Veuillez éloigner le robot de la zone et redémarrer.",
        "Unable to reach the specified area.": "Impossible d'atteindre la zone spécifiée.",
        "Please ensure that all doors in the home are open and clear any obstacles along the path.": "Veuillez vous assurer que toutes les portes sont ouvertes et dégager les obstacles le long du chemin.",
        "Please try to delete the restricted area in the path.": "Veuillez essayer de supprimer la zone restreinte sur le chemin.",
        "Cleanup route is blocked.": "Le trajet de nettoyage est bloqué.",
        "Cleanup route is blocked, returning to the dock.": "Le trajet de nettoyage est bloqué, retour à la base.",
        "Please ensure that all doors in the home are open and clear any obstacles around the vacuum-mop.": "Veuillez vous assurer que toutes les portes sont ouvertes et dégager les obstacles autour de l'aspirateur-serpillière.",
        "Please try to delete the restricted area or move the vacuum-mop out of this area.": "Veuillez essayer de supprimer la zone restreinte ou déplacer l'aspirateur-serpillière hors de cette zone.",
        "Detected that the vacuum-mop is in a restricted area.": "L'aspirateur-serpillière est détecté dans une zone restreinte.",
        "Please move the vacuum-mop out of this area.": "Veuillez déplacer l'aspirateur-serpillière hors de cette zone.",
        "Hidden area. Please move the robot to the appropriate area and retry.": "Zone masquée. Veuillez déplacer le robot dans une zone appropriée et réessayer.",
        "The area has been hidden. To reuse it, please go to the specific map and click the gray area to manually recover the hidden area.": "La zone a été masquée. Pour la réutiliser, allez dans la carte spécifique et cliquez sur la zone grise pour la récupérer manuellement.",
        # Error descriptions - Mop pad
        "Mopping completed. Please remove and clean the mop in time.": "Lavage terminé. Veuillez retirer et nettoyer la serpillière à temps.",
        "The mop pad comes off during the cleaning task.": "Le tampon de la serpillière s'est détaché pendant le nettoyage.",
        "The mop pads come off, install them before resuming working.": "Les tampons de la serpillière se sont détachés, installez-les avant de reprendre le travail.",
        "Mop Pad Stops Rotating.": "Le tampon de la serpillière a cessé de tourner.",
        "The mop pad has stopped rotating, please check.": "Le tampon de la serpillière a cessé de tourner, veuillez vérifier.",
        "Mop pad installation failed.": "Échec de l'installation du tampon de la serpillière.",
        "Failed to install mop pads. Please install manually.": "Échec de l'installation des tampons. Veuillez les installer manuellement.",
        # Error descriptions - Dirty water tank
        "The dirty water tank is full or not installed.": "Le réservoir d'eau sale est plein ou n'est pas installé.",
        "Check whether the dirty water tank is full and the dirty water tank is installed.": "Vérifiez si le réservoir d'eau sale est plein et si le réservoir d'eau sale est installé.",
        "The used water tank of robot is not installed.": "Le réservoir d'eau usée du robot n'est pas installé.",
        "Please make sure that the used water tank of robot is installed properly, and then start the task.": "Veuillez vous assurer que le réservoir d'eau usée du robot est correctement installé, puis démarrez la tâche.",
        "Dirty water tank blocked.": "Réservoir d'eau sale obstrué.",
        "Dirty water tank pump error.": "Erreur de la pompe du réservoir d'eau sale.",
        "The water level in the used water tank is too high.": "Le niveau d'eau du réservoir d'eau usée est trop élevé.",
        "Please check if the used water tank is full.": "Veuillez vérifier si le réservoir d'eau usée est plein.",
        "Insufficient water in the fresh tank, please add water. Otherwise, the robot will not return to the base to have the mop pad cleaned during the cleaning task.": "Eau insuffisante dans le réservoir d'eau propre, veuillez ajouter de l'eau. Sinon, le robot ne retournera pas à la base pour nettoyer le tampon de la serpillière pendant le nettoyage.",
        # Error descriptions - Clean water tank
        "The clean water tank is not installed, please install it.": "Le réservoir d'eau propre n'est pas installé, veuillez l'installer.",
        "Please check the clean water tank": "Veuillez vérifier le réservoir d'eau propre",
        # Error descriptions - Dust collection
        "The dust collection bag is full, or the air duct is blocked.": "Le sac de collecte de poussière est plein, ou le conduit d'air est obstrué.",
        "The system detects that the dust collection bag is full, or the air duct is blocked.": "Le système détecte que le sac de collecte de poussière est plein, ou que le conduit d'air est obstrué.",
        "The upper cover of auto-empty base is not closed, or the dust collection bag is not installed.": "Le couvercle supérieur de la base d'auto-vidage n'est pas fermé, ou le sac de collecte de poussière n'est pas installé.",
        "The system detects that the upper cover of auto-empty base is not closed, or the dust collection bag is not installed.": "Le système détecte que le couvercle supérieur de la base d'auto-vidage n'est pas fermé, ou que le sac de collecte de poussière n'est pas installé.",
        "Check whether the dust collection bag is full.": "Vérifiez si le sac de collecte de poussière est plein.",
        "If so, replace the bag. Please clean the auto-empty vents of the dust bin and the base station regularly.": "Si c'est le cas, remplacez le sac. Veuillez nettoyer régulièrement les évents d'auto-vidage du bac à poussière et de la station de base.",
        # Error descriptions - Washboard / Base station
        "The washboard is not installed properly.": "La planche de lavage n'est pas correctement installée.",
        "The washboard is not installed and the robot cannot return to the self-wash base. Please ensure that the washboard is installed and the clasps on both sides are tightly fastened.": "La planche de lavage n'est pas installée et le robot ne peut pas retourner à la base d'auto-lavage. Veuillez vous assurer que la planche de lavage est installée et que les fermoirs des deux côtés sont bien serrés.",
        "The water level of the washboard is abnormal, please clean the washboard timely.": "Le niveau d'eau de la planche de lavage est anormal, veuillez nettoyer la planche de lavage rapidement.",
        "The water level of the washboard is abnormal. Please clean it timely to avoid blockage. If the problem still cannot be solved, please contact customer service.": "Le niveau d'eau de la planche de lavage est anormal. Veuillez la nettoyer rapidement pour éviter tout blocage. Si le problème persiste, veuillez contacter le service client.",
        "The cleaning task is complete, please clean the mop pad washboard.": "La tâche de nettoyage est terminée, veuillez nettoyer la planche de lavage.",
        "Please clean the mop pad washboard in time to avoid stains or odor.": "Veuillez nettoyer la planche de lavage à temps pour éviter les taches ou les odeurs.",
        "Water level in the washboard is too high.": "Le niveau d'eau de la planche de lavage est trop élevé.",
        "Please clean the used water tank and washboard in time.": "Veuillez nettoyer le réservoir d'eau usée et la planche de lavage rapidement.",
        "Check if the mop pad is in the base station, or install the mop pad onto the robot manually.": "Vérifiez si le tampon de la serpillière est dans la station de base, ou installez-le manuellement sur le robot.",
        "The mop pad is out of place. Retry after putting it into the base station or install it onto the robot manually.": "Le tampon de la serpillière est mal positionné. Réessayez après l'avoir remis dans la station de base ou installez-le manuellement sur le robot.",
        "Base station not powered on.": "La station de base n'est pas alimentée.",
        "Please check whether the power is off or the power switch is on in your home, and re-plug both ends of the base station power supply.": "Veuillez vérifier si le courant est coupé ou si l'interrupteur est en position marche, et rebrancher les deux extrémités de l'alimentation de la station de base.",
        "Self test failed.": "Échec de l'auto-test.",
        "There is no water in the clean water tank of the upper and lower water modules.": "Il n'y a pas d'eau dans le réservoir d'eau propre des modules d'eau supérieur et inférieur.",
        "Washboard stops working. Please check.": "La planche de lavage a cessé de fonctionner. Veuillez vérifier.",
        "Washboard stops working. Please follow troubleshooting steps as below:\n1. Check if the washboard is tangled. Clean up before use\n2. Check if the washboard is installed properly\n3.如仍未解决请联系客服": "La planche de lavage a cessé de fonctionner. Veuillez suivre les étapes de dépannage ci-dessous :\n1. Vérifiez si la planche de lavage est emmêlée. Nettoyez avant utilisation\n2. Vérifiez si la planche de lavage est correctement installée\n3. Si le problème persiste, veuillez contacter le service client",
        "Failed to return to charge.": "Échec du retour à la charge.",
        "Please check the base station.\n1. Check if the ramp extension plate is installed down to the base station;\n2. Check if the base station is powered on;\n3. Make sure there is no obstacle in front of the base station.": "Veuillez vérifier la station de base.\n1. Vérifiez si la plaque d'extension de rampe est installée sur la station de base ;\n2. Vérifiez si la station de base est alimentée ;\n3. Assurez-vous qu'il n'y a aucun obstacle devant la station de base.",
    }
}


def translate_description(language: str, description: list[str]) -> list[str]:
    """Translate a description list [title, message] based on language."""
    if not language or language not in DESCRIPTION_TRANSLATIONS or not description:
        return description

    translations = DESCRIPTION_TRANSLATIONS[language]
    translated = []

    for text in description:
        if text in translations:
            translated.append(translations[text])
        else:
            translated.append(text)

    return translated


EVENT_TASK_STATUS: Final = "task_status"
EVENT_CONSUMABLE: Final = "consumable"
EVENT_WARNING: Final = "warning"
EVENT_ERROR: Final = "error"
EVENT_LOW_WATER: Final = "low_water"
EVENT_INFORMATION: Final = "information"
EVENT_DRAINAGE_STATUS: Final = "drainage_status"
