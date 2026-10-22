"""
Chasing dots -> M_LoadingChase (Material Domain = UI, Translucent)

Count 個の点が少しずつ遅れて円周を時計回りに追いかけ合うロードアイコン(1 色)。12 時で遅くなって詰まり、6 時で速くなって
離れる。点は iq の多項式 smooth min でつなぐので、詰まった点は 1 つの塊に溶け合い、離れるときに糸を引いてちぎれる。
デザインは 2026-10-14 のスピナー案第 3 弾の 4 番(2026-10-16 の第 4 弾で再掲)。smooth min は 2026-10-17 のユーザー案。
clamp(x, 0, 1) は Saturate で書く。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  s      = Time * Speed                             (Speed は 1 秒あたりの周回数、正 = 時計回り)
  点 i(0..7。点 0 が先頭):
    u_i    = fract(s - i * Stagger)                 (i が増えるほど Stagger 周ずつ遅れる)
    ang_i  = TAU * u_i - Easing * sin(TAU * u_i)    (12 時から時計回りの角度。速さは 1 - Easing * cos で、12 時で最も遅い)
    len_i  = max(length(p - Radius * (sin(ang_i), cos(ang_i))), cutoff + HIDE * (i + 1))
             cutoff = -HIDE * Count, HIDE = 10       (i >= Count の点は距離が HIDE 以上になって消える。表示する点では
                                                     右の値が 0 以下なので、0 以上の length がそのまま残る)
  kS     = max(Smoothness, 1e-4);  kInv4 = 0.25 / kS
  smin(a, b) = min(a, b) - max(kS - abs(a - b), 0)^2 * kInv4    (iq の多項式 smooth min。M_LoadingGooey と同じ)
  d      = smin(...smin(smin(len_0, len_1), len_2)..., len_7) - DotRadius
                                                    (smooth min はずらしに対して不変なので、DotRadius は最後に 1 回引く)
  aa     = max(length((ddx(d), ddy(d))), 1e-5)      (smooth min の場は距離ではなく、くびれで勾配が 1 より小さいので
                                                     PixelSize ではなく画面勾配の長さを使う。M_LoadingGooey と同じ)
  mask   = saturate(0.5 - d / aa)

  全点を計算する理由: smooth min は届く範囲のすべての点に影響され、12 時で詰まったところでは 3〜5 個が届く。
  最初の版はピクセルの角度を位相に戻し(ケプラー方程式を Halley 法 2 回で解く)、角度の上で挟む 2 点だけを描いていた
  (同じ大きさの円なら最も近い点はその 2 点のどちらかなので、min なら正確)。同じ 2 点を smooth min でつなぐと塊に段差が出て、
  外側の 2 点を位置に応じて効かなくする 4 点版でも輪郭にへこみが残った(WebGL2 のスケッチ Saved/ChaseHarness/smin.html)。
  そこで最大 8 点を展開して全部つなぐ。Count はその中で表示する数。

  デフォルトの外寸: 点が溶け合うと塊は Radius + DotRadius より外へふくらむ。Smoothness 0.12 では Radius 0.71 で 0.837
  まで出たので、Radius を 0.672 にして最大 0.8005(材質契約の基準円。Python で 1 周を 600 時刻に分けて調べた。Count 8 でも同じ)。
  Smoothness 0 では離れた点になり、外寸は Radius + DotRadius = 0.762。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion に分ける(PARAM_GROUPS)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Radius / Easing(8 箇所)と Stagger(7 箇所)は Declaration 化、Speed / Count / Smoothness / DotRadius は 1 箇所なので直接配線。
  点の距離は dot() で 8 回、smooth min は smin() で 7 回作る。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingchase.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingChase"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
TAU = 6.28318530718
MAX_DOTS = 8
HIDE = 10.0            # distance added to a dot beyond Count (far more than the widget and any Smoothness)
SMOOTH_EPSILON = 1e-4
AA_EPSILON = 1e-5
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "Count": "Shape",
    "Radius": "Shape",
    "DotRadius": "Shape",
    "Smoothness": "Shape",
    "Speed": "Motion",
    "Stagger": "Motion",
    "Easing": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / dot positions = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / smooth min / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # params / scalar intermediates = gray
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

def unary(cls, src, x, y, **props):
    n = expr(cls, x, y, **props)
    _connect(src, "", n, "")
    return n

# ---- p = MF_SpinnerCoords.P  (centered, y-up, shorter side = -1..1). PixelSize is not needed: aa comes from d ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3600, -1500, material_function=mf_coords)
make_decl("p", coords, -3300, -1550, C_UV, "P")

# ---- Shared parameters ----
# Footprint (material contract): the melted blob reaches 0.8005 with the defaults (Radius + DotRadius = 0.762 apart).
radius_p = scalar_param("Radius", 0.672, 1,
                        "Distance from the center to the dot centers (half the shorter widget side = 1.0)",
                        -3800, -1250)
make_decl("Radius", radius_p, -3550, -1250, C_SC)
easing_p = scalar_param("Easing", 0.85, 2,
                        "How much the dots slow down at 12 o'clock and speed up at 6 o'clock: "
                        "0 = steady speed, toward 1 they nearly stop at the top (below 1)", -3800, -1130)
make_decl("Easing", easing_p, -3550, -1130, C_SC)
stagger_p = scalar_param("Stagger", 0.075, 1, "Delay between neighboring dots, as a fraction of a lap",
                         -3800, -1010)
make_decl("Stagger", stagger_p, -3550, -1010, C_SC)
count_p = scalar_param("Count", 5.0, 0, "Number of dots (integer, 1 to 8)", -3800, -890)
cutoff_v = expr(unreal.MaterialExpressionMultiply, -3550, -890, const_b=-HIDE)
_connect(count_p, "", cutoff_v, "A")
make_decl("cutoff", cutoff_v, -3400, -890, C_SC)
smooth_p = scalar_param("Smoothness", 0.12, 3,
                        "How far apart two dots start to melt together (smooth-min width). "
                        "Higher = gooier; 0 = separate dots", -3800, -770)
k_max = expr(unreal.MaterialExpressionMax, -3550, -770, const_b=SMOOTH_EPSILON)
_connect(smooth_p, "", k_max, "A")
make_decl("k", k_max, -3400, -770, C_SDF)
k_inv4 = expr(unreal.MaterialExpressionDivide, -3400, -650, const_a=0.25)
_connect(k_max, "", k_inv4, "B")
make_decl("kInv4", k_inv4, -3250, -650, C_SDF)

# ---- s = Time * Speed ----
time_n = expr(unreal.MaterialExpressionTime, -3800, -450)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.55, 0, "Laps per second. Positive = clockwise", -3800, -330)
s_v = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3600, -400)
make_decl("s", s_v, -3450, -400, C_TM)

# ---- Dot i: u = fract(s - i * Stagger);  ang = TAU * u - Easing * sin(TAU * u);
#      len = max(length(p - Radius * (sin(ang), cos(ang))), cutoff + HIDE * (i + 1)) ----
def dot(i, x, y):
    s_u = use("s", x, y - 50)
    if i == 0:
        u = unary(unreal.MaterialExpressionFrac, s_u, x + 300, y)
    else:
        stag_u = use("Stagger", x, y + 50)
        i_st = expr(unreal.MaterialExpressionMultiply, x + 150, y + 50, const_b=float(i))
        _connect(stag_u, "", i_st, "A")
        s_sub = binary(unreal.MaterialExpressionSubtract, s_u, i_st, x + 300, y)
        u = unary(unreal.MaterialExpressionFrac, s_sub, x + 450, y)
    u_tau = expr(unreal.MaterialExpressionMultiply, x + 600, y - 50, const_b=TAU)
    _connect(u, "", u_tau, "A")
    u_sin = unary(unreal.MaterialExpressionSine, u, x + 600, y + 50, period=1.0)   # period 1 = sin(TAU * u)
    e_u = use("Easing", x + 600, y + 130)
    e_sin = binary(unreal.MaterialExpressionMultiply, e_u, u_sin, x + 750, y + 80)
    ang = binary(unreal.MaterialExpressionSubtract, u_tau, e_sin, x + 900, y)
    a_sin = unary(unreal.MaterialExpressionSine, ang, x + 1050, y - 50, period=TAU)   # period 2*PI = radians
    a_cos = unary(unreal.MaterialExpressionCosine, ang, x + 1050, y + 50, period=TAU)
    dir_v = binary(unreal.MaterialExpressionAppendVector, a_sin, a_cos, x + 1200, y)
    r_u = use("Radius", x + 1200, y + 100)
    c = binary(unreal.MaterialExpressionMultiply, dir_v, r_u, x + 1350, y + 50)
    p_u = use("p", x + 1350, y - 50)
    rel = binary(unreal.MaterialExpressionSubtract, p_u, c, x + 1500, y)
    ln = unary(unreal.MaterialExpressionLength, rel, x + 1650, y)
    if i == 0:
        out = ln   # Count is at least 1, so the leading dot is always shown
    else:
        cut_u = use("cutoff", x + 1650, y + 100)
        hide = expr(unreal.MaterialExpressionAdd, x + 1800, y + 100, const_b=HIDE * (i + 1))
        _connect(cut_u, "", hide, "A")
        out = binary(unreal.MaterialExpressionMax, ln, hide, x + 1950, y + 50)
    make_decl(f"len{i}", out, x + 2100, y, C_SDF)

DOT_X, DOT_Y, DOT_DY = -3200, -150, 300
for i in range(MAX_DOTS):
    dot(i, DOT_X, DOT_Y + i * DOT_DY)

# ---- smin(a, b) = min(a, b) - max(k - abs(a - b), 0)^2 * kInv4  (iq's polynomial smooth min) ----
def smin(a, b, x, y):
    diff = binary(unreal.MaterialExpressionSubtract, a, b, x, y + 100)
    diff_abs = unary(unreal.MaterialExpressionAbs, diff, x + 150, y + 100)
    k_u = use("k", x + 150, y + 220)
    k_gap = binary(unreal.MaterialExpressionSubtract, k_u, diff_abs, x + 300, y + 150)
    h = expr(unreal.MaterialExpressionMax, x + 450, y + 150, const_b=0.0)
    _connect(k_gap, "", h, "A")
    h_sq = binary(unreal.MaterialExpressionMultiply, h, h, x + 600, y + 150)
    kinv_u = use("kInv4", x + 600, y + 270)
    corr = binary(unreal.MaterialExpressionMultiply, h_sq, kinv_u, x + 750, y + 200)
    mn = binary(unreal.MaterialExpressionMin, a, b, x + 600, y - 20)
    return binary(unreal.MaterialExpressionSubtract, mn, corr, x + 900, y + 50)

# ---- d = smin(...smin(smin(len0, len1), len2)..., len7) - DotRadius ----
SMIN_X = -700
chain = use("len0", SMIN_X - 150, DOT_Y)
for i in range(1, MAX_DOTS):
    y = DOT_Y + i * DOT_DY
    nxt = use(f"len{i}", SMIN_X - 150, y + 60)
    chain = smin(chain, nxt, SMIN_X, y - 100)
dotr_p = scalar_param("DotRadius", 0.09, 2, "Radius of a dot", SMIN_X + 900, DOT_Y + MAX_DOTS * DOT_DY)
d_v = binary(unreal.MaterialExpressionSubtract, chain, dotr_p, SMIN_X + 1100, DOT_Y + MAX_DOTS * DOT_DY - 150)
make_decl("d", d_v, SMIN_X + 1250, DOT_Y + MAX_DOTS * DOT_DY - 150, C_SDF)

# ---- aa = max(length((ddx(d), ddy(d))), 1e-5);  mask = saturate(0.5 - d / aa) ----
AA_X, AA_Y = 900, 1000
d_u1 = use("d", AA_X, AA_Y - 100)
d_ddx = unary(unreal.MaterialExpressionDDX, d_u1, AA_X + 150, AA_Y - 150)
d_ddy = unary(unreal.MaterialExpressionDDY, d_u1, AA_X + 150, AA_Y - 50)
grad_v = binary(unreal.MaterialExpressionAppendVector, d_ddx, d_ddy, AA_X + 300, AA_Y - 100)
grad_len = unary(unreal.MaterialExpressionLength, grad_v, AA_X + 450, AA_Y - 100)
aa_v = expr(unreal.MaterialExpressionMax, AA_X + 600, AA_Y - 100, const_b=AA_EPSILON)
_connect(grad_len, "", aa_v, "A")
make_decl("aa", aa_v, AA_X + 750, AA_Y - 100, C_SDF)
d_u2 = use("d", AA_X, AA_Y + 200)
aa_u1 = use("aa", AA_X, AA_Y + 300)
d_over_aa = binary(unreal.MaterialExpressionDivide, d_u2, aa_u1, AA_X + 150, AA_Y + 250)
half_minus = expr(unreal.MaterialExpressionSubtract, AA_X + 300, AA_Y + 250, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_sat = unary(unreal.MaterialExpressionSaturate, half_minus, AA_X + 450, AA_Y + 250)
make_decl("mask", mask_sat, AA_X + 600, AA_Y + 250, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
OUT_X, OUT_Y = 1950, 900
primary_p = expr(unreal.MaterialExpressionVectorParameter, OUT_X, OUT_Y - 150,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Color of the dots (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, OUT_X, OUT_Y + 100)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, OUT_X + 250, OUT_Y - 100)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", OUT_X, OUT_Y + 300)
cov_a = expr(unreal.MaterialExpressionMultiply, OUT_X + 250, OUT_Y + 250)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, OUT_X + 400, OUT_Y + 200)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "PixelSize is not used: the AA width comes from the screen gradient of d",
    -3650, -1670, 750, 300, C_UV)
smt.create_comment_in_material(
    mat, "Shared parameters -> Named Reroutes. The melted blob reaches 0.8005 with the defaults (the material\n"
         "contract's reference circle; Radius + DotRadius = 0.762 when the dots are apart).\n"
         "cutoff = -10 * Count;  k = max(Smoothness, 1e-4);  kInv4 = 0.25 / k",
    -3850, -1330, 750, 850, C_SC)
smt.create_comment_in_material(
    mat, "s = Time * Speed   (laps; Time ignores pause, so the dots keep moving while the game thread is blocked)",
    -3850, -520, 750, 300, C_TM)
smt.create_comment_in_material(
    mat, "Dot i (0 leads): u = fract(s - i * Stagger);  ang = TAU * u - Easing * sin(TAU * u)   (slowest at 12 o'clock)\n"
         "len_i = max(length(p - Radius * (sin(ang), cos(ang))), cutoff + 10 * (i + 1))\n"
         "A dot beyond Count gets a distance of 10 or more and drops out; for a shown dot the right side is 0 or less",
    -3250, -320, 2500, MAX_DOTS * DOT_DY + 100, C_UV)
smt.create_comment_in_material(
    mat, "smin(a, b) = min(a, b) - max(k - abs(a - b), 0)^2 * kInv4   (iq's polynomial smooth min), over every dot:\n"
         "where the dots bunch up, three to five of them are within reach, so the two around the pixel's angle\n"
         "are not enough (that showed steps in the blob; see Saved/ChaseHarness/smin.html)",
    SMIN_X - 200, DOT_Y + DOT_DY - 220, 1200, (MAX_DOTS - 1) * DOT_DY + 150, C_SDF)
smt.create_comment_in_material(
    mat, "d = smin(...) - DotRadius   (smooth min does not change under a shift, so the radius comes off once)",
    SMIN_X + 850, DOT_Y + MAX_DOTS * DOT_DY - 250, 600, 400, C_SDF)
smt.create_comment_in_material(
    mat, "aa = max(length((ddx(d), ddy(d))), 1e-5): one pixel of d. A smooth-min field is not a true distance;\n"
         "its gradient drops below 1 in the necks, where PixelSize would blur the edge\n"
         "mask = saturate(0.5 - d / aa)",
    AA_X - 50, AA_Y - 270, 900, 650, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    OUT_X - 50, OUT_Y - 270, 650, 680, C_COL)

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
len_names = [f"len{i}" for i in range(MAX_DOTS)]
expected_decls = sorted(["p", "Radius", "Easing", "Stagger", "cutoff", "k", "kInv4", "s", "d", "aa", "mask"]
                        + len_names)
expected_usages = {"p": MAX_DOTS, "Radius": MAX_DOTS, "Easing": MAX_DOTS, "s": MAX_DOTS,
                   "Stagger": MAX_DOTS - 1, "cutoff": MAX_DOTS - 1, "k": MAX_DOTS - 1, "kInv4": MAX_DOTS - 1,
                   "d": 2, "aa": 1, "mask": 1, **{n: 1 for n in len_names}}
expected_params = sorted(["Radius", "DotRadius", "Count", "Smoothness", "Speed", "Stagger", "Easing", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 8
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
