"""
Equalizer bars -> M_LoadingEqualizer (Material Domain = UI, Translucent)

横一列に並んだ Count 本の角丸の縦棒が、左から順に中心線から上下へ伸びて縮むロードアイコン(オーディオのイコライザー風、1 色)。
デザインは 2026-10-14 のスピナー案第 3 弾の 2 番。WebGL2 のスケッチ(Saved/EqualizerHarness/harness.html)で確かめてから組んだ。
並びと時間の扱いは M_LoadingDots と同じ(パラメータ名も Count / Spacing / Speed / Stagger / PulseWidth を揃えた)。
ピクセルの x から最も近い棒の番号を直接求め、その棒のカプセル SDF を 1 回だけ評価するのでループ不要。
棒の幅はすべて同じなので、Thickness < Spacing なら棒が隣のセルにはみ出さず、最も近い棒だけを見れば足りる。
clamp(x, 0, 1) は Saturate で書く。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  half   = (Count - 1) / 2
  id     = clamp(round(p.x / Spacing + half), 0, Count - 1)
                                                    (最も近い棒の番号。0 = 左端。列の外のピクセルは端の棒へ)
  phase  = fract(Time * Speed - id * Stagger)       (棒ごとに Stagger サイクルずつ遅れる。Speed はサイクル/秒、
                                                     正 = 波が左から右へ進む)
  pulse  = (1 - cos(TAU * saturate(phase / PulseWidth))) / 2
                                                    (サイクルの先頭 PulseWidth の間に 0 -> 1 -> 0、残りは 0 で休む。
                                                     既定の 1 では休みなしの連続した波)
  capR   = Thickness / 2                            (丸い端の半径)
  seg    = max(lerp(HeightMin, HeightMax, pulse) - capR, 0)
                                                    (芯線の半分の長さ。HeightMin / HeightMax は丸い端の先までの半分の高さ)
  cx     = (id - half) * Spacing                    (棒の中心の x)
  d      = length((p.x - cx, max(abs(p.y) - seg, 0))) - capR
                                                    (中心線に上下対称の縦のカプセル)
  mask   = saturate(0.5 - d / aa)

  棒ごとに高さが違うので d はセル境界で不連続(境界の両側とも棒の外なので mask は連続)。AA 幅は fwidth(d) ではなく
  PixelSize を使う(M_LoadingDots と同じ)。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルトの外寸: 横は (Count - 1) / 2 * Spacing + Thickness / 2 = 0.72、縦はパルスのピークで HeightMax = 0.72
  (どちらも材質契約の基準正方形の半幅)。Count を増やすときは Spacing を小さくしないと列がウィジェットからはみ出す。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion に分ける(PARAM_GROUPS)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Spacing(2 箇所)は Declaration 化、Count - 1 は 1 つのノードから half と clamp の Max へ直接配線、
  Thickness は capR として Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingequalizer.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingEqualizer"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
TAU = 6.28318530718
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "Count": "Shape",
    "Spacing": "Shape",
    "Thickness": "Shape",
    "HeightMin": "Shape",
    "HeightMax": "Shape",
    "Speed": "Motion",
    "Stagger": "Motion",
    "PulseWidth": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / cell = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / pulse = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # scalar intermediates / params = gray
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

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3100, -650, material_function=mf_coords)
make_decl("p", coords, -2800, -700, C_UV, "P")
make_decl("aa", coords, -2800, -580, C_SDF, "PixelSize")

# ---- half = (Count - 1) / 2 ----
count_p = scalar_param("Count", 5.0, 0, "Number of bars (integer, 1 or more)", -3250, -300)
count_m1 = expr(unreal.MaterialExpressionSubtract, -3050, -300, const_b=1.0)   # also the clamp's Max below
_connect(count_p, "", count_m1, "A")
half_v = expr(unreal.MaterialExpressionMultiply, -2900, -350, const_b=0.5)
_connect(count_m1, "", half_v, "A")
make_decl("half", half_v, -2750, -350, C_SC)

# Footprint (material contract): (Count - 1) / 2 * Spacing + Thickness / 2 = 0.72 across, HeightMax = 0.72 up and down.
spacing_p = scalar_param("Spacing", 0.32, 1,
                         "Distance between neighboring bar centers (half the shorter widget side = 1.0)",
                         -3250, -100)
make_decl("Spacing", spacing_p, -3000, -100, C_SC)

# ---- id = clamp(round(p.x / Spacing + half), 0, Count - 1)  (nearest bar; 0 = leftmost) ----
p_u1 = use("p", -2450, -200)
p_x1 = mask_x(-2300, -200)
_connect(p_u1, "", p_x1, "")
spacing_u1 = use("Spacing", -2300, -100)
cell_div = binary(unreal.MaterialExpressionDivide, p_x1, spacing_u1, -2150, -150)
half_u1 = use("half", -2150, -30)
cell_add = binary(unreal.MaterialExpressionAdd, cell_div, half_u1, -2000, -100)
cell_round = expr(unreal.MaterialExpressionRound, -1850, -100)
_connect(cell_add, "", cell_round, "")
id_clamp = expr(unreal.MaterialExpressionClamp, -1700, -100, min_default=0.0)
_connect(cell_round, "", id_clamp, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(count_m1, "", id_clamp, "Max")
make_decl("id", id_clamp, -1550, -100, C_UV)

# ---- phase = fract(Time * Speed - id * Stagger) ----
time_n = expr(unreal.MaterialExpressionTime, -3250, 350)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 1.0, 0, "Pulse cycles per second. Positive = the wave runs left to right",
                       -3250, 470)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3050, 400)
id_u1 = use("id", -3050, 550)
stagger_p = scalar_param("Stagger", 0.12, 1, "Delay between neighboring bars, as a fraction of a cycle",
                         -3050, 650)
id_lag = binary(unreal.MaterialExpressionMultiply, id_u1, stagger_p, -2900, 600)
phase_sub = binary(unreal.MaterialExpressionSubtract, t_speed, id_lag, -2750, 450)
phase_frac = expr(unreal.MaterialExpressionFrac, -2600, 450)
_connect(phase_sub, "", phase_frac, "")

# ---- pulse = (1 - cos(TAU * saturate(phase / PulseWidth))) / 2  (0 -> 1 -> 0, then rest) ----
pulsew_p = scalar_param("PulseWidth", 1.0, 2,
                        "Length of one bar's pulse, as a fraction of a cycle (the rest of the cycle is a pause; "
                        "1 = a continuous wave)", -2600, 580)
pw_div = binary(unreal.MaterialExpressionDivide, phase_frac, pulsew_p, -2400, 500)
pw_sat = expr(unreal.MaterialExpressionSaturate, -2250, 500)
_connect(pw_div, "", pw_sat, "")
pw_ang = expr(unreal.MaterialExpressionMultiply, -2100, 500, const_b=TAU)
_connect(pw_sat, "", pw_ang, "A")
pw_cos = expr(unreal.MaterialExpressionCosine, -1950, 500, period=TAU)   # period 2*PI = radians
_connect(pw_ang, "", pw_cos, "")
pw_inv = expr(unreal.MaterialExpressionOneMinus, -1800, 500)
_connect(pw_cos, "", pw_inv, "")
pulse_v = expr(unreal.MaterialExpressionMultiply, -1650, 500, const_b=0.5)
_connect(pw_inv, "", pulse_v, "A")
make_decl("pulse", pulse_v, -1500, 500, C_TM)

# ---- capR = Thickness / 2;  seg = max(lerp(HeightMin, HeightMax, pulse) - capR, 0) ----
thick_p = scalar_param("Thickness", 0.16, 2,
                       "Bar width. The ends are rounded. Keep it below Spacing, or a bar is cut at the cell border",
                       -1250, 650)
cap_v = expr(unreal.MaterialExpressionMultiply, -1050, 650, const_b=0.5)
_connect(thick_p, "", cap_v, "A")
make_decl("capR", cap_v, -900, 650, C_SDF)
hmin_p = scalar_param("HeightMin", 0.16, 3,
                      "Half height of a bar at rest, from the center line to the tip of its rounded end "
                      "(at least Thickness / 2)", -1250, 200)
hmax_p = scalar_param("HeightMax", 0.72, 4, "Half height of a bar at the peak of its pulse", -1250, 300)
pulse_u1 = use("pulse", -1250, 400)
h_v = expr(unreal.MaterialExpressionLinearInterpolate, -1000, 300)
_connect(hmin_p, "", h_v, "A")
_connect(hmax_p, "", h_v, "B")
_connect(pulse_u1, "", h_v, "Alpha")
cap_u1 = use("capR", -1000, 420)
seg_sub = binary(unreal.MaterialExpressionSubtract, h_v, cap_u1, -850, 350)
seg_v = expr(unreal.MaterialExpressionMax, -700, 350, const_b=0.0)
_connect(seg_sub, "", seg_v, "A")

# ---- cx = (id - half) * Spacing;  d = length((p.x - cx, max(abs(p.y) - seg, 0))) - capR ----
id_u2 = use("id", -1250, -300)
half_u2 = use("half", -1250, -200)
cx_sub = binary(unreal.MaterialExpressionSubtract, id_u2, half_u2, -1100, -250)
spacing_u2 = use("Spacing", -1100, -150)
cx_v = binary(unreal.MaterialExpressionMultiply, cx_sub, spacing_u2, -950, -200)
p_u2 = use("p", -1250, -500)
p_x2 = mask_x(-1100, -550)
_connect(p_u2, "", p_x2, "")
p_y2 = mask_y(-1100, -430)
_connect(p_u2, "", p_y2, "")
dx_v = binary(unreal.MaterialExpressionSubtract, p_x2, cx_v, -800, -400)
py_abs = expr(unreal.MaterialExpressionAbs, -800, -100)
_connect(p_y2, "", py_abs, "")
dy_sub = binary(unreal.MaterialExpressionSubtract, py_abs, seg_v, -550, 0)
dy_v = expr(unreal.MaterialExpressionMax, -400, 0, const_b=0.0)
_connect(dy_sub, "", dy_v, "A")
q_v = binary(unreal.MaterialExpressionAppendVector, dx_v, dy_v, -250, -250)
q_len = expr(unreal.MaterialExpressionLength, -100, -250)
_connect(q_v, "", q_len, "")
cap_u2 = use("capR", -100, -130)
d_v = binary(unreal.MaterialExpressionSubtract, q_len, cap_u2, 50, -200)
make_decl("d", d_v, 200, -200, C_SDF)

# ---- mask = saturate(0.5 - d / aa)  (anti-aliased mask, 1px-wide edge) ----
d_u1 = use("d", 450, -250)
aa_u1 = use("aa", 450, -150)
d_over_aa = binary(unreal.MaterialExpressionDivide, d_u1, aa_u1, 600, -200)
half_minus = expr(unreal.MaterialExpressionSubtract, 750, -200, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_sat = expr(unreal.MaterialExpressionSaturate, 900, -200)
_connect(half_minus, "", mask_sat, "")
make_decl("mask", mask_sat, 1050, -200, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 1300, -300,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Bar color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 1300, -50)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, 1550, -250)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 1300, 150)
cov_a = expr(unreal.MaterialExpressionMultiply, 1550, 150)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 1700, 100)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

smt.set_material_root_position(mat, 1960, -270)

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "By default (Count - 1) / 2 * Spacing + Thickness / 2 = 0.72 across and HeightMax = 0.72 up and down: "
         "the outer size shared by the square layouts. Raise Count only together with a smaller Spacing.",
    -3300,  - 490, 650, 520, C_SC)
smt.create_comment_in_material(
    mat, "Nearest bar\n"
         "Pixels beyond the row go to the end bars. Every bar has the same width, so one capsule per pixel is "
         "enough while Thickness < Spacing.",
    -2500, -320, 1050, 380, C_UV)
smt.create_comment_in_material(
    mat, "Wave\n"
         "A bar grows over the first PulseWidth of its cycle, then rests; PulseWidth 1 gives a continuous "
         "wave. A positive Speed runs left to right.\n"
         "Time has Ignore Pause on (real time), so the bars keep moving while the game thread is blocked.",
    -3300, 250, 1950, 520, C_TM)
smt.create_comment_in_material(
    mat, "HeightMin and HeightMax reach the tip of the rounded end, so seg is half the straight part.",
    -1300, 100, 750, 700, C_SDF)
smt.create_comment_in_material(
    mat, "Anti-aliasing\n"
         "Heights differ per bar, so d jumps at cell borders: the AA width is PixelSize, not fwidth(d).",
    -1300, -620, 1650, 720, C_SDF)

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
expected_decls = sorted(["p", "aa", "half", "Spacing", "id", "pulse", "capR", "d", "mask"])
expected_usages = {"p": 2, "aa": 1, "half": 2, "Spacing": 2, "id": 2, "pulse": 1, "capR": 2, "d": 1, "mask": 1}
expected_params = sorted(["Count", "Spacing", "Thickness", "HeightMin", "HeightMax", "Speed", "Stagger",
                          "PulseWidth", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 5
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
