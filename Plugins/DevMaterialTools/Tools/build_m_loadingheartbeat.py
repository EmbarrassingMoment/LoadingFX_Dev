"""
Heartbeat monitor -> M_LoadingHeartbeat (Material Domain = UI, Translucent)

心電図の波形を、明るい先頭の点が左から右へ描いていくロードアイコン。描いた波形は先頭の後ろで薄れて消え、右端を過ぎた先頭は
左端へ戻って描き直す(古い波形はモニターのように右側に残って消えていく)。
デザインは 2026-11-21 の 1.1 向けスピナー案(Python の静止画と GIF、Saved/SpinnerConcepts)でユーザーが選んだもの。
式は Saved/SpinnerConcepts/material_formulas.py で 1 段ずつ確かめた(コンセプトの折れ線を等間隔の頂点に直した版)。
clamp(x, 0, 1) は Saturate で書く。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  cov(d) = saturate(0.5 - d / aa)

  波形: 頂点 k = -10..10 を x = k * dx に等間隔に置いた折れ線。
  L      = HalfWidth - Thickness / 2                (端の頂点の x。線の丸い端が HalfWidth に届く)
  dx     = L / 10
  y(k)   = HalfHeight * (BASE + sum_w A_w * smoothstep(0, 1, 1 - abs(k - C_w) / W_w))
                                                    (波ごとに 1 つの山。整数の k で読むので高さの表になる。
                                                     P: C -4, W 2 / Q: -1, 1 / R: 0, 1 / S: 1, 1 / T: 5, 3。
                                                     R の頂点が +1、S の谷が -1 になるよう BASE と A を中央へ寄せてある)
  ピクセルの区間: k0 = floor(p.x / dx)
  K      = clamp(k0 + (-1, 0, 1, 2), -10, 10)       (float4。ピクセルの区間と左右 1 区間ずつの 4 頂点)
  X, Y   = K * dx, y(K)                             (float4 のまま 4 頂点を一度に計算する)
  線分 3 本(K.xyz -> K.yzw)を float3 で一度に評価する(iq の sdSegment):
    pa   = (p.x - X.xyz, p.y - Y.xyz),  ba = (X.yzw - X.xyz, Y.yzw - Y.xyz)
    h    = saturate(dot(pa, ba) / max(dot(ba, ba), 1e-8))   (端でクランプした 2 頂点が重なると ba = 0)
    dist = length(pa - ba * h)
  dLine  = min(dist.x, dist.y, dist.z) - Thickness / 2
    3 本で足りる理由: ほかの線分はピクセルから x 方向に dx 以上離れている。dx(既定 0.069)が Thickness / 2 + aa / 2 より
    大きい間(既定値で約 26 px 以上のウィジェット)は、その線分がピクセルを覆うことはない。

  先頭と残像:
  u      = fract(Time * Speed)                      (Speed は 1 秒あたりの掃引回数)
  Wd     = 2 * HalfWidth / (1 - OFF)                (1 周期に先頭が進む距離。OFF = 0.1 周期は右端の外にいる)
  hx     = Wd * u - HalfWidth                       (先頭の x)
  behind = fract(u - (p.x + HalfWidth) / Wd)        (先頭がこの x を通ってからの周期。右端の外から左端へ折り返す)
  trace  = cov(dLine) * saturate(1 - behind / TrailFraction)^2 * saturate(behind * Wd / aa + 0.5)
                                                    (最後の項は先頭の縦の切り口の AA。先頭の直前では behind が 1 に近く、
                                                     残像の項が 0 なので切り口は出ない)
  先頭の点の高さはピクセル自身の 4 頂点から読む:
    hk   = hx / dx,  j = floor(hk) - k0 + 1         (先頭の区間が 4 頂点の何番目から始まるか)
    yA   = dot(Y, saturate(1 - abs((0,1,2,3) - j))),  yB = dot(Y, saturate(1 - abs((0,1,2,3) - j - 1)))
    hy   = lerp(yA, yB, fract(hk))
    点の中のピクセルは先頭から DotRadius(< dx)以内なので j は 0..2 に入る。外のピクセルの hy は意味がないが、
    そこでは点の cov が 0。
  head   = cov(length(p - (hx, hy)) - DotRadius) * smoothstep(0, 0.1, L - abs(hx))
                                                    (端の 0.1 で点が現れ、消える)
  mask   = max(trace, head)

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は HalfWidth = 0.72(材質契約の基準正方形の半幅。M_LoadingLine と同じく横幅)に合わせてある。
  縦は HalfHeight + Thickness / 2 = 0.53。M_LoadingLine と同じく、横長のウィジェットでも大きさは変わらない。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(PARAM_GROUPS、順序は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingheartbeat.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingHeartbeat"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
N_HALF = 10          # points from the center to each end of the trace
OFF_FRACTION = 0.1   # part of a cycle the head spends past the right end
HEAD_FADE = 0.1      # the head fades in and out over this distance at the ends of the trace
SEG_EPSILON = 1e-8
# Waveform, in HalfHeight units: the R peak is +1 and the S trough -1. Raw heights relative to the R peak
# (P 0.17, Q -0.2, R 1, S -0.63, T 0.28) are centered: BASE = -(1 + S) / (1 - S), A = raw * 2 / (1 - S).
RAW_S = -0.63
_SCALE = (1.0 - RAW_S) / 2.0
BASE = -(1.0 + RAW_S) / 2.0 / _SCALE
WAVES = [  # name, center (point index), half width (points), height above the baseline
    ("P", -4.0, 2.0, 0.17 / _SCALE),
    ("Q", -1.0, 1.0, -0.2 / _SCALE),
    ("R", 0.0, 1.0, 1.0 / _SCALE),
    ("S", 1.0, 1.0, RAW_S / _SCALE),
    ("T", 5.0, 3.0, 0.28 / _SCALE),
]
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "HalfWidth": "Shape",
    "HalfHeight": "Shape",
    "Thickness": "Shape",
    "DotRadius": "Shape",
    "Speed": "Motion",
    "TrailFraction": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / points = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / head = light blue
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

def mask(src, x, y, r=False, g=False, b=False, a=False):
    return unary(unreal.MaterialExpressionComponentMask, src, x, y, r=r, g=g, b=b, a=a)

def coverage(d, x, y):
    """saturate(0.5 - d / aa): the anti-aliased mask of a distance, 1px-wide edge."""
    aa_u = use("aa", x, y + 100)
    d_over = binary(unreal.MaterialExpressionDivide, d, aa_u, x + 150, y + 50)
    half_minus = expr(unreal.MaterialExpressionSubtract, x + 300, y + 50, const_a=0.5)
    _connect(d_over, "", half_minus, "B")
    return unary(unreal.MaterialExpressionSaturate, half_minus, x + 450, y + 50)

def one_hot(j, x, y):
    """saturate(1 - abs((0, 1, 2, 3) - j)): picks one of the pixel's four points (float4)."""
    lanes = expr(unreal.MaterialExpressionConstant4Vector, x, y + 100, constant=unreal.LinearColor(0.0, 1.0, 2.0, 3.0))
    diff = binary(unreal.MaterialExpressionSubtract, lanes, j, x + 150, y + 50)
    diff_abs = unary(unreal.MaterialExpressionAbs, diff, x + 300, y + 50)
    inv = unary(unreal.MaterialExpressionOneMinus, diff_abs, x + 450, y + 50)
    return unary(unreal.MaterialExpressionSaturate, inv, x + 600, y + 50)

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -4300, -2300, material_function=mf_coords)
make_decl("p", coords, -4000, -2350, C_UV, "P")
make_decl("aa", coords, -4000, -2230, C_SDF, "PixelSize")

