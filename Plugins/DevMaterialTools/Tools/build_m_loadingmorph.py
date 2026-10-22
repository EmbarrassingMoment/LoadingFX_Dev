"""
Morphing square -> M_LoadingMorph (Material Domain = UI, Translucent)

角丸の正方形が時計回りに 90° 回り、回る途中で角が丸まって円になり、また正方形に戻って止まるロードアイコン(1 色)。
デザインは 2026-10-14 のスピナー案第 3 弾の 6 番。WebGL2 のスケッチ(Saved/MorphHarness/harness.html)で確かめてから組んだ。
距離関数は M_LoadingBoxes と同じ MF_SdRoundBox2D(build_m_loadingboxes.py が作る)。clamp(x, 0, 1) は Saturate で書く。

  p     = MF_SpinnerCoords.P                        (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa    = MF_SpinnerCoords.PixelSize                (1 ピクセルを p 単位で)
  時間側(ピクセルに依存しないスカラー計算):
    u = fract(Time * Speed)                         (Speed は 1 秒あたりの 90° の回転の回数)
    e = smoothstep(0, TurnFraction, u)              (回転の進み 0..1。サイクルの残りは止まる)
    正方形は 90° 回すと元と同じ形なので、角度は e だけで決まる(1 回ごとの累積は要らない)。
    c, s = cos / sin(e * 90°)                       (Sine / Cosine は period 4 = 入力 1 で 1/4 回転)
    r = lerp(CornerRadius, HalfSize, Roundness * sin(e * 180°))   (period 2。回転の中間で最も丸く、Roundness 1 なら円)
  q = (c * p.x - s * p.y, s * p.x + c * p.y)        (ピクセルを逆向きに回す = 正方形が時計回りに回る)
  d = sdRoundBox(q, (HalfSize, HalfSize), r)        (MF_SdRoundBox2D)
  mask = saturate(0.5 - d / aa)

  デフォルトの外寸: 止まっている間は HalfSize = 0.72(材質契約の基準正方形)。回る途中は角が x / y 方向へ出るが、
  同時に丸まるので最大 0.786(e = 0.16 と 0.84 のとき。基準円 0.8 の内側)。Roundness を下げると丸まりが減り、
  Roundness 0 では 45° のときに HalfSize * sqrt(2) - (sqrt(2) - 1) * CornerRadius = 0.964 まで出る。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(PARAM_GROUPS、表示順は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  HalfSize(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingmorph.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingMorph"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
MF_BOX_PATH = "/LoadingFX/MaterialFunctions/MF_SdRoundBox2D"
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "HalfSize": "Shape",
    "CornerRadius": "Shape",
    "Roundness": "Shape",
    "Speed": "Motion",
    "TurnFraction": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / rotation = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / turn progress = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # params = gray
C_COL = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)   # coverage / output = white

mf_coords = unreal.load_asset(MF_COORDS_PATH)
assert mf_coords, f"required Material Function not found: {MF_COORDS_PATH}"
mf_box = unreal.load_asset(MF_BOX_PATH)
assert mf_box, f"required Material Function not found: {MF_BOX_PATH} (run build_m_loadingboxes.py first)"

if lib.does_asset_exist(FULL_PATH):
    lib.delete_asset(FULL_PATH)

results = []
def _connect(frm, out_name, to, in_name):
    ok = mel.connect_material_expressions(frm, out_name, to, in_name)
    if not ok:
        print(f"[TEST] FAILED connect: {frm.get_class().get_name()}('{out_name}') -> "
              f"{to.get_class().get_name()}('{in_name}')")
    results.append(ok)
    return ok

mat = tools.create_asset(ASSET_NAME, ASSET_PATH, unreal.Material, unreal.MaterialFactoryNew())
mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_UI)
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
print(f"[TEST] Created material: {FULL_PATH} (UI / Translucent)")

def expr(cls, x, y, **props):
    n = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n

decls = {}
def make_decl(name, src, x, y, color, out_name=""):
    dcl = expr(unreal.MaterialExpressionNamedRerouteDeclaration, x, y, name=name, node_color=color)
    _connect(src, out_name, dcl, "")
    decls[name] = dcl
    return dcl

def use(name, x, y):
    return smt.create_named_reroute_usage(mat, decls[name], x, y)

def scalar_param(name, default, sort, desc, x, y):
    return expr(unreal.MaterialExpressionScalarParameter, x, y,
                parameter_name=name, default_value=default, group=PARAM_GROUPS[name],
                sort_priority=sort, desc=desc)

def binary(cls, a, b, x, y):
    n = expr(cls, x, y)
    _connect(a, "", n, "A")
    _connect(b, "", n, "B")
    return n

def mask_x(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=True, g=False, b=False, a=False)

def mask_y(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=False, g=True, b=False, a=False)

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -2600, -700, material_function=mf_coords)
make_decl("p", coords, -2300, -750, C_UV, "P")
make_decl("aa", coords, -2300, -630, C_SDF, "PixelSize")

# ---- Shared parameter ----
# Footprint (material contract): HalfSize = 0.72 at rest; at most 0.786 along x or y while it turns (Roundness 1).
half_p = scalar_param("HalfSize", 0.72, 0,
                      "Half width of the square at rest (half the shorter widget side = 1.0)", -2800, -400)
make_decl("HalfSize", half_p, -2550, -400, C_SC)

# ---- u = fract(Time * Speed);  e = smoothstep(0, TurnFraction, u) ----
time_n = expr(unreal.MaterialExpressionTime, -2800, 200)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.5, 0,
                       "Quarter turns per second (each one rounds the square off and back). Positive = clockwise",
                       -2800, 320)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -2600, 250)
u_frac = expr(unreal.MaterialExpressionFrac, -2450, 250)
_connect(t_speed, "", u_frac, "")
turnf_p = scalar_param("TurnFraction", 0.6, 1,
                       "Share of a cycle spent turning; the rest is a pause (above 0, up to 1)", -2450, 380)
e_ss = expr(unreal.MaterialExpressionSmoothStep, -2250, 300, const_min=0.0)
_connect(u_frac, "", e_ss, "Value")
_connect(turnf_p, "", e_ss, "Max")
make_decl("e", e_ss, -2100, 300, C_TM)

# ---- c, s = cos / sin(e * 90 degrees)  (period 4: an input of 1 is a quarter turn) ----
e_u1 = use("e", -1850, -350)
c_cos = expr(unreal.MaterialExpressionCosine, -1700, -400, period=4.0)
_connect(e_u1, "", c_cos, "")
make_decl("c", c_cos, -1550, -400, C_UV)
s_sin = expr(unreal.MaterialExpressionSine, -1700, -280, period=4.0)
_connect(e_u1, "", s_sin, "")
make_decl("s", s_sin, -1550, -280, C_UV)

# ---- r = lerp(CornerRadius, HalfSize, Roundness * sin(e * 180 degrees))  (period 2) ----
e_u2 = use("e", -1850, 350)
round_sin = expr(unreal.MaterialExpressionSine, -1700, 350, period=2.0)
_connect(e_u2, "", round_sin, "")
roundness_p = scalar_param("Roundness", 1.0, 2,
                           "How far the square rounds off halfway through a turn: 0 = stays a square, 1 = a full circle. "
                           "Below 1 the corners reach further out while turning (at 0, HalfSize * 1.414 - CornerRadius * 0.414)", -1700, 470)
round_amt = binary(unreal.MaterialExpressionMultiply, round_sin, roundness_p, -1550, 400)
corner_p = scalar_param("CornerRadius", 0.13, 1, "Corner radius of the square at rest", -1550, 200)
half_u1 = use("HalfSize", -1550, 300)
r_lerp = expr(unreal.MaterialExpressionLinearInterpolate, -1350, 300)
_connect(corner_p, "", r_lerp, "A")
_connect(half_u1, "", r_lerp, "B")
_connect(round_amt, "", r_lerp, "Alpha")

# ---- q = (c * p.x - s * p.y, s * p.x + c * p.y)  (the pixel turns the other way = the square turns clockwise) ----
p_u1 = use("p", -1300, -550)
p_x = mask_x(-1150, -600)
_connect(p_u1, "", p_x, "")
p_y = mask_y(-1150, -480)
_connect(p_u1, "", p_y, "")
c_u1 = use("c", -1150, -380)
s_u1 = use("s", -1150, -280)
cx_v = binary(unreal.MaterialExpressionMultiply, c_u1, p_x, -950, -600)
sy_v = binary(unreal.MaterialExpressionMultiply, s_u1, p_y, -950, -480)
qx_v = binary(unreal.MaterialExpressionSubtract, cx_v, sy_v, -800, -550)
s_u2 = use("s", -1150, -150)
c_u2 = use("c", -1150, -50)
sx_v = binary(unreal.MaterialExpressionMultiply, s_u2, p_x, -950, -200)
cy_v = binary(unreal.MaterialExpressionMultiply, c_u2, p_y, -950, -80)
qy_v = binary(unreal.MaterialExpressionAdd, sx_v, cy_v, -800, -150)
q_v = binary(unreal.MaterialExpressionAppendVector, qx_v, qy_v, -680, -350)

# ---- d = sdRoundBox(q, (HalfSize, HalfSize), r)  (MF_SdRoundBox2D) ----
half_u2 = use("HalfSize", -500, 50)
half2 = binary(unreal.MaterialExpressionAppendVector, half_u2, half_u2, -350, 50)
box_call = expr(unreal.MaterialExpressionMaterialFunctionCall, -200, -150, material_function=mf_box)
_connect(q_v, "", box_call, "P")
_connect(half2, "", box_call, "B")
_connect(r_lerp, "", box_call, "R")
make_decl("d", box_call, 50, -150, C_SDF)

# ---- mask = saturate(0.5 - d / aa)  (anti-aliased mask, 1px-wide edge) ----
d_u1 = use("d", 350, -200)
aa_u1 = use("aa", 350, -100)
d_over_aa = binary(unreal.MaterialExpressionDivide, d_u1, aa_u1, 500, -150)
half_minus = expr(unreal.MaterialExpressionSubtract, 650, -150, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_sat = expr(unreal.MaterialExpressionSaturate, 800, -150)
_connect(half_minus, "", mask_sat, "")
make_decl("mask", mask_sat, 950, -150, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 1200, -250,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Color of the shape (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 1200, 0)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, 1450, -200)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 1200, 200)
cov_a = expr(unreal.MaterialExpressionMultiply, 1450, 150)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 1600, 100)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in p units)",
    -2650, -870, 700, 400, C_UV)
smt.create_comment_in_material(
    mat, "HalfSize = 0.72 at rest (the material contract's reference square). While it turns the corners\n"
         "reach at most 0.786 along x or y with Roundness 1 (inside the reference circle)",
    -2850, -470, 600, 230, C_SC)
smt.create_comment_in_material(
    mat, "u = fract(Time * Speed);  e = smoothstep(0, TurnFraction, u)   (turn progress, then a pause)\n"
         "A square looks the same after a quarter turn, so e alone sets the angle.\n"
         "Time ignores pause (real time), so the square keeps turning while the game thread is blocked",
    -2850, 130, 1000, 450, C_TM)
smt.create_comment_in_material(
    mat, "c, s = cos / sin(e * 90 degrees)   (Sine / Cosine with period 4: an input of 1 is a quarter turn)",
    -1900, -470, 600, 330, C_UV)
smt.create_comment_in_material(
    mat, "r = lerp(CornerRadius, HalfSize, Roundness * sin(e * 180 degrees))   (period 2)\n"
         "Roundest halfway through the turn: a full circle with Roundness 1",
    -1900, 130, 800, 450, C_SDF)
smt.create_comment_in_material(
    mat, "q = (c * p.x - s * p.y, s * p.x + c * p.y): the pixel turns the other way, so the square turns clockwise",
    -1320, -670, 800, 720, C_UV)
smt.create_comment_in_material(
    mat, "d = sdRoundBox(q, (HalfSize, HalfSize), r)   (MF_SdRoundBox2D, exact distance)",
    -550, -270, 750, 420, C_SDF)
smt.create_comment_in_material(
    mat, "mask = saturate(0.5 - d / aa)   (1px-wide coverage approximation at the edge)",
    300, -280, 800, 300, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    1150, -370, 650, 680, C_COL)

used_groups = [g for g in GROUP_ORDER if g in PARAM_GROUPS.values()]
smt.set_parameter_group_sort_priorities(mat, used_groups, list(range(len(used_groups))))

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
decl_names, usage_count, params, param_groups, mf_calls = [], {}, [], {}, 0
for e in smt.get_material_expressions(mat):
    if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
        decl_names.append(str(e.get_editor_property("name")))
    elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
        nm = smt.get_named_reroute_usage_display_name(e)
        usage_count[nm] = usage_count.get(nm, 0) + 1
    elif isinstance(e, (unreal.MaterialExpressionScalarParameter, unreal.MaterialExpressionVectorParameter)):
        params.append(str(e.get_editor_property("parameter_name")))
        param_groups[params[-1]] = str(e.get_editor_property("group"))
    elif isinstance(e, unreal.MaterialExpressionMaterialFunctionCall):
        mf_calls += 1
decl_names.sort()
usage_count = dict(sorted(usage_count.items()))
params.sort()
group_prios = dict(smt.get_parameter_group_sort_priorities(mat))
expected_prios = {g: i for i, g in enumerate(used_groups)}
print(f"[TEST] {ASSET_NAME} decls: {decl_names}")
print(f"[TEST] {ASSET_NAME} usages: {usage_count}")
print(f"[TEST] {ASSET_NAME} params: {params}")
print(f"[TEST] {ASSET_NAME} groups: {param_groups} order: {group_prios}")
print(f"[TEST] {ASSET_NAME} MF calls: {mf_calls}")
expected_decls = sorted(["p", "aa", "HalfSize", "e", "c", "s", "d", "mask"])
expected_usages = {"p": 1, "aa": 1, "HalfSize": 2, "e": 2, "c": 2, "s": 2, "d": 1, "mask": 1}
expected_params = sorted(["HalfSize", "CornerRadius", "Roundness", "Speed", "TurnFraction", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 2
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 9
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
