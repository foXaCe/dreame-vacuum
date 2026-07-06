# Anomalies réelles découvertes par la campagne de tests du 2026-07-06

La montée de couverture (66 % → 98,8 %, +2 063 tests) a mis au jour les
anomalies suivantes dans le moteur `dreame/`. Les 5 anomalies à impact
utilisateur (section suivante) **ont été corrigées** dans la foulée, avec
inversion des tests qui les épinglaient. Une seconde passe (2026-07-06,
branche `fix/engine-anomalies-batch2`) a corrigé 4 anomalies internes
supplémentaires (#6, #7, #15, #17) et purgé 5 zones de code mort (#18-22).
Les anomalies restantes (#8-14, #16) sont toujours documentées : la
plupart sont héritées du fork upstream, et certaines « corrections »
changeraient un comportement auquel les utilisateurs sont habitués. Chaque
anomalie restante est épinglée par un test qui documente le comportement
ACTUEL — la corriger implique d'inverser le test associé.

> Note : suite au split de `vacuum_types.py` en modules `types_*.py`
> (2026-07-06), les classes citées ci-dessous comme « `vacuum_types.py::X` »
> vivent maintenant dans `types_map.py` (RecoveryMapInfo, Furniture, Carpet,
> Polygon, Area, Segment, MapData) ou `types_capability.py`
> (DeviceCapability). Cherchez par nom de classe/fonction, pas par ligne.

## Impact utilisateur — ✅ CORRIGÉES (commit « fix: five user-impacting engine bugs »)

1. ✅ **`map_renderer/_layers.py` — filtre « stain » inversé** : désactiver le
   rendu des taches masquait tous les obstacles ordinaires et laissait les
   taches affichées. La gate teste désormais `type in STAINS` (symétrique de
   la clause pet).
2. ✅ **`map_renderer/_objects.py` — crash silencieux du chargeur en icon set
   Material** : le tuple RGB `(0, 255, 126)` passé à un tableau RGBA levait
   `ValueError: shape mismatch` (avalé → rendu gelé). Couleur RGBA complète
   `(0, 255, 126, 255)`, conforme aux autres appels.
3. ✅ **`map_editor.py::restore_map`** : l'appel passe par
   `self.map_manager._get_interim_file_data(…)` — la restauration de carte
   récupère à nouveau le fichier au lieu d'être silencieusement no-op.
4. ✅ **`map_renderer/_core.py::render_map`** : un échec du tout premier rendu
   retombe sur `default_map_image` au lieu de retourner `None`.
5. ✅ **`device_setters.py::set_property_value`** (branche SCHEDULE) :
   `string_value` est maintenant un pur flag de validité — une chaîne vide
   (effacement du planning) est acceptée et envoyée au device.

## Incohérences internes (comportement contre-intuitif, pas de crash)

6. ✅ **CORRIGÉE** (commit `51bc42e`) — **`types_map.py::RecoveryMapInfo.__eq__`** :
   logique inversée — deux instances identiques étaient « inégales », des
   instances différentes « égales ». Passé à une égalité normale
   (`date == date and map_id == map_id and object_name == object_name`).
   Audit des sites d'appel : `map_manager.request_recovery_map_list` est le
   seul endroit qui compare des `RecoveryMapInfo` pour détecter un
   changement, et il le fait via la propriété `__dict__` surchargée, pas via
   `__eq__` — aucun chemin de production ne dépendait du comportement
   inversé, seuls des tests utilisaient `==` directement.
7. ✅ **CORRIGÉE** (commit `842ce79`) — **`types_map.py::Furniture.__init__`** :
   garde par truthiness — une origine légitime `x0=0`/`y0=0` laissait les
   coins à `None`. Remplacé par `x0 is not None and y0 is not None` (les
   contrôles `width`/`height` restent en truthiness : `0` y est le vrai
   marqueur « pas de dimensions » utilisé par le décodeur).
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
15. ✅ **CORRIGÉE** (commit `9adea4e`) — **`device_actions.py::reload_shortcuts`** :
    `running = bool(state == "0" or state == "1")` était toujours vrai pour
    les deux états. `start_shortcut()` met `.running = True` juste avant
    d'envoyer la commande SHORTCUT, et la convention « chaîne booléenne »
    déjà utilisée ailleurs dans ce moteur (`device_setters.py` :
    `value == "TRUE" or value == "1"` / `value == "FALSE" or value == "0"`)
    mappe "1" → vrai, "0" → faux. Appliqué ici : `running = state == "1"`.
16. **`map_editor.py::replace_temporary_map`** : collision d'id possible entre
    la carte insérée et la carte remplacée → `map_index` retombe à 0.
17. ✅ **CORRIGÉE** (commit `82700c3`) — **`protocol.py::DreameVacuumProtocol.send/send_async`** :
    accès `self.cloud.device_id` sans garde None avant le fallback MAC.
    Ajout de la garde défensive `if self.cloud and self.cloud.device_id:`
    dans les deux méthodes (toujours inatteignable via le config flow actuel,
    qui fournit toujours les identifiants cloud ensemble, mais protégé
    quand même).

## Code mort / no-ops — ✅ PURGÉS (branche `fix/engine-anomalies-batch2`)

18. ✅ **PURGÉE** (commit `6afefb6`) — `device_map_ops.py::set_custom_cleaning` :
    le chemin legacy (sans carte) référençait `segments` non assignée →
    `UnboundLocalError` garanti dès qu'il était atteint (~58 lignes
    inatteignables). Remplacé par une `InvalidActionException` explicite
    (« Customized cleaning without a map is not supported on this device »).
    Les deux validations qui étaient réellement atteignables avant le crash
    (incohérence `cleaning_mode`/`custom_cleaning_mode`) sont conservées.
19. ✅ **PURGÉE** (commit `a303a47`) — `device_actions.py::recovery_map*` :
    la condition interne `if (map_id is None or map_id == "") and
    self.status.selected_map` était redondante avec la garde englobante
    (qui exige déjà `map_id` truthy) — supprimée dans `recovery_map` et
    `recovery_map_file`.
20. ✅ **CORRIGÉE** (commit `89705d7`) — `map_renderer/_core.py::_calculate_bounds` :
    retournait `[min_x, min_y, max_x, min_y]` (4ᵉ élément dupliqué). Prouvé
    (par calcul et par le test existant
    `test_dimensions_bounds_do_not_affect_crop_bug`) que le rétrécissement en
    aval par `dimensions.bounds` est un no-op mathématique
    (`max(min(b, v), v) ≡ v` pour tout `b`) — donc corriger le retour
    (`max_y` au lieu du doublon) ne change aucun pixel rendu. Le retour est
    corrigé ; le no-op en aval est documenté par un commentaire mais laissé
    en l'état (la suite de tests `map_renderer` — 317 tests — confirme
    l'absence de régression visuelle).
21. ✅ **CORRIGÉE** (commit `69e46c5`) — `map_manager.py::_add_map_data` :
    aucune branche pour les W-frames (ou tout autre type de frame non I/P) —
    acceptées silencieusement sans décodage ni trace. Ajout d'un `else` avec
    un log `debug` explicite ; aucun nouveau comportement de décodage
    ajouté (toujours accepté sans état modifié, comme demandé).
22. ✅ **PURGÉE** (commit `76cb424`) — `types_map.py::Segment.name_list` :
    branche `if self.type == 0` dupliquée (les deux branches calculaient la
    même expression) — collapsée en une seule assignation. `MapData.__eq__` :
    garde `other is None` morte (déjà couverte par le
    `isinstance(other, MapData)` précédent) — supprimée. `types_capability.py::
    DeviceCapability.custom_cleaning_mode` : les deux appels
    `next(iter(segments.values()))` ne sont atteints que lorsque `segments`
    est truthy (jamais de `StopIteration` en pratique), mais sans défaut
    défensif — passé à `next(..., None)` avec vérification explicite.
