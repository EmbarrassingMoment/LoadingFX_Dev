"""
Dot-ring loading spinner (user's own Shadertoy) -> M_LoadingSpinner (Material Domain = UI, Translucent)

円周の 3/4 に 8 個の丸を並べ、先頭(最大)から末尾(最小)へ半径を小さくしながら時計回りに回すロードアイコン。
角度を扇形セルに分け、ピクセルが属するセルの丸だけを評価するのでループ不要。

  p     = (2*TexCoord0 - 1) * (1,-1)                ((2*fragCoord - iResolution.xy) / iResolution.y。
                                                     Shadertoy は y 上向き。正方形ウィジェット前提)
  rot   = Time * Speed
  stepA = TAU * Arc / Count                         (丸 1 個あたりの角度)
  a     = mod(atan(p.y, p.x) + rot, TAU)            (回転座標系でのピクセル角度 0..TAU。mod は MF_GLSLMod)
  id    = floor(a / stepA)                          (扇形セルの番号。0 = 先頭の丸)
  ca    = (id + 0.5) * stepA - rot                  (セル中心の角度を画面座標系へ戻す)
  c     = Ring * vec2(cos(ca), sin(ca))
  r     = mix(RMax, RMin, id / (Count - 1))
  d     = length(p - c) - r
  aa    = fwidth(p.y)                               (2 / iResolution.y。p.y はウィジェット高さで 2.0 進むので
                                                     fwidth(p.y) = 1 ピクセル。fwidth は DDX/DDY で展開)
  mask  = (1 - smoothstep(-aa, aa, d)) * step(id, Count - 0.5)   (id >= Count のセル = 残り 1 - Arc は描かない)

  出力: FinalColor(Emissive) = DotColor、Opacity = mask。
  背景(bg)は不要なので mix(bg, fg, m) は DotColor + アルファに置き換え。

  const -> ScalarParameter / VectorParameter(グループ "LoadingSpinner"、並びは GLSL の宣言順)
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  TAU(2 箇所)と Count(3 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingspinner.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingSpinner"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_MOD_PATH = "/LoadingFX/MaterialFunctions/MF_GLSLMod"
TAU = 6.28318530718
PARAM_GROUP = "LoadingSpinner"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / rotation = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # scalar intermediates / params = gray
C_COL = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)   # coverage / output = white

mf_mod = unreal.load_asset(MF_MOD_PATH)
assert mf_mod, f"required Material Function not found: {MF_MOD_PATH}"

if lib.does_asset_exist(FULL_PATH):
    lib.delete_asset(FULL_PATH)
mat = tools.create_asset(ASSET_NAME, ASSET_PATH, unreal.Material, unreal.MaterialFactoryNew())
mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_UI)
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
print(f"[TEST] Created material: {FULL_PATH} (UI / Translucent)")

def expr(cls, x, y, **props):
    n = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n

results = []
def _connect(frm, out_name, to, in_name):
    ok = mel.connect_material_expressions(frm, out_name, to, in_name)
    if not ok:
        print(f"[TEST] FAILED connect: {frm.get_class().get_name()}('{out_name}') -> "
              f"{to.get_class().get_name()}('{in_name}')")
    results.append(ok)
    return ok

decls = {}
def make_decl(name, src, x, y, color):
    dcl = expr(unreal.MaterialExpressionNamedRerouteDeclaration, x, y, name=name, node_color=color)
    _connect(src, "", dcl, "")
    decls[name] = dcl
    return dcl

def use(name, x, y):
    return smt.create_named_reroute_usage(mat, decls[name], x, y)

def scalar_param(name, default, sort, desc, x, y):
    return expr(unreal.MaterialExpressionScalarParameter, x, y,
                parameter_name=name, default_value=default, group=PARAM_GROUP,
                sort_priority=sort, desc=desc)

def mask_x(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=True, g=False, b=False, a=False)

def mask_y(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=False, g=True, b=False, a=False)

# ---- const TAU (used twice -> Named Reroute) ----
tau_c = expr(unreal.MaterialExpressionConstant, -4250, -1000, r=TAU)
make_decl("TAU", tau_c, -4050, -1000, C_SC)

# ---- const COUNT (used three times -> Named Reroute) ----
count_p = scalar_param("Count", 8.0, 0, "Number of dots (integer, 2 or more)", -4250, -720)
make_decl("Count", count_p, -4000, -720, C_SC)

# ---- p = (2*TexCoord0 - 1) * (1,-1)  (Shadertoy is y-up; square widget assumed) ----
texc = expr(unreal.MaterialExpressionTextureCoordinate, -4250, -400)
mul2 = expr(unreal.MaterialExpressionMultiply, -4100, -400, const_b=2.0)
_connect(texc, "", mul2, "A")
sub1 = expr(unreal.MaterialExpressionSubtract, -3950, -400, const_b=1.0)
_connect(mul2, "", sub1, "A")
yflip_c = expr(unreal.MaterialExpressionConstant2Vector, -3950, -280, r=1.0, g=-1.0)
p_v = expr(unreal.MaterialExpressionMultiply, -3800, -350)
_connect(sub1, "", p_v, "A")
_connect(yflip_c, "", p_v, "B")
make_decl("p", p_v, -3650, -350, C_UV)

# ---- rot = Time * Speed  (rotation angle in radians) ----
time_n = expr(unreal.MaterialExpressionTime, -4250, 50)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 4.0, 5, "Rotation speed (rad/s). Positive = clockwise", -4250, 150)
rot_v = expr(unreal.MaterialExpressionMultiply, -4000, 100)
_connect(time_n, "", rot_v, "A")
_connect(speed_p, "", rot_v, "B")
make_decl("rot", rot_v, -3850, 100, C_TM)

# ---- stepA = TAU * Arc / Count  (angle taken by one dot) ----
tau_u1 = use("TAU", -3150, -950)
arc_p = scalar_param("Arc", 0.75, 1,
                     "Fraction of the circle covered by the row of dots (0.75 = 3/4 turn)", -3150, -850)
tau_arc = expr(unreal.MaterialExpressionMultiply, -2900, -900)
_connect(tau_u1, "", tau_arc, "A")
_connect(arc_p, "", tau_arc, "B")
count_u1 = use("Count", -2900, -780)
step_div = expr(unreal.MaterialExpressionDivide, -2750, -850)
_connect(tau_arc, "", step_div, "A")
_connect(count_u1, "", step_div, "B")
make_decl("stepA", step_div, -2600, -850, C_SC)

# ---- aa = 2 / iResolution.y = fwidth(p.y)  (fwidth expanded with DDX/DDY) ----
p_u1 = use("p", -3150, -380)
p_y1 = mask_y(-3000, -380)
_connect(p_u1, "", p_y1, "")
p_ddx = expr(unreal.MaterialExpressionDDX, -2850, -440)
p_ddy = expr(unreal.MaterialExpressionDDY, -2850, -320)
_connect(p_y1, "", p_ddx, "")
_connect(p_y1, "", p_ddy, "")
abs_dx = expr(unreal.MaterialExpressionAbs, -2700, -440)
abs_dy = expr(unreal.MaterialExpressionAbs, -2700, -320)
_connect(p_ddx, "", abs_dx, "")
_connect(p_ddy, "", abs_dy, "")
aa_v = expr(unreal.MaterialExpressionAdd, -2550, -380)
_connect(abs_dx, "", aa_v, "A")
_connect(abs_dy, "", aa_v, "B")
make_decl("aa", aa_v, -2400, -380, C_SDF)

# ---- a = mod(atan(p.y, p.x) + rot, TAU)  (pixel angle in the rotating frame, 0..TAU) ----
p_u2 = use("p", -3150, 80)
p_y2 = mask_y(-3000, 80)
_connect(p_u2, "", p_y2, "")
p_u3 = use("p", -3150, 200)
p_x = mask_x(-3000, 200)
_connect(p_u3, "", p_x, "")
a_atan = expr(unreal.MaterialExpressionArctangent2, -2850, 130)   # atan2(Y, X) = GLSL atan(y, x)
_connect(p_y2, "", a_atan, "Y")
_connect(p_x, "", a_atan, "X")
rot_u1 = use("rot", -2850, 280)
a_rot = expr(unreal.MaterialExpressionAdd, -2700, 180)
_connect(a_atan, "", a_rot, "A")
_connect(rot_u1, "", a_rot, "B")
tau_u2 = use("TAU", -2700, 330)
# mod(x, y) via MF_GLSLMod (never inline / Fmod).
a_mod = expr(unreal.MaterialExpressionMaterialFunctionCall, -2550, 230, material_function=mf_mod)
_connect(a_rot, "", a_mod, "X")
_connect(tau_u2, "", a_mod, "Y")
make_decl("a", a_mod, -2350, 230, C_UV)

# ---- id = floor(a / stepA)  (index of the wedge-shaped cell; 0 = leading dot) ----
a_u1 = use("a", -1900, 180)
stepa_u1 = use("stepA", -1900, 280)
a_div = expr(unreal.MaterialExpressionDivide, -1750, 230)
_connect(a_u1, "", a_div, "A")
_connect(stepa_u1, "", a_div, "B")
id_floor = expr(unreal.MaterialExpressionFloor, -1600, 230)
_connect(a_div, "", id_floor, "")
make_decl("id", id_floor, -1450, 230, C_SC)

# ---- ca = (id + 0.5) * stepA - rot  (angle of the cell center, back in the screen frame) ----
id_u1 = use("id", -1050, 100)
id_half = expr(unreal.MaterialExpressionAdd, -900, 100, const_b=0.5)
_connect(id_u1, "", id_half, "A")
stepa_u2 = use("stepA", -900, 220)
ca_mul = expr(unreal.MaterialExpressionMultiply, -750, 150)
_connect(id_half, "", ca_mul, "A")
_connect(stepa_u2, "", ca_mul, "B")
rot_u2 = use("rot", -750, 290)
ca_v = expr(unreal.MaterialExpressionSubtract, -600, 200)
_connect(ca_mul, "", ca_v, "A")
_connect(rot_u2, "", ca_v, "B")
make_decl("ca", ca_v, -450, 200, C_UV)

# ---- c = Ring * vec2(cos(ca), sin(ca))  (dot center on the ring) ----
ca_u1 = use("ca", -150, 120)
ca_cos = expr(unreal.MaterialExpressionCosine, 0, 120, period=TAU)   # period 2*PI = radians
_connect(ca_u1, "", ca_cos, "")
ca_u2 = use("ca", -150, 240)
ca_sin = expr(unreal.MaterialExpressionSine, 0, 240, period=TAU)
_connect(ca_u2, "", ca_sin, "")
dir_v = expr(unreal.MaterialExpressionAppendVector, 150, 180)
_connect(ca_cos, "", dir_v, "A")
_connect(ca_sin, "", dir_v, "B")
ring_p = scalar_param("Ring", 0.55, 2,
                      "Radius of the circle the dots sit on (widget half height = 1.0)", 100, 330)
c_v = expr(unreal.MaterialExpressionMultiply, 350, 230)
_connect(ring_p, "", c_v, "A")
_connect(dir_v, "", c_v, "B")
make_decl("c", c_v, 500, 230, C_UV)

# ---- r = mix(RMax, RMin, id / (Count - 1))  (the larger the id, the smaller the dot) ----
id_u2 = use("id", -1050, 800)
count_u2 = use("Count", -1050, 920)
count_m1 = expr(unreal.MaterialExpressionSubtract, -900, 920, const_b=1.0)
_connect(count_u2, "", count_m1, "A")
id_t = expr(unreal.MaterialExpressionDivide, -750, 850)
_connect(id_u2, "", id_t, "A")
_connect(count_m1, "", id_t, "B")
rmax_p = scalar_param("RMax", 0.14, 3,
                      "Radius of the leading (largest) dot. Keep below Ring * sin(PI * Arc / Count)", -650, 580)
rmin_p = scalar_param("RMin", 0.03, 4, "Radius of the trailing (smallest) dot", -650, 680)
r_v = expr(unreal.MaterialExpressionLinearInterpolate, -400, 700)
_connect(rmax_p, "", r_v, "A")
_connect(rmin_p, "", r_v, "B")
_connect(id_t, "", r_v, "Alpha")
make_decl("r", r_v, -250, 700, C_SDF)

# ---- d = length(p - c) - r  (circle SDF of the dot that owns this cell) ----
p_u4 = use("p", 950, 150)
c_u1 = use("c", 950, 250)
pc_sub = expr(unreal.MaterialExpressionSubtract, 1100, 200)
_connect(p_u4, "", pc_sub, "A")
_connect(c_u1, "", pc_sub, "B")
pc_len = expr(unreal.MaterialExpressionLength, 1250, 200)
_connect(pc_sub, "", pc_len, "")
r_u1 = use("r", 1250, 320)
d_v = expr(unreal.MaterialExpressionSubtract, 1400, 250)
_connect(pc_len, "", d_v, "A")
_connect(r_u1, "", d_v, "B")
make_decl("d", d_v, 1550, 250, C_SDF)

# ---- mask = (1 - smoothstep(-aa, aa, d)) * step(id, Count - 0.5) ----
aa_u1 = use("aa", 2000, 50)
aa_neg = expr(unreal.MaterialExpressionMultiply, 2150, 0, const_b=-1.0)
_connect(aa_u1, "", aa_neg, "A")
d_u1 = use("d", 2000, 200)
edge = expr(unreal.MaterialExpressionSmoothStep, 2300, 80)
_connect(aa_neg, "", edge, "Min")
_connect(aa_u1, "", edge, "Max")
_connect(d_u1, "", edge, "Value")
dot_cov = expr(unreal.MaterialExpressionOneMinus, 2450, 80)
_connect(edge, "", dot_cov, "")
id_u3 = use("id", 2000, 400)
count_u3 = use("Count", 2000, 500)
count_half = expr(unreal.MaterialExpressionSubtract, 2150, 500, const_b=0.5)
_connect(count_u3, "", count_half, "A")
# UE Step(Y, X) returns 1 when X >= Y, i.e. GLSL step(edge=Y, x=X).
# GLSL step(id, COUNT - 0.5) therefore maps to Y = id (edge), X = Count - 0.5.
drawn = expr(unreal.MaterialExpressionStep, 2300, 430)
_connect(id_u3, "", drawn, "Y")
_connect(count_half, "", drawn, "X")
m_v = expr(unreal.MaterialExpressionMultiply, 2600, 250)
_connect(dot_cov, "", m_v, "A")
_connect(drawn, "", m_v, "B")
make_decl("mask", m_v, 2750, 250, C_COL)

# ---- Output: FinalColor = DotColor, Opacity = mask  (bg dropped) ----
dotcolor_p = expr(unreal.MaterialExpressionVectorParameter, 3150, 0,
                  parameter_name="DotColor", default_value=unreal.LinearColor(0.95, 0.95, 0.95, 1.0),
                  group=PARAM_GROUP, sort_priority=6, desc="Dot color")
results.append(mel.connect_material_property(dotcolor_p, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 3150, 300)
results.append(mel.connect_material_property(mask_u1, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "const TAU = 2*PI   (used twice -> Named Reroute)",
    -4300, -1100, 550, 230, C_SC)
smt.create_comment_in_material(
    mat, "const COUNT -> ScalarParameter (used three times -> Named Reroute).\n"
         "Arc / Ring / RMax / RMin / Speed / DotColor are wired directly at their single use site",
    -4300, -840, 650, 260, C_SC)
smt.create_comment_in_material(
    mat, "p = (2*TexCoord0 - 1) * (1,-1)   (= (2*fragCoord - iResolution.xy) / iResolution.y)\n"
         "Y flipped (Shadertoy is y-up). Square widget assumed: widget half height = 1.0",
    -4300, -520, 900, 400, C_UV)
smt.create_comment_in_material(
    mat, "rot = Time * Speed   (rotation angle in radians)",
    -4300, -60, 700, 360, C_TM)
smt.create_comment_in_material(
    mat, "stepA = TAU * Arc / Count   (angle taken by one dot)",
    -3200, -1060, 850, 420, C_SC)
smt.create_comment_in_material(
    mat, "aa = 2 / iResolution.y = fwidth(p.y)\n"
         "p.y spans 2.0 over the widget height, so fwidth(p.y) is one pixel (DDX/DDY expansion)",
    -3200, -560, 1050, 400, C_SDF)
smt.create_comment_in_material(
    mat, "a = mod(atan(p.y, p.x) + rot, TAU)\n"
         "Pixel angle in the rotating frame, normalized to 0..TAU (mod via MF_GLSLMod)",
    -3200, -60, 1100, 520, C_UV)
smt.create_comment_in_material(
    mat, "id = floor(a / stepA)\n"
         "Index of the wedge-shaped cell the pixel is in (0 = leading dot)",
    -1950, 60, 750, 360, C_SC)
smt.create_comment_in_material(
    mat, "ca = (id + 0.5) * stepA - rot\n"
         "Angle of the cell center, rotated back to the screen frame",
    -1100, -40, 900, 470, C_UV)
smt.create_comment_in_material(
    mat, "c = Ring * vec2(cos(ca), sin(ca))   (dot center on the ring)\n"
         "Sine / Cosine period = 2*PI -> radians",
    -200, -40, 950, 500, C_UV)
smt.create_comment_in_material(
    mat, "r = mix(RMax, RMin, id / (Count - 1))\n"
         "The larger the id, the smaller the dot (leading dot = RMax, trailing dot = RMin)",
    -1100, 460, 1100, 600, C_SDF)
smt.create_comment_in_material(
    mat, "d = length(p - c) - r   (circle SDF of the dot that owns this cell)",
    900, 40, 900, 400, C_SDF)
smt.create_comment_in_material(
    mat, "mask = (1 - smoothstep(-aa, aa, d)) * step(id, Count - 0.5)\n"
         "Anti-aliased dot. Cells with id >= Count (the remaining 1 - Arc of the circle) are not drawn",
    1950, -120, 1050, 760, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = DotColor, Opacity = mask\n"
         "Background dropped: mix(bg, fg, m) becomes DotColor with alpha = mask",
    3100, -120, 600, 560, C_COL)

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
decl_names, usage_count, param_names, mf_calls = [], {}, [], 0
for e in smt.get_material_expressions(mat):
    if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
        decl_names.append(str(e.get_editor_property("name")))
    elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
        nm = smt.get_named_reroute_usage_display_name(e)
        usage_count[nm] = usage_count.get(nm, 0) + 1
    elif isinstance(e, (unreal.MaterialExpressionScalarParameter,
                        unreal.MaterialExpressionVectorParameter)):
        param_names.append(str(e.get_editor_property("parameter_name")))
    elif isinstance(e, unreal.MaterialExpressionMaterialFunctionCall):
        mf_calls += 1
print(f"[TEST] {ASSET_NAME} decls: {sorted(decl_names)}")
print(f"[TEST] {ASSET_NAME} usages: {dict(sorted(usage_count.items()))}")
print(f"[TEST] {ASSET_NAME} params: {sorted(param_names)}")
print(f"[TEST] {ASSET_NAME} MF calls: {mf_calls}")

expected_decls = sorted(["TAU", "Count", "p", "rot", "stepA", "aa", "a", "id", "ca", "c", "r", "d", "mask"])
expected_usages = {"TAU": 2, "Count": 3, "p": 4, "rot": 2, "stepA": 2, "aa": 1, "a": 1, "id": 3,
                   "ca": 2, "c": 1, "r": 1, "d": 1, "mask": 1}
expected_params = sorted(["Count", "Arc", "Ring", "RMax", "RMin", "Speed", "DotColor"])
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == expected_params
mf_ok = mf_calls == 1
comments_ok = len(smt.get_material_comment_texts(mat)) == 14
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
