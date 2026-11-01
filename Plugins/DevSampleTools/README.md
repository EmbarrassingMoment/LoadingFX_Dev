# Dev Sample Tools (Local)

Local-only editor plugin for developing the LoadingFX sample (`/Game/Sample`). It is **not** part of the LoadingFX distribution and is excluded from the sample project release zip.

## Why

The sample Blueprints and maps are drafted through MCP in the UE 5.8 workbench, but the sample content must stay loadable in UE 5.5, and nothing converts a 5.8 package back. So the drafts travel as text: the workbench exports them, and UE 5.5 rebuilds the assets from that text. The text is what is committed, like the material builder scripts in `DevMaterialTools`.

## What it does

`UDevSampleTools` (`unreal.DevSampleTools` in Python) exposes what Python cannot reach. It works the same in UE 5.5 and 5.8.

- `export_graph_nodes` / `replace_graph_nodes`: every node of an event graph or a function as graph editor copy text (Ctrl+C / Ctrl+V), imported with its positions and GUIDs. A function's entry and result nodes come along (a paste skips them), so its signature travels too. Ghost events are left out. `get_function_graph_names` lists the functions.
- `export_member_variables` / `replace_member_variables`: `UBlueprint::NewVariables` as property text. The export writes each variable's current default from the class default object into `DefaultValue`, which a full compile clears.
- `export_widget_tree` / `replace_widget_tree`: the widget tree as UMG designer copy text.
- `export_level_actors` / `replace_level_actors`: a level's actors as level editor copy text, without World Settings, the builder brush and the Level Blueprint's actor. `get_level_blueprint` returns the Level Blueprint, which the functions above handle like any Blueprint.
- `compile_blueprint_with_messages`: compiles and returns the errors and warnings.

## Source text

`Sample/<AssetName>/` holds one asset: `Asset.json` (path, kind, parent class, function and event graph names, the engine it was exported with), `Variables.txt`, `WidgetTree.t3d` for a widget blueprint, `Actors.t3d` for a map, and `<Graph>.t3d` per graph (a map's are its Level Blueprint's).

## Scripts

Export from the workbench (the UE 5.8 editor must be open with remote execution on, see `Tools/ue_exec.py`; save the current level first, since a map is opened to be exported; the text lands in this checkout, next to the script):

```
python Tools/ue_exec.py --project-root <workbench> Plugins/DevSampleTools/Tools/export_sample.py /Game/Sample/UI/WBP_LFXSample_Hub /Game/Sample/Maps/L_LFXSample_Hub
```

Rebuild everything with **UE 5.5** (the editor open on this checkout):

```
python Tools/ue_exec.py Plugins/DevSampleTools/Tools/build_sample.py
```

Existing assets are reused, so references to them stay. Blueprints reference each other, so they are built in passes (variables, widget trees, functions, event graphs, with compiles in between), and the maps come last. Each asset is checked by exporting it again and comparing that with the source text (graph nodes, links and pin defaults, widgets and their properties, variables, actors and their components' properties), and every Blueprint must compile without errors or warnings. A few lines of level text differ between engine versions without the level being different; `sample_text.py` lists them and leaves them out. The script prints `[TEST] RESULT: PASS` when everything matches.

The same command with `--project-root <workbench>` rebuilds the drafts in the workbench from the text, for example after the workbench was recreated.

In Git Bash, prefix the commands with `MSYS_NO_PATHCONV=1`, or `/Game/...` arguments are turned into Windows paths.
