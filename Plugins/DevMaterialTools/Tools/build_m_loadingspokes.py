"""
Spoke spinner (user's own Shadertoy) -> M_LoadingSpokes (Material Domain = UI, Translucent)

角丸の棒 N 本を放射状に並べ、12 時の棒から時計回りに「白 -> 薄い」のフェードを巡回させる、定番のロードアイコン。
ピクセルの角度から最も近い棒の番号を求め、その棒が真上を向くよう座標を回転してからカプセル SDF を 1 回だけ評価する
のでループ不要。棒はすべて同じ形なので d は「最も近い棒までの正確な距離」になり、セル境界でも連続。

  p     = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  a     = atan(p.x, p.y) / TAU                     (12 時を 0 として時計回りに増える角度、-0.5..0.5)
  id    = floor(a * Count + 0.5)                   (最も近い棒の番号。12 時が 0、時計回りに増える)
  ang   = id / Count * TAU
  c, s  = cos(ang), sin(ang)
  q     = (dot(p, (c, -s)), dot(p, (s, c)))        (= (c*p.x - s*p.y, s*p.x + c*p.y): その棒が真上を向くよう回転)
  q.y  -= clamp(q.y, InnerRadius, OuterRadius)     (カプセルの芯線に射影)
  d     = length(q) - Thickness / 2                (角丸の棒の距離関数。GLSL の WIDTH は半径なので Thickness = 2 * WIDTH)
  aa    = max(fwidth(d), 1e-5)                     (= abs(ddx(d)) + abs(ddy(d))。2026-10-09 ユーザー指示で
                                                    GLSL の aa = 2 / iResolution.y を導関数ベースに置き換え)
  mask  = clamp(0.5 - d / aa, 0, 1)                (アンチエイリアス付きマスク)
  fade  = fract(Time * Speed - id / Count)         (棒ごとに 1/Count ずつ位相をずらす。Speed は回転数/秒)
  alpha = mix(1, OpacityMin, fade)                 (0 で最も明るく、1 に向かって薄くなる)

  fwidth(d) について: d は「最も近い棒までの距離」で、棒はすべて同じ形なので隣のセルとの境界(二等分線)上で
  両側の値が一致し連続。6 時方向の atan の切れ目でも id = ±Count/2 が同じ回転・同じ位相を与えるので連続。
  よって M_LoadingDotGrid(セルごとに半径が違い d が不連続)と違い、fwidth(d) を使っても継ぎ目は出ない。
  max(…, 1e-5) は棒の芯線上で ddx/ddy が同時に 0 になるピクセル(0 除算 -> inf/NaN)の保険。

  デフォルト値は Shadertoy の定数(R_IN 0.12 / R_OUT 0.30 / WIDTH 0.035)を 2.39 倍し、
  OuterRadius + Thickness/2 = 0.8(材質契約の基準円。1.0 = 短辺の端)に合わせたもの。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * alpha * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  背景(bg)は不要なので mix(bg, white, mask * alpha) は PrimaryColor + アルファに置き換え。

  const -> ScalarParameter / VectorParameter(グループ Appearance / Shape / Motion、並びはグループ内の Sort Priority)
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  TAU(2 箇所)と Count(3 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingspokes.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingSpokes"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
TAU = 6.28318530718
AA_EPSILON = 1e-5
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "OpacityMin": "Appearance",
    "Count": "Shape",
    "InnerRadius": "Shape",
    "OuterRadius": "Shape",
    "Thickness": "Shape",
    "Speed": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / rotation = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / fade = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # scalar intermediates / params = gray
C_COL = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)   # coverage / output = white

mf_coords = unreal.load_asset(MF_COORDS_PATH)
assert mf_coords, f"required Material Function not found: {MF_COORDS_PATH}"

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

def mask_x(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=True, g=False, b=False, a=False)

def mask_y(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=False, g=True, b=False, a=False)

# ---- const TAU (used twice -> Named Reroute) ----
tau_c = expr(unreal.MaterialExpressionConstant, -4250, -1000, r=TAU)
make_decl("TAU", tau_c, -4050, -1000, C_SC)

# ---- const N -> Count (used three times -> Named Reroute) ----
count_p = scalar_param("Count", 8.0, 0, "Number of bars (integer, 2 or more)", -4250, -720)
make_decl("Count", count_p, -4000, -720, C_SC)

# ---- p = MF_SpinnerCoords.P  (centered, y-up, shorter side = -1..1). PixelSize is not needed: aa = fwidth(d) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -4100, -350, material_function=mf_coords)
make_decl("p", coords, -3800, -400, C_UV, "P")

# ---- a = atan(p.x, p.y) / TAU  (0 at 12 o'clock, clockwise, -0.5..0.5) ----
p_u1 = use("p", -3150, 80)
p_x1 = mask_x(-3000, 80)
_connect(p_u1, "", p_x1, "")
p_u2 = use("p", -3150, 200)
p_y1 = mask_y(-3000, 200)
_connect(p_u2, "", p_y1, "")
a_atan = expr(unreal.MaterialExpressionArctangent2, -2850, 130)   # atan2(Y, X) = GLSL atan(y, x)
_connect(p_x1, "", a_atan, "Y")
_connect(p_y1, "", a_atan, "X")
tau_u1 = use("TAU", -2850, 280)
a_div = expr(unreal.MaterialExpressionDivide, -2700, 180)
_connect(a_atan, "", a_div, "A")
_connect(tau_u1, "", a_div, "B")
make_decl("a", a_div, -2550, 180, C_UV)

# ---- id = floor(a * Count + 0.5)  (nearest bar; 0 = 12 o'clock, increases clockwise) ----
a_u1 = use("a", -2300, 180)
count_u1 = use("Count", -2300, 280)
id_mul = expr(unreal.MaterialExpressionMultiply, -2150, 230)
_connect(a_u1, "", id_mul, "A")
_connect(count_u1, "", id_mul, "B")
id_half = expr(unreal.MaterialExpressionAdd, -2000, 230, const_b=0.5)
_connect(id_mul, "", id_half, "A")
id_floor = expr(unreal.MaterialExpressionFloor, -1850, 230)
_connect(id_half, "", id_floor, "")
make_decl("id", id_floor, -1700, 230, C_SC)

# ---- ang = id / Count * TAU; c = cos(ang), s = sin(ang) ----
id_u1 = use("id", -1450, 130)
count_u2 = use("Count", -1450, 230)
turn = expr(unreal.MaterialExpressionDivide, -1300, 180)
_connect(id_u1, "", turn, "A")
_connect(count_u2, "", turn, "B")
tau_u2 = use("TAU", -1300, 300)
ang_v = expr(unreal.MaterialExpressionMultiply, -1150, 230)
_connect(turn, "", ang_v, "A")
_connect(tau_u2, "", ang_v, "B")
make_decl("ang", ang_v, -1000, 230, C_UV)
ang_u1 = use("ang", -800, 130)
ang_cos = expr(unreal.MaterialExpressionCosine, -650, 130, period=TAU)   # period 2*PI = radians
_connect(ang_u1, "", ang_cos, "")
make_decl("c", ang_cos, -500, 130, C_UV)
ang_u2 = use("ang", -800, 280)
ang_sin = expr(unreal.MaterialExpressionSine, -650, 280, period=TAU)
_connect(ang_u2, "", ang_sin, "")
make_decl("s", ang_sin, -500, 280, C_UV)

# ---- q = (dot(p, (c, -s)), dot(p, (s, c)))  (= (c*p.x - s*p.y, s*p.x + c*p.y): bar `id` now points up) ----
c_u1 = use("c", -250, 50)
s_u1 = use("s", -250, 150)
s_neg = expr(unreal.MaterialExpressionMultiply, -100, 150, const_b=-1.0)
_connect(s_u1, "", s_neg, "A")
row_x = expr(unreal.MaterialExpressionAppendVector, 50, 100)    # (c, -s)
_connect(c_u1, "", row_x, "A")
_connect(s_neg, "", row_x, "B")
s_u2 = use("s", -250, 300)
c_u2 = use("c", -250, 400)
row_y = expr(unreal.MaterialExpressionAppendVector, 50, 350)    # (s, c)
_connect(s_u2, "", row_y, "A")
_connect(c_u2, "", row_y, "B")
p_u3 = use("p", 200, 30)
q_x = expr(unreal.MaterialExpressionDotProduct, 350, 80)
_connect(p_u3, "", q_x, "A")
_connect(row_x, "", q_x, "B")
p_u4 = use("p", 200, 280)
q_y = expr(unreal.MaterialExpressionDotProduct, 350, 330)
_connect(p_u4, "", q_y, "A")
_connect(row_y, "", q_y, "B")
q_v = expr(unreal.MaterialExpressionAppendVector, 550, 200)
_connect(q_x, "", q_v, "A")
_connect(q_y, "", q_v, "B")
make_decl("q", q_v, 700, 200, C_UV)

# ---- d = length(q - (0, clamp(q.y, InnerRadius, OuterRadius))) - Thickness / 2  (capsule SDF) ----
q_u1 = use("q", 950, 100)
qx = mask_x(1100, 100)
_connect(q_u1, "", qx, "")
q_u2 = use("q", 950, 250)
qy = mask_y(1100, 250)
_connect(q_u2, "", qy, "")
# Footprint (material contract): OuterRadius + Thickness / 2 = 0.8, the reference circle.
inner_p = scalar_param("InnerRadius", 0.29, 1,
                       "Distance from the center to the inner end of a bar (half the shorter widget side = 1.0)",
                       1050, 380)
outer_p = scalar_param("OuterRadius", 0.715, 2, "Distance from the center to the outer end of a bar", 1050, 480)
seg = expr(unreal.MaterialExpressionClamp, 1300, 330)   # clamp(q.y, InnerRadius, OuterRadius)
_connect(qy, "", seg, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(inner_p, "", seg, "Min")
_connect(outer_p, "", seg, "Max")
qy_seg = expr(unreal.MaterialExpressionSubtract, 1500, 260)   # q.y -= clamp(...)
_connect(qy, "", qy_seg, "A")
_connect(seg, "", qy_seg, "B")
q_cap = expr(unreal.MaterialExpressionAppendVector, 1650, 160)
_connect(qx, "", q_cap, "A")
_connect(qy_seg, "", q_cap, "B")
q_len = expr(unreal.MaterialExpressionLength, 1800, 160)
_connect(q_cap, "", q_len, "")
thick_p = scalar_param("Thickness", 0.17, 3,
                       "Bar thickness. The ends are rounded, so each bar extends half of this past the two radii",
                       1750, 300)
thick_half = expr(unreal.MaterialExpressionMultiply, 1950, 300, const_b=0.5)
_connect(thick_p, "", thick_half, "A")
d_v = expr(unreal.MaterialExpressionSubtract, 2100, 200)
_connect(q_len, "", d_v, "A")
_connect(thick_half, "", d_v, "B")
make_decl("d", d_v, 2250, 200, C_SDF)

# ---- aa = max(fwidth(d), eps) = max(abs(ddx(d)) + abs(ddy(d)), eps)  (one pixel of d, per pixel) ----
d_u1 = use("d", 2500, -300)
d_ddx = expr(unreal.MaterialExpressionDDX, 2650, -300)
_connect(d_u1, "", d_ddx, "")
abs_dx = expr(unreal.MaterialExpressionAbs, 2800, -300)
_connect(d_ddx, "", abs_dx, "")
d_u2 = use("d", 2500, -180)
d_ddy = expr(unreal.MaterialExpressionDDY, 2650, -180)
_connect(d_u2, "", d_ddy, "")
abs_dy = expr(unreal.MaterialExpressionAbs, 2800, -180)
_connect(d_ddy, "", abs_dy, "")
fwidth_d = expr(unreal.MaterialExpressionAdd, 2950, -240)
_connect(abs_dx, "", fwidth_d, "A")
_connect(abs_dy, "", fwidth_d, "B")
aa_v = expr(unreal.MaterialExpressionMax, 3100, -240, const_b=AA_EPSILON)
_connect(fwidth_d, "", aa_v, "A")
make_decl("aa", aa_v, 3250, -240, C_SDF)

# ---- mask = clamp(0.5 - d / aa, 0, 1)  (anti-aliased mask, 1px-wide edge) ----
d_u3 = use("d", 2500, 100)
aa_u1 = use("aa", 2500, 200)
d_over_aa = expr(unreal.MaterialExpressionDivide, 2650, 150)
_connect(d_u3, "", d_over_aa, "A")
_connect(aa_u1, "", d_over_aa, "B")
half_minus = expr(unreal.MaterialExpressionSubtract, 2800, 150, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_clamp = expr(unreal.MaterialExpressionClamp, 2950, 150, min_default=0.0, max_default=1.0)
_connect(half_minus, "", mask_clamp, "")
make_decl("mask", mask_clamp, 3100, 150, C_COL)

# ---- fade = fract(Time * Speed - id / Count)  (each bar lags the previous one by 1/Count of a cycle) ----
time_n = expr(unreal.MaterialExpressionTime, -1450, 650)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 1.0, 0, "Revolutions per second. Positive = clockwise", -1450, 750)
t_speed = expr(unreal.MaterialExpressionMultiply, -1300, 700)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
id_u2 = use("id", -1450, 870)
count_u3 = use("Count", -1450, 970)
id_turn = expr(unreal.MaterialExpressionDivide, -1300, 920)
_connect(id_u2, "", id_turn, "A")
_connect(count_u3, "", id_turn, "B")
t_sub = expr(unreal.MaterialExpressionSubtract, -1150, 800)
_connect(t_speed, "", t_sub, "A")
_connect(id_turn, "", t_sub, "B")
t_frac = expr(unreal.MaterialExpressionFrac, -1000, 800)
_connect(t_sub, "", t_frac, "")
make_decl("fade", t_frac, -850, 800, C_TM)

# ---- alpha = mix(1, OpacityMin, fade)  (brightest at fade 0, fades towards OpacityMin) ----
opacitymin_p = scalar_param("OpacityMin", 0.12, 1, "Faintest bar (depth of the fade); the leading bar is fully bright",
                            -600, 700)
fade_u1 = use("fade", -600, 820)
alpha_v = expr(unreal.MaterialExpressionLinearInterpolate, -400, 750, const_a=1.0)
_connect(opacitymin_p, "", alpha_v, "B")
_connect(fade_u1, "", alpha_v, "Alpha")
make_decl("alpha", alpha_v, -250, 750, C_TM)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb,
#      Opacity = mask * alpha * PrimaryColor.a * VertexColor.a  (bg dropped) ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 3500, 0,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Bar color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 3500, 250)
emissive = expr(unreal.MaterialExpressionMultiply, 3750, 50)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 3500, 450)
alpha_u1 = use("alpha", 3500, 550)
coverage = expr(unreal.MaterialExpressionMultiply, 3650, 500)
_connect(mask_u1, "", coverage, "A")
_connect(alpha_u1, "", coverage, "B")
cov_a = expr(unreal.MaterialExpressionMultiply, 3800, 450)
_connect(coverage, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 3950, 400)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "const TAU = 2*PI   (used twice -> Named Reroute)",
    -4300, -1100, 550, 230, C_SC)
smt.create_comment_in_material(
    mat, "const N -> ScalarParameter Count (used three times -> Named Reroute).\n"
         "InnerRadius / OuterRadius / Thickness / Speed / OpacityMin / PrimaryColor are wired directly at their single use site",
    -4300, -840, 650, 260, C_SC)
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "PixelSize is not used here: the AA width comes from fwidth(d) instead",
    -4300, -520, 900, 400, C_UV)
smt.create_comment_in_material(
    mat, "a = atan(p.x, p.y) / TAU\n"
         "Angle from +Y (12 o'clock), clockwise, as a fraction of a turn (-0.5..0.5)",
    -3200, -20, 850, 420, C_UV)
smt.create_comment_in_material(
    mat, "id = floor(a * Count + 0.5)\n"
         "Index of the nearest bar (0 = 12 o'clock, increases clockwise). id = +-Count/2 is the same bar at 6 o'clock",
    -2350, 60, 850, 300, C_SC)
smt.create_comment_in_material(
    mat, "ang = id / Count * TAU;  c = cos(ang), s = sin(ang)\n"
         "Sine / Cosine period = 2*PI -> radians",
    -1500, 0, 1200, 450, C_UV)
smt.create_comment_in_material(
    mat, "q = (dot(p, (c, -s)), dot(p, (s, c))) = (c*p.x - s*p.y, s*p.x + c*p.y)\n"
         "Rotate so that bar `id` points straight up: one capsule SDF then draws every bar",
    -300, -60, 1150, 560, C_UV)
smt.create_comment_in_material(
    mat, "Capsule SDF: q.y -= clamp(q.y, InnerRadius, OuterRadius);  d = length(q) - Thickness / 2\n"
         "(the GLSL WIDTH is a radius, so Thickness = 2 * WIDTH)",
    900, -20, 1500, 620, C_SDF)
smt.create_comment_in_material(
    mat, "aa = max(fwidth(d), 1e-5) = max(abs(ddx(d)) + abs(ddy(d)), 1e-5)   (one screen pixel of d, per pixel)\n"
         "Replaces the GLSL aa = 2 / iResolution.y. Safe here: every bar has the same shape, so d is the exact\n"
         "distance to the nearest bar and continuous across cell borders (unlike M_LoadingDotGrid, where per-cell radii differ).\n"
         "The epsilon guards pixels on a bar's center line where ddx and ddy are both 0 (d / 0 -> inf / NaN)",
    2450, -420, 1000, 340, C_SDF)
smt.create_comment_in_material(
    mat, "mask = clamp(0.5 - d / aa, 0, 1)   (1px-wide coverage approximation at the edge)",
    2450, 20, 850, 300, C_COL)
smt.create_comment_in_material(
    mat, "fade = fract(Time * Speed - id / Count)   (Speed in revolutions per second)\n"
         "Each bar lags the previous one by 1/Count of a cycle, so the highlight runs clockwise.\n"
         "Time ignores pause (real time), so the spinner keeps turning while the game thread is blocked",
    -1500, 560, 800, 520, C_TM)
smt.create_comment_in_material(
    mat, "alpha = mix(1, OpacityMin, fade)\n"
         "Fully bright at fade 0, fades linearly to OpacityMin",
    -650, 600, 600, 330, C_TM)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * alpha * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)\n"
         "Background dropped: mix(bg, white, mask * alpha) becomes PrimaryColor with alpha",
    3450, -120, 700, 800, C_COL)

used_groups = [g for g in GROUP_ORDER if g in PARAM_GROUPS.values()]
smt.set_parameter_group_sort_priorities(mat, used_groups, list(range(len(used_groups))))

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
decl_names, usage_count, param_names, param_groups, mf_calls = [], {}, [], {}, 0
for e in smt.get_material_expressions(mat):
    if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
        decl_names.append(str(e.get_editor_property("name")))
    elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
        nm = smt.get_named_reroute_usage_display_name(e)
        usage_count[nm] = usage_count.get(nm, 0) + 1
    elif isinstance(e, (unreal.MaterialExpressionScalarParameter,
                        unreal.MaterialExpressionVectorParameter)):
        name = str(e.get_editor_property("parameter_name"))
        param_names.append(name)
        param_groups[name] = str(e.get_editor_property("group"))
    elif isinstance(e, unreal.MaterialExpressionMaterialFunctionCall):
        mf_calls += 1
group_prios = dict(smt.get_parameter_group_sort_priorities(mat))
expected_prios = {g: i for i, g in enumerate(used_groups)}
print(f"[TEST] {ASSET_NAME} decls: {sorted(decl_names)}")
print(f"[TEST] {ASSET_NAME} usages: {dict(sorted(usage_count.items()))}")
print(f"[TEST] {ASSET_NAME} params: {sorted(param_names)}")
print(f"[TEST] {ASSET_NAME} groups: {param_groups} order: {group_prios}")
print(f"[TEST] {ASSET_NAME} MF calls: {mf_calls}")

expected_decls = sorted(["TAU", "Count", "p", "a", "id", "ang", "c", "s", "q", "d", "aa", "mask", "fade", "alpha"])
expected_usages = {"TAU": 2, "Count": 3, "p": 4, "a": 1, "id": 2, "ang": 2, "c": 2, "s": 2, "q": 2,
                   "d": 3, "aa": 1, "mask": 1, "fade": 1, "alpha": 1}
expected_params = sorted(["Count", "InnerRadius", "OuterRadius", "Thickness", "Speed", "OpacityMin", "PrimaryColor"])
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == expected_params
groups_ok = param_groups == PARAM_GROUPS and group_prios == expected_prios
mf_ok = mf_calls == 1
comments_ok = len(smt.get_material_comment_texts(mat)) == 13
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and groups_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
