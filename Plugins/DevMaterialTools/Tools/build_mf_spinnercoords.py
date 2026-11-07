"""
UI スピナー共通の座標系を Material Function 化 -> MF_SpinnerCoords。
ウィジェットのピクセルサイズを UV のスクリーン微分から求めるので、パラメータ不要・素の UMG Image でも動く。

  uv        = TexCoord0
  fw        = abs(ddx(uv)) + abs(ddy(uv))      (1 ピクセルあたりの UV。fw = (1/幅, 1/高さ) ピクセル)
  m         = max(fw.x, fw.y)                  (= 1 / 短辺ピクセル数)
  P         = (2*uv - 1) * (m / fw) * (1,-1)   (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも真円のまま中央に収まる)
  PixelSize = 2 * m                            (1 ピクセルを P 単位で。AA 幅用)
  Extent    = m / fw                           (ウィジェットの半幅・半高を P 単位で。短辺側は 1、長辺側は縦横比。
                                                横に伸びるバー系のマテリアルが幅いっぱいに描くために使う。2026-10-16 追加)

fw は回転(RenderTransform)しても縦横比が保たれる(|cos|+|sin| が両軸で共通)。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_mf_spinnercoords.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

MF_PATH = "/LoadingFX/MaterialFunctions"
MF_NAME = "MF_SpinnerCoords"
FULL_PATH = f"{MF_PATH}/{MF_NAME}"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # pixel size / AA = green

if lib.does_asset_exist(FULL_PATH):
    lib.delete_asset(FULL_PATH)
fn = tools.create_asset(MF_NAME, MF_PATH, unreal.MaterialFunction, unreal.MaterialFunctionFactoryNew())
fn.set_editor_property("description",
    "Coordinates for UI spinner materials. P: y-up, (0,0) at the widget center, the shorter side spans -1..1, "
    "so shapes stay round and fit inside a non-square widget. PixelSize: one screen pixel in P units "
    "(anti-aliasing width). Extent: the widget's half extents in P units (1 on the shorter side, the aspect "
    "ratio on the longer one), for shapes that stretch along the widget such as bars. "
    "The widget size comes from the UV screen derivatives: no parameters needed.")
fn.set_editor_property("expose_to_library", True)

results = []
def _connect(frm, out_name, to, in_name):
    ok = mel.connect_material_expressions(frm, out_name, to, in_name)
    if not ok:
        print(f"[TEST] FAILED connect: {frm.get_class().get_name()}('{out_name}') -> "
              f"{to.get_class().get_name()}('{in_name}')")
    results.append(ok)
    return ok

def fnode(cls, x, y, **props):
    n = mel.create_material_expression_in_function(fn, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n

fdecls = {}
def fdecl(name, src, x, y, color):
    dcl = fnode(unreal.MaterialExpressionNamedRerouteDeclaration, x, y, name=name, node_color=color)
    _connect(src, "", dcl, "")
    fdecls[name] = dcl
    return dcl

def fuse(name, x, y):
    return smt.create_named_reroute_usage_in_function(fn, fdecls[name], x, y)

def mask_x(x, y):
    return fnode(unreal.MaterialExpressionComponentMask, x, y, r=True, g=False, b=False, a=False)

def mask_y(x, y):
    return fnode(unreal.MaterialExpressionComponentMask, x, y, r=False, g=True, b=False, a=False)

# ---- uv = TexCoord0 ----
texc = fnode(unreal.MaterialExpressionTextureCoordinate, -1600, 0)
fdecl("uv", texc, -1400, 0, C_UV)

# ---- fw = abs(ddx(uv)) + abs(ddy(uv))  (UV per screen pixel, per axis) ----
uv_u1 = fuse("uv", -1150, -400)
uv_u2 = fuse("uv", -1150, -280)
uv_ddx = fnode(unreal.MaterialExpressionDDX, -1000, -400)
uv_ddy = fnode(unreal.MaterialExpressionDDY, -1000, -280)
_connect(uv_u1, "", uv_ddx, "")
_connect(uv_u2, "", uv_ddy, "")
abs_dx = fnode(unreal.MaterialExpressionAbs, -850, -400)
abs_dy = fnode(unreal.MaterialExpressionAbs, -850, -280)
_connect(uv_ddx, "", abs_dx, "")
_connect(uv_ddy, "", abs_dy, "")
fw_v = fnode(unreal.MaterialExpressionAdd, -700, -340)
_connect(abs_dx, "", fw_v, "A")
_connect(abs_dy, "", fw_v, "B")
fdecl("fw", fw_v, -550, -340, C_SDF)

# ---- m = max(fw.x, fw.y)  (= 1 / shorter side in pixels) ----
fw_u1 = fuse("fw", -300, -400)
fw_u2 = fuse("fw", -300, -280)
fw_x = mask_x(-150, -400)
fw_y = mask_y(-150, -280)
_connect(fw_u1, "", fw_x, "")
_connect(fw_u2, "", fw_y, "")
m_v = fnode(unreal.MaterialExpressionMax, 0, -340)
_connect(fw_x, "", m_v, "A")
_connect(fw_y, "", m_v, "B")
fdecl("m", m_v, 150, -340, C_SDF)

# ---- P = (2*uv - 1) * (m / fw) * (1,-1) ----
uv_u3 = fuse("uv", -1150, 100)
mul2 = fnode(unreal.MaterialExpressionMultiply, -1000, 100, const_b=2.0)
_connect(uv_u3, "", mul2, "A")
sub1 = fnode(unreal.MaterialExpressionSubtract, -850, 100, const_b=1.0)
_connect(mul2, "", sub1, "A")
m_u1 = fuse("m", -300, 200)
fw_u3 = fuse("fw", -300, 300)
aspect = fnode(unreal.MaterialExpressionDivide, -150, 250)   # m / fw: also the Extent output below
_connect(m_u1, "", aspect, "A")
_connect(fw_u3, "", aspect, "B")
scaled = fnode(unreal.MaterialExpressionMultiply, 0, 150)
_connect(sub1, "", scaled, "A")
_connect(aspect, "", scaled, "B")
yflip_c = fnode(unreal.MaterialExpressionConstant2Vector, 0, 300, r=1.0, g=-1.0)
p_v = fnode(unreal.MaterialExpressionMultiply, 150, 200)
_connect(scaled, "", p_v, "A")
_connect(yflip_c, "", p_v, "B")
p_out = fnode(unreal.MaterialExpressionFunctionOutput, 350, 200, output_name="P", sort_priority=0,
              description="y-up, (0,0) at the widget center, shorter side spans -1..1")
_connect(p_v, "", p_out, "")

# ---- PixelSize = 2 * m ----
m_u2 = fuse("m", 150, -200)
px_v = fnode(unreal.MaterialExpressionMultiply, 300, -200, const_b=2.0)
_connect(m_u2, "", px_v, "A")
px_out = fnode(unreal.MaterialExpressionFunctionOutput, 450, -200, output_name="PixelSize", sort_priority=1,
               description="One screen pixel in P units (anti-aliasing width)")
_connect(px_v, "", px_out, "")

# ---- Extent = m / fw  (half extents of the widget in P units: 1 on the shorter side, width / height or height / width on the longer) ----
ext_out = fnode(unreal.MaterialExpressionFunctionOutput, 350, 450, output_name="Extent", sort_priority=2,
                description="Half extents of the widget in P units: (1, 1) when square, the aspect ratio on the longer side. For bars that span the widget")
_connect(aspect, "", ext_out, "")

# ---- Comments (English) ----
smt.create_comment_in_function(
    fn, "Widget size\n"
        "fw is (1 / width, 1 / height) in pixels, so no size parameter is needed. Rotation keeps the ratio: "
        "|cos| + |sin| scales both axes alike.",
    -1200, -500, 1500, 320, C_SDF)
smt.create_comment_in_function(
    fn, "Aspect correction\n"
        "The shorter side spans -1..1, so round shapes stay round in a non-square widget.",
    -1200, 0, 1450, 430, C_UV)

mel.update_material_function(fn)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
decl_names, usage_count, outputs = [], {}, []
for e in smt.get_material_function_expressions(fn):
    if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
        decl_names.append(str(e.get_editor_property("name")))
    elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
        nm = smt.get_named_reroute_usage_display_name(e)
        usage_count[nm] = usage_count.get(nm, 0) + 1
    elif isinstance(e, unreal.MaterialExpressionFunctionOutput):
        outputs.append(str(e.get_editor_property("output_name")))
print(f"[TEST] {MF_NAME} decls: {sorted(decl_names)}")
print(f"[TEST] {MF_NAME} usages: {dict(sorted(usage_count.items()))}")
print(f"[TEST] {MF_NAME} outputs: {sorted(outputs)}")

decls_ok = sorted(decl_names) == ["fw", "m", "uv"]
usages_ok = usage_count == {"uv": 3, "fw": 3, "m": 2}
outputs_ok = sorted(outputs) == ["Extent", "P", "PixelSize"]
comments_ok = len(smt.get_function_comment_texts(fn)) == 2

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = all(results) and decls_ok and usages_ok and outputs_ok and comments_ok and saved
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
