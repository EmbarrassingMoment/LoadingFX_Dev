"""
Pie timer -> M_LoadingTimer (Material Domain = UI, Translucent)

細い外周リングの中で、12 時から時計回りに扇形が満ちていき、満ちきると同じ向きに始点側から欠けていくタイマー風のロードアイコン。
デザインは 2026-10-11 のスピナー案第 2 弾(Canvas プレビュー)から。扇形は iq の sdPie: 扇の中心が真上を向くよう座標を回転し
x を折り返すので 1 回の評価で済む。始点・終点の動きは M_LoadingArc と同じ smoothstep 2 本で、ループも分岐もない。

  p     = MF_SpinnerCoords.P                        (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa    = MF_SpinnerCoords.PixelSize                (1 ピクセルを p 単位で)
  u     = fract(Time * Speed)                       (Speed は満ちて欠けるサイクル数/秒、正 = 時計回り)
  head  = smoothstep(0, 0.5, u)                     (扇の終点。12 時から時計回りの回転数。前半で 0 -> 1)
  tail  = smoothstep(0.5, 1, u)                     (扇の始点。後半で 0 -> 1)
  span  = head - tail                               (扇の大きさ、回転数 0..1)
  mid   = (tail + head) * PI                        (扇の中心の向き、ラジアン。= (tail + head) / 2 * TAU)
  c, s  = cos(mid), sin(mid)
  q     = (abs(c*p.x - s*p.y), s*p.x + c*p.y)       (扇の中心が真上を向くよう回転し、左右を折り返す)
  sc    = (sin(h), cos(h)),  h = span * PI          (半開き角)
  dDisc = length(q) - PieRadius                     (扇を含む円板の距離。length(q) = length(p))
  dPie  = max(dDisc, length(q - sc * clamp(dot(q, sc), 0, PieRadius)) * sign(sc.y * q.x - sc.x * q.y))
                                                    (iq の sdPie。sign が正 = 扇の外の角度)
  dRing = abs(length(p) - Radius) - Thickness / 2
  rimPx = TAU * PieRadius / aa                      (扇の外周 1 周のピクセル数)
  fade  = saturate(span * rimPx)                    (外周での扇の幅が 1 ピクセル未満なら、その幅に比例して薄くする)
  full  = saturate(1 - (1 - span) * rimPx)          (外周でのすき間が 1 ピクセル未満なら、円板へ寄せる)
  pie   = lerp(clamp(0.5 - dPie / aa, 0, 1), clamp(0.5 - dDisc / aa, 0, 1), full) * fade
  ring  = clamp(0.5 - dRing / aa, 0, 1) * RingOpacity
  mask  = max(pie, ring)

  fade と full がない場合、1 ピクセルより細い扇やすき間は距離 0 の線として AA で 0.5 の濃さに描かれる。smoothstep は
  満ちきる前後と空になる前後で遅いので、12 時の細い線が 0.1 秒以上残っていた(Gallery で確認)。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は Radius + Thickness/2 = 0.8(材質契約の基準円。1.0 = 短辺の端)に合わせてある。

  ScalarParameter / VectorParameter はグループ "LoadingTimer"。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  PieRadius(3 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingtimer.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingTimer"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
PI = 3.14159265359
TAU = 6.28318530718
PARAM_GROUP = "LoadingTimer"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / rotation = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / pie edges = light blue
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

# ---- u = fract(Time * Speed);  head = smoothstep(0, 0.5, u);  tail = smoothstep(0.5, 1, u) ----
time_n = expr(unreal.MaterialExpressionTime, -3750, 300)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.5, 4,
                       "Fill-and-empty cycles per second. Positive = the pie sweeps clockwise", -3750, 420)
t_speed = expr(unreal.MaterialExpressionMultiply, -3550, 350)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
u_frac = expr(unreal.MaterialExpressionFrac, -3400, 350)
_connect(t_speed, "", u_frac, "")
make_decl("u", u_frac, -3250, 350, C_TM)
u_u1 = use("u", -3000, 250)
head_ss = expr(unreal.MaterialExpressionSmoothStep, -2850, 250, const_min=0.0, const_max=0.5)
_connect(u_u1, "", head_ss, "Value")
make_decl("head", head_ss, -2700, 250, C_TM)
u_u2 = use("u", -3000, 450)
tail_ss = expr(unreal.MaterialExpressionSmoothStep, -2850, 450, const_min=0.5, const_max=1.0)
_connect(u_u2, "", tail_ss, "Value")
make_decl("tail", tail_ss, -2700, 450, C_TM)

# ---- mid = (tail + head) * PI;  c = cos(mid), s = sin(mid) ----
tail_u1 = use("tail", -2450, 150)
head_u1 = use("head", -2450, 250)
mid_add = expr(unreal.MaterialExpressionAdd, -2300, 200)
_connect(tail_u1, "", mid_add, "A")
_connect(head_u1, "", mid_add, "B")
mid_v = expr(unreal.MaterialExpressionMultiply, -2150, 200, const_b=PI)   # = (tail + head) / 2 * TAU
_connect(mid_add, "", mid_v, "A")
mid_cos = expr(unreal.MaterialExpressionCosine, -2000, 150, period=TAU)   # period 2*PI = radians
_connect(mid_v, "", mid_cos, "")
make_decl("c", mid_cos, -1850, 150, C_UV)
mid_sin = expr(unreal.MaterialExpressionSine, -2000, 270, period=TAU)
_connect(mid_v, "", mid_sin, "")
make_decl("s", mid_sin, -1850, 270, C_UV)

# ---- span = head - tail;  sc = (sin h, cos h),  h = span * PI  (half aperture) ----
head_u2 = use("head", -2450, 450)
tail_u2 = use("tail", -2450, 550)
ap_sub = expr(unreal.MaterialExpressionSubtract, -2300, 500)
_connect(head_u2, "", ap_sub, "A")
_connect(tail_u2, "", ap_sub, "B")
make_decl("span", ap_sub, -2150, 600, C_TM)
span_u1 = use("span", -2150, 480)
half_ap = expr(unreal.MaterialExpressionMultiply, -2000, 480, const_b=PI)
_connect(span_u1, "", half_ap, "A")
ap_sin = expr(unreal.MaterialExpressionSine, -1850, 430, period=TAU)
_connect(half_ap, "", ap_sin, "")
ap_cos = expr(unreal.MaterialExpressionCosine, -1850, 550, period=TAU)
_connect(half_ap, "", ap_cos, "")
sc_v = expr(unreal.MaterialExpressionAppendVector, -1700, 480)
_connect(ap_sin, "", sc_v, "A")
_connect(ap_cos, "", sc_v, "B")
make_decl("sc", sc_v, -1550, 480, C_UV)

# ---- q = (abs(dot(p, (c, -s))), dot(p, (s, c)))  (pie center now points up; fold the left half) ----
c_u1 = use("c", -1500, -150)
s_u1 = use("s", -1500, -50)
s_neg = expr(unreal.MaterialExpressionMultiply, -1350, -50, const_b=-1.0)
_connect(s_u1, "", s_neg, "A")
row_x = expr(unreal.MaterialExpressionAppendVector, -1200, -100)    # (c, -s)
_connect(c_u1, "", row_x, "A")
_connect(s_neg, "", row_x, "B")
s_u2 = use("s", -1500, 100)
c_u2 = use("c", -1500, 200)
row_y = expr(unreal.MaterialExpressionAppendVector, -1200, 150)    # (s, c)
_connect(s_u2, "", row_y, "A")
_connect(c_u2, "", row_y, "B")
p_u1 = use("p", -1050, -200)
q_x = expr(unreal.MaterialExpressionDotProduct, -900, -150)
_connect(p_u1, "", q_x, "A")
_connect(row_x, "", q_x, "B")
q_xabs = expr(unreal.MaterialExpressionAbs, -750, -150)
_connect(q_x, "", q_xabs, "")
p_u2 = use("p", -1050, 100)
q_y = expr(unreal.MaterialExpressionDotProduct, -900, 150)
_connect(p_u2, "", q_y, "A")
_connect(row_y, "", q_y, "B")
q_v = expr(unreal.MaterialExpressionAppendVector, -600, 0)
_connect(q_xabs, "", q_v, "A")
_connect(q_y, "", q_v, "B")
make_decl("q", q_v, -450, 0, C_UV)

pier_p = scalar_param("PieRadius", 0.6, 2, "Radius of the pie inside the ring", -450, 300)
make_decl("PieRadius", pier_p, -200, 300, C_SC)

# ---- dPie = max(length(q) - PieRadius, length(q - sc * clamp(dot(q, sc), 0, PieRadius)) * sign(sc.y*q.x - sc.x*q.y)) ----
q_u1 = use("q", -100, -300)
q_len = expr(unreal.MaterialExpressionLength, 50, -300)
_connect(q_u1, "", q_len, "")
pier_u1 = use("PieRadius", 50, -200)
pie_l = expr(unreal.MaterialExpressionSubtract, 200, -250)   # distance to the disc the pie is cut from
_connect(q_len, "", pie_l, "A")
_connect(pier_u1, "", pie_l, "B")
make_decl("dDisc", pie_l, 350, -250, C_SDF)
q_u2 = use("q", -100, 0)
sc_u1 = use("sc", -100, 100)
q_dot = expr(unreal.MaterialExpressionDotProduct, 50, 50)
_connect(q_u2, "", q_dot, "A")
_connect(sc_u1, "", q_dot, "B")
pier_u2 = use("PieRadius", 50, 170)
q_proj = expr(unreal.MaterialExpressionClamp, 200, 50, min_default=0.0)
_connect(q_dot, "", q_proj, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(pier_u2, "", q_proj, "Max")
sc_u2 = use("sc", 200, 170)
edge_pt = expr(unreal.MaterialExpressionMultiply, 350, 100)   # nearest point on the pie's straight edge
_connect(sc_u2, "", edge_pt, "A")
_connect(q_proj, "", edge_pt, "B")
q_u3 = use("q", 350, -20)
to_edge = expr(unreal.MaterialExpressionSubtract, 500, 40)
_connect(q_u3, "", to_edge, "A")
_connect(edge_pt, "", to_edge, "B")
pie_m = expr(unreal.MaterialExpressionLength, 650, 40)
_connect(to_edge, "", pie_m, "")
sc_u3 = use("sc", -100, 350)
sc_y = mask_y(50, 350)
_connect(sc_u3, "", sc_y, "")
q_u4 = use("q", -100, 450)
q_xcomp = mask_x(50, 450)
_connect(q_u4, "", q_xcomp, "")
side_a = expr(unreal.MaterialExpressionMultiply, 200, 400)
_connect(sc_y, "", side_a, "A")
_connect(q_xcomp, "", side_a, "B")
sc_u4 = use("sc", -100, 600)
sc_x = mask_x(50, 600)
_connect(sc_u4, "", sc_x, "")
q_u5 = use("q", -100, 700)
q_ycomp = mask_y(50, 700)
_connect(q_u5, "", q_ycomp, "")
side_b = expr(unreal.MaterialExpressionMultiply, 200, 650)
_connect(sc_x, "", side_b, "A")
_connect(q_ycomp, "", side_b, "B")
side_sub = expr(unreal.MaterialExpressionSubtract, 350, 520)
_connect(side_a, "", side_sub, "A")
_connect(side_b, "", side_sub, "B")
side_sign = expr(unreal.MaterialExpressionSign, 500, 520)   # +1 past the pie's straight edges, -1 inside the aperture
_connect(side_sub, "", side_sign, "")
pie_ms = expr(unreal.MaterialExpressionMultiply, 800, 250)
_connect(pie_m, "", pie_ms, "A")
_connect(side_sign, "", pie_ms, "B")
ddisc_u1 = use("dDisc", 800, -100)
dpie_v = expr(unreal.MaterialExpressionMax, 950, 0)
_connect(ddisc_u1, "", dpie_v, "A")
_connect(pie_ms, "", dpie_v, "B")
make_decl("dPie", dpie_v, 1100, 0, C_SDF)

# ---- dRing = abs(length(p) - Radius) - Thickness / 2 ----
# Footprint (material contract): Radius + Thickness / 2 = 0.8, the reference circle.
p_u3 = use("p", 500, 800)
p_len = expr(unreal.MaterialExpressionLength, 650, 800)
_connect(p_u3, "", p_len, "")
radius_p = scalar_param("Radius", 0.77, 0,
                        "Distance from the center to the middle of the outer ring (half the shorter widget side = 1.0)",
                        500, 900)
ring_sub = expr(unreal.MaterialExpressionSubtract, 800, 850)
_connect(p_len, "", ring_sub, "A")
_connect(radius_p, "", ring_sub, "B")
ring_abs = expr(unreal.MaterialExpressionAbs, 950, 850)
_connect(ring_sub, "", ring_abs, "")
thick_p = scalar_param("Thickness", 0.06, 1, "Stroke width of the outer ring", 950, 950)
thick_half = expr(unreal.MaterialExpressionMultiply, 1100, 950, const_b=0.5)
_connect(thick_p, "", thick_half, "A")
dring_v = expr(unreal.MaterialExpressionSubtract, 1250, 900)
_connect(ring_abs, "", dring_v, "A")
_connect(thick_half, "", dring_v, "B")
make_decl("dRing", dring_v, 1400, 900, C_SDF)

# ---- pie = clamp(0.5 - dPie / aa, 0, 1);  ring = clamp(0.5 - dRing / aa, 0, 1) * RingOpacity;  mask = max(pie, ring) ----
dpie_u1 = use("dPie", 1400, -100)
aa_u1 = use("aa", 1400, 0)
pie_div = expr(unreal.MaterialExpressionDivide, 1550, -50)
_connect(dpie_u1, "", pie_div, "A")
_connect(aa_u1, "", pie_div, "B")
pie_half = expr(unreal.MaterialExpressionSubtract, 1700, -50, const_a=0.5)
_connect(pie_div, "", pie_half, "B")
pie_cov = expr(unreal.MaterialExpressionClamp, 1850, -50, min_default=0.0, max_default=1.0)
_connect(pie_half, "", pie_cov, "")
dring_u1 = use("dRing", 1400, 700)
aa_u2 = use("aa", 1400, 800)
ring_div = expr(unreal.MaterialExpressionDivide, 1550, 750)
_connect(dring_u1, "", ring_div, "A")
_connect(aa_u2, "", ring_div, "B")
ring_half = expr(unreal.MaterialExpressionSubtract, 1700, 750, const_a=0.5)
_connect(ring_div, "", ring_half, "B")
ring_cov = expr(unreal.MaterialExpressionClamp, 1850, 750, min_default=0.0, max_default=1.0)
_connect(ring_half, "", ring_cov, "")
ringop_p = scalar_param("RingOpacity", 1.0, 3, "Opacity of the outer ring (0 hides it)", 1850, 870)
ring_v = expr(unreal.MaterialExpressionMultiply, 2000, 800)
_connect(ring_cov, "", ring_v, "A")
_connect(ringop_p, "", ring_v, "B")

# ---- rimPx = TAU * PieRadius / aa;  fade = saturate(span * rimPx);  full = saturate(1 - (1 - span) * rimPx) ----
pier_u3 = use("PieRadius", 1400, 1150)
rim_len = expr(unreal.MaterialExpressionMultiply, 1550, 1150, const_b=TAU)
_connect(pier_u3, "", rim_len, "A")
aa_u3 = use("aa", 1550, 1250)
rim_px = expr(unreal.MaterialExpressionDivide, 1700, 1200)
_connect(rim_len, "", rim_px, "A")
_connect(aa_u3, "", rim_px, "B")
make_decl("rimPx", rim_px, 1850, 1200, C_SDF)
span_u2 = use("span", 1400, 1350)
rim_u1 = use("rimPx", 1400, 1450)
pie_px = expr(unreal.MaterialExpressionMultiply, 1550, 1400)   # pie width at the rim, in pixels
_connect(span_u2, "", pie_px, "A")
_connect(rim_u1, "", pie_px, "B")
fade_sat = expr(unreal.MaterialExpressionSaturate, 1700, 1400)
_connect(pie_px, "", fade_sat, "")
make_decl("fade", fade_sat, 1850, 1400, C_COL)
span_u3 = use("span", 1850, 1550)
gap_frac = expr(unreal.MaterialExpressionOneMinus, 2000, 1550)
_connect(span_u3, "", gap_frac, "")
rim_u2 = use("rimPx", 2000, 1650)
gap_px = expr(unreal.MaterialExpressionMultiply, 2150, 1600)   # gap width at the rim, in pixels
_connect(gap_frac, "", gap_px, "A")
_connect(rim_u2, "", gap_px, "B")
full_inv = expr(unreal.MaterialExpressionOneMinus, 2300, 1600)
_connect(gap_px, "", full_inv, "")
full_sat = expr(unreal.MaterialExpressionSaturate, 2450, 1600)
_connect(full_inv, "", full_sat, "")
make_decl("full", full_sat, 2600, 1600, C_COL)

# ---- pie = lerp(pieCoverage, discCoverage, full) * fade;  mask = max(pie, ring) ----
ddisc_u2 = use("dDisc", 1400, -400)
aa_u4 = use("aa", 1400, -300)
disc_div = expr(unreal.MaterialExpressionDivide, 1550, -350)
_connect(ddisc_u2, "", disc_div, "A")
_connect(aa_u4, "", disc_div, "B")
disc_half = expr(unreal.MaterialExpressionSubtract, 1700, -350, const_a=0.5)
_connect(disc_div, "", disc_half, "B")
disc_cov = expr(unreal.MaterialExpressionClamp, 1850, -350, min_default=0.0, max_default=1.0)
_connect(disc_half, "", disc_cov, "")
full_u1 = use("full", 1900, -50)
pie_full = expr(unreal.MaterialExpressionLinearInterpolate, 2050, -150)
_connect(pie_cov, "", pie_full, "A")
_connect(disc_cov, "", pie_full, "B")
_connect(full_u1, "", pie_full, "Alpha")
fade_u1 = use("fade", 2050, 50)
pie_v = expr(unreal.MaterialExpressionMultiply, 2200, -100)
_connect(pie_full, "", pie_v, "A")
_connect(fade_u1, "", pie_v, "B")
mask_max = expr(unreal.MaterialExpressionMax, 2500, 350)
_connect(pie_v, "", mask_max, "A")
_connect(ring_v, "", mask_max, "B")
make_decl("mask", mask_max, 2650, 350, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2900, 200,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUP, sort_priority=5, desc="Color of the pie and the ring (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 2900, 450)
emissive = expr(unreal.MaterialExpressionMultiply, 3150, 250)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 2900, 650)
cov_a = expr(unreal.MaterialExpressionMultiply, 3150, 600)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 3300, 550)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in p units)",
    -3650, -820, 900, 400, C_UV)
smt.create_comment_in_material(
    mat, "u = fract(Time * Speed);  head = smoothstep(0, 0.5, u) (the pie fills);  tail = smoothstep(0.5, 1, u) (it empties)\n"
         "Edges in turns clockwise from 12 o'clock. Time ignores pause (real time), so the timer keeps running while\n"
         "the game thread is blocked",
    -3800, 150, 1300, 450, C_TM)
smt.create_comment_in_material(
    mat, "mid = (tail + head) * PI   (pie center, radians);  c = cos(mid), s = sin(mid)",
    -2500, 50, 800, 330, C_UV)
smt.create_comment_in_material(
    mat, "span = head - tail   (pie size, turns);  sc = (sin h, cos h),  h = span * PI   (half aperture)",
    -2500, 380, 1050, 330, C_UV)
smt.create_comment_in_material(
    mat, "q = (abs(c*p.x - s*p.y), s*p.x + c*p.y)\n"
         "Rotate so that the pie's center points straight up, then fold the left half onto the right",
    -1550, -280, 1250, 560, C_UV)
smt.create_comment_in_material(
    mat, "PieRadius is used three times -> Named Reroute",
    -500, 230, 500, 200, C_SC)
smt.create_comment_in_material(
    mat, "iq's sdPie: dDisc = length(q) - PieRadius;  dPie = max(dDisc, m * sign(sc.y * q.x - sc.x * q.y)),\n"
         "m = length(q - sc * clamp(dot(q, sc), 0, PieRadius))   (distance to the straight edge)",
    -150, -400, 1350, 1200, C_SDF)
smt.create_comment_in_material(
    mat, "dRing = abs(length(p) - Radius) - Thickness / 2\n"
         "Radius + Thickness / 2 = 0.8 by default (the material contract's reference circle)",
    450, 700, 1100, 380, C_SDF)
smt.create_comment_in_material(
    mat, "pie = lerp(clamp(0.5 - dPie / aa, 0, 1), clamp(0.5 - dDisc / aa, 0, 1), full) * fade\n"
         "ring = clamp(0.5 - dRing / aa, 0, 1) * RingOpacity;  mask = max(pie, ring)",
    1350, -500, 1450, 1450, C_COL)
smt.create_comment_in_material(
    mat, "rimPx = TAU * PieRadius / aa   (pixels around the pie's rim)\n"
         "fade = saturate(span * rimPx): a pie thinner than a pixel at the rim fades with its width.\n"
         "full = saturate(1 - (1 - span) * rimPx): a gap thinner than a pixel at the rim closes toward the disc.\n"
         "Without them a sub-pixel pie or gap is a zero-distance line drawn at half coverage, and smoothstep lingers\n"
         "near full and empty, so a hairline at 12 o'clock stayed for over 0.1 s",
    1350, 1050, 1450, 750, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    2850, 80, 650, 700, C_COL)

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

expected_decls = sorted(["p", "aa", "u", "head", "tail", "span", "c", "s", "sc", "q", "PieRadius", "dDisc", "dPie",
                         "dRing", "rimPx", "fade", "full", "mask"])
expected_usages = {"p": 3, "aa": 4, "u": 2, "head": 2, "tail": 2, "span": 3, "c": 2, "s": 2, "sc": 4, "q": 5,
                   "PieRadius": 3, "dDisc": 2, "dPie": 1, "dRing": 1, "rimPx": 2, "fade": 1, "full": 1, "mask": 1}
expected_params = sorted(["Radius", "Thickness", "PieRadius", "RingOpacity", "Speed", "PrimaryColor"])
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
