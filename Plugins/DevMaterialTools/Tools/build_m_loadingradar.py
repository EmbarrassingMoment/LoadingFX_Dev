"""
Radar sweep -> M_LoadingRadar (Material Domain = UI, Translucent)

円い画面の中を針が時計回りに回り、針の後ろに扇形の残像が尾を引くロードアイコン。画面には薄い格子(半径の半分の円と十字)と
3 つの点(ブリップ)があり、ブリップは針が通った直後に光って 1 周かけて消える。
デザインは 2026-11-21 の 1.1 向けスピナー案(Python の静止画と GIF、Saved/SpinnerConcepts)でユーザーが選んだもの。
層の重ね方は他のスピナーと同じく max(M_LoadingTimer の max(pie, ring) と同じ)。clamp(x, 0, 1) は Saturate で書く。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  cov(d) = saturate(0.5 - d / aa)                   (1 ピクセル幅の AA。下の 5 層すべてで使う)
  r      = length(p)
  a      = atan2(p.x, p.y) / TAU                    (ピクセルの向き。12 時から時計回りの回転数、-0.5..0.5)
  h      = fract(Time * Speed)                      (針の向き。Speed は回転数/秒、正 = 時計回り)
  delta  = fract(h - a)                             (針の上で 0、針の後ろ(反時計回り)へ 1 周で 1 に近づく)
  inner  = Radius - Thickness / 2                   (縁の内側。格子・残像・針はこの内側)
  disc   = cov(r - inner)
  rim    = cov(abs(r - Radius) - Thickness / 2)     (縁)
  grid   = cov(min(abs(r - Radius / 2), abs(p.x), abs(p.y)) - GridThickness / 2) * disc * GridOpacity
  trail  = saturate(1 - delta / TrailFraction)^2 * disc * TrailOpacity
                                                    (針の直後で TrailOpacity、TrailFraction 周後に 0。針の直前で
                                                     delta が 1 から 0 へ折り返す段差は針の線が覆う)
  dir    = (sin(TAU * h), cos(TAU * h))             (Sine / Cosine の Period 1)
  line   = cov(length(p - dir * clamp(dot(p, dir), 0, inner)) - SweepThickness / 2)
                                                    (中心から縁の内側までの針。iq の sdSegment の始点が原点の形)
  dBlip  = min_k length(p - Radius * B_k) - DotRadius
                                                    (B_k は固定の 3 点。半径の比 0.67 / 0.36 / 0.77、
                                                     12 時から時計回りに 0.14 / 0.47 / 0.71 周)
  blip   = cov(dBlip) * (1 - delta)^3 * BlipOpacity
                                                    (ピクセル自身の delta で消えるので、ブリップは針が通った部分から光る)
  mask   = max(grid, trail, rim, line, blip)

  atan2(0, 0) が中心ちょうどで NaN を返しても、trail は saturate で 0 になり、中心は針の線が覆う。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は Radius + Thickness / 2 = 0.8(材質契約の基準円。1.0 = 短辺の端)に合わせてある。格子の円とブリップの位置は
  Radius に比例する。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(PARAM_GROUPS、順序は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingradar.py"
"""
import math

import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingRadar"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
TAU = 6.28318530718
# Blips: (distance from the center as a fraction of Radius, turns clockwise from 12 o'clock)
BLIPS = [(0.67, 0.14), (0.36, 0.47), (0.77, 0.71)]
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "GridOpacity": "Appearance",
    "TrailOpacity": "Appearance",
    "BlipOpacity": "Appearance",
    "Radius": "Shape",
    "Thickness": "Shape",
    "GridThickness": "Shape",
    "SweepThickness": "Shape",
    "DotRadius": "Shape",
    "Speed": "Motion",
    "TrailFraction": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / positions = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / sweep = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # params / scalar intermediates = gray
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

def mask(src, x, y, r=False, g=False):
    return unary(unreal.MaterialExpressionComponentMask, src, x, y, r=r, g=g, b=False, a=False)

def coverage(d, x, y):
    """saturate(0.5 - d / aa): the anti-aliased mask of a distance, 1px-wide edge."""
    aa_u = use("aa", x, y + 100)
    d_over = binary(unreal.MaterialExpressionDivide, d, aa_u, x + 150, y + 50)
    half_minus = expr(unreal.MaterialExpressionSubtract, x + 300, y + 50, const_a=0.5)
    _connect(d_over, "", half_minus, "B")
    return unary(unreal.MaterialExpressionSaturate, half_minus, x + 450, y + 50)

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3900, -1700, material_function=mf_coords)
make_decl("p", coords, -3600, -1750, C_UV, "P")
make_decl("aa", coords, -3600, -1630, C_SDF, "PixelSize")

