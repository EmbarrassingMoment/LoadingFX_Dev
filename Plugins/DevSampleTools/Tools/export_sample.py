"""
Exports sample Blueprints drafted in the UE 5.8 workbench as text into this checkout's
Plugins/DevSampleTools/Sample/, for build_sample.py to rebuild them with UE 5.5.
Run it in the workbench editor (its content is 5.8-only and never committed):

  python Tools/ue_exec.py --project-root <workbench> Plugins/DevSampleTools/Tools/export_sample.py /Game/Sample/UI/WBP_X ...

The text is written next to this script, not into the workbench, because the script path
(this checkout) is what ue_exec passes to the editor.
"""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_text  # noqa: E402

GRAPHS = ["EventGraph"]


def export(asset_path):
    bp = unreal.load_asset(asset_path)
    if not isinstance(bp, unreal.Blueprint):
        raise RuntimeError(f"{asset_path} is not a Blueprint")

    name = asset_path.rsplit("/", 1)[-1]
    out = sample_text.asset_dir(name)
    os.makedirs(out, exist_ok=True)

    errors = unreal.DevSampleTools.compile_blueprint_with_messages(bp)
    if errors:
        raise RuntimeError(f"{asset_path} does not compile cleanly: {list(errors)}")

    files = {"Variables.txt": unreal.DevSampleTools.export_member_variables(bp)}
    is_widget = isinstance(bp, unreal.WidgetBlueprint)
    if is_widget:
        files["WidgetTree.t3d"] = unreal.DevSampleTools.export_widget_tree(bp)
    graphs = []
    for graph in GRAPHS:
        text = unreal.DevSampleTools.export_graph_nodes(bp, graph)
        if text:
            files[f"{graph}.t3d"] = text
            graphs.append(graph)

    for file_name, text in files.items():
        sample_text.write_text(os.path.join(out, file_name), text)

    parent = bp.get_blueprint_parent_class()
    sample_text.write_manifest(name, {
        "path": asset_path,
        "kind": "WidgetBlueprint" if is_widget else "Blueprint",
        "parent": parent.get_path_name(),
        "graphs": graphs,
        "exported_with": unreal.SystemLibrary.get_engine_version(),
    })
    print(f"[EXPORT] {asset_path} -> {out}: {sorted(files)}")


for path in sys.argv[1:]:
    export(path)
