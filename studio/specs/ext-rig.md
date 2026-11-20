# Extension: rig

Package `quartz_studio/rig` (about 3.6k lines). Loaded by `ext/install.py` as `quartz_studio.rig`.

## Purpose

Character rigging: joint objects and chains, a biped preset, skin binding with automatic weights (linear blend or dual quaternion), weight painting, two-bone and CCD IK with poles and FK blend, and a live rig updater.

## Data in extras

Joints are scene objects of kind `joint` (`joints.JOINT_KIND`).

Object extras (through `rig.data.read` and `write`, cached):

| Key | Shape |
|-----|-------|
| `skin` (`data.SKIN_KEY`) | `{"joints": [names], "bind_matrices": [4x4], "object_bind_matrix": 4x4, "bind_points": (n, 3), "weights": (n_points, n_joints), "method": "Linear" or dual quaternion, "enabled": bool}` on the mesh |
| `ik` (`data.IK_KEY`) | on the chain start joint: `{"end", "goal", "pole" (object names), "solver", "blend", "iterations", "tolerance", "match_goal_rotation", "twist", "enabled", "fk": stored FK rotations}` |

## Public functions

- `joints`: `create_joint`, `create_chain`, `chain_from_selection`, `build_joints`, `build_biped`, `find_joint`, `is_joint`, `joints`, `joint_children`, `joint_parent`, `root_joints`, `joint_hierarchy`, `joint_chain`, `orient_joints`, `update_bone_display`, `mirror_name`, `set_world_position`, `set_world_rotation`, `set_world_matrix`. `BIPED_LAYOUT`.
- `skin`: `bind_skin`, `unbind_skin`, `rebind_skin`, `auto_weights`, `apply_weights`, `deform_skin`, `mirror_weights`, `paint_weights`, `reset_bind_pose`, `set_skin_method`, `skin_of`, `is_skinned`, `skinned_objects`, `linear_blend`, `dual_quaternion_blend`, weight helpers (`normalize_weights`, `limit_influences`, `prune_weights`, `smooth_weights`).
- `ik`: `add_ik`, `remove_ik`, `set_ik`, `store_fk`, `solve_ik`, `solve_all`, `solve_two_bone`, `solve_ccd`, `sync_to_pose`, `ik_tag`, `ik_tags`.
- `runtime`: `evaluate_rig(scene, emit)`, `RigUpdater`, `updater_for`, `ReferenceGuard`, `rename_object`, `rename_references`.
- `paint`: `WeightBrush`, `WeightPainter` (stroke, undo, falloff).
- Package level: `last_error()`.

## Widgets

`RigPanel` (joint, chain, orient, align, bind, auto weights, unbind, mirror, bind pose, IK), `JointList` (hierarchy tree, add child, delete, rename), `WeightPaintPanel` with `WeightPreview` (own 3D preview painting) and `WeightPaintController` (viewport painting).

## Menus, docks, pages, shortcuts

- Menu `Character` (installed under `Animate > Character`): Joint, Joint Chain from Points, Joint Chain from Points (Nearest Order), Orient Joints, Align Bone Display, Skin (Bind Skin, Auto Weights, Mirror Weights, Set Bind Pose, Go to Bind Pose, Unbind Skin), IK (Add IK, Remove IK), Presets (Biped Skeleton, Biped Skeleton with IK), Update Rig, Live Rig Update.
- Docks: Rig (right), Weight Paint (right), Joints (left).
- Layout: `Rigging` (dock layout).
- Key actions: `rig.update`, `rig.live`, `rig.joint` with no shortcuts.

## Known gaps

- No default shortcuts.
- The tags package also has `ik`, `weight` and `skin` tag types; `tags.builtin.sync_ik` mirrors IK tags into the `ik` extra, so two editing paths exist for the same data.
- Deformation is CPU numpy per evaluation; no GPU skinning.