# ---- Shape: L = HalfWidth - Thickness / 2 (the end points), dx = L / 10 ----
# Footprint (material contract): HalfWidth = 0.72, the reference square, as M_LoadingLine.
halfw_p = scalar_param("HalfWidth", 0.72, 0,
                       "Half width of the trace, to the outer edge of its round ends "
                       "(half the shorter widget side = 1.0)", -4300, -1950)
make_decl("HalfWidth", halfw_p, -4000, -1950, C_SC)
thick_p = scalar_param("Thickness", 0.06, 2, "Stroke width of the trace", -4300, -1830)
half_thick = expr(unreal.MaterialExpressionMultiply, -4100, -1830, const_b=0.5)
_connect(thick_p, "", half_thick, "A")
make_decl("halfThickness", half_thick, -3950, -1830, C_SC)
halfw_u0 = use("HalfWidth", -3800, -1950)
half_thick_u0 = use("halfThickness", -3800, -1850)
l_v = binary(unreal.MaterialExpressionSubtract, halfw_u0, half_thick_u0, -3650, -1900)
make_decl("L", l_v, -3500, -1900, C_SC)
l_u0 = use("L", -3500, -1780)
dx_v = expr(unreal.MaterialExpressionDivide, -3350, -1780, const_b=float(N_HALF))
_connect(l_u0, "", dx_v, "A")
make_decl("dx", dx_v, -3200, -1780, C_UV)