# ---- Shape parameters: Radius, Thickness / 2, inner = Radius - Thickness / 2 ----
# Footprint (material contract): Radius + Thickness / 2 = 0.8, the reference circle.
radius_p = scalar_param("Radius", 0.775, 0,
                        "Radius of the rim's centerline (half the shorter widget side = 1.0). "
                        "The grid circle and the blips scale with it", -3900, -1300)
make_decl("Radius", radius_p, -3600, -1300, C_SC)
thick_p = scalar_param("Thickness", 0.05, 1, "Stroke width of the rim", -3900, -1180)
half_thick = expr(unreal.MaterialExpressionMultiply, -3700, -1180, const_b=0.5)
_connect(thick_p, "", half_thick, "A")
make_decl("halfThickness", half_thick, -3550, -1180, C_SC)
radius_u0 = use("Radius", -3550, -1060)
half_thick_u0 = use("halfThickness", -3550, -960)
inner_v = binary(unreal.MaterialExpressionSubtract, radius_u0, half_thick_u0, -3400, -1010)
make_decl("inner", inner_v, -3250, -1010, C_SC)

# ---- r = length(p);  a = atan2(p.x, p.y) / TAU  (turns clockwise from 12 o'clock) ----
p_u1 = use("p", -3000, -1550)
r_v = unary(unreal.MaterialExpressionLength, p_u1, -2850, -1550)
make_decl("r", r_v, -2700, -1550, C_UV)
p_u2 = use("p", -3000, -1350)
p_x = mask(p_u2, -2850, -1400, r=True)
p_y = mask(p_u2, -2850, -1300, g=True)
# atan2(Y = p.x, X = p.y): 0 at 12 o'clock, growing clockwise (p is y-up).
a_atan = expr(unreal.MaterialExpressionArctangent2, -2650, -1350)
_connect(p_x, "", a_atan, "Y")
_connect(p_y, "", a_atan, "X")
a_div = expr(unreal.MaterialExpressionDivide, -2450, -1350, const_b=TAU)
_connect(a_atan, "", a_div, "A")
make_decl("a", a_div, -2300, -1350, C_UV)

# ---- h = fract(Time * Speed);  delta = fract(h - a) ----
time_n = expr(unreal.MaterialExpressionTime, -3900, -500)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.5, 0, "Turns per second. Positive = clockwise", -3900, -380)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3700, -450)
h_frac = unary(unreal.MaterialExpressionFrac, t_speed, -3550, -450)
make_decl("h", h_frac, -3400, -450, C_TM)
h_u1 = use("h", -3000, -650)
a_u1 = use("a", -3000, -550)
behind = binary(unreal.MaterialExpressionSubtract, h_u1, a_u1, -2850, -600)
delta_frac = unary(unreal.MaterialExpressionFrac, behind, -2700, -600)
make_decl("delta", delta_frac, -2550, -600, C_TM)

# ---- disc = cov(r - inner);  rim = cov(abs(r - Radius) - Thickness / 2) ----
r_u1 = use("r", -2300, -1050)
inner_u1 = use("inner", -2300, -950)
disc_d = binary(unreal.MaterialExpressionSubtract, r_u1, inner_u1, -2150, -1000)
make_decl("disc", coverage(disc_d, -2000, -1050), -1450, -1000, C_COL)

r_u2 = use("r", -2300, -800)
radius_u1 = use("Radius", -2300, -700)
rim_off = binary(unreal.MaterialExpressionSubtract, r_u2, radius_u1, -2150, -750)
rim_abs = unary(unreal.MaterialExpressionAbs, rim_off, -2000, -750)
half_thick_u1 = use("halfThickness", -2000, -650)
rim_d = binary(unreal.MaterialExpressionSubtract, rim_abs, half_thick_u1, -1850, -700)
make_decl("rim", coverage(rim_d, -1700, -750), -1150, -700, C_COL)

