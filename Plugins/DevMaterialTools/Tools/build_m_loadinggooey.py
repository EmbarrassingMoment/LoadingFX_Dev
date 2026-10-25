"""
Gooey droplets -> M_LoadingGooey (Material Domain = UI, Translucent)

丸い核から Count 個の滴がちぎれるように出て Radius まで離れ、全体が時計回りに回りながら、また溶けて核に戻るロードアイコン
(メタボール風、1 色)。核と滴は iq の多項式 smooth min でつなぐので、離れかけた滴と核の間に液体のくびれができる。
デザインは 2026-10-14 のスピナー案第 3 弾の 3 番。WebGL2 のスケッチ(Saved/GooeyHarness/harness.html)で確かめてから組んだ。
clamp(x, 0, 1) は Saturate で書く。

  p     = MF_SpinnerCoords.P                        (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  時間側(ピクセルに依存しないスカラー計算):
    rot  = Time * Speed                             (回転数。正 = 時計回り)
    dist = Radius * (1 - cos(TAU * Time * SpreadSpeed)) / 2
                                                    (滴の中心の距離。0(核に溶けている)-> Radius -> 0)
  滴の選び方(ループなし):
    step = 1 / Count;  a = atan2(p.x, p.y) / TAU    (12 時から時計回りの回転数)
    k    = floor((a - rot) / step)                  (ピクセルは滴 k と k + 1 の間にある)
    angA = rot + k * step;  angB = angA + step
    dA, dB = length(p - dist * (sin(TAU ang), cos(TAU ang))) - DropletRadius   (Sine / Cosine は period 1 = 回転数で入力)
    これより遠い滴は 1 step 以上離れているので省く。滴の軸の上では両側のペアが鏡像になるので、d は連続のまま。
    全滴を smooth min でつなぐ版(デザインプレビュー)と比べて見た目はほぼ同じで、滴が溶け合った塊の大きさが Count に
    よらない(全滴版は Count を増やすほど塊が膨らむ)。2 個を smooth min でなく min でつなぐ版は、くびれに角が出た。
    Count 1 では同じ滴を 2 回つなぐので、滴が Smoothness / 4 だけ太る。Count は 2 以上。
  kS   = max(Smoothness, 1e-4);  kInv4 = 0.25 / kS
  smin(a, b) = min(a, b) - max(kS - abs(a - b), 0)^2 * kInv4    (iq の多項式 smooth min)
  d    = smin(length(p) - CoreRadius, smin(dA, dB))
  aa   = max(length((ddx(d), ddy(d))), 1e-5)        (d の 1 ピクセル分。smooth min の場は距離ではなく、くびれで勾配が 1 より
                                                     小さいので、PixelSize で AA するとそこだけぼやける。d は連続なので
                                                     画面微分が使える。fwidth(abs + abs)より斜めの縁が正確な勾配の長さを取る)
  mask = saturate(0.5 - d / aa)

  デフォルトの外寸: Radius + DropletRadius = 0.8(材質契約の基準円、滴が最も離れたとき)。
  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion に分ける(PARAM_GROUPS)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  DropletRadius(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。
  smooth min は smin() で 2 回、滴の距離は droplet() で 2 回作る。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadinggooey.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingGooey"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
TAU = 6.28318530718
SMOOTH_EPSILON = 1e-4
AA_EPSILON = 1e-5
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "Count": "Shape",
    "CoreRadius": "Shape",
    "DropletRadius": "Shape",
    "Radius": "Shape",
    "Smoothness": "Shape",
    "Speed": "Motion",
    "SpreadSpeed": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / positions = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # params = gray
C_COL = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)   # coverage / output = white

mf_coords = unreal.load_asset(MF_COORDS_PATH)
assert mf_coords, f"required Material Function not found: {MF_COORDS_PATH}"

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

# ---- p = MF_SpinnerCoords.P  (centered, y-up, shorter side = -1..1). PixelSize is not needed: aa comes from d ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3600, -700, material_function=mf_coords)
make_decl("p", coords, -3300, -750, C_UV, "P")

# ---- Shared parameters ----
# Footprint (material contract): Radius + DropletRadius = 0.8 at full spread.
dropr_p = scalar_param("DropletRadius", 0.15, 2, "Radius of a droplet (half the shorter widget side = 1.0)",
                       -3800, -400)
make_decl("DropletRadius", dropr_p, -3550, -400, C_SC)
smooth_p = scalar_param("Smoothness", 0.3, 4,
                        "How far apart two shapes start to melt together (smooth-min width). "
                        "Higher = gooier; near 0 = hard edges", -3800, -250)
k_max = expr(unreal.MaterialExpressionMax, -3550, -250, const_b=SMOOTH_EPSILON)
_connect(smooth_p, "", k_max, "A")
make_decl("k", k_max, -3400, -250, C_SDF)
k_inv4 = expr(unreal.MaterialExpressionDivide, -3400, -130, const_a=0.25)
_connect(k_max, "", k_inv4, "B")
make_decl("kInv4", k_inv4, -3250, -130, C_SDF)

# ---- rot = Time * Speed;  dist = Radius * (1 - cos(TAU * Time * SpreadSpeed)) / 2 ----
time_n = expr(unreal.MaterialExpressionTime, -3800, 300)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.25, 0, "Revolutions per second. Positive = clockwise", -3800, 420)
rot_v = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3600, 350)
make_decl("rot", rot_v, -3450, 350, C_TM)
spread_p = scalar_param("SpreadSpeed", 0.5, 1,
                        "Out-and-back cycles per second of the droplets (0 keeps them melted into the core)",
                        -3800, 600)
spread_t = binary(unreal.MaterialExpressionMultiply, time_n, spread_p, -3600, 550)
spread_cos = expr(unreal.MaterialExpressionCosine, -3450, 550, period=1.0)   # period 1: the input is in cycles
_connect(spread_t, "", spread_cos, "")
spread_inv = expr(unreal.MaterialExpressionOneMinus, -3300, 550)
_connect(spread_cos, "", spread_inv, "")
spread_half = expr(unreal.MaterialExpressionMultiply, -3150, 550, const_b=0.5)
_connect(spread_inv, "", spread_half, "A")
radius_p = scalar_param("Radius", 0.65, 3,
                        "Distance from the center to the droplet centers at full spread", -3150, 670)
dist_v = binary(unreal.MaterialExpressionMultiply, radius_p, spread_half, -3000, 600)
make_decl("dist", dist_v, -2850, 600, C_TM)

# ---- step = 1 / Count;  a = atan2(p.x, p.y) / TAU;  k = floor((a - rot) / step);  angA = rot + k * step ----
count_p = scalar_param("Count", 3.0, 0, "Number of droplets (integer, 2 or more)", -3000, -700)
step_v = expr(unreal.MaterialExpressionDivide, -2800, -700, const_a=1.0)
_connect(count_p, "", step_v, "B")
make_decl("step", step_v, -2650, -700, C_SC)
p_u1 = use("p", -3000, -450)
p_x1 = mask_x(-2850, -500)
_connect(p_u1, "", p_x1, "")
p_y1 = mask_y(-2850, -400)
_connect(p_u1, "", p_y1, "")
a_atan = expr(unreal.MaterialExpressionArctangent2, -2700, -450)   # atan2(Y, X) = GLSL atan(y, x)
_connect(p_x1, "", a_atan, "Y")
_connect(p_y1, "", a_atan, "X")
a_turns = expr(unreal.MaterialExpressionDivide, -2550, -450, const_b=TAU)   # turns clockwise from 12 o'clock
_connect(a_atan, "", a_turns, "A")
rot_u1 = use("rot", -2550, -330)
a_rel = binary(unreal.MaterialExpressionSubtract, a_turns, rot_u1, -2400, -400)
step_u1 = use("step", -2400, -280)
sector = binary(unreal.MaterialExpressionDivide, a_rel, step_u1, -2250, -350)
sector_k = expr(unreal.MaterialExpressionFloor, -2100, -350)
_connect(sector, "", sector_k, "")
step_u2 = use("step", -2100, -230)
k_step = binary(unreal.MaterialExpressionMultiply, sector_k, step_u2, -1950, -300)
rot_u2 = use("rot", -1950, -180)
ang_a = binary(unreal.MaterialExpressionAdd, rot_u2, k_step, -1800, -250)
make_decl("angA", ang_a, -1650, -250, C_UV)

# ---- Droplet distance: length(p - dist * (sin(TAU ang), cos(TAU ang))) - DropletRadius ----
def droplet(ang, x, y):
    sin_n = expr(unreal.MaterialExpressionSine, x, y - 60, period=1.0)   # period 1: the input is in turns
    _connect(ang, "", sin_n, "")
    cos_n = expr(unreal.MaterialExpressionCosine, x, y + 60, period=1.0)
    _connect(ang, "", cos_n, "")
    dir_v = binary(unreal.MaterialExpressionAppendVector, sin_n, cos_n, x + 150, y)
    dist_u = use("dist", x + 150, y + 120)
    c_v = binary(unreal.MaterialExpressionMultiply, dir_v, dist_u, x + 300, y)
    p_u = use("p", x + 300, y - 120)
    q_v = binary(unreal.MaterialExpressionSubtract, p_u, c_v, x + 450, y - 50)
    q_len = expr(unreal.MaterialExpressionLength, x + 600, y - 50)
    _connect(q_v, "", q_len, "")
    dropr_u = use("DropletRadius", x + 600, y + 70)
    return binary(unreal.MaterialExpressionSubtract, q_len, dropr_u, x + 750, y)

ang_a_u1 = use("angA", -1450, -650)
d_a = droplet(ang_a_u1, -1300, -650)
make_decl("dA", d_a, -400, -650, C_SDF)
ang_a_u2 = use("angA", -1600, 50)
step_u3 = use("step", -1600, 150)
ang_b = binary(unreal.MaterialExpressionAdd, ang_a_u2, step_u3, -1450, 100)
d_b = droplet(ang_b, -1300, 100)
make_decl("dB", d_b, -400, 100, C_SDF)

# ---- smin(a, b) = min(a, b) - max(k - abs(a - b), 0)^2 * kInv4  (iq's polynomial smooth min) ----
def smin(a, b, x, y):
    diff = binary(unreal.MaterialExpressionSubtract, a, b, x, y + 100)
    diff_abs = expr(unreal.MaterialExpressionAbs, x + 150, y + 100)
    _connect(diff, "", diff_abs, "")
    k_u = use("k", x + 150, y + 220)
    k_gap = binary(unreal.MaterialExpressionSubtract, k_u, diff_abs, x + 300, y + 150)
    h = expr(unreal.MaterialExpressionMax, x + 450, y + 150, const_b=0.0)
    _connect(k_gap, "", h, "A")
    h_sq = binary(unreal.MaterialExpressionMultiply, h, h, x + 600, y + 150)
    kinv_u = use("kInv4", x + 600, y + 270)
    corr = binary(unreal.MaterialExpressionMultiply, h_sq, kinv_u, x + 750, y + 200)
    mn = binary(unreal.MaterialExpressionMin, a, b, x + 600, y - 20)
    return binary(unreal.MaterialExpressionSubtract, mn, corr, x + 900, y + 50)

# ---- d = smin(length(p) - CoreRadius, smin(dA, dB)) ----
da_u1 = use("dA", -150, -300)
db_u1 = use("dB", -150, -200)
drops = smin(da_u1, db_u1, 0, -300)
p_u2 = use("p", -150, 350)
core_len = expr(unreal.MaterialExpressionLength, 0, 350)
_connect(p_u2, "", core_len, "")
core_p = scalar_param("CoreRadius", 0.22, 1, "Radius of the core the droplets bud off from", 0, 470)
core_d = binary(unreal.MaterialExpressionSubtract, core_len, core_p, 150, 400)
d_v = smin(core_d, drops, 1050, 300)
make_decl("d", d_v, 2050, 350, C_SDF)

# ---- aa = max(length((ddx(d), ddy(d))), 1e-5);  mask = saturate(0.5 - d / aa) ----
d_u1 = use("d", 2300, -100)
d_ddx = expr(unreal.MaterialExpressionDDX, 2450, -150)
_connect(d_u1, "", d_ddx, "")
d_ddy = expr(unreal.MaterialExpressionDDY, 2450, -50)
_connect(d_u1, "", d_ddy, "")
grad_v = binary(unreal.MaterialExpressionAppendVector, d_ddx, d_ddy, 2600, -100)
grad_len = expr(unreal.MaterialExpressionLength, 2750, -100)
_connect(grad_v, "", grad_len, "")
aa_v = expr(unreal.MaterialExpressionMax, 2900, -100, const_b=AA_EPSILON)
_connect(grad_len, "", aa_v, "A")
make_decl("aa", aa_v, 3050, -100, C_SDF)
d_u2 = use("d", 2300, 200)
aa_u1 = use("aa", 2300, 300)
d_over_aa = binary(unreal.MaterialExpressionDivide, d_u2, aa_u1, 2450, 250)
half_minus = expr(unreal.MaterialExpressionSubtract, 2600, 250, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_sat = expr(unreal.MaterialExpressionSaturate, 2750, 250)
_connect(half_minus, "", mask_sat, "")
make_decl("mask", mask_sat, 2900, 250, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 3300, -250,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Color of the core and the droplets (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 3300, 0)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, 3550, -200)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 3300, 200)
cov_a = expr(unreal.MaterialExpressionMultiply, 3550, 150)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 3700, 100)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "PixelSize is not used: the AA width comes from the screen gradient of d",
    -3650, -870, 750, 300, C_UV)
smt.create_comment_in_material(
    mat, "Shared parameters -> Named Reroutes. Radius + DropletRadius = 0.8 at full spread\n"
         "(the material contract's reference circle).  k = max(Smoothness, 1e-4);  kInv4 = 0.25 / k",
    -3850, -520, 750, 500, C_SC)
smt.create_comment_in_material(
    mat, "rot = Time * Speed   (turns, clockwise)\n"
         "dist = Radius * (1 - cos(TAU * Time * SpreadSpeed)) / 2   (0 = melted into the core -> Radius -> 0)\n"
         "Time ignores pause (real time), so the droplets keep moving while the game thread is blocked",
    -3850, 200, 1100, 600, C_TM)
smt.create_comment_in_material(
    mat, "step = 1 / Count;  a = atan2(p.x, p.y) / TAU   (turns clockwise from 12 o'clock)\n"
         "k = floor((a - rot) / step);  angA = rot + k * step: the pixel lies between droplets k and k + 1.\n"
         "Further droplets are a whole step off and are left out (no loop). On a droplet's axis the pairs on both\n"
         "sides mirror each other, so d stays continuous; the merged blob keeps its size for any Count",
    -3050, -820, 1550, 750, C_UV)
smt.create_comment_in_material(
    mat, "dA = length(p - dist * (sin(TAU angA), cos(TAU angA))) - DropletRadius   (Sine / Cosine period 1: turns)",
    -1500, -800, 1300, 450, C_SDF)
smt.create_comment_in_material(
    mat, "dB: the same for angB = angA + step",
    -1650, -50, 1450, 450, C_SDF)
smt.create_comment_in_material(
    mat, "smin(dA, dB) = min(dA, dB) - max(k - abs(dA - dB), 0)^2 * kInv4   (iq's polynomial smooth min)",
    -200, -420, 1150, 550, C_SDF)
smt.create_comment_in_material(
    mat, "d = smin(length(p) - CoreRadius, smin(dA, dB))   (the core and the droplets melt together)",
    -200, 230, 2400, 420, C_SDF)
smt.create_comment_in_material(
    mat, "aa = max(length((ddx(d), ddy(d))), 1e-5): one pixel of d. A smooth-min field is not a true distance;\n"
         "its gradient drops below 1 in the necks, where PixelSize would blur the edge. d is continuous\n"
         "mask = saturate(0.5 - d / aa)",
    2250, -270, 1000, 700, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    3250, -370, 650, 680, C_COL)

used_groups = [g for g in GROUP_ORDER if g in PARAM_GROUPS.values()]
smt.set_parameter_group_sort_priorities(mat, used_groups, list(range(len(used_groups))))

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
decl_names, usage_count, params, mf_calls, param_groups = [], {}, [], 0, {}
for e in smt.get_material_expressions(mat):
    if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
        decl_names.append(str(e.get_editor_property("name")))
    elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
        nm = smt.get_named_reroute_usage_display_name(e)
        usage_count[nm] = usage_count.get(nm, 0) + 1
    elif isinstance(e, (unreal.MaterialExpressionScalarParameter, unreal.MaterialExpressionVectorParameter)):
        name = str(e.get_editor_property("parameter_name"))
        params.append(name)
        param_groups[name] = str(e.get_editor_property("group"))
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
expected_decls = sorted(["p", "DropletRadius", "k", "kInv4", "rot", "dist", "step", "angA", "dA", "dB", "d", "aa",
                         "mask"])
expected_usages = {"p": 4, "DropletRadius": 2, "k": 2, "kInv4": 2, "rot": 2, "dist": 2, "step": 3, "angA": 2,
                   "dA": 1, "dB": 1, "d": 2, "aa": 1, "mask": 1}
expected_params = sorted(["Count", "CoreRadius", "DropletRadius", "Radius", "Smoothness", "Speed", "SpreadSpeed",
                          "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 10
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