# ---- k0 = floor(p.x / dx);  K = clamp(k0 + (-1, 0, 1, 2), -10, 10)  (float4) ----
p_u1 = use("p", -2900, -2000)
p_x1 = mask(p_u1, -2750, -2000, r=True)
dx_u1 = use("dx", -2750, -1900)
cell_div = binary(unreal.MaterialExpressionDivide, p_x1, dx_u1, -2600, -1950)
k0_floor = unary(unreal.MaterialExpressionFloor, cell_div, -2450, -1950)
make_decl("k0", k0_floor, -2300, -1950, C_UV)
k0_u1 = use("k0", -2900, -1700)
k_lanes = expr(unreal.MaterialExpressionConstant4Vector, -2900, -1600,
               constant=unreal.LinearColor(-1.0, 0.0, 1.0, 2.0))
k_add = binary(unreal.MaterialExpressionAdd, k0_u1, k_lanes, -2700, -1650)
k_clamp = expr(unreal.MaterialExpressionClamp, -2550, -1650, min_default=-float(N_HALF), max_default=float(N_HALF))
_connect(k_add, "", k_clamp, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
make_decl("K", k_clamp, -2400, -1650, C_UV)

# ---- Y = HalfHeight * (BASE + sum_w A_w * smoothstep(0, 1, 1 - abs(K - C_w) / W_w))  (float4) ----
WAVE_X, WAVE_Y, WAVE_DY = -2900, -1100, 220
total = None
for i, (name, center, width, height) in enumerate(WAVES):
    y = WAVE_Y + i * WAVE_DY
    k_u = use("K", WAVE_X, y)
    off = expr(unreal.MaterialExpressionSubtract, WAVE_X + 150, y, const_b=center)
    _connect(k_u, "", off, "A")
    rel = unary(unreal.MaterialExpressionAbs, off, WAVE_X + 300, y)
    if width != 1.0:
        scaled = expr(unreal.MaterialExpressionMultiply, WAVE_X + 450, y, const_b=1.0 / width)
        _connect(rel, "", scaled, "A")
        rel = scaled
    bump_in = unary(unreal.MaterialExpressionOneMinus, rel, WAVE_X + 600, y)
    bump = expr(unreal.MaterialExpressionSmoothStep, WAVE_X + 750, y, const_min=0.0, const_max=1.0)
    _connect(bump_in, "", bump, "Value")
    term = expr(unreal.MaterialExpressionMultiply, WAVE_X + 900, y, const_b=height)
    _connect(bump, "", term, "A")
    total = term if total is None else binary(unreal.MaterialExpressionAdd, total, term, WAVE_X + 1100, y - 60)
y_base = expr(unreal.MaterialExpressionAdd, WAVE_X + 1250, WAVE_Y + len(WAVES) * WAVE_DY, const_b=BASE)
_connect(total, "", y_base, "A")
halfh_p = scalar_param("HalfHeight", 0.5, 1,
                       "Half the height of the waveform: the tallest spike reaches +HalfHeight, the deepest -HalfHeight",
                       WAVE_X + 1250, WAVE_Y + len(WAVES) * WAVE_DY + 120)
y_v = binary(unreal.MaterialExpressionMultiply, y_base, halfh_p, WAVE_X + 1450, WAVE_Y + len(WAVES) * WAVE_DY + 50)
make_decl("Y", y_v, WAVE_X + 1600, WAVE_Y + len(WAVES) * WAVE_DY + 50, C_UV)

# ---- X = K * dx;  three segments (K.xyz -> K.yzw) at once in float3 (iq's sdSegment);
#      dLine = min(dist.x, dist.y, dist.z) - Thickness / 2 ----
SEG_X, SEG_Y = -900, -2000
k_u2 = use("K", SEG_X, SEG_Y)
dx_u2 = use("dx", SEG_X, SEG_Y + 100)
x_v = binary(unreal.MaterialExpressionMultiply, k_u2, dx_u2, SEG_X + 150, SEG_Y + 50)
make_decl("X", x_v, SEG_X + 300, SEG_Y + 50, C_UV)
x_u1 = use("X", SEG_X, SEG_Y + 250)
y_u1 = use("Y", SEG_X, SEG_Y + 450)
ax = mask(x_u1, SEG_X + 150, SEG_Y + 200, r=True, g=True, b=True)
bx = mask(x_u1, SEG_X + 150, SEG_Y + 300, g=True, b=True, a=True)
ay = mask(y_u1, SEG_X + 150, SEG_Y + 400, r=True, g=True, b=True)
by = mask(y_u1, SEG_X + 150, SEG_Y + 500, g=True, b=True, a=True)
p_u2 = use("p", SEG_X + 150, SEG_Y + 650)
p_x2 = mask(p_u2, SEG_X + 300, SEG_Y + 600, r=True)
p_y2 = mask(p_u2, SEG_X + 300, SEG_Y + 700, g=True)
pax = binary(unreal.MaterialExpressionSubtract, p_x2, ax, SEG_X + 450, SEG_Y + 550)
pay = binary(unreal.MaterialExpressionSubtract, p_y2, ay, SEG_X + 450, SEG_Y + 700)
bax = binary(unreal.MaterialExpressionSubtract, bx, ax, SEG_X + 450, SEG_Y + 200)
bay = binary(unreal.MaterialExpressionSubtract, by, ay, SEG_X + 450, SEG_Y + 400)
num = binary(unreal.MaterialExpressionAdd,
             binary(unreal.MaterialExpressionMultiply, pax, bax, SEG_X + 600, SEG_Y + 500),
             binary(unreal.MaterialExpressionMultiply, pay, bay, SEG_X + 600, SEG_Y + 650), SEG_X + 750, SEG_Y + 550)
den = binary(unreal.MaterialExpressionAdd,
             binary(unreal.MaterialExpressionMultiply, bax, bax, SEG_X + 600, SEG_Y + 200),
             binary(unreal.MaterialExpressionMultiply, bay, bay, SEG_X + 600, SEG_Y + 350), SEG_X + 750, SEG_Y + 250)
den_max = expr(unreal.MaterialExpressionMax, SEG_X + 900, SEG_Y + 250, const_b=SEG_EPSILON)
_connect(den, "", den_max, "A")
h_div = binary(unreal.MaterialExpressionDivide, num, den_max, SEG_X + 1050, SEG_Y + 400)
h_sat = unary(unreal.MaterialExpressionSaturate, h_div, SEG_X + 1200, SEG_Y + 400)
ex = binary(unreal.MaterialExpressionSubtract, pax,
            binary(unreal.MaterialExpressionMultiply, bax, h_sat, SEG_X + 1350, SEG_Y + 300), SEG_X + 1500, SEG_Y + 350)
ey = binary(unreal.MaterialExpressionSubtract, pay,
            binary(unreal.MaterialExpressionMultiply, bay, h_sat, SEG_X + 1350, SEG_Y + 550), SEG_X + 1500, SEG_Y + 550)
dist_sq = binary(unreal.MaterialExpressionAdd,
                 binary(unreal.MaterialExpressionMultiply, ex, ex, SEG_X + 1650, SEG_Y + 350),
                 binary(unreal.MaterialExpressionMultiply, ey, ey, SEG_X + 1650, SEG_Y + 550), SEG_X + 1800, SEG_Y + 450)
dist = unary(unreal.MaterialExpressionSquareRoot, dist_sq, SEG_X + 1950, SEG_Y + 450)
dist_min = binary(unreal.MaterialExpressionMin,
                  binary(unreal.MaterialExpressionMin, mask(dist, SEG_X + 2100, SEG_Y + 350, r=True),
                         mask(dist, SEG_X + 2100, SEG_Y + 450, g=True), SEG_X + 2250, SEG_Y + 400),
                  mask(dist, SEG_X + 2100, SEG_Y + 550, b=True), SEG_X + 2400, SEG_Y + 450)
half_thick_u1 = use("halfThickness", SEG_X + 2400, SEG_Y + 570)
dline_v = binary(unreal.MaterialExpressionSubtract, dist_min, half_thick_u1, SEG_X + 2550, SEG_Y + 500)
make_decl("dLine", dline_v, SEG_X + 2700, SEG_Y + 500, C_SDF)

# ---- u = fract(Time * Speed);  Wd = 2 * HalfWidth / (1 - OFF);  hx = Wd * u - HalfWidth;
#      behind = fract(u - (p.x + HalfWidth) / Wd) ----
TM_X, TM_Y = -4300, 650
time_n = expr(unreal.MaterialExpressionTime, TM_X, TM_Y)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.5, 0, "Sweeps per second (left to right)", TM_X, TM_Y + 120)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, TM_X + 200, TM_Y + 50)
u_frac = unary(unreal.MaterialExpressionFrac, t_speed, TM_X + 350, TM_Y + 50)
make_decl("u", u_frac, TM_X + 500, TM_Y + 50, C_TM)
halfw_u1 = use("HalfWidth", TM_X, TM_Y + 300)
wd_v = expr(unreal.MaterialExpressionMultiply, TM_X + 150, TM_Y + 300, const_b=2.0 / (1.0 - OFF_FRACTION))
_connect(halfw_u1, "", wd_v, "A")
make_decl("Wd", wd_v, TM_X + 300, TM_Y + 300, C_TM)
u_u1 = use("u", TM_X + 700, TM_Y)
wd_u1 = use("Wd", TM_X + 700, TM_Y + 100)
hx_mul = binary(unreal.MaterialExpressionMultiply, u_u1, wd_u1, TM_X + 850, TM_Y + 50)
halfw_u2 = use("HalfWidth", TM_X + 850, TM_Y + 170)
hx_v = binary(unreal.MaterialExpressionSubtract, hx_mul, halfw_u2, TM_X + 1000, TM_Y + 100)
make_decl("hx", hx_v, TM_X + 1150, TM_Y + 100, C_TM)
p_u3 = use("p", TM_X + 700, TM_Y + 350)
p_x3 = mask(p_u3, TM_X + 850, TM_Y + 350, r=True)
halfw_u3 = use("HalfWidth", TM_X + 850, TM_Y + 450)
px_shift = binary(unreal.MaterialExpressionAdd, p_x3, halfw_u3, TM_X + 1000, TM_Y + 400)
wd_u2 = use("Wd", TM_X + 1000, TM_Y + 520)
px_cyc = binary(unreal.MaterialExpressionDivide, px_shift, wd_u2, TM_X + 1150, TM_Y + 450)
u_u2 = use("u", TM_X + 1150, TM_Y + 330)
behind_sub = binary(unreal.MaterialExpressionSubtract, u_u2, px_cyc, TM_X + 1300, TM_Y + 400)
behind_frac = unary(unreal.MaterialExpressionFrac, behind_sub, TM_X + 1450, TM_Y + 400)
make_decl("behind", behind_frac, TM_X + 1600, TM_Y + 400, C_TM)