# ---- grid = cov(min(abs(r - Radius / 2), abs(p.x), abs(p.y)) - GridThickness / 2) * disc * GridOpacity ----
r_u3 = use("r", -2300, -400)
radius_u2 = use("Radius", -2300, -300)
grid_r = expr(unreal.MaterialExpressionMultiply, -2150, -300, const_b=0.5)
_connect(radius_u2, "", grid_r, "A")
ring_off = binary(unreal.MaterialExpressionSubtract, r_u3, grid_r, -2000, -350)
ring_abs = unary(unreal.MaterialExpressionAbs, ring_off, -1850, -350)
p_u3 = use("p", -2300, -150)
p_abs = unary(unreal.MaterialExpressionAbs, p_u3, -2150, -150)
cross_x = mask(p_abs, -2000, -200, r=True)
cross_y = mask(p_abs, -2000, -100, g=True)
cross_min = binary(unreal.MaterialExpressionMin, cross_x, cross_y, -1850, -150)
grid_min = binary(unreal.MaterialExpressionMin, ring_abs, cross_min, -1700, -250)
gridth_p = scalar_param("GridThickness", 0.02, 2, "Stroke width of the grid circle and cross", -1850, -30)
gridth_half = expr(unreal.MaterialExpressionMultiply, -1700, -30, const_b=0.5)
_connect(gridth_p, "", gridth_half, "A")
grid_d = binary(unreal.MaterialExpressionSubtract, grid_min, gridth_half, -1550, -200)
grid_cov = coverage(grid_d, -1400, -250)
disc_u1 = use("disc", -950, -100)
grid_in = binary(unreal.MaterialExpressionMultiply, grid_cov, disc_u1, -800, -200)
gridop_p = scalar_param("GridOpacity", 0.22, 1, "Opacity of the grid circle and cross (0 hides them)", -950, 0)
grid_v = binary(unreal.MaterialExpressionMultiply, grid_in, gridop_p, -650, -150)
make_decl("grid", grid_v, -500, -150, C_COL)

# ---- trail = saturate(1 - delta / TrailFraction)^2 * disc * TrailOpacity ----
delta_u1 = use("delta", -2300, 250)
trailf_p = scalar_param("TrailFraction", 0.3, 1,
                        "Length of the fading wedge behind the sweep, as a fraction of a turn", -2300, 350)
trail_div = binary(unreal.MaterialExpressionDivide, delta_u1, trailf_p, -2100, 300)
trail_inv = unary(unreal.MaterialExpressionOneMinus, trail_div, -1950, 300)
trail_sat = unary(unreal.MaterialExpressionSaturate, trail_inv, -1800, 300)
trail_sq = binary(unreal.MaterialExpressionMultiply, trail_sat, trail_sat, -1650, 300)
disc_u2 = use("disc", -1650, 420)
trail_in = binary(unreal.MaterialExpressionMultiply, trail_sq, disc_u2, -1500, 350)
trailop_p = scalar_param("TrailOpacity", 0.55, 2, "Opacity of the wedge right behind the sweep", -1500, 470)
trail_v = binary(unreal.MaterialExpressionMultiply, trail_in, trailop_p, -1350, 400)
make_decl("trail", trail_v, -1200, 400, C_COL)

