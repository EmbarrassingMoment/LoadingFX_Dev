"""
Pulsing dot row -> M_LoadingDotRow (Material Domain = UI, Translucent)

横一列に並んだ Count 個の点が、左から順に膨らんで明るくなり、また小さく薄く戻るロードアイコン(入力中インジケーター風)。
ピクセルの x から最も近い点の番号を直接求め、その点の円 SDF を 1 回だけ評価するのでループ不要。
DotRadiusMax <= Spacing / 2 なら点が隣のセルにはみ出さないので、最も近い点だけを見れば足りる。
デザインは 2026-10-10 のスピナー案(Canvas プレビュー)でユーザーが選んだもの。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  half   = (Count - 1) / 2
  id     = clamp(round(p.x / Spacing + half), 0, Count - 1)
                                                    (最も近い点の番号。0 = 左端。列の外のピクセルは端の点へ)
  phase  = fract(Time * Speed - id * Stagger)       (点ごとに Stagger サイクルずつ遅れる。Speed はサイクル/秒、
                                                     正 = 波が左から右へ進む)
  pulse  = (1 - cos(TAU * saturate(phase / PulseWidth))) / 2
                                                    (サイクルの先頭 PulseWidth の間に 0 -> 1 -> 0、残りは 0 で休む)
  r      = lerp(DotRadiusMin, DotRadiusMax, pulse)
  cx     = (id - half) * Spacing                    (点の中心の x)
  d      = length((p.x - cx, p.y)) - r
  mask   = clamp(0.5 - d / aa, 0, 1)
  alpha  = lerp(OpacityMin, 1, pulse)

  点ごとに半径が違うので d はセル境界で不連続。AA 幅は fwidth(d) ではなく PixelSize を使う(M_LoadingDotGrid と同じ)。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * alpha * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は (Count - 1) / 2 * Spacing + DotRadiusMax = 0.72(材質契約の基準正方形の半幅、パルスのピーク時)に合わせてある。
  Count を増やすときは Spacing を小さくしないと列がウィジェットからはみ出す。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(並びはグループ内の Sort Priority)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Spacing(2 箇所)は Declaration 化、Count - 1 は 1 つのノードから half と clamp の Max へ直接配線、
  他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingdotrow.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingDotRow"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
TAU = 6.28318530718
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "OpacityMin": "Appearance",
    "Count": "Shape",
    "Spacing": "Shape",
    "DotRadiusMin": "Shape",
    "DotRadiusMax": "Shape",
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

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3100, -650, material_function=mf_coords)
make_decl("p", coords, -2800, -700, C_UV, "P")
make_decl("aa", coords, -2800, -580, C_SDF, "PixelSize")

# ---- half = (Count - 1) / 2 ----
count_p = scalar_param("Count", 3.0, 0, "Number of dots (integer, 1 or more)", -3250, -300)
count_m1 = expr(unreal.MaterialExpressionSubtract, -3050, -300, const_b=1.0)   # also the clamp's Max below
_connect(count_p, "", count_m1, "A")
half_v = expr(unreal.MaterialExpressionMultiply, -2900, -350, const_b=0.5)
_connect(count_m1, "", half_v, "A")
make_decl("half", half_v, -2750, -350, C_SC)

# Footprint (material contract): (Count - 1) / 2 * Spacing + DotRadiusMax = 0.72, the reference square, at the pulse peak.
spacing_p = scalar_param("Spacing", 0.52, 1,
                         "Distance between neighboring dot centers (half the shorter widget side = 1.0)",
                         -3250, -100)
make_decl("Spacing", spacing_p, -3000, -100, C_SC)

# ---- id = clamp(round(p.x / Spacing + half), 0, Count - 1)  (nearest dot; 0 = leftmost) ----
p_u1 = use("p", -2450, -200)
p_x1 = mask_x(-2300, -200)
_connect(p_u1, "", p_x1, "")
spacing_u1 = use("Spacing", -2300, -100)
cell_div = expr(unreal.MaterialExpressionDivide, -2150, -150)
_connect(p_x1, "", cell_div, "A")
_connect(spacing_u1, "", cell_div, "B")
half_u1 = use("half", -2150, -30)
cell_add = expr(unreal.MaterialExpressionAdd, -2000, -100)
_connect(cell_div, "", cell_add, "A")
_connect(half_u1, "", cell_add, "B")
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
speed_p = scalar_param("Speed", 1.1, 0, "Pulse cycles per second. Positive = the wave runs left to right",
                       -3250, 470)
t_speed = expr(unreal.MaterialExpressionMultiply, -3050, 400)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
id_u1 = use("id", -3050, 550)
stagger_p = scalar_param("Stagger", 0.16, 1, "Delay between neighboring dots, as a fraction of a cycle",
                         -3050, 650)
id_lag = expr(unreal.MaterialExpressionMultiply, -2900, 600)
_connect(id_u1, "", id_lag, "A")
_connect(stagger_p, "", id_lag, "B")
phase_sub = expr(unreal.MaterialExpressionSubtract, -2750, 450)
_connect(t_speed, "", phase_sub, "A")
_connect(id_lag, "", phase_sub, "B")
phase_frac = expr(unreal.MaterialExpressionFrac, -2600, 450)
_connect(phase_sub, "", phase_frac, "")

# ---- pulse = (1 - cos(TAU * saturate(phase / PulseWidth))) / 2  (0 -> 1 -> 0, then rest) ----
pulsew_p = scalar_param("PulseWidth", 0.55, 2,
                        "Length of one dot's pulse, as a fraction of a cycle (the rest of the cycle is a pause)",
                        -2600, 580)
pw_div = expr(unreal.MaterialExpressionDivide, -2400, 500)
_connect(phase_frac, "", pw_div, "A")
_connect(pulsew_p, "", pw_div, "B")
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

# ---- cx = (id - half) * Spacing;  d = length((p.x - cx, p.y)) - lerp(DotRadiusMin, DotRadiusMax, pulse) ----
id_u2 = use("id", -1250, -300)
half_u2 = use("half", -1250, -200)
cx_sub = expr(unreal.MaterialExpressionSubtract, -1100, -250)
_connect(id_u2, "", cx_sub, "A")
_connect(half_u2, "", cx_sub, "B")
spacing_u2 = use("Spacing", -1100, -150)
cx_v = expr(unreal.MaterialExpressionMultiply, -950, -200)
_connect(cx_sub, "", cx_v, "A")
_connect(spacing_u2, "", cx_v, "B")
p_u2 = use("p", -1250, -500)
p_x2 = mask_x(-1100, -550)
_connect(p_u2, "", p_x2, "")
p_y2 = mask_y(-1100, -430)
_connect(p_u2, "", p_y2, "")
dx_v = expr(unreal.MaterialExpressionSubtract, -800, -400)
_connect(p_x2, "", dx_v, "A")
_connect(cx_v, "", dx_v, "B")
q_v = expr(unreal.MaterialExpressionAppendVector, -650, -450)
_connect(dx_v, "", q_v, "A")
_connect(p_y2, "", q_v, "B")
q_len = expr(unreal.MaterialExpressionLength, -500, -450)
_connect(q_v, "", q_len, "")
rmin_p = scalar_param("DotRadiusMin", 0.1, 2, "Dot radius at rest", -1250, 100)
rmax_p = scalar_param("DotRadiusMax", 0.2, 3,
                      "Dot radius at the peak of its pulse (at most Spacing / 2, or a dot is cut at the cell border)",
                      -1250, 200)
pulse_u1 = use("pulse", -1250, 300)
r_v = expr(unreal.MaterialExpressionLinearInterpolate, -1000, 200)
_connect(rmin_p, "", r_v, "A")
_connect(rmax_p, "", r_v, "B")
_connect(pulse_u1, "", r_v, "Alpha")
d_v = expr(unreal.MaterialExpressionSubtract, -350, -200)
_connect(q_len, "", d_v, "A")
_connect(r_v, "", d_v, "B")
make_decl("d", d_v, -200, -200, C_SDF)

# ---- mask = clamp(0.5 - d / aa, 0, 1)  (anti-aliased mask, 1px-wide edge) ----
d_u1 = use("d", 100, -250)
aa_u1 = use("aa", 100, -150)
d_over_aa = expr(unreal.MaterialExpressionDivide, 250, -200)
_connect(d_u1, "", d_over_aa, "A")
_connect(aa_u1, "", d_over_aa, "B")
half_minus = expr(unreal.MaterialExpressionSubtract, 400, -200, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_clamp = expr(unreal.MaterialExpressionClamp, 550, -200, min_default=0.0, max_default=1.0)
_connect(half_minus, "", mask_clamp, "")
make_decl("mask", mask_clamp, 700, -200, C_COL)

# ---- alpha = lerp(OpacityMin, 1, pulse) ----
opacitymin_p = scalar_param("OpacityMin", 0.35, 1, "Opacity of a dot at rest; 1 at the peak of its pulse", 100, 100)
pulse_u2 = use("pulse", 100, 220)
alpha_v = expr(unreal.MaterialExpressionLinearInterpolate, 350, 150, const_b=1.0)
_connect(opacitymin_p, "", alpha_v, "A")
_connect(pulse_u2, "", alpha_v, "Alpha")
make_decl("alpha", alpha_v, 550, 150, C_TM)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb,
#      Opacity = mask * alpha * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 1000, -300,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Dot color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 1000, -50)
emissive = expr(unreal.MaterialExpressionMultiply, 1250, -250)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 1000, 150)
alpha_u1 = use("alpha", 1000, 250)
coverage = expr(unreal.MaterialExpressionMultiply, 1150, 200)
_connect(mask_u1, "", coverage, "A")
_connect(alpha_u1, "", coverage, "B")
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
    mat, "(Count - 1) / 2 * Spacing + DotRadiusMax = 0.72 by default: the outer size shared by the square "
         "layouts. Raise Count only together with a smaller Spacing, or the row leaves the widget.",
    -3300,  - 490, 650, 520, C_SC)
smt.create_comment_in_material(
    mat, "Nearest dot\n"
         "Pixels beyond the row go to the end dots. One circle per pixel is enough while DotRadiusMax <= "
         "Spacing / 2.",
    -2500, -320, 1050, 380, C_UV)
smt.create_comment_in_material(
    mat, "Pulse\n"
         "A dot swells and brightens over the first PulseWidth of its cycle, then rests. A positive Speed runs "
         "left to right.\n"
         "Time has Ignore Pause on (real time), so the dots keep pulsing while the game thread is blocked.",
    -3300, 250, 1950, 520, C_TM)
smt.create_comment_in_material(
    mat, "Anti-aliasing\n"
         "Radii differ per dot, so d jumps at cell borders: the AA width is PixelSize, not fwidth(d).",
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

expected_decls = sorted(["p", "aa", "half", "Spacing", "id", "pulse", "d", "mask", "alpha"])
expected_usages = {"p": 2, "aa": 1, "half": 2, "Spacing": 2, "id": 2, "pulse": 2, "d": 1, "mask": 1, "alpha": 1}
expected_params = sorted(["Count", "Spacing", "DotRadiusMin", "DotRadiusMax", "OpacityMin", "Speed", "Stagger",
                          "PulseWidth", "PrimaryColor"])
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