# ---- trace = cov(dLine) * saturate(1 - behind / TrailFraction)^2 * saturate(behind * Wd / aa + 0.5) ----
TR_X, TR_Y = -900, -900
dline_u1 = use("dLine", TR_X, TR_Y)
line_cov = coverage(dline_u1, TR_X + 150, TR_Y - 50)
behind_u1 = use("behind", TR_X, TR_Y + 250)
trailf_p = scalar_param("TrailFraction", 0.6, 1,
                        "How long the trace stays after the head has drawn it, as a fraction of a sweep "
                        "(below 1)", TR_X, TR_Y + 350)
trail_div = binary(unreal.MaterialExpressionDivide, behind_u1, trailf_p, TR_X + 200, TR_Y + 300)
trail_inv = unary(unreal.MaterialExpressionOneMinus, trail_div, TR_X + 350, TR_Y + 300)
trail_sat = unary(unreal.MaterialExpressionSaturate, trail_inv, TR_X + 500, TR_Y + 300)
trail_sq = binary(unreal.MaterialExpressionMultiply, trail_sat, trail_sat, TR_X + 650, TR_Y + 300)
behind_u2 = use("behind", TR_X, TR_Y + 500)
wd_u3 = use("Wd", TR_X, TR_Y + 600)
behind_len = binary(unreal.MaterialExpressionMultiply, behind_u2, wd_u3, TR_X + 150, TR_Y + 550)
aa_u1 = use("aa", TR_X + 150, TR_Y + 670)
edge_div = binary(unreal.MaterialExpressionDivide, behind_len, aa_u1, TR_X + 300, TR_Y + 600)
edge_add = expr(unreal.MaterialExpressionAdd, TR_X + 450, TR_Y + 600, const_b=0.5)
_connect(edge_div, "", edge_add, "A")
edge_sat = unary(unreal.MaterialExpressionSaturate, edge_add, TR_X + 600, TR_Y + 600)
trace_tr = binary(unreal.MaterialExpressionMultiply, line_cov, trail_sq, TR_X + 800, TR_Y + 150)
trace_v = binary(unreal.MaterialExpressionMultiply, trace_tr, edge_sat, TR_X + 950, TR_Y + 350)
make_decl("trace", trace_v, TR_X + 1100, TR_Y + 350, C_COL)

