"""
Dot wave -> M_LoadingDotWave (Material Domain = UI, Translucent)

横一列に並んだ Count 個の点が、左から右へ進む正弦波に乗って上下するロードアイコン。波の山にある点ほど明るい。
デザインは 2026-11-21 の 1.1 向けスピナー案(Python の静止画と GIF、Saved/SpinnerConcepts)でユーザーが選んだもの。
M_LoadingDotRow と同じく、ピクセルの x から最も近い点の番号を直接求め、その点の円 SDF を 1 回だけ評価する。
点は上下に動くが、x は固定なので、DotRadius < Spacing / 2 なら各点は自分の列(幅 Spacing)の中に収まる。
ピクセルを覆いうるのはその列の点だけなので、x で最も近い点だけを見れば足りる(2D で最も近い点とは限らないが、
覆う点は必ずそれ)。clamp(x, 0, 1) は Saturate で書く。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  half   = (Count - 1) / 2
  id     = clamp(round(p.x / Spacing + half), 0, Count - 1)
                                                    (最も近い列の番号。0 = 左端。列の外のピクセルは端の点へ)
  phase  = fract(Time * Speed - id * Stagger)       (点ごとに Stagger サイクルずつ遅れる。Speed はサイクル/秒、
                                                     正 = 波が左から右へ進む。先に fract して角度を小さく保つ)
  s      = sin(TAU * phase)                         (Sine の Period 1)
  c      = ((id - half) * Spacing, s * WaveHeight)  (点の中心)
  d      = length(p - c) - DotRadius
  mask   = saturate(0.5 - d / aa)
  alpha  = lerp(OpacityMin, 1, s * 0.5 + 0.5)       (谷で OpacityMin、山で 1)

  点ごとに中心の高さが違うので d は列の境界で不連続。AA 幅は fwidth(d) ではなく PixelSize を使う(M_LoadingDotRow と同じ)。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * alpha * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は (Count - 1) / 2 * Spacing + DotRadius = 0.72(材質契約の基準正方形の半幅)に合わせてある。
  縦は WaveHeight + DotRadius = 0.42。Count を増やすときは Spacing を小さくしないと列がウィジェットからはみ出す。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(PARAM_GROUPS、順序は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Spacing(2 箇所)は Declaration 化、Count - 1 は 1 つのノードから half と clamp の Max へ直接配線、
  他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingdotwave.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingDotWave"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "OpacityMin": "Appearance",
    "Count": "Shape",
    "Spacing": "Shape",
    "DotRadius": "Shape",
    "WaveHeight": "Shape",
    "Speed": "Motion",
    "Stagger": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / columns = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / wave = light blue
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

def binary(cls, a, b, x, y):
    n = expr(cls, x, y)
    _connect(a, "", n, "A")
    _connect(b, "", n, "B")
    return n

def unary(cls, src, x, y, **props):
    n = expr(cls, x, y, **props)
    _connect(src, "", n, "")
    return n

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3100, -650, material_function=mf_coords)
make_decl("p", coords, -2800, -700, C_UV, "P")
make_decl("aa", coords, -2800, -580, C_SDF, "PixelSize")

# ---- half = (Count - 1) / 2 ----
count_p = scalar_param("Count", 5.0, 0, "Number of dots (integer, 1 or more)", -3250, -300)
count_m1 = expr(unreal.MaterialExpressionSubtract, -3050, -300, const_b=1.0)   # also the clamp's Max below
_connect(count_p, "", count_m1, "A")
half_v = expr(unreal.MaterialExpressionMultiply, -2900, -350, const_b=0.5)
_connect(count_m1, "", half_v, "A")
make_decl("half", half_v, -2750, -350, C_SC)

# Footprint (material contract): (Count - 1) / 2 * Spacing + DotRadius = 0.72, the reference square.
spacing_p = scalar_param("Spacing", 0.31, 1,
                         "Distance between neighboring dot centers (half the shorter widget side = 1.0)",
                         -3250, -100)
make_decl("Spacing", spacing_p, -3000, -100, C_SC)

# ---- id = clamp(round(p.x / Spacing + half), 0, Count - 1)  (nearest column; 0 = leftmost) ----
p_u1 = use("p", -2450, -200)
p_x1 = unary(unreal.MaterialExpressionComponentMask, p_u1, -2300, -200, r=True, g=False, b=False, a=False)
spacing_u1 = use("Spacing", -2300, -100)
cell_div = binary(unreal.MaterialExpressionDivide, p_x1, spacing_u1, -2150, -150)
half_u1 = use("half", -2150, -30)
cell_add = binary(unreal.MaterialExpressionAdd, cell_div, half_u1, -2000, -100)
cell_round = unary(unreal.MaterialExpressionRound, cell_add, -1850, -100)
id_clamp = expr(unreal.MaterialExpressionClamp, -1700, -100, min_default=0.0)
_connect(cell_round, "", id_clamp, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(count_m1, "", id_clamp, "Max")
make_decl("id", id_clamp, -1550, -100, C_UV)

# ---- s = sin(TAU * fract(Time * Speed - id * Stagger)) ----
time_n = expr(unreal.MaterialExpressionTime, -3250, 350)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 1.0, 0, "Wave cycles per second. Positive = the wave runs left to right",
                       -3250, 470)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3050, 400)
id_u1 = use("id", -3050, 550)
stagger_p = scalar_param("Stagger", 0.12, 1, "Delay between neighboring dots, as a fraction of a cycle",
                         -3050, 650)
id_lag = binary(unreal.MaterialExpressionMultiply, id_u1, stagger_p, -2900, 600)
phase_sub = binary(unreal.MaterialExpressionSubtract, t_speed, id_lag, -2750, 450)
phase_frac = unary(unreal.MaterialExpressionFrac, phase_sub, -2600, 450)
wave_sin = unary(unreal.MaterialExpressionSine, phase_frac, -2450, 450, period=1.0)   # period 1 = sin(TAU * x)
make_decl("s", wave_sin, -2300, 450, C_TM)

# ---- c = ((id - half) * Spacing, s * WaveHeight);  d = length(p - c) - DotRadius ----
id_u2 = use("id", -1250, -300)
half_u2 = use("half", -1250, -200)
cx_sub = binary(unreal.MaterialExpressionSubtract, id_u2, half_u2, -1100, -250)
spacing_u2 = use("Spacing", -1100, -150)
cx_v = binary(unreal.MaterialExpressionMultiply, cx_sub, spacing_u2, -950, -200)
s_u1 = use("s", -1250, 0)
height_p = scalar_param("WaveHeight", 0.32, 3, "How far a dot rises above and sinks below the center line",
                        -1250, 100)
cy_v = binary(unreal.MaterialExpressionMultiply, s_u1, height_p, -1050, 50)
c_v = binary(unreal.MaterialExpressionAppendVector, cx_v, cy_v, -800, -100)
p_u2 = use("p", -800, -250)
rel_v = binary(unreal.MaterialExpressionSubtract, p_u2, c_v, -650, -200)
rel_len = unary(unreal.MaterialExpressionLength, rel_v, -500, -200)
dotr_p = scalar_param("DotRadius", 0.1, 2,
                      "Radius of a dot (below Spacing / 2, or a dot is cut at the column border)", -650, -50)
d_v = binary(unreal.MaterialExpressionSubtract, rel_len, dotr_p, -350, -150)
make_decl("d", d_v, -200, -150, C_SDF)

# ---- mask = saturate(0.5 - d / aa)  (anti-aliased mask, 1px-wide edge) ----
d_u1 = use("d", 100, -250)
aa_u1 = use("aa", 100, -150)
d_over_aa = binary(unreal.MaterialExpressionDivide, d_u1, aa_u1, 250, -200)
half_minus = expr(unreal.MaterialExpressionSubtract, 400, -200, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_sat = unary(unreal.MaterialExpressionSaturate, half_minus, 550, -200)
make_decl("mask", mask_sat, 700, -200, C_COL)

# ---- alpha = lerp(OpacityMin, 1, s * 0.5 + 0.5) ----
s_u2 = use("s", 100, 220)
crest_mul = expr(unreal.MaterialExpressionMultiply, 250, 220, const_b=0.5)
_connect(s_u2, "", crest_mul, "A")
crest_add = expr(unreal.MaterialExpressionAdd, 400, 220, const_b=0.5)
_connect(crest_mul, "", crest_add, "A")
opacitymin_p = scalar_param("OpacityMin", 0.4, 1, "Opacity of a dot in the trough of the wave; 1 at the crest",
                            250, 100)
alpha_v = expr(unreal.MaterialExpressionLinearInterpolate, 550, 150, const_b=1.0)
_connect(opacitymin_p, "", alpha_v, "A")
_connect(crest_add, "", alpha_v, "Alpha")
make_decl("alpha", alpha_v, 700, 150, C_TM)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb,
#      Opacity = mask * alpha * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 1000, -300,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Dot color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 1000, -50)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, 1250, -250)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 1000, 150)
alpha_u1 = use("alpha", 1000, 250)
coverage = binary(unreal.MaterialExpressionMultiply, mask_u1, alpha_u1, 1150, 200)
cov_a = expr(unreal.MaterialExpressionMultiply, 1300, 150)
_connect(coverage, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 1450, 100)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

smt.set_material_root_position(mat, 1660, -270)

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "(Count - 1) / 2 * Spacing + DotRadius = 0.72 by default: the outer size shared by the square layouts. "
         "Raise Count only together with a smaller Spacing, or the row leaves the widget.",
    -3300, -490, 650, 520, C_SC)
smt.create_comment_in_material(
    mat, "Nearest column\n"
         "A dot moves only up and down, so it stays in its own column while DotRadius < Spacing / 2: the dot "
         "of the pixel's column is the only one that can cover it.",
    -2500, -320, 1050, 380, C_UV)
smt.create_comment_in_material(
    mat, "Wave\n"
         "A positive Speed runs the wave left to right. The Sine has Period 1: it takes cycles.\n"
         "Time has Ignore Pause on (real time), so the dots keep moving while the game thread is blocked.",
    -3300, 250, 1250, 520, C_TM)
smt.create_comment_in_material(
    mat, "Anti-aliasing\n"
         "Each dot sits at its own height, so d jumps at column borders: the AA width is PixelSize, not fwidth(d).",
    -1300, -620, 1250, 1000, C_SDF)

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

expected_decls = sorted(["p", "aa", "half", "Spacing", "id", "s", "d", "mask", "alpha"])
expected_usages = {"p": 2, "aa": 1, "half": 2, "Spacing": 2, "id": 2, "s": 2, "d": 1, "mask": 1, "alpha": 1}
expected_params = sorted(PARAM_GROUPS)
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == expected_params
groups_ok = param_groups == PARAM_GROUPS and group_prios == expected_prios
mf_ok = mf_calls == 1
comments_ok = len(smt.get_material_comment_texts(mat)) == 4
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and groups_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
