"""
Rebuilds the sample under /Game/Sample from the text in Plugins/DevSampleTools/Sample/ (written by
export_sample.py from the UE 5.8 workbench). Run it with UE 5.5 so the saved assets stay loadable in 5.5:

  python Tools/ue_exec.py Plugins/DevSampleTools/Tools/build_sample.py

It rebuilds every asset folder; existing assets are reused (their variables, widget trees, graphs and, for maps,
actors are replaced), so references to them stay. Blueprints reference each other, so they are built in passes:
create, variables, compile, widget trees, compile, functions, event graphs (each twice, with a compile in between,
for calls to functions and custom events imported in the same pass), compile. Maps come last, one at a time:
actors, then the Level Blueprint the same way.

Each asset is checked by exporting it again and comparing the result with the source text: graph nodes, links
and pin defaults, widgets and their properties, variables, and the level's actors and their components' properties
must match, and every Blueprint must compile without errors or warnings.
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


def read(asset_name, file_name):
    return sample_text.read_text(os.path.join(sample_text.asset_dir(asset_name), file_name))


def load_or_create(manifest):
    path = manifest["path"]
    folder, name = path.rsplit("/", 1)
    expected = unreal.WidgetBlueprint if manifest["kind"] == "WidgetBlueprint" else unreal.Blueprint
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        bp = unreal.load_asset(path)
        if not isinstance(bp, expected):
            raise RuntimeError(f"{path} exists but is a {bp.get_class().get_name()}")
        return bp
    factory = unreal.WidgetBlueprintFactory() if expected is unreal.WidgetBlueprint else unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.load_class(None, manifest["parent"]))
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, None, factory)
    if bp is None:
        raise RuntimeError(f"{path}: could not create the asset")
    print(f"[BUILD] created {path}")
    return bp


def import_functions(bp, asset_name, manifest, problems):
    existing = {str(n) for n in tools.get_function_graph_names(bp)}
    for function in manifest.get("functions", []):
        if function not in existing:
            graph = unreal.BlueprintEditorLibrary.add_function_graph(bp, function)
            if graph.get_name() != function:
                problems.append(f"function {function} was created as {graph.get_name()}")
        if tools.replace_graph_nodes(bp, function, read(asset_name, f"{function}.t3d")) < 0:
            problems.append(f"{function}: no such graph")


def import_event_graphs(bp, asset_name, manifest, problems):
    for graph in manifest.get("graphs", []):
        if tools.replace_graph_nodes(bp, graph, read(asset_name, f"{graph}.t3d")) < 0:
            problems.append(f"{graph}: no such graph")


def compare_blueprint(bp, asset_name, manifest, problems):
    """Exports the rebuilt Blueprint again and compares it with its source text."""
    variables = read(asset_name, "Variables.txt")
    problems += sample_text.diff_sets(
        "variable",
        [f"{k}: {v}" for k, v in sample_text.variable_summary(variables).items()],
        [f"{k}: {v}" for k, v in sample_text.variable_summary(tools.export_member_variables(bp)).items()])
    if manifest["kind"] == "WidgetBlueprint":
        expected = sample_text.widget_summary(read(asset_name, "WidgetTree.t3d"))
        actual = sample_text.widget_summary(tools.export_widget_tree(bp))
        problems += sample_text.diff_sets("widget", [f"{k} ({v[0]})" for k, v in expected.items()],
                                          [f"{k} ({v[0]})" for k, v in actual.items()])
        for key in sorted(set(expected) & set(actual)):
            problems += sample_text.diff_sets(f"widget {key} property", expected[key][1], actual[key][1])
    counts = []
    for graph in manifest.get("functions", []) + manifest.get("graphs", []):
        e_nodes, e_links, e_defaults = sample_text.graph_summary(read(asset_name, f"{graph}.t3d"))
        a_nodes, a_links, a_defaults = sample_text.graph_summary(tools.export_graph_nodes(bp, graph))
        problems += sample_text.diff_sets(f"{graph} node", [f"{k} {v}" for k, v in e_nodes.items()],
                                          [f"{k} {v}" for k, v in a_nodes.items()])
        problems += sample_text.diff_sets(f"{graph} link", e_links, a_links)
        problems += sample_text.diff_sets(f"{graph} default", e_defaults, a_defaults)
        counts.append(f"{graph} {len(a_nodes)}/{len(a_links)}/{len(a_defaults)}")
    return counts


def report(asset_name, counts, problems):
    print(f"[TEST] {asset_name}: {', '.join(counts)} (nodes/links/defaults)")
    for problem in problems:
        print(f"[TEST]   {problem}")
    print(f"[TEST] {asset_name}: {'PASS' if not problems else 'FAIL'}")
    return not problems


def build_blueprints(names):
    """Builds every Blueprint asset in passes; returns {name: (bp, manifest, problems)}."""
    built = {}
    for name in names:
        manifest = sample_text.read_manifest(name)
        built[name] = (load_or_create(manifest), manifest, [])
        print(f"[BUILD] {manifest['path']} (exported with {manifest['exported_with']})")

    def compile_all(record):
        for bp, _, problems in built.values():
            messages = tools.compile_blueprint_with_messages(bp)
            if record:
                problems += [f"compile: {m}" for m in messages]

    for name, (bp, _, problems) in built.items():
        problems += [f"variables: {m}" for m in tools.replace_member_variables(bp, read(name, "Variables.txt"))]
    compile_all(False)
    for name, (bp, manifest, problems) in built.items():
        if manifest["kind"] == "WidgetBlueprint" and not tools.replace_widget_tree(bp, read(name, "WidgetTree.t3d")):
            problems.append("widget tree: the text does not hold exactly one root widget")
    compile_all(False)
    # Twice each: a call to a function or custom event imported in the same pass finds nothing to call yet.
    for _ in range(2):
        for name, (bp, manifest, problems) in built.items():
            import_functions(bp, name, manifest, problems)
        compile_all(False)
    for _ in range(2):
        for name, (bp, manifest, problems) in built.items():
            import_event_graphs(bp, name, manifest, problems)
        compile_all(False)
    compile_all(True)
    for bp, _, problems in built.values():
        if not unreal.EditorAssetLibrary.save_loaded_asset(bp, only_if_is_dirty=False):
            problems.append("could not save the asset")
    return built


def build_map(name):
    """Opens or creates the map, replaces its actors and Level Blueprint, saves it, and checks it."""
    manifest = sample_text.read_manifest(name)
    path = manifest["path"]
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        opened = levels.load_level(path)
    else:
        opened = levels.new_level(path)
        print(f"[BUILD] created {path}")
    if not opened:
        raise RuntimeError(f"could not open {path}")
    print(f"[BUILD] {path} (exported with {manifest['exported_with']})")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    problems = []
    actors = read(name, "Actors.t3d")
    pasted = tools.replace_level_actors(world, actors)
    print(f"[BUILD]   {pasted} actors")

    bp = tools.get_level_blueprint(world)
    problems += [f"variables: {m}" for m in tools.replace_member_variables(bp, read(name, "Variables.txt"))]
    tools.compile_blueprint_with_messages(bp)
    for import_graphs in (import_functions, import_functions, import_event_graphs, import_event_graphs):
        import_graphs(bp, name, manifest, problems)
        tools.compile_blueprint_with_messages(bp)
    problems += [f"compile: {m}" for m in tools.compile_blueprint_with_messages(bp)]
    if not levels.save_current_level():
        problems.append("could not save the level")

    expected = sample_text.level_summary(actors)
    actual = sample_text.level_summary(tools.export_level_actors(world))
    problems += sample_text.diff_sets("actor", [f"{k} ({v[0]})" for k, v in expected.items()],
                                      [f"{k} ({v[0]})" for k, v in actual.items()])
    for key in sorted(set(expected) & set(actual)):
        problems += sample_text.diff_sets(f"actor {key} property", expected[key][1], actual[key][1])
    counts = [f"{len([k for k in actual if '/' not in k])} actors"]
    counts += compare_blueprint(bp, name, manifest, problems)
    return report(name, counts, problems)


def main():
    names = sample_text.list_assets()
    maps = [n for n in names if sample_text.read_manifest(n)["kind"] == "Level"]
    blueprints = [n for n in names if n not in maps]
    results = []
    for name, (bp, manifest, problems) in build_blueprints(blueprints).items():
        results.append(report(name, compare_blueprint(bp, name, manifest, problems), problems))
    for name in maps:
        results.append(build_map(name))
    print("[TEST] RESULT: " + ("PASS" if all(results) else "FAIL"))


main()
