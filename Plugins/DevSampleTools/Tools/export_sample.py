"""
Exports sample Blueprints and maps drafted in the UE 5.8 workbench as text into this checkout's
Plugins/DevSampleTools/Sample/, for build_sample.py to rebuild them with UE 5.5.
Run it in the workbench editor (its content is 5.8-only and never committed):

  python Tools/ue_exec.py --project-root <workbench> Plugins/DevSampleTools/Tools/export_sample.py /Game/Sample/UI/WBP_X /Game/Sample/Maps/L_Y ...

A map is opened in the editor to be exported (save the current level first). The text is written next to this
script, not into the workbench, because the script path (this checkout) is what ue_exec passes to the editor.
"""
import importlib
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_text  # noqa: E402

# The editor's interpreter keeps modules between runs: pick up changes to the shared module.
importlib.reload(sample_text)

tools = unreal.DevSampleTools


def export_blueprint(bp, files):
    """Writes the Blueprint's variables and graphs into files; returns (functions, graphs)."""
    errors = tools.compile_blueprint_with_messages(bp)
    if errors:
        raise RuntimeError(f"{bp.get_path_name()} does not compile cleanly: {list(errors)}")
    files["Variables.txt"] = tools.export_member_variables(bp)
    functions = [str(name) for name in tools.get_function_graph_names(bp)]
    for name in functions:
        files[f"{name}.t3d"] = tools.export_graph_nodes(bp, name)
    graphs = []
    if tools.export_graph_nodes(bp, "EventGraph"):
        files["EventGraph.t3d"] = tools.export_graph_nodes(bp, "EventGraph")
        graphs.append("EventGraph")
    return functions, graphs


def export_map(asset_path, files):
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.load_level(asset_path):
        raise RuntimeError(f"could not open {asset_path} (unsaved changes in the current level?)")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    files["Actors.t3d"] = tools.export_level_actors(world)
    functions, graphs = export_blueprint(tools.get_level_blueprint(world), files)
    return {"kind": "Level", "functions": functions, "graphs": graphs}


def export(asset_path):
    name = asset_path.rsplit("/", 1)[-1]
    files = {}
    if unreal.EditorAssetLibrary.find_asset_data(asset_path).asset_class_path.asset_name == "World":
        manifest = export_map(asset_path, files)
    else:
        bp = unreal.load_asset(asset_path)
        if not isinstance(bp, unreal.Blueprint):
            raise RuntimeError(f"{asset_path} is neither a Blueprint nor a map")
        functions, graphs = export_blueprint(bp, files)
        manifest = {"kind": "WidgetBlueprint" if isinstance(bp, unreal.WidgetBlueprint) else "Blueprint",
                    "parent": bp.get_blueprint_parent_class().get_path_name(),
                    "functions": functions, "graphs": graphs}
        if isinstance(bp, unreal.WidgetBlueprint):
            files["WidgetTree.t3d"] = tools.export_widget_tree(bp)

    out = sample_text.asset_dir(name)
    os.makedirs(out, exist_ok=True)
    for old in os.listdir(out):
        if old not in files and old != "Asset.json":
            os.remove(os.path.join(out, old))
    for file_name, text in files.items():
        sample_text.write_text(os.path.join(out, file_name), text)
    manifest = dict({"path": asset_path}, **manifest, exported_with=unreal.SystemLibrary.get_engine_version())
    sample_text.write_manifest(name, manifest)
    print(f"[EXPORT] {asset_path} -> {out}: {sorted(files)}")


def main():
    for path in sys.argv[1:]:
        export(path)


main()
