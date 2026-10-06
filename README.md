# Weight Tools — Bone Center Falloff

**Controlled vertex weight distribution along the active bone.**

A Blender rigging add-on that assigns weights to selected vertices using their projected position along a bone. Influence reaches its maximum at the bone's midpoint and falls to zero at configurable boundaries, with an adjustable transition from linear to smooth.

| At a glance | Details |
| --- | --- |
| Add-on version | 1.0.0 |
| Blender version declared in the script | 5.2.0 |
| Category | Rigging |
| File | `weight_tools.py` |
| Panel | 3D Viewport → Sidebar → **Weight Tools** |
| Supported modes | Object, Edit, and Weight Paint |

> **Compatibility:** The script declares Blender 5.2.0 in its metadata. This README documents the supplied code; runtime compatibility with Blender releases has not been tested here.

---

## Contents

- [Features](#features)
- [Installation](#installation)
- [Before you begin](#before-you-begin)
- [Quick start](#quick-start)
- [Settings](#settings)
- [How the falloff works](#how-the-falloff-works)
- [Working in different modes](#working-in-different-modes)
- [Weight editing behavior](#weight-editing-behavior)
- [Troubleshooting](#troubleshooting)

## Features

- **Bone-centered influence:** The maximum weight occurs at the bone's midpoint, `t = 0.5`.
- **Adjustable boundaries:** Define where the influence starts and ends along the bone.
- **Smooth falloff:** Blend between linear ramps and a smootherstep curve.
- **Selection isolation:** Update only selected, visible vertices in the active vertex group.
- **Rest-position calculations:** Use the original mesh coordinates and bone rest position rather than the current animated pose.
- **Transform-aware projection:** Convert the bone into mesh object space before calculating weights.
- **Persistent settings:** Store panel values in the scene so they are saved with the `.blend` file.
- **Undo support:** The distribution operator supports Blender's Undo workflow.

## Installation

1. Save the supplied script as `weight_tools.py`.
2. Open **Edit → Preferences → Add-ons** in Blender.
3. Use the available add-on installation command to select the Python file. The command's label and location depend on the Blender version.
4. Enable **Weight Tools - Bone Center Falloff**.
5. In the **3D Viewport**, press **N** and open the **Weight Tools** tab.

Most controls use English labels. Some tooltips, panel messages, and operator reports in the supplied script are in Portuguese.

## Before you begin

The operation requires:

- An active **mesh** object associated with exactly **one armature**.
- An active **bone** in that armature, with **Deform** enabled.
- An active, unlocked **vertex group** whose name exactly matches the active bone's name.
- At least one selected, visible vertex.
- Valid boundaries: **`0.0 ≤ Start < 0.5 < End ≤ 1.0`**.

The tool does not create missing vertex groups or automatically choose a bone. Configure the armature, bone, group, and vertex selection before applying weights.

## Quick start

1. Select the desired deform bone in the armature, for example in Pose Mode.
2. Make the character mesh active and select the vertex group with the same name as that bone.
3. Enter **Edit Mode** with only that mesh being edited.
4. Select the vertices you want to update.
5. Open **Sidebar → Weight Tools**.
6. Set the maximum weight, boundaries, and smoothness.
7. Click **Distribute Selected Weights**.
8. Inspect the result in Weight Paint or test the deformation in Pose Mode.

> **Selection matters:** Every selected, visible vertex is eligible for an update, even if it does not already belong to the active group. Select only the region you intend to affect.

## Settings

| Setting | Default | Range / rule | Effect |
| --- | --- | --- | --- |
| **Max Weight** | `1.0` | `0.0–1.0` | Sets the peak influence at the bone's midpoint. |
| **Start Boundary** | `0.0` | Must be below `0.5` | Sets the lower boundary of the influence interval. |
| **End Boundary** | `1.0` | Must be above `0.5` | Sets the upper boundary of the influence interval. |
| **Falloff Smoothness** | `1.0` | `0.0–1.0` | Blends linear ramps (`0.0`) with smootherstep (`1.0`). |

The boundaries describe normalized positions along the bone, not distances in meters. The peak stays at `0.5`, even when the boundaries are asymmetric.

### Example configurations

| Goal | Max Weight | Start | End | Smoothness |
| --- | --- | --- | --- | --- |
| Smooth influence across the full bone | `1.0` | `0.0` | `1.0` | `1.0` |
| Narrower influence around the midpoint | `1.0` | `0.25` | `0.75` | `1.0` |
| Lower maximum influence | `0.5` | `0.0` | `1.0` | `1.0` |
| Linear rise and fall | `1.0` | `0.0` | `1.0` | `0.0` |

These are starting points. Appropriate values depend on the selected region and the intended deformation.

## How the falloff works

The tool projects each selected vertex onto the bone's head-to-tail axis:

```text
d = tail - head
t = dot(vertex - head, d) / dot(d, d)
```

The projected position is clamped to the interval `[0, 1]`.

| Position | Normalized value | Result with default settings |
| --- | --- | --- |
| Bone head or before it | `0.0` | Zero weight |
| Quarter of the bone | `0.25` | Half of Max Weight |
| Bone midpoint | `0.5` | Max Weight |
| Three quarters of the bone | `0.75` | Half of Max Weight |
| Bone tail or beyond it | `1.0` | Zero weight |

At or outside the configured boundaries, the weight is zero. Inside the interval, separate ramps rise toward the fixed midpoint and fall away from it. Smoothness blends these ramps with:

```text
smootherstep(u) = 6u⁵ - 15u⁴ + 10u³
```

> **Axial falloff:** The calculation uses position along the bone, not perpendicular distance from it. Vertices far from the bone can receive the same weight as nearby vertices when their projected positions match. Use vertex selection to limit the affected area.

## Working in different modes

### Edit Mode

Select the vertices directly and run the operator from the Sidebar. Only one mesh may be in Edit Mode at a time for this operation.

### Weight Paint Mode

Enable **Vertex Selection Mask** in the Weight Tools panel, select the intended vertices, and click **Distribute Selected Weights**.

The same operator is also available from:

**Weights → Bone Center Falloff — Selected**

Vertex selection masking is required. Face selection masking alone does not satisfy the operator's check.

### Object Mode

The operator uses the mesh's stored vertex selection. Select the vertices in Edit Mode first, return to Object Mode, and apply the distribution.

Selecting the mesh object alone does not define the intended vertex region.

## Weight editing behavior

- Calculated positive weights **replace** existing weights in the active group for the affected vertices.
- A calculated weight of zero **removes membership** from that group.
- Unselected and hidden vertices are left unchanged.
- Other vertex groups are left unchanged.
- The tool does **not normalize** weights across groups.
- The operation does not rewrite mesh geometry, UVs, or shape keys.

> **Normalization:** Because other groups are preserved, total weights across groups may not equal `1.0` after applying the tool. Review the result and normalize separately if your workflow requires it.

Setting **Max Weight** to `0.0` removes the selected, visible vertices from the active group. Use **Undo** to revert an unwanted distribution.

## Troubleshooting

| Issue | What to check |
| --- | --- |
| The panel is missing | Enable the add-on, press **N** in the 3D Viewport, and open **Weight Tools**. |
| The operation is unavailable | Make a mesh active and use Object, Edit, or Weight Paint Mode. |
| The panel displays `Start < 0.5 < End` | Move Start below `0.5` and End above `0.5`. A boundary cannot equal the midpoint. |
| No active vertex group | Select or create the group corresponding to the intended bone. |
| Group and bone names do not match | Activate the matching bone in the armature and its identically named group on the mesh. |
| The active group is locked | Unlock that vertex group before applying the operation. |
| The armature association is rejected | Ensure the mesh resolves to exactly one armature; several distinct rigs are ambiguous. |
| The bone is rejected | Enable **Deform** and check that the bone has a nonzero length. |
| Weight Paint requests vertex masking | Enable **Vertex Selection Mask** and select vertices. |
| No selected vertices are reported | Select vertices and ensure they are not hidden. |
| Mesh transformation is invalid | Check for a non-invertible mesh transform, such as a zero scale component. |
| Unexpected vertices receive influence | Restrict the selection; the falloff has no radial distance cutoff. |

---

**Select the region. Shape the falloff. Apply controlled weights.**
