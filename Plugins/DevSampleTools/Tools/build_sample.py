"""
Rebuilds the sample Blueprints under /Game/Sample from the text in Plugins/DevSampleTools/Sample/
(written by export_sample.py from the UE 5.8 workbench). Run it with UE 5.5 so the saved assets
stay loadable in 5.5:

  python Tools/ue_exec.py Plugins/DevSampleTools/Tools/build_sample.py [AssetName ...]

Without names it rebuilds every asset folder. An existing asset is reused (its variables, widget
tree and graphs are replaced), so references to it and its package stay as they are.

Each asset is checked by exporting it again and comparing the result with the source text:
the graph's nodes, links and pin defaults, the widgets and their properties, and the variables
must match, and the Blueprint must compile without errors or warnings.
"""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_text  # noqa: E402

tools = unreal.DevSampleTools


def load_or_create(manifest):
    path = manifest["path"]
    folder, name = path.rsplit("/", 1)
    parent = unreal.load_class(None, manifest["parent"])
    if parent is None:
        raise RuntimeError(f"{path}: parent class {manifest['parent']} not found")

    if unreal.EditorAssetLibrary.does_asset_exist(path):
        bp = unreal.load_asset(path)
        expected = unreal.WidgetBlueprint if manifest["kind"] == "WidgetBlueprint" else unreal.Blueprint
        if not isinstance(bp, expected):
            raise RuntimeError(f"{path} exists but is a {bp.get_class().get_name()}")
        return bp, False

    if manifest["kind"] == "WidgetBlueprint":
        factory = unreal.WidgetBlueprintFactory()
    else:
        factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent)
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, None, factory)
    if bp is None:
        raise RuntimeError(f"{path}: could not create the asset")
    return bp, True


def build(asset_name):
    manifest = sample_text.read_manifest(asset_name)
    src = sample_text.asset_dir(asset_name)
    path = manifest["path"]
    bp, created = load_or_create(manifest)
    print(f"[BUILD] {path} ({'created' if created else 'reused'}, exported with {manifest['exported_with']})")
    problems = []

    # Variables first, then widgets: graph nodes resolve the members they reference.
    variables = sample_text.read_text(os.path.join(src, "Variables.txt"))
    for message in tools.replace_member_variables(bp, variables):
        problems.append(f"variables: {message}")

    widgets = None
    if manifest["kind"] == "WidgetBlueprint":
        widgets = sample_text.read_text(os.path.join(src, "WidgetTree.t3d"))
        if not tools.replace_widget_tree(bp, widgets):
            problems.append("widget tree: the text does not hold exactly one root widget")

    graphs = {}
    for graph in manifest["graphs"]:
        graphs[graph] = sample_text.read_text(os.path.join(src, f"{graph}.t3d"))
        count = tools.replace_graph_nodes(bp, graph, graphs[graph])
        if count < 0:
            problems.append(f"{graph}: no such graph")
        print(f"[BUILD]   {graph}: {count} nodes")

    for message in tools.compile_blueprint_with_messages(bp):
        problems.append(f"compile: {message}")

    saved = unreal.EditorAssetLibrary.save_loaded_asset(bp, only_if_is_dirty=False)
    if not saved:
        problems.append("could not save the asset")

    # Round-trip check: what the rebuilt asset exports must match the source text.
    problems += sample_text.diff_sets(
        "variable",
        [f"{k}: {v}" for k, v in sample_text.variable_summary(variables).items()],
        [f"{k}: {v}" for k, v in sample_text.variable_summary(tools.export_member_variables(bp)).items()])

    if widgets is not None:
        expected = sample_text.widget_summary(widgets)
        actual = sample_text.widget_summary(tools.export_widget_tree(bp))
        problems += sample_text.diff_sets("widget", [f"{k} ({v[0]})" for k, v in expected.items()],
                                          [f"{k} ({v[0]})" for k, v in actual.items()])
        for key in sorted(set(expected) & set(actual)):
            problems += sample_text.diff_sets(f"widget {key} property", expected[key][1], actual[key][1])

    for graph, text in graphs.items():
        e_nodes, e_links, e_defaults = sample_text.graph_summary(text)
        a_nodes, a_links, a_defaults = sample_text.graph_summary(tools.export_graph_nodes(bp, graph))
        problems += sample_text.diff_sets(f"{graph} node", [f"{k} {v}" for k, v in e_nodes.items()],
                                          [f"{k} {v}" for k, v in a_nodes.items()])
        problems += sample_text.diff_sets(f"{graph} link", e_links, a_links)
        problems += sample_text.diff_sets(f"{graph} default", e_defaults, a_defaults)
        print(f"[TEST] {graph}: {len(a_nodes)} nodes, {len(a_links)} links, {len(a_defaults)} pin defaults")

    for problem in problems:
        print(f"[TEST]   {problem}")
    print(f"[TEST] {asset_name}: {'PASS' if not problems else 'FAIL'}")
    return not problems


names = sys.argv[1:] or sample_text.list_assets()
results = [build(name) for name in names]
print("[TEST] RESULT: " + ("PASS" if all(results) else "FAIL"))