# ---- dir = (sin(TAU * h), cos(TAU * h));  line = cov(length(p - dir * clamp(dot(p, dir), 0, inner)) - SweepThickness / 2) ----
h_u2 = use("h", -2300, 750)
dir_sin = unary(unreal.MaterialExpressionSine, h_u2, -2150, 700, period=1.0)     # period 1 = sin(TAU * h)
dir_cos = unary(unreal.MaterialExpressionCosine, h_u2, -2150, 800, period=1.0)
dir_v = binary(unreal.MaterialExpressionAppendVector, dir_sin, dir_cos, -2000, 750)
make_decl("dir", dir_v, -1850, 750, C_TM)
p_u4 = use("p", -1650, 650)
dir_u1 = use("dir", -1650, 750)
proj_dot = binary(unreal.MaterialExpressionDotProduct, p_u4, dir_u1, -1500, 700)
inner_u2 = use("inner", -1500, 820)
proj = expr(unreal.MaterialExpressionClamp, -1350, 750, min_default=0.0)
_connect(proj_dot, "", proj, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(inner_u2, "", proj, "Max")
dir_u2 = use("dir", -1350, 880)
foot = binary(unreal.MaterialExpressionMultiply, dir_u2, proj, -1200, 820)
p_u5 = use("p", -1200, 700)
line_rel = binary(unreal.MaterialExpressionSubtract, p_u5, foot, -1050, 750)
line_len = unary(unreal.MaterialExpressionLength, line_rel, -900, 750)
sweepth_p = scalar_param("SweepThickness", 0.03, 3, "Stroke width of the sweep line", -900, 870)
sweepth_half = expr(unreal.MaterialExpressionMultiply, -750, 870, const_b=0.5)
_connect(sweepth_p, "", sweepth_half, "A")
line_d = binary(unreal.MaterialExpressionSubtract, line_len, sweepth_half, -600, 800)
make_decl("line", coverage(line_d, -450, 750), 100, 800, C_COL)

# ---- dBlip = min_k length(p - Radius * B_k) - DotRadius;  blip = cov(dBlip) * (1 - delta)^3 * BlipOpacity ----
p_u6 = use("p", -2300, 1250)
radius_u3 = use("Radius", -2300, 1450)
blip_lens = []
for k, (frac_r, turns) in enumerate(BLIPS):
    y = 1150 + k * 200
    b = expr(unreal.MaterialExpressionConstant2Vector, -2150, y + 100,
             r=frac_r * math.sin(TAU * turns), g=frac_r * math.cos(TAU * turns))
    bc = binary(unreal.MaterialExpressionMultiply, b, radius_u3, -2000, y + 100)
    rel = binary(unreal.MaterialExpressionSubtract, p_u6, bc, -1850, y + 50)
    blip_lens.append(unary(unreal.MaterialExpressionLength, rel, -1700, y + 50))
blip_min01 = binary(unreal.MaterialExpressionMin, blip_lens[0], blip_lens[1], -1550, 1250)
blip_min = binary(unreal.MaterialExpressionMin, blip_min01, blip_lens[2], -1400, 1350)
dotr_p = scalar_param("DotRadius", 0.05, 4, "Radius of a blip", -1400, 1500)
blip_d = binary(unreal.MaterialExpressionSubtract, blip_min, dotr_p, -1250, 1400)
blip_cov = coverage(blip_d, -1100, 1350)
delta_u2 = use("delta", -1100, 1600)
fade = unary(unreal.MaterialExpressionOneMinus, delta_u2, -950, 1600)
fade_sq = binary(unreal.MaterialExpressionMultiply, fade, fade, -800, 1600)
fade_cube = binary(unreal.MaterialExpressionMultiply, fade_sq, fade, -650, 1550)
blip_lit = binary(unreal.MaterialExpressionMultiply, blip_cov, fade_cube, -500, 1450)
blipop_p = scalar_param("BlipOpacity", 1.0, 3, "Opacity of a blip right after the sweep passes (0 hides them)",
                        -500, 1600)
blip_v = binary(unreal.MaterialExpressionMultiply, blip_lit, blipop_p, -350, 1500)
make_decl("blip", blip_v, -200, 1500, C_COL)

# ---- mask = max(grid, trail, rim, line, blip) ----
MAX_X, MAX_Y = 400, 300
grid_u = use("grid", MAX_X, MAX_Y - 200)
trail_u = use("trail", MAX_X, MAX_Y - 100)
rim_u = use("rim", MAX_X, MAX_Y)
line_u = use("line", MAX_X, MAX_Y + 100)
blip_u = use("blip", MAX_X, MAX_Y + 200)
max_gt = binary(unreal.MaterialExpressionMax, grid_u, trail_u, MAX_X + 150, MAX_Y - 150)
max_rl = binary(unreal.MaterialExpressionMax, rim_u, line_u, MAX_X + 150, MAX_Y + 50)
max_4 = binary(unreal.MaterialExpressionMax, max_gt, max_rl, MAX_X + 300, MAX_Y - 50)
max_5 = binary(unreal.MaterialExpressionMax, max_4, blip_u, MAX_X + 450, MAX_Y + 50)
make_decl("mask", max_5, MAX_X + 600, MAX_Y + 50, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
OUT_X, OUT_Y = 1300, 200
primary_p = expr(unreal.MaterialExpressionVectorParameter, OUT_X, OUT_Y - 150,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0,
                 desc="Color of the radar (alpha scales the opacity)")
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

smt.set_material_root_position(mat, OUT_X + 660, OUT_Y - 120)

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "Radius + Thickness / 2 = 0.8 by default: the outer size shared by the ring spinners. The grid circle and "
         "the blips scale with Radius.",
    -3950, -1408, 900, 548, C_SC)
smt.create_comment_in_material(
    mat, "Time has Ignore Pause on (real time), so the sweep keeps turning while the game thread is blocked.",
    -3950, -620, 750, 340, C_TM)
smt.create_comment_in_material(
    mat, "Trail\n"
         "delta jumps from 1 to 0 on the sweep line, which the line itself covers.",
    -2350, 130, 1400, 460, C_TM)
smt.create_comment_in_material(
    mat, "Sweep line\n"
         "The Sine and Cosine on h have Period 1: they take turns. The line is iq's sdSegment from the center.",
    -2350, 610, 2700, 410, C_TM)
smt.create_comment_in_material(
    mat, "Blips\n"
         "Three fixed places, as fractions of Radius. Each fades by the pixel's own delta, so a blip lights up "
         "where the sweep has just passed and dies out over the turn that follows.",
    -2350, 1030, 2450, 700, C_UV)

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
expected_decls = sorted(["p", "aa", "Radius", "halfThickness", "inner", "r", "a", "h", "delta", "disc", "rim",
                         "grid", "trail", "dir", "line", "blip", "mask"])
expected_usages = {"p": 6, "aa": 5, "Radius": 4, "halfThickness": 2, "inner": 2, "r": 3, "a": 1, "h": 2,
                   "delta": 2, "disc": 2, "dir": 2, "grid": 1, "trail": 1, "rim": 1, "line": 1, "blip": 1, "mask": 1}
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == sorted(PARAM_GROUPS) and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 5
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
