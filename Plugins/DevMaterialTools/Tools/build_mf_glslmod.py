"""
GLSL mod(x, y) = x - y * floor(x / y) を Material Function 化。
HLSL の fmod (trunc ベース) と異なり、負の x でも結果の符号が y に従う。
Shadertoy 移植時の角度折り畳み・ドメインリピート用(スカラー入出力)。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_mf_glslmod.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

MF_PATH = "/LoadingFX/MaterialFunctions"
MF_NAME = "MF_GLSLMod"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

results = []
def _connect(frm, out_name, to, in_name):
    ok = mel.connect_material_expressions(frm, out_name, to, in_name)
    if not ok:
        print(f"[TEST] FAILED connect: {frm.get_class().get_name()}('{out_name}') -> "
              f"{to.get_class().get_name()}('{in_name}')")
    results.append(ok)
    return ok

def vec4(x, y, z, w):
    v = unreal.Vector4f()
    v.set_editor_properties({"x": x, "y": y, "z": z, "w": w})
    return v

full = f"{MF_PATH}/{MF_NAME}"
if lib.does_asset_exist(full):
    lib.delete_asset(full)
fn = tools.create_asset(MF_NAME, MF_PATH, unreal.MaterialFunction,
                        unreal.MaterialFunctionFactoryNew())
fn.set_editor_property("description",
    "GLSL mod: x - y * floor(x / y). "
    "Unlike HLSL fmod (trunc-based), the result has the sign of y, "
    "so it stays correct for negative x (angle folding, domain repeat).")
fn.set_editor_property("expose_to_library", True)

def expr(cls, x, y):
    return mel.create_material_expression_in_function(fn, cls, x, y)

x_in = expr(unreal.MaterialExpressionFunctionInput, -900, -60)
x_in.set_editor_property("input_name", "X")
x_in.set_editor_property("input_type", unreal.FunctionInputType.FUNCTION_INPUT_SCALAR)
x_in.set_editor_property("sort_priority", 0)
x_in.set_editor_property("preview_value", vec4(0.0, 0.0, 0.0, 0.0))

y_in = expr(unreal.MaterialExpressionFunctionInput, -900, 100)
y_in.set_editor_property("input_name", "Y")
y_in.set_editor_property("input_type", unreal.FunctionInputType.FUNCTION_INPUT_SCALAR)
y_in.set_editor_property("sort_priority", 1)
y_in.set_editor_property("preview_value", vec4(1.0, 0.0, 0.0, 0.0))

div = expr(unreal.MaterialExpressionDivide, -700, 20)
_connect(x_in, "", div, "A")
_connect(y_in, "", div, "B")

flr = expr(unreal.MaterialExpressionFloor, -560, 20)
_connect(div, "", flr, "")

mul = expr(unreal.MaterialExpressionMultiply, -420, 60)
_connect(y_in, "", mul, "A")
_connect(flr, "", mul, "B")

sub = expr(unreal.MaterialExpressionSubtract, -280, -20)
_connect(x_in, "", sub, "A")
_connect(mul, "", sub, "B")

out = expr(unreal.MaterialExpressionFunctionOutput, -130, -20)
out.set_editor_property("output_name", "Result")
_connect(sub, "", out, "")

smt.create_comment_in_function(
    fn, "GLSL mod(x, y) = x - y * floor(x / y)  (sign follows y, unlike HLSL fmod)",
    -750, -140, 620, 340, unreal.LinearColor(0.6, 1.0, 0.2, 1.0))

mel.update_material_function(fn)
lib.save_asset(full)

# 検証: ノード構成の確認
counts = {}
for e in smt.get_material_function_expressions(fn):
    cn = e.get_class().get_name()
    counts[cn] = counts.get(cn, 0) + 1
print(f"[TEST] {MF_NAME} nodes: {dict(sorted(counts.items()))}")
expected = {
    "MaterialExpressionFunctionInput": 2,
    "MaterialExpressionDivide": 1,
    "MaterialExpressionFloor": 1,
    "MaterialExpressionMultiply": 1,
    "MaterialExpressionSubtract": 1,
    "MaterialExpressionFunctionOutput": 1,
}
nodes_ok = counts == expected
comments_ok = len(smt.get_function_comment_texts(fn)) == 1

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = all(results) and nodes_ok and comments_ok
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
