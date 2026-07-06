# Anomalies réelles découvertes par la campagne de tests du 2026-07-06

La montée de couverture (66 % → 98,8 %, +2 063 tests) a mis au jour les
anomalies suivantes dans le moteur `dreame/`. **Aucune n'a été corrigée dans
cette passe** : la plupart sont héritées du fork upstream, et certaines
« corrections » changeraient un comportement auquel les utilisateurs sont
habitués. Chaque anomalie est épinglée par un test qui documente le
comportement ACTUEL — corriger l'anomalie implique d'inverser le test associé.

## Impact utilisateur probable (à corriger en priorité)

1. **`map_renderer/_layers.py` — filtre « stain » inversé** (`render_objects`,
   boucle OBSTACLES) : `not config.stain and type != LIQUID_STAIN …` masque les
   obstacles *non*-taches quand le rendu des taches est désactivé — l'inverse
   de l'intention apparente.
2. **`map_renderer/_objects.py` — crash silencieux du chargeur en icon set
   Material** : `_set_icon_color(icon, size, (0, 255, 126))` passe un tuple RGB
   à un tableau RGBA → `ValueError: shape mismatch`, avalé par le try/except de
   `render_map` → rendu cassé/gelé sans erreur visible.
3. **`map_editor.py::restore_map`** : appelle `self._get_interim_file_data(…)`
   qui n'existe que sur `DreameMapVacuumMapManager` → `AttributeError` avalé →
   la restauration de carte est silencieusement no-op quand `raw_map` est absent.
4. **`map_renderer/_core.py::render_map`** : une exception pendant le tout
   premier rendu laisse `self._image = None` et la méthode (typée `-> bytes`)
   retourne `None` au lieu de `default_map_image`.
5. **`device_setters.py::set_property_value`** (branche SCHEDULE) : une valeur
   vide est validée mais stockée dans `string_value` (chaîne vide falsy) que le
   contrôle final rejette → impossible d'effacer le planning par chaîne vide.

## Incohérences internes (comportement contre-intuitif, pas de crash)

6. **`vacuum_types.py::RecoveryMapInfo.__eq__`** : logique inversée — deux
   instances identiques sont « inégales », des instances différentes « égales ».
7. **`vacuum_types.py::Furniture.__init__`** : garde par truthiness — une
   origine légitime `x0=0`/`y0=0` laisse les coins à `None`.
8. **`vacuum_types.py::Carpet/Polygon.__eq__`** : seule la diagonale
   `x0/y0/x2/y2` est comparée (angle et autres coins ignorés).
9. **`vacuum_types.py::Area.check_size()`** : suppose un ordre de coins
   incompatible avec `Zone.as_area()`.
10. **`map_manager.py::request_map_list`** : le `cleanset` calculé pour la
    carte sélectionnée (l. ~1381) n'est jamais stocké — la branche empruntée ne
    copie que `custom_name`/`rotation`.
11. **`map_decoder.py::get_segments`** (fallback vslam) :
    `x = (endI - startI) + startI` ≡ `x = endI` — midpoint sans le `/2`.
12. **`map_decoder.py`** : détection carpet incohérente entre I-frames
    (bit `0x40`) et P-frames (`pixel & 0x03 == 3`).
13. **`map_decoder.py::carpet_info`** : `Carpet(carpet_type=None, …)` avec
    `carpet[4]`/`carpet[5]` positionnels dans `segments`/`ignored_areas` —
    ordre de champs suspect.
14. **`device_actions.py::rename_shortcut`** : le rollback capture l'objet
    `Shortcut` entier au lieu de `.name` → structure auto-référentielle en cas
    d'échec.
15. **`device_actions.py::reload_shortcuts`** :
    `running = bool(state == "0" or state == "1")` — toujours vrai pour les
    deux états.
16. **`map_editor.py::replace_temporary_map`** : collision d'id possible entre
    la carte insérée et la carte remplacée → `map_index` retombe à 0.
17. **`protocol.py::DreameVacuumProtocol.send/send_async`** : accès
    `self.cloud.device_id` sans garde None avant le fallback MAC (inatteignable
    via le config flow actuel — garde défensive à ajouter au prochain passage).

## Code mort / no-ops identifiés (candidats à suppression future)

18. `device_map_ops.py::set_custom_cleaning` — le chemin legacy (sans carte)
    référence `segments` non assignée → `UnboundLocalError` : ~58 lignes
    inatteignables (l. 1163-1220).
19. `device_actions.py::recovery_map*` — condition interne redondante avec la
    garde englobante (l. 1344, 1353).
20. `map_renderer/_core.py::_calculate_bounds` — retourne
    `[min_x, min_y, max_x, min_y]` (4ᵉ élément dupliqué) ; sans effet car le
    rétrécissement par `dimensions.bounds` en aval est un no-op mathématique
    (`max(min(b, v), v)` ≡ `v`).
21. `map_manager.py::_add_map_data` — pas de branche pour les W-frames
    valides : acceptées silencieusement sans décodage.
22. `vacuum_types.py::Segment.name_list` — branche `if self.type == 0`
    dupliquée ; `MapData.__eq__` garde `other is None` mort ;
    `DeviceCapability.custom_cleaning_mode` : `next(iter(…))` sans défaut.
