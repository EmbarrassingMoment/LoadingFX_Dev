"""
Bouncing ball -> MF_SdEllipse2D + M_LoadingBounce (Material Domain = UI, Translucent)

ボールが床で弾み、着地している間だけ横に広がって縦につぶれるロードアイコン。床の上に、ボールが高いほど小さく薄くなる影を置く(1 色)。
デザインは 2026-10-11 のスピナー案第 2 弾から。プレビューは着地前後の空中でもつぶれていたので、1 サイクルを
「床にいる ContactFraction」と「飛んでいる残り」に分け、つぶれるのは床にいる間だけにした。clamp(x, 0, 1) は Saturate で書く。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  時間側(ピクセルに依存しないスカラー計算):
    u       = fract(Time * Speed)                   (Speed は 1 秒あたりの弾む回数。u = 0 が着地の瞬間)
    halfC   = ContactFraction / 2
    v       = saturate((u - halfC) / (1 - ContactFraction))   (飛んでいる間の進み 0..1。床にいる間は 0 か 1)
    hgt     = 1 - (2v - 1)^2                        (高さ 0..1。時間に対する放物線なので落下ほど速い。床では 0)
    squash  = Squash * (1 + cos(PI * saturate(min(u, 1 - u) / halfC))) / 2
                                                    (着地の瞬間に Squash、床を離れるときに 0)
    ballR   = BallRadius * (1 + squash, 1 - squash) (横に広がり縦につぶれる)
    cy      = Floor + ballR.y + BounceHeight * hgt  (ボールの中心。つぶれても下端は床に付いたまま)
  dBall   = sdEllipse(p - (0, cy), ballR)           (MF_SdEllipse2D、iq の楕円の近似距離)
  sw      = ShadowWidth * (1 - 0.5 * hgt)           (影の半幅。ボールが高いほど小さい)
  sh      = max(ShadowHeight, aa / 2)               (影の半分の高さ。1 ピクセルより薄くしない)
  dShadow = sdEllipse(p - (0, Floor - ShadowGap), (sw, sh))
  shadowFade = ShadowOpacity * (1 - 0.6 * hgt) * (ShadowHeight / sh)
                                                    (高いほど薄い。sh を太らせた分だけ濃さを下げる: 1 ピクセルより
                                                     薄い形は濃さ 0.5 の線になるので(M_LoadingTimer の教訓))
  mask    = max(saturate(0.5 - dBall / aa), saturate(0.5 - dShadow / aa) * shadowFade)

  デフォルトの外寸: 跳ねた頂点でボールの上端が Floor + BounceHeight + 2 * BallRadius = 0.72、影の下端が
  Floor - ShadowGap - ShadowHeight = -0.715(どちらも材質契約の基準正方形 0.72)。横はつぶれたボールと影で 0.26。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion に分ける(PARAM_GROUPS)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  BallRadius / Floor / ContactFraction / ShadowHeight(各 2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingbounce.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingBounce"
MF_NAME = "MF_SdEllipse2D"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_PATH = "/LoadingFX/MaterialFunctions"
MF_FULL_PATH = f"{MF_PATH}/{MF_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
PI = 3.14159265359
TAU = 6.28318530718
K1_EPSILON = 1e-5
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "ShadowOpacity": "Appearance",
    "BallRadius": "Shape",
    "Floor": "Shape",
    "BounceHeight": "Shape",
    "Squash": "Shape",
    "ShadowWidth": "Shape",
    "ShadowHeight": "Shape",
    "ShadowGap": "Shape",
    "Speed": "Motion",
    "ContactFraction": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / positions = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / height / squash = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # scalar intermediates / params / MF inputs = gray
C_COL = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)   # coverage / output = white

mf_coords = unreal.load_asset(MF_COORDS_PATH)
assert mf_coords, f"required Material Function not found: {MF_COORDS_PATH}"

# The material references the MF, so delete it first.
for path in (FULL_PATH, MF_FULL_PATH):
    if lib.does_asset_exist(path):
        lib.delete_asset(path)

results = []
def _connect(frm, out_name, to, in_name):
    ok = mel.connect_material_expressions(frm, out_name, to, in_name)
    if not ok:
        print(f"[TEST] FAILED connect: {frm.get_class().get_name()}('{out_name}') -> "
              f"{to.get_class().get_name()}('{in_name}')")
    results.append(ok)
    return ok

def vec4(x, y, z, w):
    v = unreal.Vector4f()
    v.set_editor_properties({"x": x, "y": y, "z": z, "w": w})
    return v

def mask_x(new, x, y):
    return new(unreal.MaterialExpressionComponentMask, x, y, r=True, g=False, b=False, a=False)

def mask_y(new, x, y):
    return new(unreal.MaterialExpressionComponentMask, x, y, r=False, g=True, b=False, a=False)

# ============================================================
#  MF_SdEllipse2D  (iq's ellipse approximation, guarded at the center)
#    float sdEllipse(vec2 p, vec2 r) {
#        float k0 = length(p / r);
#        float k1 = length(p / (r * r));
#        return (k0 - 1.0) * clamp(k0 / max(k1, 1e-5), min(r.x, r.y), max(r.x, r.y));
#    }
#  iq writes k0 * (k0 - 1) / k1. k0 / k1 always lies between the two radii, except at the exact center where it
#  is 0 / 0; the clamp makes the center read -min(r) instead of 0 (a half-covered pixel) and changes nothing else.
# ============================================================
fn = tools.create_asset(MF_NAME, MF_PATH, unreal.MaterialFunction, unreal.MaterialFunctionFactoryNew())
fn.set_editor_property("description",
    "Approximate signed distance to an axis-aligned ellipse centered at the origin (iq): "
    "k0 = length(P / R), k1 = length(P / (R * R)); returns (k0 - 1) * clamp(k0 / max(k1, 1e-5), min(R.x, R.y), "
    "max(R.x, R.y)). P = point relative to the center, R = the two radii. Exact sign, close to the true distance "
    "near the edge (good for anti-aliasing); not exact far away.")
fn.set_editor_property("expose_to_library", True)

def fnode(cls, x, y, **props):
    n = mel.create_material_expression_in_function(fn, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n

fdecls = {}
def fdecl(name, src, x, y, color):
    dcl = fnode(unreal.MaterialExpressionNamedRerouteDeclaration, x, y, name=name, node_color=color)
    _connect(src, "", dcl, "")
    fdecls[name] = dcl
    return dcl

def fuse(name, x, y):
    return smt.create_named_reroute_usage_in_function(fn, fdecls[name], x, y)

def finput(name, sort, preview, x, y):
    n = fnode(unreal.MaterialExpressionFunctionInput, x, y,
              input_name=name, input_type=unreal.FunctionInputType.FUNCTION_INPUT_VECTOR2,
              sort_priority=sort, preview_value=preview)
    fdecl(name, n, x + 200, y, C_SC)
    return n

finput("P", 0, vec4(0.0, 0.0, 0.0, 0.0), -1500, -200)
finput("R", 1, vec4(0.5, 0.25, 0.0, 0.0), -1500, 100)

# k0 = length(P / R)
p_fu1 = fuse("P", -1050, -300)
r_fu1 = fuse("R", -1050, -200)
p_over_r = fnode(unreal.MaterialExpressionDivide, -900, -250)
_connect(p_fu1, "", p_over_r, "A")
_connect(r_fu1, "", p_over_r, "B")
k0_len = fnode(unreal.MaterialExpressionLength, -750, -250)
_connect(p_over_r, "", k0_len, "")
fdecl("k0", k0_len, -600, -250, C_SDF)

# k1 = max(length(P / (R * R)), eps)
r_fu2 = fuse("R", -1050, -50)
r_sq = fnode(unreal.MaterialExpressionMultiply, -900, -50)
_connect(r_fu2, "", r_sq, "A")
_connect(r_fu2, "", r_sq, "B")
p_fu2 = fuse("P", -1050, 50)
p_over_r2 = fnode(unreal.MaterialExpressionDivide, -750, 0)
_connect(p_fu2, "", p_over_r2, "A")
_connect(r_sq, "", p_over_r2, "B")
k1_len = fnode(unreal.MaterialExpressionLength, -600, 0)
_connect(p_over_r2, "", k1_len, "")
k1_max = fnode(unreal.MaterialExpressionMax, -450, 0, const_b=K1_EPSILON)
_connect(k1_len, "", k1_max, "A")

# ratio = clamp(k0 / k1, min(R.x, R.y), max(R.x, R.y))
k0_fu1 = fuse("k0", -450, -100)
ratio = fnode(unreal.MaterialExpressionDivide, -300, -50)
_connect(k0_fu1, "", ratio, "A")
_connect(k1_max, "", ratio, "B")
r_fu3 = fuse("R", -750, 200)
r_x = mask_x(fnode, -600, 150)
_connect(r_fu3, "", r_x, "")
r_y = mask_y(fnode, -600, 250)
_connect(r_fu3, "", r_y, "")
r_lo = fnode(unreal.MaterialExpressionMin, -450, 150)
_connect(r_x, "", r_lo, "A")
_connect(r_y, "", r_lo, "B")
r_hi = fnode(unreal.MaterialExpressionMax, -450, 260)
_connect(r_x, "", r_hi, "A")
_connect(r_y, "", r_hi, "B")
ratio_c = fnode(unreal.MaterialExpressionClamp, -150, 50)
_connect(ratio, "", ratio_c, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
_connect(r_lo, "", ratio_c, "Min")
_connect(r_hi, "", ratio_c, "Max")

# Result = (k0 - 1) * ratio
k0_fu2 = fuse("k0", -150, -200)
k0_m1 = fnode(unreal.MaterialExpressionSubtract, 0, -200, const_b=1.0)
_connect(k0_fu2, "", k0_m1, "A")
res_n = fnode(unreal.MaterialExpressionMultiply, 150, -100)
_connect(k0_m1, "", res_n, "A")
_connect(ratio_c, "", res_n, "B")
f_out = fnode(unreal.MaterialExpressionFunctionOutput, 300, -100, output_name="Result")
_connect(res_n, "", f_out, "")

smt.create_comment_in_function(
    fn, "sdEllipse (iq's approximation)\n"
        "P is relative to the ellipse's center, R holds the two radii. k0 / k1 already lies between the "
        "radii; the clamp only fixes the exact center (0 / 0).",
    -1550, -400, 2000, 750, C_SDF)

mel.update_material_function(fn)
mf_saved = lib.save_asset(MF_FULL_PATH)
print(f"[TEST] Saved: {MF_FULL_PATH} -> {mf_saved}")

# ============================================================
#  M_LoadingBounce
# ============================================================
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

def append(a, b, x, y):
    n = expr(unreal.MaterialExpressionAppendVector, x, y)
    _connect(a, "", n, "A")
    _connect(b, "", n, "B")
    return n

def ellipse(p_node, r_node, x, y):
    n = expr(unreal.MaterialExpressionMaterialFunctionCall, x, y, material_function=fn)
    _connect(p_node, "", n, "P")
    _connect(r_node, "", n, "R")
    return n

def coverage(d_name, x, y):
    """saturate(0.5 - d / aa): 1px-wide anti-aliased coverage of the distance declared as d_name."""
    d_u = use(d_name, x, y - 50)
    aa_u = use("aa", x, y + 50)
    div = expr(unreal.MaterialExpressionDivide, x + 150, y)
    _connect(d_u, "", div, "A")
    _connect(aa_u, "", div, "B")
    half = expr(unreal.MaterialExpressionSubtract, x + 300, y, const_a=0.5)
    _connect(div, "", half, "B")
    sat = expr(unreal.MaterialExpressionSaturate, x + 450, y)
    _connect(half, "", sat, "")
    return sat

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3600, -700, material_function=mf_coords)
make_decl("p", coords, -3300, -750, C_UV, "P")
make_decl("aa", coords, -3300, -630, C_SDF, "PixelSize")

# ---- Shared parameters ----
# Footprint (material contract): Floor + BounceHeight + 2 * BallRadius = 0.72 at the top of the bounce, and
# Floor - ShadowGap - ShadowHeight = -0.715: both touch the reference square.
ballr_p = scalar_param("BallRadius", 0.2, 0, "Radius of the ball in the air (half the shorter widget side = 1.0)",
                       -3800, -400)
make_decl("BallRadius", ballr_p, -3550, -400, C_SC)
floor_p = scalar_param("Floor", -0.62, 1, "Height of the floor the ball lands on (y, center = 0, up is positive)",
                       -3800, -280)
make_decl("Floor", floor_p, -3550, -280, C_SC)
contact_p = scalar_param("ContactFraction", 0.12, 1,
                         "Share of a cycle the ball spends on the floor, squashed (0..1)", -3800, -160)
make_decl("ContactFraction", contact_p, -3550, -160, C_SC)
shadowh_p = scalar_param("ShadowHeight", 0.035, 5, "Half height of the shadow", -3800, -40)
make_decl("ShadowHeight", shadowh_p, -3550, -40, C_SC)

# ---- u = fract(Time * Speed);  halfC = ContactFraction / 2 ----
time_n = expr(unreal.MaterialExpressionTime, -3800, 300)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.9, 0, "Bounces per second", -3800, 420)
t_speed = expr(unreal.MaterialExpressionMultiply, -3600, 350)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
u_frac = expr(unreal.MaterialExpressionFrac, -3450, 350)
_connect(t_speed, "", u_frac, "")
make_decl("u", u_frac, -3300, 350, C_TM)
contact_u1 = use("ContactFraction", -3600, 550)
halfc_v = expr(unreal.MaterialExpressionMultiply, -3450, 550, const_b=0.5)
_connect(contact_u1, "", halfc_v, "A")
make_decl("halfC", halfc_v, -3300, 550, C_TM)

# ---- v = saturate((u - halfC) / (1 - ContactFraction));  hgt = 1 - (2v - 1)^2 ----
u_u1 = use("u", -3050, 250)
halfc_u1 = use("halfC", -3050, 350)
air_t = expr(unreal.MaterialExpressionSubtract, -2900, 300)
_connect(u_u1, "", air_t, "A")
_connect(halfc_u1, "", air_t, "B")
contact_u2 = use("ContactFraction", -3050, 450)
air_len = expr(unreal.MaterialExpressionOneMinus, -2900, 450)
_connect(contact_u2, "", air_len, "")
v_div = expr(unreal.MaterialExpressionDivide, -2750, 350)
_connect(air_t, "", v_div, "A")
_connect(air_len, "", v_div, "B")
v_sat = expr(unreal.MaterialExpressionSaturate, -2600, 350)
_connect(v_div, "", v_sat, "")
v2 = expr(unreal.MaterialExpressionMultiply, -2450, 350, const_b=2.0)
_connect(v_sat, "", v2, "A")
v2m1 = expr(unreal.MaterialExpressionSubtract, -2300, 350, const_b=1.0)
_connect(v2, "", v2m1, "A")
v_sq = expr(unreal.MaterialExpressionMultiply, -2150, 350)
_connect(v2m1, "", v_sq, "A")
_connect(v2m1, "", v_sq, "B")
hgt_v = expr(unreal.MaterialExpressionOneMinus, -2000, 350)
_connect(v_sq, "", hgt_v, "")
make_decl("hgt", hgt_v, -1850, 350, C_TM)

# ---- squash = Squash * (1 + cos(PI * saturate(min(u, 1 - u) / halfC))) / 2 ----
u_u2 = use("u", -3050, 650)
u_back = expr(unreal.MaterialExpressionOneMinus, -2900, 700)
_connect(u_u2, "", u_back, "")
to_land = expr(unreal.MaterialExpressionMin, -2750, 650)   # cycle distance to the landing moment (u = 0)
_connect(u_u2, "", to_land, "A")
_connect(u_back, "", to_land, "B")
halfc_u2 = use("halfC", -2750, 770)
land_div = expr(unreal.MaterialExpressionDivide, -2600, 700)
_connect(to_land, "", land_div, "A")
_connect(halfc_u2, "", land_div, "B")
land_sat = expr(unreal.MaterialExpressionSaturate, -2450, 700)
_connect(land_div, "", land_sat, "")
land_ang = expr(unreal.MaterialExpressionMultiply, -2300, 700, const_b=PI)
_connect(land_sat, "", land_ang, "A")
land_cos = expr(unreal.MaterialExpressionCosine, -2150, 700, period=TAU)   # period 2*PI = radians
_connect(land_ang, "", land_cos, "")
land_bump = expr(unreal.MaterialExpressionAdd, -2000, 700, const_b=1.0)
_connect(land_cos, "", land_bump, "A")
land_half = expr(unreal.MaterialExpressionMultiply, -1850, 700, const_b=0.5)
_connect(land_bump, "", land_half, "A")
squash_p = scalar_param("Squash", 0.3, 3,
                        "How much the ball flattens on landing (0 = never; 0.3 = 30% wider and 30% lower)",
                        -1850, 820)
squash_v = expr(unreal.MaterialExpressionMultiply, -1700, 750)
_connect(land_half, "", squash_v, "A")
_connect(squash_p, "", squash_v, "B")
make_decl("squash", squash_v, -1550, 750, C_TM)

# ---- ballR = BallRadius * (1 + squash, 1 - squash) ----
squash_u1 = use("squash", -1350, 650)
wide_v = expr(unreal.MaterialExpressionAdd, -1200, 650, const_a=1.0)
_connect(squash_u1, "", wide_v, "B")
squash_u2 = use("squash", -1350, 800)
low_v = expr(unreal.MaterialExpressionOneMinus, -1200, 800)
_connect(squash_u2, "", low_v, "")
ballr_u1 = use("BallRadius", -1200, 550)
rx_v = expr(unreal.MaterialExpressionMultiply, -1050, 600)
_connect(ballr_u1, "", rx_v, "A")
_connect(wide_v, "", rx_v, "B")
ballr_u2 = use("BallRadius", -1200, 900)
ry_v = expr(unreal.MaterialExpressionMultiply, -1050, 850)
_connect(ballr_u2, "", ry_v, "A")
_connect(low_v, "", ry_v, "B")
ballr_v = append(rx_v, ry_v, -900, 700)
make_decl("ballR", ballr_v, -750, 700, C_UV)

# ---- cy = Floor + ballR.y + BounceHeight * hgt;  dBall = sdEllipse(p - (0, cy), ballR) ----
floor_u1 = use("Floor", -1350, 100)
ballr_u3 = use("ballR", -1350, 200)
ry_comp = mask_y(expr, -1200, 200)
_connect(ballr_u3, "", ry_comp, "")
on_floor = expr(unreal.MaterialExpressionAdd, -1050, 150)   # center while the ball rests on the floor
_connect(floor_u1, "", on_floor, "A")
_connect(ry_comp, "", on_floor, "B")
bounce_p = scalar_param("BounceHeight", 0.94, 2, "How high the ball rises above its resting height", -1350, 300)
hgt_u1 = use("hgt", -1350, 400)
lift_v = expr(unreal.MaterialExpressionMultiply, -1200, 350)
_connect(bounce_p, "", lift_v, "A")
_connect(hgt_u1, "", lift_v, "B")
cy_v = expr(unreal.MaterialExpressionAdd, -900, 250)
_connect(on_floor, "", cy_v, "A")
_connect(lift_v, "", cy_v, "B")
ball_c = append(expr(unreal.MaterialExpressionConstant, -900, 130, r=0.0), cy_v, -750, 200)
p_u1 = use("p", -750, 80)
q_ball = expr(unreal.MaterialExpressionSubtract, -600, 150)
_connect(p_u1, "", q_ball, "A")
_connect(ball_c, "", q_ball, "B")
ballr_u4 = use("ballR", -600, 280)
dball_call = ellipse(q_ball, ballr_u4, -400, 200)
make_decl("dBall", dball_call, -150, 200, C_SDF)

# ---- Shadow: sw = ShadowWidth * (1 - 0.5 * hgt);  sh = max(ShadowHeight, aa / 2);
#      dShadow = sdEllipse(p - (0, Floor - ShadowGap), (sw, sh)) ----
hgt_u2 = use("hgt", -1350, -650)
sw_shrink = expr(unreal.MaterialExpressionMultiply, -1200, -650, const_b=-0.5)
_connect(hgt_u2, "", sw_shrink, "A")
sw_scale = expr(unreal.MaterialExpressionAdd, -1050, -650, const_b=1.0)
_connect(sw_shrink, "", sw_scale, "A")
shadoww_p = scalar_param("ShadowWidth", 0.26, 4, "Half width of the shadow while the ball is on the floor",
                         -1200, -770)
sw_v = expr(unreal.MaterialExpressionMultiply, -900, -700)
_connect(shadoww_p, "", sw_v, "A")
_connect(sw_scale, "", sw_v, "B")
shadowh_u1 = use("ShadowHeight", -1200, -500)
aa_u1 = use("aa", -1350, -400)
aa_half = expr(unreal.MaterialExpressionMultiply, -1200, -400, const_b=0.5)
_connect(aa_u1, "", aa_half, "A")
sh_v = expr(unreal.MaterialExpressionMax, -1050, -450)   # never thinner than one pixel in total
_connect(shadowh_u1, "", sh_v, "A")
_connect(aa_half, "", sh_v, "B")
make_decl("sh", sh_v, -900, -450, C_SDF)
sh_u1 = use("sh", -900, -580)
shadow_r = append(sw_v, sh_u1, -750, -650)
floor_u2 = use("Floor", -1050, -250)
gap_p = scalar_param("ShadowGap", 0.06, 6, "How far below the floor the shadow's center lies", -1050, -150)
shadow_y = expr(unreal.MaterialExpressionSubtract, -900, -200)
_connect(floor_u2, "", shadow_y, "A")
_connect(gap_p, "", shadow_y, "B")
shadow_c = append(expr(unreal.MaterialExpressionConstant, -900, -300, r=0.0), shadow_y, -750, -250)
p_u2 = use("p", -750, -380)
q_shadow = expr(unreal.MaterialExpressionSubtract, -600, -320)
_connect(p_u2, "", q_shadow, "A")
_connect(shadow_c, "", q_shadow, "B")
dshadow_call = ellipse(q_shadow, shadow_r, -400, -450)
make_decl("dShadow", dshadow_call, -150, -450, C_SDF)

# ---- shadowFade = ShadowOpacity * (1 - 0.6 * hgt) * (ShadowHeight / sh) ----
hgt_u3 = use("hgt", -700, -1000)
fade_h = expr(unreal.MaterialExpressionMultiply, -550, -1000, const_b=-0.6)
_connect(hgt_u3, "", fade_h, "A")
fade_hv = expr(unreal.MaterialExpressionAdd, -400, -1000, const_b=1.0)
_connect(fade_h, "", fade_hv, "A")
shadowo_p = scalar_param("ShadowOpacity", 0.35, 1, "Opacity of the shadow while the ball is on the floor (0 hides it)",
                         -550, -1120)
fade_o = expr(unreal.MaterialExpressionMultiply, -250, -1050)
_connect(shadowo_p, "", fade_o, "A")
_connect(fade_hv, "", fade_o, "B")
shadowh_u2 = use("ShadowHeight", -550, -850)
sh_u2 = use("sh", -550, -750)
thin_ratio = expr(unreal.MaterialExpressionDivide, -400, -800)
_connect(shadowh_u2, "", thin_ratio, "A")
_connect(sh_u2, "", thin_ratio, "B")
fade_v = expr(unreal.MaterialExpressionMultiply, -100, -950)
_connect(fade_o, "", fade_v, "A")
_connect(thin_ratio, "", fade_v, "B")
make_decl("shadowFade", fade_v, 50, -950, C_COL)

# ---- mask = max(saturate(0.5 - dBall / aa), saturate(0.5 - dShadow / aa) * shadowFade) ----
ball_cov = coverage("dBall", 350, 200)
shadow_cov = coverage("dShadow", 350, -450)
fade_u1 = use("shadowFade", 800, -330)
shadow_v = expr(unreal.MaterialExpressionMultiply, 950, -400)
_connect(shadow_cov, "", shadow_v, "A")
_connect(fade_u1, "", shadow_v, "B")
mask_max = expr(unreal.MaterialExpressionMax, 1100, -100)
_connect(ball_cov, "", mask_max, "A")
_connect(shadow_v, "", mask_max, "B")
make_decl("mask", mask_max, 1250, -100, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 1450, -250,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Color of the ball and its shadow (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 1450, 0)
emissive = expr(unreal.MaterialExpressionMultiply, 1700, -200)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 1450, 200)
cov_a = expr(unreal.MaterialExpressionMultiply, 1700, 150)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 1850, 100)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

smt.set_material_root_position(mat, 2110, -220)

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "By default the ball's top reaches 0.72 and the shadow's bottom -0.715: the outer size shared by the "
         "square layouts.",
    -3850, -520, 600, 600, C_SC)
smt.create_comment_in_material(
    mat, "Bounce timing\n"
         "Each cycle splits into ContactFraction on the floor and the flight. The height is a parabola in "
         "time, fastest near the floor, and the ball only flattens while it touches the floor.\n"
         "Time has Ignore Pause on (real time), so the ball keeps bouncing while the game thread is blocked.",
    -3850, 150, 2450, 800, C_TM)
smt.create_comment_in_material(
    mat, "Ball\n"
         "The bottom of the ball stays on the floor while it is squashed.",
    -1400, 4, 1450, 966, C_SDF)
smt.create_comment_in_material(
    mat, "Shadow\n"
         "It shrinks and fades as the ball rises. It stays at least one pixel thick and loses opacity in "
         "proportion, because a thinner shape would show at half coverage.",
    -1400, -1228, 1650, 1168, C_SDF)

used_groups = [g for g in GROUP_ORDER if g in PARAM_GROUPS.values()]
smt.set_parameter_group_sort_priorities(mat, used_groups, list(range(len(used_groups))))

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
def audit(exprs):
    decl_names, usage_count, params, mf_calls, param_groups = [], {}, [], 0, {}
    for e in exprs:
        if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
            decl_names.append(str(e.get_editor_property("name")))
        elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
            nm = smt.get_named_reroute_usage_display_name(e)
            usage_count[nm] = usage_count.get(nm, 0) + 1
        elif isinstance(e, (unreal.MaterialExpressionScalarParameter,
                            unreal.MaterialExpressionVectorParameter)):
            name = str(e.get_editor_property("parameter_name"))
            params.append(name)
            param_groups[name] = str(e.get_editor_property("group"))
        elif isinstance(e, unreal.MaterialExpressionMaterialFunctionCall):
            mf_calls += 1
    return sorted(decl_names), dict(sorted(usage_count.items())), sorted(params), mf_calls, param_groups

f_decls, f_usages, _, _, _ = audit(smt.get_material_function_expressions(fn))
print(f"[TEST] {MF_NAME} decls: {f_decls}")
print(f"[TEST] {MF_NAME} usages: {f_usages}")
mf_ok = (f_decls == ["P", "R", "k0"]
         and f_usages == {"P": 2, "R": 3, "k0": 2}
         and len(smt.get_function_comment_texts(fn)) == 1
         and mf_saved)

m_decls, m_usages, m_params, m_calls, param_groups = audit(smt.get_material_expressions(mat))
group_prios = dict(smt.get_parameter_group_sort_priorities(mat))
expected_prios = {g: i for i, g in enumerate(used_groups)}
print(f"[TEST] {ASSET_NAME} decls: {m_decls}")
print(f"[TEST] {ASSET_NAME} usages: {m_usages}")
print(f"[TEST] {ASSET_NAME} params: {m_params}")
print(f"[TEST] {ASSET_NAME} groups: {param_groups} order: {group_prios}")
print(f"[TEST] {ASSET_NAME} MF calls: {m_calls}")
expected_decls = sorted(["p", "aa", "BallRadius", "Floor", "ContactFraction", "ShadowHeight", "u", "halfC", "hgt",
                         "squash", "ballR", "dBall", "sh", "dShadow", "shadowFade", "mask"])
expected_usages = {"p": 2, "aa": 3, "BallRadius": 2, "Floor": 2, "ContactFraction": 2, "ShadowHeight": 2, "u": 2,
                   "halfC": 2, "hgt": 3, "squash": 2, "ballR": 2, "dBall": 1, "sh": 2, "dShadow": 1,
                   "shadowFade": 1, "mask": 1}
expected_params = sorted(["BallRadius", "Floor", "BounceHeight", "Squash", "ContactFraction", "ShadowWidth",
                          "ShadowHeight", "ShadowGap", "ShadowOpacity", "Speed", "PrimaryColor"])
mat_ok = (m_decls == expected_decls and m_usages == dict(sorted(expected_usages.items()))
          and m_params == expected_params and m_calls == 3
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 4
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {MF_NAME}: {'OK' if mf_ok else 'NG'} / {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mf_ok and mat_ok else "FAIL"))
