"""
Segmented ring that fills and drains -> M_LoadingSegments (Material Domain = UI, Translucent)

リングを Count 個の角丸の弧(区切り)に分け、12 時から時計回りに 1 つずつ点いて全部点くと、同じ順に 1 つずつ消えるロードアイコン。
消えている区切りは BrightMin の不透明度で薄く残る(1 色)。デザインは 2026-10-11 のスピナー案第 2 弾(Canvas プレビュー)から。
ピクセルの角度から担当の区切りの番号を求め、その区切りの中心が真上を向くよう座標を回転して x を折り返し、
iq の sdArc を 1 回だけ評価する(M_LoadingArc と同じ形)。区切りはすべて同じ形なので d はセル境界でも連続。
点灯は番号の比較だけでループも分岐もない。

  p     = MF_SpinnerCoords.P                        (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa    = MF_SpinnerCoords.PixelSize                (1 ピクセルを p 単位で)
  id    = clamp(floor(fract(atan2(p.x, p.y) / TAU) * Count), 0, Count - 1)
                                                    (担当の区切り。0 = 12 時から時計回り。clamp は中心ちょうどで
                                                     atan2(0, 0) が NaN を返した場合の保険)
  ang   = (id + 0.5) / Count * TAU                  (区切りの中心の向き)
  c, s  = cos(ang), sin(ang)
  q     = (abs(c*p.x - s*p.y), s*p.x + c*p.y)       (区切りの中心が真上を向くよう回転し、左右を折り返す)
  h     = max(PI / Count - (Gap + Thickness) / (2 * Radius), 0)
                                                    (弧の半開き角。丸い端どうしのすき間が Gap(p 単位の長さ)になる)
  sc    = (sin(h), cos(h))
  d     = (sc.y * q.x >= sc.x * q.y ? length(q - sc * Radius) : abs(length(q) - Radius)) - Thickness / 2
                                                    (iq の sdArc。Step + Lerp で分岐なし)
  mask  = clamp(0.5 - d / aa, 0, 1)
  k     = floor(fract(Time * Speed) * 2 * Count)    (1 サイクルを 2 * Count 段に分けた今の段。Speed はサイクル/秒。
                                                     正 = 時計回りに満ちる)
  lit   = step(id, k) * step(k - Count + 1, id)     (点いている区切りは番号 k - Count + 1 .. k の窓。前半(k < Count)は
                                                     0..k が点いて満ちていき、後半は先頭から消えていく)
  alpha = lerp(BrightMin, 1, lit)

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * alpha * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は Radius + Thickness/2 = 0.8(材質契約の基準円。1.0 = 短辺の端)に合わせてある。

  ScalarParameter / VectorParameter はグループ "LoadingSegments"。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Count(6 箇所)、Radius(3 箇所)、Thickness(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingsegments.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingSegments"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
PI = 3.14159265359
TAU = 6.28318530718
PARAM_GROUP = "LoadingSegments"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / cell = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / lit state = light blue
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
                parameter_name=name, default_value=default, group=PARAM_GROUP,
                sort_priority=sort, desc=desc)

def mask_x(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=True, g=False, b=False, a=False)

def mask_y(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=False, g=True, b=False, a=False)

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3600, -650, material_function=mf_coords)
make_decl("p", coords, -3300, -700, C_UV, "P")
make_decl("aa", coords, -3300, -580, C_SDF, "PixelSize")

# ---- Shared parameters ----
count_p = scalar_param("Count", 10.0, 0, "Number of segments (integer, 1 or more)", -3750, -300)
make_decl("Count", count_p, -3500, -300, C_SC)
# Footprint (material contract): Radius + Thickness / 2 = 0.8, the reference circle.
radius_p = scalar_param("Radius", 0.735, 1,
                        "Distance from the center to the middle of the stroke (half the shorter widget side = 1.0)",
                        -3750, -150)
make_decl("Radius", radius_p, -3500, -150, C_SC)
thick_p = scalar_param("Thickness", 0.13, 2,
                       "Stroke width. The segment ends are rounded", -3750, 0)
make_decl("Thickness", thick_p, -3500, 0, C_SC)

# ---- id = clamp(floor(fract(atan2(p.x, p.y) / TAU) * Count), 0, Count - 1) ----
p_u1 = use("p", -3000, -350)
p_x = mask_x(-2850, -400)
_connect(p_u1, "", p_x, "")
p_y = mask_y(-2850, -280)
_connect(p_u1, "", p_y, "")
# atan2(Y = p.x, X = p.y): 0 at 12 o'clock, growing clockwise (p is y-up).
a_atan = expr(unreal.MaterialExpressionArctangent2, -2700, -350)
_connect(p_x, "", a_atan, "Y")
_connect(p_y, "", a_atan, "X")
a_div = expr(unreal.MaterialExpressionDivide, -2550, -350, const_b=TAU)
_connect(a_atan, "", a_div, "A")
a_frac = expr(unreal.MaterialExpressionFrac, -2400, -350)   # 0..1 turns clockwise from 12 o'clock
_connect(a_div, "", a_frac, "")
count_u1 = use("Count", -2400, -230)
cell_mul = expr(unreal.MaterialExpressionMultiply, -2250, -300)
_connect(a_frac, "", cell_mul, "A")
_connect(count_u1, "", cell_mul, "B")
cell_floor = expr(unreal.MaterialExpressionFloor, -2100, -300)
_connect(cell_mul, "", cell_floor, "")
count_u2 = use("Count", -2250, -150)
count_m1 = expr(unreal.MaterialExpressionSubtract, -2100, -150, const_b=1.0)
_connect(count_u2, "", count_m1, "A")
id_clamp = expr(unreal.MaterialExpressionClamp, -1950, -300, min_default=0.0)
_connect(cell_floor, "", id_clamp, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(count_m1, "", id_clamp, "Max")
make_decl("id", id_clamp, -1800, -300, C_UV)

# ---- ang = (id + 0.5) / Count * TAU;  c = cos(ang), s = sin(ang) ----
id_u1 = use("id", -1550, -400)
id_mid = expr(unreal.MaterialExpressionAdd, -1400, -400, const_b=0.5)
_connect(id_u1, "", id_mid, "A")
count_u3 = use("Count", -1400, -300)
turn = expr(unreal.MaterialExpressionDivide, -1250, -350)
_connect(id_mid, "", turn, "A")
_connect(count_u3, "", turn, "B")
ang_v = expr(unreal.MaterialExpressionMultiply, -1100, -350, const_b=TAU)
_connect(turn, "", ang_v, "A")
ang_cos = expr(unreal.MaterialExpressionCosine, -950, -400, period=TAU)   # period 2*PI = radians
_connect(ang_v, "", ang_cos, "")
make_decl("c", ang_cos, -800, -400, C_UV)
ang_sin = expr(unreal.MaterialExpressionSine, -950, -280, period=TAU)
_connect(ang_v, "", ang_sin, "")
make_decl("s", ang_sin, -800, -280, C_UV)

# ---- q = (abs(dot(p, (c, -s))), dot(p, (s, c)))  (segment center now points up; fold the left half) ----
c_u1 = use("c", -550, -500)
s_u1 = use("s", -550, -400)
s_neg = expr(unreal.MaterialExpressionMultiply, -400, -400, const_b=-1.0)
_connect(s_u1, "", s_neg, "A")
row_x = expr(unreal.MaterialExpressionAppendVector, -250, -450)    # (c, -s)
_connect(c_u1, "", row_x, "A")
_connect(s_neg, "", row_x, "B")
s_u2 = use("s", -550, -250)
c_u2 = use("c", -550, -150)
row_y = expr(unreal.MaterialExpressionAppendVector, -250, -200)    # (s, c)
_connect(s_u2, "", row_y, "A")
_connect(c_u2, "", row_y, "B")
p_u2 = use("p", -100, -550)
q_x = expr(unreal.MaterialExpressionDotProduct, 50, -500)
_connect(p_u2, "", q_x, "A")
_connect(row_x, "", q_x, "B")
q_xabs = expr(unreal.MaterialExpressionAbs, 200, -500)
_connect(q_x, "", q_xabs, "")
p_u3 = use("p", -100, -250)
q_y = expr(unreal.MaterialExpressionDotProduct, 50, -200)
_connect(p_u3, "", q_y, "A")
_connect(row_y, "", q_y, "B")
q_v = expr(unreal.MaterialExpressionAppendVector, 350, -350)
_connect(q_xabs, "", q_v, "A")
_connect(q_y, "", q_v, "B")
make_decl("q", q_v, 500, -350, C_UV)

# ---- h = max(PI / Count - (Gap + Thickness) / (2 * Radius), 0);  sc = (sin h, cos h) ----
count_u4 = use("Count", -550, 100)
half_cell = expr(unreal.MaterialExpressionDivide, -400, 100, const_a=PI)
_connect(count_u4, "", half_cell, "B")
gap_p = scalar_param("Gap", 0.15, 3,
                     "Space between the rounded ends of neighboring segments, measured along the ring", -700, 250)
thick_u1 = use("Thickness", -700, 370)
gap_len = expr(unreal.MaterialExpressionAdd, -550, 300)
_connect(gap_p, "", gap_len, "A")
_connect(thick_u1, "", gap_len, "B")
radius_u1 = use("Radius", -550, 430)
radius_2 = expr(unreal.MaterialExpressionMultiply, -400, 430, const_b=2.0)
_connect(radius_u1, "", radius_2, "A")
gap_ang = expr(unreal.MaterialExpressionDivide, -250, 350)   # half of the gap's angle, in radians
_connect(gap_len, "", gap_ang, "A")
_connect(radius_2, "", gap_ang, "B")
h_sub = expr(unreal.MaterialExpressionSubtract, -100, 200)
_connect(half_cell, "", h_sub, "A")
_connect(gap_ang, "", h_sub, "B")
h_max = expr(unreal.MaterialExpressionMax, 50, 200, const_b=0.0)   # a gap wider than the cell leaves dots
_connect(h_sub, "", h_max, "A")
h_sin = expr(unreal.MaterialExpressionSine, 200, 150, period=TAU)
_connect(h_max, "", h_sin, "")
h_cos = expr(unreal.MaterialExpressionCosine, 200, 270, period=TAU)
_connect(h_max, "", h_cos, "")
sc_v = expr(unreal.MaterialExpressionAppendVector, 350, 200)
_connect(h_sin, "", sc_v, "A")
_connect(h_cos, "", sc_v, "B")
make_decl("sc", sc_v, 500, 200, C_UV)

# ---- dCap = length(q - sc * Radius)  (distance to the rounded end) ----
q_u1 = use("q", 850, -650)
sc_u1 = use("sc", 700, -550)
radius_u2 = use("Radius", 700, -450)
end_pt = expr(unreal.MaterialExpressionMultiply, 850, -500)
_connect(sc_u1, "", end_pt, "A")
_connect(radius_u2, "", end_pt, "B")
to_end = expr(unreal.MaterialExpressionSubtract, 1000, -580)
_connect(q_u1, "", to_end, "A")
_connect(end_pt, "", to_end, "B")
d_cap = expr(unreal.MaterialExpressionLength, 1150, -580)
_connect(to_end, "", d_cap, "")

# ---- dRing = abs(length(q) - Radius)  (distance to the full circle) ----
q_u2 = use("q", 700, -300)
q_len = expr(unreal.MaterialExpressionLength, 850, -300)
_connect(q_u2, "", q_len, "")
radius_u3 = use("Radius", 850, -200)
ring_sub = expr(unreal.MaterialExpressionSubtract, 1000, -250)
_connect(q_len, "", ring_sub, "A")
_connect(radius_u3, "", ring_sub, "B")
d_ring = expr(unreal.MaterialExpressionAbs, 1150, -250)
_connect(ring_sub, "", d_ring, "")

# ---- cap = step(sc.x * q.y, sc.y * q.x)  (1 when the pixel's angle is past the segment's end) ----
sc_u2 = use("sc", 700, 0)
sc_x = mask_x(850, 0)
_connect(sc_u2, "", sc_x, "")
q_u3 = use("q", 700, 100)
q_ycomp = mask_y(850, 100)
_connect(q_u3, "", q_ycomp, "")
edge_y = expr(unreal.MaterialExpressionMultiply, 1000, 50)
_connect(sc_x, "", edge_y, "A")
_connect(q_ycomp, "", edge_y, "B")
sc_u3 = use("sc", 700, 250)
sc_y = mask_y(850, 250)
_connect(sc_u3, "", sc_y, "")
q_u4 = use("q", 700, 350)
q_xcomp = mask_x(850, 350)
_connect(q_u4, "", q_xcomp, "")
edge_x = expr(unreal.MaterialExpressionMultiply, 1000, 300)
_connect(sc_y, "", edge_x, "A")
_connect(q_xcomp, "", edge_x, "B")
# UE Step(Y, X) returns 1 when X >= Y, i.e. GLSL step(edge=Y, x=X).
cap_step = expr(unreal.MaterialExpressionStep, 1150, 170)
_connect(edge_y, "", cap_step, "Y")
_connect(edge_x, "", cap_step, "X")

# ---- d = lerp(dRing, dCap, cap) - Thickness / 2 ----
d_sel = expr(unreal.MaterialExpressionLinearInterpolate, 1350, -300)
_connect(d_ring, "", d_sel, "A")
_connect(d_cap, "", d_sel, "B")
_connect(cap_step, "", d_sel, "Alpha")
thick_u2 = use("Thickness", 1350, -150)
thick_half = expr(unreal.MaterialExpressionMultiply, 1500, -150, const_b=0.5)
_connect(thick_u2, "", thick_half, "A")
d_v = expr(unreal.MaterialExpressionSubtract, 1650, -250)
_connect(d_sel, "", d_v, "A")
_connect(thick_half, "", d_v, "B")
make_decl("d", d_v, 1800, -250, C_SDF)

# ---- mask = clamp(0.5 - d / aa, 0, 1)  (anti-aliased mask, 1px-wide edge) ----
d_u1 = use("d", 2000, -300)
aa_u1 = use("aa", 2000, -200)
d_over_aa = expr(unreal.MaterialExpressionDivide, 2150, -250)
_connect(d_u1, "", d_over_aa, "A")
_connect(aa_u1, "", d_over_aa, "B")
half_minus = expr(unreal.MaterialExpressionSubtract, 2300, -250, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_clamp = expr(unreal.MaterialExpressionClamp, 2450, -250, min_default=0.0, max_default=1.0)
_connect(half_minus, "", mask_clamp, "")
make_decl("mask", mask_clamp, 2600, -250, C_COL)

# ---- k = floor(fract(Time * Speed) * 2 * Count)  (current step of the fill-and-drain cycle) ----
time_n = expr(unreal.MaterialExpressionTime, -3750, 750)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.45, 5,
                       "Fill-and-drain cycles per second. Positive = the segments fill clockwise", -3750, 870)
t_speed = expr(unreal.MaterialExpressionMultiply, -3550, 800)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
t_frac = expr(unreal.MaterialExpressionFrac, -3400, 800)
_connect(t_speed, "", t_frac, "")
count_u5 = use("Count", -3400, 920)
steps = expr(unreal.MaterialExpressionMultiply, -3250, 850, const_b=2.0)
_connect(count_u5, "", steps, "A")
k_mul = expr(unreal.MaterialExpressionMultiply, -3100, 800)
_connect(t_frac, "", k_mul, "A")
_connect(steps, "", k_mul, "B")
k_floor = expr(unreal.MaterialExpressionFloor, -2950, 800)
_connect(k_mul, "", k_floor, "")
make_decl("k", k_floor, -2800, 800, C_TM)

# ---- lit = step(id, k) * step(k - Count + 1, id)  (lit segments are the window k - Count + 1 .. k) ----
id_u2 = use("id", -2500, 650)
k_u1 = use("k", -2500, 750)
lit_hi = expr(unreal.MaterialExpressionStep, -2350, 700)   # 1 when k >= id
_connect(id_u2, "", lit_hi, "Y")
_connect(k_u1, "", lit_hi, "X")
k_u2 = use("k", -2500, 900)
count_u6 = use("Count", -2500, 1000)
lo_sub = expr(unreal.MaterialExpressionSubtract, -2350, 950)
_connect(k_u2, "", lo_sub, "A")
_connect(count_u6, "", lo_sub, "B")
lo_v = expr(unreal.MaterialExpressionAdd, -2200, 950, const_b=1.0)
_connect(lo_sub, "", lo_v, "A")
id_u3 = use("id", -2200, 1070)
lit_lo = expr(unreal.MaterialExpressionStep, -2050, 1000)   # 1 when id >= k - Count + 1
_connect(lo_v, "", lit_lo, "Y")
_connect(id_u3, "", lit_lo, "X")
lit_v = expr(unreal.MaterialExpressionMultiply, -1900, 850)
_connect(lit_hi, "", lit_v, "A")
_connect(lit_lo, "", lit_v, "B")

# ---- alpha = lerp(BrightMin, 1, lit) ----
brightmin_p = scalar_param("BrightMin", 0.15, 4, "Opacity of an unlit segment (0 hides it); lit segments are 1",
                           -1900, 700)
alpha_v = expr(unreal.MaterialExpressionLinearInterpolate, -1700, 800, const_b=1.0)
_connect(brightmin_p, "", alpha_v, "A")
_connect(lit_v, "", alpha_v, "Alpha")
make_decl("alpha", alpha_v, -1550, 800, C_TM)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb,
#      Opacity = mask * alpha * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2850, -400,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUP, sort_priority=6, desc="Segment color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 2850, -150)
emissive = expr(unreal.MaterialExpressionMultiply, 3100, -350)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 2850, 50)
alpha_u1 = use("alpha", 2850, 150)
coverage = expr(unreal.MaterialExpressionMultiply, 3000, 100)
_connect(mask_u1, "", coverage, "A")
_connect(alpha_u1, "", coverage, "B")
cov_a = expr(unreal.MaterialExpressionMultiply, 3150, 50)
_connect(coverage, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 3300, 0)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in p units)",
    -3650, -820, 900, 400, C_UV)
smt.create_comment_in_material(
    mat, "Count / Radius / Thickness are used several times -> Named Reroutes.\n"
         "Radius + Thickness / 2 = 0.8 by default (the material contract's reference circle)",
    -3800, -400, 550, 550, C_SC)
smt.create_comment_in_material(
    mat, "id = clamp(floor(fract(atan2(p.x, p.y) / TAU) * Count), 0, Count - 1)\n"
         "Segment that owns the pixel (0 at 12 o'clock, clockwise). The clamp also catches a NaN from atan2(0, 0)",
    -3050, -500, 1350, 450, C_UV)
smt.create_comment_in_material(
    mat, "ang = (id + 0.5) / Count * TAU   (segment center);  c = cos(ang), s = sin(ang)",
    -1600, -500, 900, 350, C_UV)
smt.create_comment_in_material(
    mat, "q = (abs(c*p.x - s*p.y), s*p.x + c*p.y)\n"
         "Rotate so that the segment's center points straight up, then fold the left half onto the right",
    -600, -650, 1250, 560, C_UV)
smt.create_comment_in_material(
    mat, "h = max(PI / Count - (Gap + Thickness) / (2 * Radius), 0);  sc = (sin h, cos h)\n"
         "Half aperture of one segment: the space between rounded ends is Gap, measured along the ring",
    -750, 30, 1400, 520, C_UV)
smt.create_comment_in_material(
    mat, "iq's sdArc: dCap = length(q - sc * Radius), dRing = abs(length(q) - Radius)\n"
         "cap = step(sc.x * q.y, sc.y * q.x): 1 past the end;  d = lerp(dRing, dCap, cap) - Thickness / 2\n"
         "Every segment has the same shape, so d is continuous across cell borders",
    650, -780, 1300, 1250, C_SDF)
smt.create_comment_in_material(
    mat, "mask = clamp(0.5 - d / aa, 0, 1)   (1px-wide coverage approximation at the edge)",
    1950, -380, 800, 300, C_COL)
smt.create_comment_in_material(
    mat, "k = floor(fract(Time * Speed) * 2 * Count)   (current step: Count steps to fill, Count to drain)\n"
         "Time ignores pause (real time), so the segments keep stepping while the game thread is blocked",
    -3800, 650, 1150, 380, C_TM)
smt.create_comment_in_material(
    mat, "lit = step(id, k) * step(k - Count + 1, id): the lit segments are the window k - Count + 1 .. k.\n"
         "While k < Count it is 0..k (filling); after that the first ones go out (draining).\n"
         "alpha = lerp(BrightMin, 1, lit)",
    -2550, 550, 1100, 650, C_TM)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * alpha * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    2800, -520, 650, 800, C_COL)

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

expected_decls = sorted(["p", "aa", "Count", "Radius", "Thickness", "id", "c", "s", "q", "sc", "d", "mask", "k",
                         "alpha"])
expected_usages = {"p": 3, "aa": 1, "Count": 6, "Radius": 3, "Thickness": 2, "id": 3, "c": 2, "s": 2, "q": 4,
                   "sc": 3, "d": 1, "mask": 1, "k": 2, "alpha": 1}
expected_params = sorted(["Count", "Radius", "Thickness", "Gap", "BrightMin", "Speed", "PrimaryColor"])
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == expected_params
mf_ok = mf_calls == 1
comments_ok = len(smt.get_material_comment_texts(mat)) == 11
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