# ---- Head: hk = hx / dx;  j = floor(hk) - k0 + 1;  hy = lerp(dot(Y, onehot(j)), dot(Y, onehot(j + 1)), fract(hk)) ----
HD_X, HD_Y = -2900, 1600
hx_u1 = use("hx", HD_X, HD_Y)
dx_u3 = use("dx", HD_X, HD_Y + 100)
hk_v = binary(unreal.MaterialExpressionDivide, hx_u1, dx_u3, HD_X + 150, HD_Y + 50)
make_decl("hk", hk_v, HD_X + 300, HD_Y + 50, C_TM)
hk_u1 = use("hk", HD_X, HD_Y + 300)
hk_floor = unary(unreal.MaterialExpressionFloor, hk_u1, HD_X + 150, HD_Y + 300)
k0_u2 = use("k0", HD_X + 150, HD_Y + 420)
j_sub = binary(unreal.MaterialExpressionSubtract, hk_floor, k0_u2, HD_X + 300, HD_Y + 350)
j_v = expr(unreal.MaterialExpressionAdd, HD_X + 450, HD_Y + 350, const_b=1.0)
_connect(j_sub, "", j_v, "A")
j_next = expr(unreal.MaterialExpressionAdd, HD_X + 600, HD_Y + 600, const_b=1.0)
_connect(j_v, "", j_next, "A")
w_a = one_hot(j_v, HD_X + 650, HD_Y + 250)
w_b = one_hot(j_next, HD_X + 750, HD_Y + 550)
y_u2 = use("Y", HD_X + 1300, HD_Y + 150)
y_a = binary(unreal.MaterialExpressionDotProduct, y_u2, w_a, HD_X + 1450, HD_Y + 250)
y_b = binary(unreal.MaterialExpressionDotProduct, y_u2, w_b, HD_X + 1450, HD_Y + 550)
hk_u2 = use("hk", HD_X + 1450, HD_Y + 700)
hk_frac = unary(unreal.MaterialExpressionFrac, hk_u2, HD_X + 1600, HD_Y + 700)
hy_v = expr(unreal.MaterialExpressionLinearInterpolate, HD_X + 1750, HD_Y + 450)
_connect(y_a, "", hy_v, "A")
_connect(y_b, "", hy_v, "B")
_connect(hk_frac, "", hy_v, "Alpha")

