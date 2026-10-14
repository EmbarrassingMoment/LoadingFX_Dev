"""
Ripple -> M_LoadingRipple (Material Domain = UI, Translucent)

中心から輪が生まれ、減速しながら Radius まで広がり、広がるほど薄くなって消えるロードアイコン(1 色)。
Count 本の輪が時間的に等間隔で並ぶ。デザインは 2026-10-14 のスピナー案第 3 弾の 1 番(波紋)。
WebGL2 のスケッチ(Saved/RippleHarness/harness.html)で形と式を確かめてから組んだ。clamp(x, 0, 1) は Saturate で書く。

  rho  = length(MF_SpinnerCoords.P)                 (中心からの距離。P は中心 (0,0)、y 上向き、短辺が -1..1)
  aa   = MF_SpinnerCoords.PixelSize                 (1 ピクセルを P 単位で)
  s    = fract(Time * Speed * Count)                (輪 k = 0..Count-1 の位相は (k + s) / Count。Speed は 1 秒あたりの
                                                     広がりの回数で、1 本の輪は 1 / Speed 秒で Radius に届く)
  g(phi) = 1 - (1 - phi)^Easing                     (輪の半径 = Radius * g(phi)。Easing > 1 で最初が速く Radius 手前で遅い)
  th   = max(Thickness, aa)                         (1 ピクセルより細くしない)
  輪の選び方(ループなし):
    phiIn = 1 - (1 - saturate((rho - (th - aa) / 2) / Radius))^(1 / Easing)
                                                    (g の逆関数を「線の内側の縁」で評価: この位相より外の輪のうち最も内側の輪 kOut が、
                                                     AA の縁ではなく線の本体でピクセルに届く最も内側の輪)
    k0    = floor(phiIn * Count - s)
    kIn   = clamp(k0, 0, Count - 1)                 (kOut の 1 本内側。外側の AA の縁がまだピクセルにかかり得る)
    kOut  = clamp(k0 + 1, 0, Count - 1)
    輪は Radius 手前で減速して詰まり、重なることがある。輪は広がるほど薄いので、重なりではピクセルにかかる最も内側の輪が
    最も濃い。よってこの 2 本で全輪の max と一致する(隣の輪が 1 ピクセル以上離れている間は厳密。WebGL2 スケッチで
    全輪の総当たりと比べ、既定値では 32..512 px のどれでも誤差 0。Count 5 / Easing 2 でも差は 32 px だけ。輪が 1 ピクセルより
    詰まるところでは、Radius 際の薄い輪の AA の縁が少し欠ける。輪の中心で逆関数を取る版は、Count 5 で全サイズにわたって
    重なった濃い輪を取りこぼした(濃さで最大 0.1))
  1 本の輪(k = kIn, kOut):
    phi  = (k + s) / Count
    d    = abs(rho - Radius * g(phi)) - th / 2
    ring = saturate(0.5 - d / aa) * (1 - phi) * smoothstep(0, 0.1, phi)
                                                    (広がるほど薄く、生まれた直後の 0.1 だけフェードイン: 中心の点が急に出ない)
  mask = max(ringIn, ringOut) * (Thickness / th)    (th を太らせた分だけ濃さを下げる: 1 ピクセルより細い形は濃さ 0.5 の線に
                                                     なるので(M_LoadingTimer の教訓))
  Speed が負なら輪は外から中心へ縮む(位相が逆に進むだけで、式はそのまま成り立つ)。

  デフォルトの外寸: Radius + Thickness / 2 = 0.8(材質契約の基準円。輪は消える瞬間に Radius に届く)。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。

  ScalarParameter / VectorParameter はグループ "LoadingRipple"。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Radius / Thickness / Count / Easing(複数箇所)は Declaration 化、Speed は 1 箇所なので直接配線。
  1 本の輪を描くノード列は ring_chain() で kIn 用と kOut 用に 2 回作る。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingripple.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingRipple"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
FADE_IN = 0.1   # share of a ring's life spent fading in at the center
PARAM_GROUP = "LoadingRipple"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / distances = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / phases / ring selection = light blue
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
                parameter_name=name, default_value=default, group=PARAM_GROUP,
                sort_priority=sort, desc=desc)

def binary(cls, a, b, x, y):
    n = expr(cls, x, y)
    _connect(a, "", n, "A")
    _connect(b, "", n, "B")
    return n

# ---- rho = length(MF_SpinnerCoords.P), aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3600, -700, material_function=mf_coords)
rho_len = expr(unreal.MaterialExpressionLength, -3350, -750)
_connect(coords, "P", rho_len, "")
make_decl("rho", rho_len, -3200, -750, C_UV)
make_decl("aa", coords, -3200, -630, C_SDF, "PixelSize")

# ---- Shared parameters ----
# Footprint (material contract): Radius + Thickness / 2 = 0.8, reached as a ring vanishes.
radius_p = scalar_param("Radius", 0.77, 0,
                        "Distance from the center at which a ring vanishes, to the middle of its stroke "
                        "(half the shorter widget side = 1.0)", -3800, -400)
make_decl("Radius", radius_p, -3550, -400, C_SC)
thick_p = scalar_param("Thickness", 0.06, 1, "Stroke width of a ring", -3800, -280)
make_decl("Thickness", thick_p, -3550, -280, C_SC)
count_p = scalar_param("Count", 3.0, 2, "Rings on screen at a time, evenly spaced in time (integer, 1 or more)",
                       -3800, -160)
make_decl("Count", count_p, -3550, -160, C_SC)
easing_p = scalar_param("Easing", 2.0, 3,
                        "How a ring slows down as it spreads: 1 = constant speed, 2 = quadratic ease-out; "
                        "higher = faster at first and slower near Radius (above 0)", -3800, -40)
make_decl("Easing", easing_p, -3550, -40, C_SC)

# ---- s = fract(Time * Speed * Count): ring k = 0 .. Count - 1 has the phase (k + s) / Count ----
time_n = expr(unreal.MaterialExpressionTime, -3800, 300)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.5, 4,
                       "Spreads per second: each ring takes 1 / Speed seconds to reach Radius. "
                       "Negative = the rings close in toward the center", -3800, 420)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3600, 350)
count_u1 = use("Count", -3600, 480)
t_count = binary(unreal.MaterialExpressionMultiply, t_speed, count_u1, -3450, 400)
s_frac = expr(unreal.MaterialExpressionFrac, -3300, 400)
_connect(t_count, "", s_frac, "")
make_decl("s", s_frac, -3150, 400, C_TM)

# ---- th = max(Thickness, aa): never thinner than one pixel ----
thick_u1 = use("Thickness", -3600, 800)
aa_u1 = use("aa", -3600, 900)
th_max = binary(unreal.MaterialExpressionMax, thick_u1, aa_u1, -3450, 850)
make_decl("th", th_max, -3300, 850, C_SDF)

# ---- phiIn = 1 - (1 - saturate((rho - (th - aa) / 2) / Radius))^(1 / Easing)   (g inverted at the stroke's inner edge) ----
th_u1 = use("th", -3000, -350)
aa_u2 = use("aa", -3000, -250)
th_aa = binary(unreal.MaterialExpressionSubtract, th_u1, aa_u2, -2850, -300)
th_aa_half = expr(unreal.MaterialExpressionMultiply, -2700, -300, const_b=0.5)
_connect(th_aa, "", th_aa_half, "A")
rho_u1 = use("rho", -2700, -420)
rho_inner = binary(unreal.MaterialExpressionSubtract, rho_u1, th_aa_half, -2550, -380)
radius_u1 = use("Radius", -2550, -250)
x_div = binary(unreal.MaterialExpressionDivide, rho_inner, radius_u1, -2400, -330)
x_sat = expr(unreal.MaterialExpressionSaturate, -2250, -330)
_connect(x_div, "", x_sat, "")
x_rest = expr(unreal.MaterialExpressionOneMinus, -2100, -330)
_connect(x_sat, "", x_rest, "")
easing_u1 = use("Easing", -2250, -200)
inv_easing = expr(unreal.MaterialExpressionDivide, -2100, -200, const_a=1.0)
_connect(easing_u1, "", inv_easing, "B")
inv_pow = expr(unreal.MaterialExpressionPower, -1950, -280)
_connect(x_rest, "", inv_pow, "Base")
_connect(inv_easing, "", inv_pow, "Exp")
phi_in = expr(unreal.MaterialExpressionOneMinus, -1800, -280)
_connect(inv_pow, "", phi_in, "")

# ---- k0 = floor(phiIn * Count - s);  kIn = clamp(k0, 0, Count - 1);  kOut = clamp(k0 + 1, 0, Count - 1) ----
count_u2 = use("Count", -1800, -160)
phi_count = binary(unreal.MaterialExpressionMultiply, phi_in, count_u2, -1650, -230)
s_u1 = use("s", -1650, -110)
k_raw = binary(unreal.MaterialExpressionSubtract, phi_count, s_u1, -1500, -180)
k0_floor = expr(unreal.MaterialExpressionFloor, -1350, -180)
_connect(k_raw, "", k0_floor, "")
count_u3 = use("Count", -1350, 0)
count_m1 = expr(unreal.MaterialExpressionSubtract, -1200, 0, const_b=1.0)   # the Max of both clamps below
_connect(count_u3, "", count_m1, "A")
kin_clamp = expr(unreal.MaterialExpressionClamp, -1050, -250, min_default=0.0)
_connect(k0_floor, "", kin_clamp, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(count_m1, "", kin_clamp, "Max")
make_decl("kIn", kin_clamp, -900, -250, C_TM)
k0_next = expr(unreal.MaterialExpressionAdd, -1200, -100, const_b=1.0)
_connect(k0_floor, "", k0_next, "A")
kout_clamp = expr(unreal.MaterialExpressionClamp, -1050, -100, min_default=0.0)
_connect(k0_next, "", kout_clamp, "")
_connect(count_m1, "", kout_clamp, "Max")
make_decl("kOut", kout_clamp, -900, -100, C_TM)

# ---- One ring (built for kIn and for kOut) ----
#   phi  = (k + s) / Count
#   d    = abs(rho - Radius * (1 - (1 - phi)^Easing)) - th / 2
#   ring = saturate(0.5 - d / aa) * (1 - phi) * smoothstep(0, FADE_IN, phi)
def ring_chain(k_name, x, y):
    k_u = use(k_name, x, y - 50)
    s_u = use("s", x, y + 50)
    ks = binary(unreal.MaterialExpressionAdd, k_u, s_u, x + 150, y)
    count_u = use("Count", x + 150, y + 120)
    phi = binary(unreal.MaterialExpressionDivide, ks, count_u, x + 300, y)
    phi_rest = expr(unreal.MaterialExpressionOneMinus, x + 450, y)   # 1 - phi: the ring's opacity as it spreads
    _connect(phi, "", phi_rest, "")
    easing_u = use("Easing", x + 450, y + 120)
    ease_pow = expr(unreal.MaterialExpressionPower, x + 600, y + 50)
    _connect(phi_rest, "", ease_pow, "Base")
    _connect(easing_u, "", ease_pow, "Exp")
    g = expr(unreal.MaterialExpressionOneMinus, x + 750, y + 50)
    _connect(ease_pow, "", g, "")
    radius_u = use("Radius", x + 750, y + 170)
    r = binary(unreal.MaterialExpressionMultiply, radius_u, g, x + 900, y + 100)
    rho_u = use("rho", x + 900, y - 20)
    dr = binary(unreal.MaterialExpressionSubtract, rho_u, r, x + 1050, y + 50)
    dr_abs = expr(unreal.MaterialExpressionAbs, x + 1200, y + 50)
    _connect(dr, "", dr_abs, "")
    th_u = use("th", x + 1200, y + 170)
    th_half = expr(unreal.MaterialExpressionMultiply, x + 1350, y + 170, const_b=0.5)
    _connect(th_u, "", th_half, "A")
    d = binary(unreal.MaterialExpressionSubtract, dr_abs, th_half, x + 1500, y + 100)
    aa_u = use("aa", x + 1500, y + 220)
    d_aa = binary(unreal.MaterialExpressionDivide, d, aa_u, x + 1650, y + 150)
    cov_half = expr(unreal.MaterialExpressionSubtract, x + 1800, y + 150, const_a=0.5)
    _connect(d_aa, "", cov_half, "B")
    cov = expr(unreal.MaterialExpressionSaturate, x + 1950, y + 150)
    _connect(cov_half, "", cov, "")
    fade_in = expr(unreal.MaterialExpressionSmoothStep, x + 600, y - 150, const_min=0.0, const_max=FADE_IN)
    _connect(phi, "", fade_in, "Value")
    fade = binary(unreal.MaterialExpressionMultiply, phi_rest, fade_in, x + 900, y - 150)
    return binary(unreal.MaterialExpressionMultiply, cov, fade, x + 2100, y)

ring_in = ring_chain("kIn", -650, -600)
ring_out = ring_chain("kOut", -650, 300)

# ---- mask = max(ringIn, ringOut) * (Thickness / th) ----
ring_max = binary(unreal.MaterialExpressionMax, ring_in, ring_out, 1850, -150)
thick_u2 = use("Thickness", 1700, 0)
th_u2 = use("th", 1700, 100)
thin_ratio = binary(unreal.MaterialExpressionDivide, thick_u2, th_u2, 1850, 50)
mask_v = binary(unreal.MaterialExpressionMultiply, ring_max, thin_ratio, 2000, -50)
make_decl("mask", mask_v, 2150, -50, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2350, -250,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUP, sort_priority=10, desc="Color of the rings (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 2350, 0)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, 2600, -200)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 2350, 200)
cov_a = expr(unreal.MaterialExpressionMultiply, 2600, 150)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 2750, 100)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "rho = length(MF_SpinnerCoords.P)   (P: centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in P units)",
    -3650, -870, 700, 400, C_UV)
smt.create_comment_in_material(
    mat, "Shared parameters -> Named Reroutes.\n"
         "Radius + Thickness / 2 = 0.8: the material contract's reference circle, reached as a ring vanishes",
    -3850, -520, 600, 600, C_SC)
smt.create_comment_in_material(
    mat, "s = fract(Time * Speed * Count): ring k = 0 .. Count - 1 has the phase (k + s) / Count\n"
         "Each ring takes 1 / Speed seconds to spread. Time ignores pause (real time),\n"
         "so the rings keep spreading while the game thread is blocked",
    -3850, 200, 900, 400, C_TM)
smt.create_comment_in_material(
    mat, "th = max(Thickness, aa): never thinner than one pixel\n"
         "(a thinner ring would show at half coverage; mask loses opacity in proportion instead)",
    -3650, 700, 600, 350, C_SDF)
smt.create_comment_in_material(
    mat, "phiIn = 1 - (1 - saturate((rho - (th - aa) / 2) / Radius))^(1 / Easing)\n"
         "A ring's radius is Radius * g(phi), g(phi) = 1 - (1 - phi)^Easing. Inverting g at the stroke's inner edge\n"
         "gives the phase of a ring whose solid stroke would just reach this pixel",
    -3050, -520, 1350, 450, C_TM)
smt.create_comment_in_material(
    mat, "k0 = floor(phiIn * Count - s);  kIn = clamp(k0, 0, Count - 1);  kOut = clamp(k0 + 1, 0, Count - 1)\n"
         "kOut is the innermost ring whose stroke reaches the pixel, kIn the one inside it (its AA edge may still).\n"
         "Rings bunch up near Radius and may overlap; a ring fades as it spreads, so the innermost covering ring is\n"
         "the brightest: these two give the max over all rings (exact while neighbors are a pixel apart, no loop)",
    -1850, -420, 1150, 550, C_TM)
smt.create_comment_in_material(
    mat, "Ring kIn:  phi = (kIn + s) / Count;  d = abs(rho - Radius * (1 - (1 - phi)^Easing)) - th / 2\n"
         "ring = saturate(0.5 - d / aa) * (1 - phi) * smoothstep(0, 0.1, phi)   (fades as it spreads; fades in at birth)",
    -700, -870, 2350, 650, C_SDF)
smt.create_comment_in_material(
    mat, "Ring kOut: the same nodes for kOut",
    -700, 30, 2350, 650, C_SDF)
smt.create_comment_in_material(
    mat, "mask = max(ringIn, ringOut) * (Thickness / th)   (one color)",
    1650, -270, 650, 500, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    2300, -370, 650, 680, C_COL)

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
decl_names, usage_count, params, mf_calls = [], {}, [], 0
for e in smt.get_material_expressions(mat):
    if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
        decl_names.append(str(e.get_editor_property("name")))
    elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
        nm = smt.get_named_reroute_usage_display_name(e)
        usage_count[nm] = usage_count.get(nm, 0) + 1
    elif isinstance(e, (unreal.MaterialExpressionScalarParameter, unreal.MaterialExpressionVectorParameter)):
        params.append(str(e.get_editor_property("parameter_name")))
    elif isinstance(e, unreal.MaterialExpressionMaterialFunctionCall):
        mf_calls += 1
decl_names.sort()
usage_count = dict(sorted(usage_count.items()))
params.sort()
print(f"[TEST] {ASSET_NAME} decls: {decl_names}")
print(f"[TEST] {ASSET_NAME} usages: {usage_count}")
print(f"[TEST] {ASSET_NAME} params: {params}")
print(f"[TEST] {ASSET_NAME} MF calls: {mf_calls}")
expected_decls = sorted(["rho", "aa", "Radius", "Thickness", "Count", "Easing", "s", "th", "kIn", "kOut", "mask"])
expected_usages = {"rho": 3, "aa": 4, "Radius": 3, "Thickness": 2, "Count": 5, "Easing": 3, "s": 3, "th": 4,
                   "kIn": 1, "kOut": 1, "mask": 1}
expected_params = sorted(["Radius", "Thickness", "Count", "Easing", "Speed", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and len(smt.get_material_comment_texts(mat)) == 10
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
