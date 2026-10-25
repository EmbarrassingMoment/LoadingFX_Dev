# Dev Sample Tools (Local)

Local-only editor plugin for developing the LoadingFX sample (`/Game/Sample`). It is **not** part of the LoadingFX distribution and is excluded from the sample project release zip.

## Why

The sample Blueprints are drafted through MCP in the UE 5.8 workbench, but the sample content must stay loadable in UE 5.5, and nothing converts a 5.8 package back. So the drafts travel as text: the workbench exports them, and UE 5.5 rebuilds the assets from that text. The text is what is committed, like the material builder scripts in `DevMaterialTools`.

## What it does

`UDevSampleTools` (`unreal.DevSampleTools` in Python) exposes what Python cannot reach. It works the same in UE 5.5 and 5.8.

- `export_graph_nodes` / `replace_graph_nodes`: every node of a graph as graph editor copy text (Ctrl+C / Ctrl+V), imported with its positions and GUIDs. Ghost events and a function's entry and result nodes are left out, so only event graphs round-trip for now.
- `export_member_variables` / `replace_member_variables`: `UBlueprint::NewVariables` as property text. The export writes each variable's current default from the class default object into `DefaultValue`, which a full compile clears.
- `export_widget_tree` / `replace_widget_tree`: the widget tree as UMG designer copy text.
- `compile_blueprint_with_messages`: compiles and returns the errors and warnings.

## Source text

`Sample/<AssetName>/` holds one asset: `Asset.json` (path, kind, parent class, graphs, the engine it was exported with), `Variables.txt`, `WidgetTree.t3d` for widget blueprints, and `<Graph>.t3d` per graph.

## Scripts

Export from the workbench (the UE 5.8 editor must be open with remote execution on, see `Tools/ue_exec.py`; the text lands in this checkout, next to the script):

```
python Tools/ue_exec.py --project-root <workbench> Plugins/DevSampleTools/Tools/export_sample.py /Game/Sample/UI/WBP_LFXSample_TravelButton
```

Rebuild with **UE 5.5** (the editor open on this checkout):

```
python Tools/ue_exec.py Plugins/DevSampleTools/Tools/build_sample.py [AssetName ...]
```

An existing asset is reused, so its references stay. Each asset is checked by exporting it again and comparing that with the source text (graph nodes, links and pin defaults, widgets and their properties, variables), and it must compile without errors or warnings. The script prints `[TEST] RESULT: PASS` when everything matches. In Git Bash, prefix the commands with `MSYS_NO_PATHCONV=1`, or `/Game/...` arguments are turned into Windows paths.