# ---- head = cov(length(p - (hx, hy)) - DotRadius) * smoothstep(0, 0.1, L - abs(hx)) ----
hx_u2 = use("hx", HD_X + 1750, HD_Y + 250)
head_pos = binary(unreal.MaterialExpressionAppendVector, hx_u2, hy_v, HD_X + 1900, HD_Y + 350)
p_u4 = use("p", HD_X + 1900, HD_Y + 200)
head_rel = binary(unreal.MaterialExpressionSubtract, p_u4, head_pos, HD_X + 2050, HD_Y + 300)
head_len = unary(unreal.MaterialExpressionLength, head_rel, HD_X + 2200, HD_Y + 300)
dotr_p = scalar_param("DotRadius", 0.055, 3, "Radius of the bright dot at the head of the trace",
                      HD_X + 2200, HD_Y + 420)
head_d = binary(unreal.MaterialExpressionSubtract, head_len, dotr_p, HD_X + 2350, HD_Y + 350)
head_cov = coverage(head_d, HD_X + 2500, HD_Y + 300)
l_u1 = use("L", HD_X + 2500, HD_Y + 650)
hx_u3 = use("hx", HD_X + 2500, HD_Y + 750)
hx_abs = unary(unreal.MaterialExpressionAbs, hx_u3, HD_X + 2650, HD_Y + 750)
inside = binary(unreal.MaterialExpressionSubtract, l_u1, hx_abs, HD_X + 2800, HD_Y + 700)
vis = expr(unreal.MaterialExpressionSmoothStep, HD_X + 2950, HD_Y + 700, const_min=0.0, const_max=HEAD_FADE)
_connect(inside, "", vis, "Value")
head_v = binary(unreal.MaterialExpressionMultiply, head_cov, vis, HD_X + 3150, HD_Y + 500)
make_decl("head", head_v, HD_X + 3300, HD_Y + 500, C_COL)

