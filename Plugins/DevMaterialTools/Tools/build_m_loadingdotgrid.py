"""
Dot grid (Shadertoy, loop-free) -> M_LoadingDotGrid (Material Domain = UI, Translucent)

8 つの球を四角形に配置し、12 時の位置から時計回りに拡大パルスが巡回するロードアイコン。
ピクセルが属するグリッドセルから担当の球を直接求めるのでループ不要。

パルスは非対称: 先頭が来る直前に Attack(球数単位)で素早く膨らみ、通過後は Trail(球数単位)かけて
ゆっくり縮む(余韻)。元の Shadertoy は abs 距離の対称パルス(Width)だったが、2026-10-02 ユーザー指示で
「静止時の球を小さく + 余韻」に変更。

  uv       = MF_SpinnerCoords.P                     (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa       = MF_SpinnerCoords.PixelSize             (1 ピクセルを uv 単位で)
  cell     = clamp(round(uv / Spacing), -1, 1)
  isCenter = step(dot(cell, cell), 0.5)
  a        = atan(cell.x, cell.y + isCenter)         (Arctangent2: Y = cell.x, X = cell.y + isCenter)
  idx      = mod(round(a * 4/PI), 8)                 (mod は MF_GLSLMod)
  head     = fract(Time * Speed) * 8
  age      = mod(head - idx + Attack, 8)             (0 = 膨らみ始め、Attack = 先頭が球に到達(最大)、以降が余韻)
  rise     = smoothstep(0, Attack, age)
  fall     = 1 - smoothstep(0, Trail, age - Attack)
  pulse    = rise * fall                             (Attack + Trail <= 8 なら一周の継ぎ目で不連続にならない)
  r        = DotRadiusMin + (DotRadiusMax - DotRadiusMin) * pulse
  d        = length(uv - cell*Spacing) - r           (sdCircle をインライン展開)
  d       += isCenter * 1e5                          (中央セルは描画しない)
  mask     = clamp(0.5 - d/aa, 0, 1)

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  背景(BG)は不要なので mix は省略。
  デフォルト値は Spacing + DotRadiusMax = 0.72(材質契約の基準正方形の半幅、パルスのピーク時)に合わせてある。

  const  -> ScalarParameter (Spacing/DotRadiusMin/DotRadiusMax/Speed/Attack/Trail、グループ Appearance / Shape / Motion)
  色     -> VectorParameter PrimaryColor(元の Shadertoy は白固定)
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Spacing(2 箇所)と Attack(3 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingdotgrid.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingDotGrid"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_MOD_PATH = "/LoadingFX/MaterialFunctions/MF_GLSLMod"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
PI = 3.14159265
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "Spacing": "Shape",
    "DotRadiusMin": "Shape",
    "DotRadiusMax": "Shape",
    "Speed": "Motion",
    "Attack": "Motion",
    "Trail": "Motion",
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

mf_mod = unreal.load_asset(MF_MOD_PATH)
assert mf_mod, f"required Material Function not found: {MF_MOD_PATH}"
mf_coords = unreal.load_asset(MF_COORDS_PATH)
assert mf_coords, f"required Material Function not found: {MF_COORDS_PATH}"

if lib.does_asset_exist(FULL_PATH):
    lib.delete_asset(FULL_PATH)
mat = tools.create_asset(ASSET_NAME, ASSET_PATH, unreal.Material, unreal.MaterialFactoryNew())
mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_UI)
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
print(f"[TEST] Created material: {FULL_PATH} (UI / Translucent)")

def expr(cls, x, y):
    return mel.create_material_expression(mat, cls, x, y)

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
    dcl = expr(unreal.MaterialExpressionNamedRerouteDeclaration, x, y)
    dcl.set_editor_property("name", name)
    dcl.set_editor_property("node_color", color)
    _connect(src, out_name, dcl, "")
    decls[name] = dcl
    return dcl

def use(name, x, y):
    return smt.create_named_reroute_usage(mat, decls[name], x, y)

def scalar_param(name, default, sort, desc, x, y):
    p_ = expr(unreal.MaterialExpressionScalarParameter, x, y)
    p_.set_editor_property("parameter_name", name)
    p_.set_editor_property("default_value", default)
    p_.set_editor_property("group", PARAM_GROUPS[name])
    p_.set_editor_property("sort_priority", sort)
    p_.set_editor_property("desc", desc)
    return p_

def constant(value, x, y):
    c_ = expr(unreal.MaterialExpressionConstant, x, y)
    c_.set_editor_property("r", value)
    return c_

def mask_x(x, y):
    m_ = expr(unreal.MaterialExpressionComponentMask, x, y)
    m_.set_editor_property("r", True); m_.set_editor_property("g", False)
    m_.set_editor_property("b", False); m_.set_editor_property("a", False)
    return m_

def mask_y(x, y):
    m_ = expr(unreal.MaterialExpressionComponentMask, x, y)
    m_.set_editor_property("r", False); m_.set_editor_property("g", True)
    m_.set_editor_property("b", False); m_.set_editor_property("a", False)
    return m_

def glsl_mod(x_src, y_value, x, y):
    """mod(x, y_value) via MF_GLSLMod (never inline / Fmod)."""
    y_c = constant(y_value, x - 150, y + 120)
    call = expr(unreal.MaterialExpressionMaterialFunctionCall, x, y)
    call.set_editor_property("material_function", mf_mod)
    _connect(x_src, "", call, "X")
    _connect(y_c, "", call, "Y")
    return call

# ---- const SPACING (used twice -> Named Reroute) ----
# Footprint (material contract): Spacing + DotRadiusMax = 0.72, the reference square (grid layout, at the pulse peak).
spacing_p = scalar_param("Spacing", 0.54, 0,
                         "Distance between neighboring dot centers (half the shorter widget side = 1.0)", -4300, -300)
make_decl("Spacing", spacing_p, -4100, -300, C_SC)

# ---- uv = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -4150, 50)
coords.set_editor_property("material_function", mf_coords)
make_decl("uv", coords, -3850, 0, C_UV, "P")
make_decl("aa", coords, -3850, 120, C_SDF, "PixelSize")

# ---- 1. cell = clamp(round(uv / Spacing), -1, 1)  (3x3 grid cell, clamped to the outer ring) ----
uv_u1 = use("uv", -3500, 0)
spacing_u1 = use("Spacing", -3500, 100)
cell_div = expr(unreal.MaterialExpressionDivide, -3350, 50)
_connect(uv_u1, "", cell_div, "A")
_connect(spacing_u1, "", cell_div, "B")
cell_round = expr(unreal.MaterialExpressionRound, -3200, 50)
_connect(cell_div, "", cell_round, "")
cell_clamp = expr(unreal.MaterialExpressionClamp, -3050, 50)
cell_clamp.set_editor_property("min_default", -1.0)
cell_clamp.set_editor_property("max_default", 1.0)
_connect(cell_round, "", cell_clamp, "")
make_decl("cell", cell_clamp, -2900, 50, C_UV)

# ---- isCenter = step(dot(cell, cell), 0.5)  (center cell has no ball) ----
cell_u1 = use("cell", -2700, 300)
cell_dot = expr(unreal.MaterialExpressionDotProduct, -2550, 300)
_connect(cell_u1, "", cell_dot, "A")
_connect(cell_u1, "", cell_dot, "B")
# UE Step(Y, X) returns 1 when X >= Y, i.e. GLSL step(edge=Y, x=X).
# GLSL step(dot, 0.5) therefore maps to Y = dot (edge), X = const 0.5.
center_step = expr(unreal.MaterialExpressionStep, -2400, 300)   # 1 when 0.5 >= dot
center_step.set_editor_property("const_x", 0.5)
_connect(cell_dot, "", center_step, "Y")
make_decl("isCenter", center_step, -2250, 300, C_SC)

# ---- 2. a = atan(cell.x, cell.y + isCenter)  (0 at 12 o'clock, clockwise; isCenter avoids atan(0,0)) ----
cell_u2 = use("cell", -2700, 500)
cell_x = mask_x(-2550, 500)
_connect(cell_u2, "", cell_x, "")
cell_u3 = use("cell", -2700, 620)
cell_y = mask_y(-2550, 620)
_connect(cell_u3, "", cell_y, "")
center_u1 = use("isCenter", -2550, 740)
cell_y_safe = expr(unreal.MaterialExpressionAdd, -2400, 680)
_connect(cell_y, "", cell_y_safe, "A")
_connect(center_u1, "", cell_y_safe, "B")
a_atan = expr(unreal.MaterialExpressionArctangent2, -2250, 560)   # atan2(Y, X) = GLSL atan(y, x)
_connect(cell_x, "", a_atan, "Y")
_connect(cell_y_safe, "", a_atan, "X")
make_decl("a", a_atan, -2100, 560, C_SC)

# ---- idx = mod(round(a * 4/PI), 8)  (ball index 0..7) ----
a_u1 = use("a", -1900, 560)
a_scaled = expr(unreal.MaterialExpressionMultiply, -1750, 560)
a_scaled.set_editor_property("const_b", 4.0 / PI)
_connect(a_u1, "", a_scaled, "A")
a_round = expr(unreal.MaterialExpressionRound, -1600, 560)
_connect(a_scaled, "", a_round, "")
idx_mod = glsl_mod(a_round, 8.0, -1450, 600)
make_decl("idx", idx_mod, -1300, 600, C_SC)

# ---- 3. head = fract(Time * Speed) * 8  (pulse position, 0..8) ----
time_n = expr(unreal.MaterialExpressionTime, -1900, 900)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.8, 0, "Revolutions of the pulse per second. Positive = clockwise", -1900, 1000)
t_speed = expr(unreal.MaterialExpressionMultiply, -1750, 950)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
t_frac = expr(unreal.MaterialExpressionFrac, -1600, 950)
_connect(t_speed, "", t_frac, "")
head_v = expr(unreal.MaterialExpressionMultiply, -1450, 950)
head_v.set_editor_property("const_b", 8.0)
_connect(t_frac, "", head_v, "A")
make_decl("head", head_v, -1300, 950, C_TM)

# ---- const ATTACK (used three times -> Named Reroute) ----
attack_p = scalar_param("Attack", 0.5, 1, "Dots over which a dot swells before the head reaches it", -1900, 1150)
make_decl("Attack", attack_p, -1750, 1150, C_TM)

# ---- age = mod(head - idx + Attack, 8)  (0 = starts to swell, Attack = head on the ball, then the trail) ----
head_u1 = use("head", -1100, 800)
idx_u1 = use("idx", -1100, 900)
hi_sub = expr(unreal.MaterialExpressionSubtract, -950, 850)
_connect(head_u1, "", hi_sub, "A")
_connect(idx_u1, "", hi_sub, "B")
attack_u1 = use("Attack", -950, 980)
hi_add = expr(unreal.MaterialExpressionAdd, -800, 900)
_connect(hi_sub, "", hi_add, "A")
_connect(attack_u1, "", hi_add, "B")
age_mod = glsl_mod(hi_add, 8.0, -650, 930)
make_decl("age", age_mod, -500, 930, C_TM)

# ---- rise = smoothstep(0, Attack, age); fall = 1 - smoothstep(0, Trail, age - Attack); pulse = rise * fall ----
age_u1 = use("age", -250, 780)
attack_u2 = use("Attack", -250, 880)
rise_ss = expr(unreal.MaterialExpressionSmoothStep, -100, 800)
rise_ss.set_editor_property("const_min", 0.0)
_connect(attack_u2, "", rise_ss, "Max")
_connect(age_u1, "", rise_ss, "Value")
age_u2 = use("age", -250, 1000)
attack_u3 = use("Attack", -250, 1100)
age_after = expr(unreal.MaterialExpressionSubtract, -100, 1040)
_connect(age_u2, "", age_after, "A")
_connect(attack_u3, "", age_after, "B")
trail_p = scalar_param("Trail", 4.0, 2,
                       "Dots over which a dot shrinks back after the head passed (keep Attack + Trail <= 8)", -100, 1160)
fall_ss = expr(unreal.MaterialExpressionSmoothStep, 50, 1060)
fall_ss.set_editor_property("const_min", 0.0)
_connect(trail_p, "", fall_ss, "Max")
_connect(age_after, "", fall_ss, "Value")
fall_om = expr(unreal.MaterialExpressionOneMinus, 200, 1060)
_connect(fall_ss, "", fall_om, "")
pulse_v = expr(unreal.MaterialExpressionMultiply, 350, 930)
_connect(rise_ss, "", pulse_v, "A")
_connect(fall_om, "", pulse_v, "B")
make_decl("pulse", pulse_v, 450, 930, C_TM)

# ---- r = DotRadiusMin + (DotRadiusMax - DotRadiusMin) * pulse ----
rmin_p = scalar_param("DotRadiusMin", 0.06, 1, "Dot radius at rest", 450, 1080)
make_decl("DotRadiusMin", rmin_p, 650, 1080, C_SC)
rmax_p = scalar_param("DotRadiusMax", 0.18, 2, "Dot radius at the peak of the pulse", 450, 980)
rmin_u1 = use("DotRadiusMin", 600, 1030)
r_range = expr(unreal.MaterialExpressionSubtract, 750, 980)   # DotRadiusMax - DotRadiusMin
_connect(rmax_p, "", r_range, "A")
_connect(rmin_u1, "", r_range, "B")
pulse_u1 = use("pulse", 750, 880)
r_grow = expr(unreal.MaterialExpressionMultiply, 900, 920)
_connect(r_range, "", r_grow, "A")
_connect(pulse_u1, "", r_grow, "B")
rmin_u2 = use("DotRadiusMin", 900, 800)
r_v = expr(unreal.MaterialExpressionAdd, 1050, 850)
_connect(rmin_u2, "", r_v, "A")
_connect(r_grow, "", r_v, "B")
make_decl("r", r_v, 1200, 850, C_SDF)

# ---- 4. d = length(uv - cell*Spacing) - r  (sdCircle expanded inline); d += isCenter * 1e5 ----
cell_u4 = use("cell", 600, 300)
spacing_u2 = use("Spacing", 600, 400)
cell_center = expr(unreal.MaterialExpressionMultiply, 750, 350)
_connect(cell_u4, "", cell_center, "A")
_connect(spacing_u2, "", cell_center, "B")
uv_u2 = use("uv", 750, 250)
p_local = expr(unreal.MaterialExpressionSubtract, 900, 300)
_connect(uv_u2, "", p_local, "A")
_connect(cell_center, "", p_local, "B")
zero2 = expr(unreal.MaterialExpressionConstant2Vector, 900, 420)
p_len = expr(unreal.MaterialExpressionDistance, 1050, 350)   # length(p) = distance(p, 0)
_connect(p_local, "", p_len, "A")
_connect(zero2, "", p_len, "B")
r_u1 = use("r", 1050, 470)
d_circle = expr(unreal.MaterialExpressionSubtract, 1200, 400)
_connect(p_len, "", d_circle, "A")
_connect(r_u1, "", d_circle, "B")
center_u2 = use("isCenter", 1200, 550)
center_big = expr(unreal.MaterialExpressionMultiply, 1350, 550)
center_big.set_editor_property("const_b", 1e5)
_connect(center_u2, "", center_big, "A")
d_v = expr(unreal.MaterialExpressionAdd, 1500, 450)
_connect(d_circle, "", d_v, "A")
_connect(center_big, "", d_v, "B")
make_decl("d", d_v, 1650, 450, C_SDF)

# ---- mask = clamp(0.5 - d/aa, 0, 1)  (1px-wide coverage approximation around the edge) ----
d_u1 = use("d", 1900, 300)
aa_u1 = use("aa", 1900, 400)
d_over_aa = expr(unreal.MaterialExpressionDivide, 2050, 350)
_connect(d_u1, "", d_over_aa, "A")
_connect(aa_u1, "", d_over_aa, "B")
half_minus = expr(unreal.MaterialExpressionSubtract, 2200, 350)
half_minus.set_editor_property("const_a", 0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_clamp = expr(unreal.MaterialExpressionClamp, 2350, 350)
mask_clamp.set_editor_property("min_default", 0.0)
mask_clamp.set_editor_property("max_default", 1.0)
_connect(half_minus, "", mask_clamp, "")
make_decl("mask", mask_clamp, 2500, 350, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2700, 100)
primary_p.set_editor_property("parameter_name", "PrimaryColor")
primary_p.set_editor_property("default_value", unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
primary_p.set_editor_property("group", PARAM_GROUPS["PrimaryColor"])
primary_p.set_editor_property("sort_priority", 0)
primary_p.set_editor_property("desc", "Dot color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 2700, 350)
emissive = expr(unreal.MaterialExpressionMultiply, 2950, 150)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 2700, 550)
mask_a = expr(unreal.MaterialExpressionMultiply, 2950, 450)
_connect(mask_u1, "", mask_a, "A")
_connect(primary_p, "A", mask_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 3100, 500)
_connect(mask_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "const SPACING -> ScalarParameter (used twice -> Named Reroute; ATTACK and DotRadiusMin likewise).\n"
         "DotRadiusMax / Speed / Trail / PrimaryColor are wired directly at their single use site",
    -4350, -400, 650, 250, C_SC)
smt.create_comment_in_material(
    mat, "uv = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in uv units)",
    -4350, -100, 850, 400, C_UV)
smt.create_comment_in_material(
    mat, "1. cell = clamp(round(uv / Spacing), -1, 1)\n"
         "3x3 grid cell (-1, 0, 1); pixels outside the grid snap to the outer ring",
    -3550, -100, 850, 300, C_UV)
smt.create_comment_in_material(
    mat, "isCenter = step(dot(cell, cell), 0.5)   (center cell has no ball)",
    -2750, 200, 700, 200, C_SC)
smt.create_comment_in_material(
    mat, "2. a = atan(cell.x, cell.y + isCenter)\n"
         "Angle from +Y (12 o'clock), clockwise. isCenter avoids atan(0, 0) in the center cell",
    -2750, 420, 850, 450, C_SC)
smt.create_comment_in_material(
    mat, "idx = mod(round(a * 4/PI), 8)   (ball index 0..7, mod via MF_GLSLMod)",
    -1950, 480, 850, 350, C_SC)
smt.create_comment_in_material(
    mat, "3. head = fract(Time * Speed) * 8   (pulse head position, 0..8)",
    -1950, 820, 850, 300, C_TM)
smt.create_comment_in_material(
    mat, "age = mod(head - idx + Attack, 8)\n"
         "0 = the ball starts to swell, Attack = pulse head on the ball (peak), after that the trail",
    -1150, 720, 800, 500, C_TM)
smt.create_comment_in_material(
    mat, "rise = smoothstep(0, Attack, age)   (quick swell just before the head arrives)\n"
         "fall = 1 - smoothstep(0, Trail, age - Attack)   (slow afterglow behind the head)\n"
         "pulse = rise * fall; r = DotRadiusMin + (DotRadiusMax - DotRadiusMin) * pulse   (keep Attack + Trail <= 8 for a seamless wrap)",
    -300, 700, 1650, 580, C_TM)
smt.create_comment_in_material(
    mat, "4. sdCircle expanded inline: d = length(uv - cell*Spacing) - r\n"
         "d += isCenter * 1e5   (center cell is never drawn)",
    550, 180, 1250, 480, C_SDF)
smt.create_comment_in_material(
    mat, "mask = clamp(0.5 - d/aa, 0, 1)   (1px-wide coverage approximation at the edge)\n"
         "aa is the pixel size of uv, not fwidth(d): d is discontinuous at cell borders (would draw seams).\n"
         "The circle SDF has unit gradient, so the pixel size of uv equals the pixel size of d",
    1850, 200, 800, 300, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)\n"
         "Background dropped: mix(BG, color, mask) becomes PrimaryColor with alpha",
    2650, 0, 600, 700, C_COL)

used_groups = [g for g in GROUP_ORDER if g in PARAM_GROUPS.values()]
smt.set_parameter_group_sort_priorities(mat, used_groups, list(range(len(used_groups))))

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {saved}")

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

expected_decls = sorted(["Spacing", "Attack", "DotRadiusMin", "uv", "cell", "isCenter", "a", "idx", "head", "age",
                         "pulse", "r", "d", "aa", "mask"])
expected_usages = {"Spacing": 2, "Attack": 3, "DotRadiusMin": 2, "uv": 2, "cell": 4, "isCenter": 2, "a": 1,
                   "idx": 1, "head": 1, "age": 2, "pulse": 1, "r": 1, "d": 1, "aa": 1, "mask": 1}
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == ["Attack", "DotRadiusMax", "DotRadiusMin", "PrimaryColor", "Spacing", "Speed", "Trail"]
groups_ok = param_groups == PARAM_GROUPS and group_prios == expected_prios
mf_ok = mf_calls == 3
comments_ok = len(smt.get_material_comment_texts(mat)) == 12
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and groups_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
