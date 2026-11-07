"""Arranges the LoadingFX material graphs with MaterialToolbox's auto layout, in the open UE 5.5 editor.

The builders only decide which nodes each comment box holds. The positions come from this pass, so run it
after every rebuild (see "Graph layout" in CLAUDE.md for how to start the editor with the plugin):

    python Tools/layout_materials.py                  every material and Material Function
    python Tools/layout_materials.py M_LoadingArc     only these assets

The layout measures live Slate widgets, so it needs a GUI editor whose window is not minimized.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

UE_EXEC = Path(__file__).resolve().parent / "ue_exec.py"
FOLDERS = ("/LoadingFX/MaterialFunctions", "/LoadingFX/Materials")
# Room for four lines of comment text. The plugin's default, 64, holds two.
CONFIG = {"comment_pad_top": 130.0}
TIMEOUT_SECONDS = 120


def run(code):
    """Runs Python in the editor and returns its last line of output."""
    result = subprocess.run([sys.executable, str(UE_EXEC), "-c", code], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"The editor command failed:\n{result.stdout}{result.stderr}")
    return result.stdout.strip().splitlines()[-1]


def list_assets():
    code = ("import json, unreal\n"
            f"folders = {FOLDERS!r}\n"
            "unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(list(folders), True)\n"
            "print(json.dumps([p.split('.')[0] for f in folders\n"
            "                  for p in unreal.EditorAssetLibrary.list_assets(f, recursive=False)]))")
    return json.loads(run(code))


def comment_count(path):
    return int(run("import unreal\n"
                   f"a = unreal.load_asset({path!r})\n"
                   "tools = unreal.DevMaterialTools\n"
                   "print(len(tools.get_function_comment_texts(a) if isinstance(a, unreal.MaterialFunction)\n"
                   "          else tools.get_material_comment_texts(a)))"))


def layout(path):
    code = (f"import mtb_auto_layout as m; print(m.layout_asset({path!r}, apply=True, save=True, close=True, "
            f"config={CONFIG!r}))")
    if run(code) != "True":
        return {"ok": False, "message": "the layout was not scheduled"}
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(0.5)
        result = json.loads(run("import mtb_auto_layout as m; print(m.get_last_result_json())"))
        if result.get("state") != "pending":
            return result
    return {"ok": False, "message": f"no result after {TIMEOUT_SECONDS} s"}


def main():
    parser = argparse.ArgumentParser(description="Arrange the LoadingFX material graphs.")
    parser.add_argument("names", nargs="*", help="asset names (default: all)")
    args = parser.parse_args()

    if "ModuleNotFoundError" in run("try:\n    import mtb_auto_layout\n    print('ok')\n"
                                    "except ImportError as e:\n    print('ModuleNotFoundError')"):
        sys.exit("MaterialToolbox is not loaded in the editor (see \"Graph layout\" in CLAUDE.md).")

    assets = list_assets()
    if args.names:
        assets = [a for a in assets if a.rsplit("/", 1)[1] in args.names]
    failed = 0
    for path in assets:
        name = path.rsplit("/", 1)[1]
        comments = comment_count(path)
        result = layout(path)
        kept = result.get("comment_blocks", 0)
        if not result.get("ok") or not result.get("saved"):
            print(f"{name}: FAILED: {result.get('message')}")
            failed += 1
        elif kept != comments:
            # A comment with no node entirely inside its box stays where it is, away from the group it describes.
            print(f"{name}: only {kept} of {comments} comments hold nodes: fix the boxes in its builder")
            failed += 1
        else:
            print(f"{name}: {result['arranged']} nodes, {kept} comments, {result['crossings']} crossings")
    print(f"{len(assets) - failed} of {len(assets)} arranged")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