# ---- mask = max(trace, head) ----
MAX_X, MAX_Y = 900, 0
trace_u = use("trace", MAX_X, MAX_Y)
head_u = use("head", MAX_X, MAX_Y + 100)
mask_v = binary(unreal.MaterialExpressionMax, trace_u, head_u, MAX_X + 150, MAX_Y + 50)
make_decl("mask", mask_v, MAX_X + 300, MAX_Y + 50, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
OUT_X, OUT_Y = 1500, 0
primary_p = expr(unreal.MaterialExpressionVectorParameter, OUT_X, OUT_Y - 150,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0,
                 desc="Color of the trace (alpha scales the opacity)")
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
    mat, "HalfWidth = 0.72 by default: the outer size shared by the square layouts, as M_LoadingLine. "
         "The trace joins 21 points, dx apart.",
    -4350, -2058, 1380, 420, C_SC)
smt.create_comment_in_material(
    mat, "Points around the pixel\n"
         "K holds the pixel's cell and one cell on each side, clamped to the ends of the trace.",
    -2950, -2108, 850, 620, C_UV)
smt.create_comment_in_material(
    mat, "Waveform: P, Q, R, S, T\n"
         "One smoothstep bump per wave, read at whole point numbers: a table of heights in nodes. "
         "R peaks at +1 and S at -1, times HalfHeight.",
    -2950, WAVE_Y - 170, 1900, len(WAVES) * WAVE_DY + 450, C_UV)
smt.create_comment_in_material(
    mat, "Segments (iq's sdSegment, three at once in float3)\n"
         "Every other segment is at least dx away in x, more than half the stroke plus the AA edge in a "
         "widget above about 26 px. Clamped end points can meet: hence the max in the divisor.",
    SEG_X - 50, SEG_Y - 170, 2950, 950, C_SDF)
smt.create_comment_in_material(
    mat, "Time has Ignore Pause on (real time), so the trace keeps moving while the game thread is blocked. "
         "The head spends a tenth of each sweep past the right end.",
    TM_X - 50, TM_Y - 150, 1850, 750, C_TM)
smt.create_comment_in_material(
    mat, "Trail\n"
         "Right before the head, behind is close to 1, so the cut at the head shows only once it has passed.",
    TR_X - 50, TR_Y - 150, 1350, 900, C_COL)
smt.create_comment_in_material(
    mat, "Head\n"
         "Its height comes from the pixel's own four points: a pixel inside the dot is less than dx from it. "
         "Elsewhere hy is meaningless, but the dot does not cover those pixels.",
    HD_X - 50, HD_Y - 170, 3550, 1050, C_TM)

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
expected_decls = sorted(["p", "aa", "HalfWidth", "halfThickness", "L", "dx", "k0", "K", "Y", "X", "dLine", "u",
                         "Wd", "hx", "behind", "trace", "hk", "head", "mask"])
expected_usages = {"p": 4, "aa": 3, "HalfWidth": 4, "halfThickness": 2, "L": 2, "dx": 3, "k0": 2,
                   "K": len(WAVES) + 1, "Y": 2, "X": 1, "dLine": 1, "u": 2, "Wd": 3, "hx": 3, "behind": 2,
                   "trace": 1, "hk": 2, "head": 1, "mask": 1}
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == sorted(PARAM_GROUPS) and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 7
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
