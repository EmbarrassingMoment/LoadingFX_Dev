"""
Prototype only: duplicates M_LoadingDotRing into /Game/Prototype/M_LoadingDotRing_GameTime with the Time node's
Ignore Pause turned off (= View.GameTime), so the verification prototype can show RealTime and GameTime side by side
while the game thread is blocked. Run build_all.py first.

Usage:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_proto_gametime_variant.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan (see the builder scripts).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX", "/Game/Prototype"], True)

SRC_PATH = "/LoadingFX/Materials/M_LoadingDotRing"
DST_PATH = "/Game/Prototype/M_LoadingDotRing_GameTime"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools

assert lib.does_asset_exist(SRC_PATH), f"source material not found: {SRC_PATH} (run build_all.py first)"
if lib.does_asset_exist(DST_PATH):
    lib.delete_asset(DST_PATH)

mat = lib.duplicate_asset(SRC_PATH, DST_PATH)
assert mat, f"failed to duplicate {SRC_PATH} -> {DST_PATH}"

time_nodes = [e for e in smt.get_material_expressions(mat) if isinstance(e, unreal.MaterialExpressionTime)]
for node in time_nodes:
    node.set_editor_property("ignore_pause", False)

mel.recompile_material(mat)
saved = lib.save_asset(DST_PATH)

print(f"[TEST] {DST_PATH}: Time nodes = {len(time_nodes)}, saved = {saved}")
passed = (len(time_nodes) == 1 and saved
          and all(not n.get_editor_property("ignore_pause") for n in time_nodes))
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
