"""
Hourglass -> MF_SdSegment2D + M_LoadingHourglass (Material Domain = UI, Translucent)

砂が上の部屋から下の部屋へ落ちきると、ガラスが時計回りに半回転してひっくり返り、また落ち始めるロードアイコン(1 色)。
デザインは 2026-10-11 のスピナー案第 2 弾から。2026-10-12 に同じ式の GLSL(Shadertoy 形式)を WebGL2 でコンパイル・描画して
ユーザーと確認した。clamp(x, 0, 1) はすべて Saturate で書く(2026-10-12 ユーザー指示)。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  時間側(ピクセルに依存しないスカラー計算):
    u        = fract(Time * Speed)                  (Speed は 1 サイクル(落ちる + ひっくり返る)/秒、正 = 時計回り)
    flowEnd  = 1 - FlipFraction                     (砂が落ちている区間の終わり)
    flow     = saturate(u / flowEnd)                (下の部屋にある砂の割合 0..1)
    turn     = smoothstep(flowEnd, 1, u)            (ひっくり返る間に 0 -> 1)
    c, s     = cos(PI * turn), sin(PI * turn)       (半回転、時計回り)
    scale    = 1 - FlipShrink * s                   (横倒しの瞬間がいちばん小さい)
  q      = (c*p.x - s*p.y, s*p.x + c*p.y) / scale   (ピクセルを逆に回す = ガラスが時計回りに回る。縮みも戻す)
  aaQ    = aa / scale                               (q での距離は p の距離 / scale なので、AA 幅も aa / scale)
  f      = abs(q)                                   (ガラスは上下左右対称なので両軸を折り返す)
  dGlass = min(sdSegment(f, (Neck, 0), (HalfWidth, HalfHeight)),
               sdSegment(f, (0, HalfHeight), (HalfWidth + CapExtra, HalfHeight))) - Thickness / 2
                                                    (斜めの辺 1 本と蓋 1 本。sdSegment は MF_SdSegment2D)
  inset  = Thickness / 2 + SandGap
  outward = normalize((HalfHeight, Neck - HalfWidth))   (右の斜めの辺の外向き法線。v / length(v))
  dChamber = max(dot(f - (Neck, 0), outward), f.y - HalfHeight) + inset
                                                    (ガラスの内側を SandGap だけ離した部屋。半平面 2 枚)
  level  = (HalfHeight - inset) * sqrt(1 - flow)    (部屋はほぼ三角形なので、高さ y より下の砂は y^2 に比例し、
                                                     上の砂の高さと下の砂の表面が同じ値になる)
  dSand  = min(max(dChamber, q.y - level, -q.y),    (上の部屋: くびれから +level まで)
               max(dChamber, q.y + level))          (下の部屋: 蓋から -level まで)
  wStream = max(StreamWidth, aaQ)
  dStream = sdSegment(q, (0, 0), (0, -level)) - wStream / 2
  streamFade = (StreamWidth / wStream) * (1 - step(1, flow))
                                                    (落ちる砂の線は 1 ピクセル未満なら 1 ピクセルの太さで描いて濃さを下げる。
                                                     そのまま描くと M_LoadingTimer の細い線と同じく濃さ 0.5 になる。
                                                     上に砂が残っている間だけ描く)
  mask   = max(saturate(0.5 - dGlass / aaQ), saturate(0.5 - dSand / aaQ),
               saturate(0.5 - dStream / aaQ) * streamFade)

  デフォルトの外寸: 止まっているときは HalfHeight + Thickness/2 = 0.72(材質契約の基準正方形)。そのまま回すと 45° で
  蓋の角が x / y 方向に 0.946 まで出るので、FlipShrink = 0.3 で縮め、回転中の max(|x|, |y|) を 0.794 に抑える
  (基準正方形 0.72 と基準円 0.8 の間。半径ではないので、蓋の角は止まっているときと同じく基準円の外に出る)。
  単純化: 砂の表面は平ら。部屋を三角形とみなすので、上の砂は計算上の終わりより 2% ほど早く空になる。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。

  ScalarParameter / VectorParameter はグループ "LoadingHourglass"。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  HalfHeight(6 箇所)、HalfWidth(3 箇所)、Neck(2 箇所)、StreamWidth(2 箇所)、Thickness / 2(2 箇所)は
  Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadinghourglass.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingHourglass"
MF_NAME = "MF_SdSegment2D"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_PATH = "/LoadingFX/MaterialFunctions"
MF_FULL_PATH = f"{MF_PATH}/{MF_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
PI = 3.14159265359
TAU = 6.28318530718
PARAM_GROUP = "LoadingHourglass"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / rotation = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / flow / flip = light blue
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
#  MF_SdSegment2D
#    float sdSegment(vec2 p, vec2 a, vec2 b) {
#        vec2 pa = p - a, ba = b - a;
#        float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
#        return length(pa - ba * h);
#    }
# ============================================================
fn = tools.create_asset(MF_NAME, MF_PATH, unreal.MaterialFunction, unreal.MaterialFunctionFactoryNew())
fn.set_editor_property("description",
    "Distance from P to the 2D segment A-B (iq's sdSegment): h = saturate(dot(P - A, B - A) / dot(B - A, B - A)); "
    "returns length(P - A - (B - A) * h). Always >= 0; subtract half a stroke width for a capsule.")
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
finput("A", 1, vec4(0.0, 0.0, 0.0, 0.0), -1500, 0)
finput("B", 2, vec4(0.5, 0.0, 0.0, 0.0), -1500, 200)

# pa = P - A, ba = B - A
p_fu = fuse("P", -1050, -250)
a_fu1 = fuse("A", -1050, -150)
pa_v = fnode(unreal.MaterialExpressionSubtract, -900, -200)
_connect(p_fu, "", pa_v, "A")
_connect(a_fu1, "", pa_v, "B")
fdecl("pa", pa_v, -750, -200, C_SDF)
b_fu = fuse("B", -1050, 50)
a_fu2 = fuse("A", -1050, 150)
ba_v = fnode(unreal.MaterialExpressionSubtract, -900, 100)
_connect(b_fu, "", ba_v, "A")
_connect(a_fu2, "", ba_v, "B")
fdecl("ba", ba_v, -750, 100, C_SDF)

# h = saturate(dot(pa, ba) / dot(ba, ba))
pa_fu1 = fuse("pa", -500, -250)
ba_fu1 = fuse("ba", -500, -150)
dot_pb = fnode(unreal.MaterialExpressionDotProduct, -350, -200)
_connect(pa_fu1, "", dot_pb, "A")
_connect(ba_fu1, "", dot_pb, "B")
ba_fu2 = fuse("ba", -500, 0)
dot_bb = fnode(unreal.MaterialExpressionDotProduct, -350, 0)
_connect(ba_fu2, "", dot_bb, "A")
_connect(ba_fu2, "", dot_bb, "B")
h_div = fnode(unreal.MaterialExpressionDivide, -200, -100)
_connect(dot_pb, "", h_div, "A")
_connect(dot_bb, "", h_div, "B")
h_sat = fnode(unreal.MaterialExpressionSaturate, -50, -100)
_connect(h_div, "", h_sat, "")

# Result = length(pa - ba * h)
ba_fu3 = fuse("ba", -50, 50)
ba_h = fnode(unreal.MaterialExpressionMultiply, 100, 0)
_connect(ba_fu3, "", ba_h, "A")
_connect(h_sat, "", ba_h, "B")
pa_fu2 = fuse("pa", 100, -150)
to_seg = fnode(unreal.MaterialExpressionSubtract, 250, -100)
_connect(pa_fu2, "", to_seg, "A")
_connect(ba_h, "", to_seg, "B")
seg_len = fnode(unreal.MaterialExpressionLength, 400, -100)
_connect(to_seg, "", seg_len, "")
f_out = fnode(unreal.MaterialExpressionFunctionOutput, 550, -100, output_name="Result")
_connect(seg_len, "", f_out, "")

smt.create_comment_in_function(
    fn, "Inputs -> Named Reroute (P, A, B)\n"
        "P = point, A and B = the segment's ends (all vec2)",
    -1550, -320, 750, 650, C_SC)
smt.create_comment_in_function(
    fn, "iq's sdSegment: pa = P - A, ba = B - A;  h = saturate(dot(pa, ba) / dot(ba, ba))\n"
        "Result = length(pa - ba * h)   (distance to the nearest point of the segment, >= 0)",
    -1100, -370, 1700, 650, C_SDF)

mel.update_material_function(fn)
mf_saved = lib.save_asset(MF_FULL_PATH)
print(f"[TEST] Saved: {MF_FULL_PATH} -> {mf_saved}")

# ============================================================
#  M_LoadingHourglass
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
                parameter_name=name, default_value=default, group=PARAM_GROUP,
                sort_priority=sort, desc=desc)

def const(value, x, y):
    return expr(unreal.MaterialExpressionConstant, x, y, r=value)

def append(a, b, x, y):
    n = expr(unreal.MaterialExpressionAppendVector, x, y)
    _connect(a, "", n, "A")
    _connect(b, "", n, "B")
    return n

def segment(p_node, a_node, b_node, x, y):
    n = expr(unreal.MaterialExpressionMaterialFunctionCall, x, y, material_function=fn)
    _connect(p_node, "", n, "P")
    _connect(a_node, "", n, "A")
    _connect(b_node, "", n, "B")
    return n

def coverage(d_name, x, y):
    """saturate(0.5 - d / aaQ): 1px-wide anti-aliased coverage of the distance declared as d_name."""
    d_u = use(d_name, x, y - 50)
    aa_u = use("aaQ", x, y + 50)
    div = expr(unreal.MaterialExpressionDivide, x + 150, y)
    _connect(d_u, "", div, "A")
    _connect(aa_u, "", div, "B")
    half = expr(unreal.MaterialExpressionSubtract, x + 300, y, const_a=0.5)
    _connect(div, "", half, "B")
    sat = expr(unreal.MaterialExpressionSaturate, x + 450, y)
    _connect(half, "", sat, "")
    return sat

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -4300, -700, material_function=mf_coords)
make_decl("p", coords, -4000, -750, C_UV, "P")
make_decl("aa", coords, -4000, -630, C_SDF, "PixelSize")

# ---- Shared parameters ----
# Footprint (material contract): HalfHeight + Thickness / 2 = 0.72, the reference square, at rest.
hh_p = scalar_param("HalfHeight", 0.685, 0,
                    "Height of the caps above and below the center (half the shorter widget side = 1.0)",
                    -4550, -400)
make_decl("HalfHeight", hh_p, -4300, -400, C_SC)
hw_p = scalar_param("HalfWidth", 0.5, 1, "Half width of a bulb at its cap", -4550, -280)
make_decl("HalfWidth", hw_p, -4300, -280, C_SC)
neck_p = scalar_param("Neck", 0.07, 2,
                      "Half width of the waist. Keep it well above Thickness / 2, or the sides meet in an X",
                      -4550, -160)
make_decl("Neck", neck_p, -4300, -160, C_SC)
thick_p = scalar_param("Thickness", 0.07, 4, "Stroke width of the glass", -4550, -40)
thick_half = expr(unreal.MaterialExpressionMultiply, -4350, -40, const_b=0.5)
_connect(thick_p, "", thick_half, "A")
make_decl("halfT", thick_half, -4200, -40, C_SC)

# ---- u = fract(Time * Speed);  flowEnd = 1 - FlipFraction;  flow = saturate(u / flowEnd) ----
time_n = expr(unreal.MaterialExpressionTime, -4550, 850)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.35, 7,
                       "Cycles per second (the sand runs out, then the glass turns over). Positive = turns clockwise",
                       -4550, 970)
t_speed = expr(unreal.MaterialExpressionMultiply, -4350, 900)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
u_frac = expr(unreal.MaterialExpressionFrac, -4200, 900)
_connect(t_speed, "", u_frac, "")
make_decl("u", u_frac, -4050, 900, C_TM)
flipf_p = scalar_param("FlipFraction", 0.2, 8, "Share of a cycle spent turning over (0..1)", -4550, 1100)
flow_end = expr(unreal.MaterialExpressionOneMinus, -4350, 1100)
_connect(flipf_p, "", flow_end, "")
make_decl("flowEnd", flow_end, -4200, 1100, C_TM)
u_u1 = use("u", -3800, 850)
flowend_u1 = use("flowEnd", -3800, 950)
flow_div = expr(unreal.MaterialExpressionDivide, -3650, 900)
_connect(u_u1, "", flow_div, "A")
_connect(flowend_u1, "", flow_div, "B")
flow_sat = expr(unreal.MaterialExpressionSaturate, -3500, 900)
_connect(flow_div, "", flow_sat, "")
make_decl("flow", flow_sat, -3350, 900, C_TM)

# ---- turn = smoothstep(flowEnd, 1, u);  c, s = cos / sin(PI * turn);  scale = 1 - FlipShrink * s ----
u_u2 = use("u", -3800, 1150)
flowend_u2 = use("flowEnd", -3800, 1250)
turn_ss = expr(unreal.MaterialExpressionSmoothStep, -3650, 1200, const_max=1.0)
_connect(flowend_u2, "", turn_ss, "Min")
_connect(u_u2, "", turn_ss, "Value")
ang_v = expr(unreal.MaterialExpressionMultiply, -3500, 1200, const_b=PI)   # half a turn, clockwise
_connect(turn_ss, "", ang_v, "A")
ang_cos = expr(unreal.MaterialExpressionCosine, -3350, 1150, period=TAU)   # period 2*PI = radians
_connect(ang_v, "", ang_cos, "")
make_decl("c", ang_cos, -3200, 1150, C_UV)
ang_sin = expr(unreal.MaterialExpressionSine, -3350, 1270, period=TAU)
_connect(ang_v, "", ang_sin, "")
make_decl("s", ang_sin, -3200, 1270, C_UV)
s_u1 = use("s", -3050, 1250)
shrink_p = scalar_param("FlipShrink", 0.3, 9,
                        "Shrink at the sideways moment, so the turning glass stays close to its resting size",
                        -3050, 1350)
shrink_v = expr(unreal.MaterialExpressionMultiply, -2900, 1300)
_connect(s_u1, "", shrink_v, "A")
_connect(shrink_p, "", shrink_v, "B")
scale_v = expr(unreal.MaterialExpressionOneMinus, -2750, 1300)
_connect(shrink_v, "", scale_v, "")
make_decl("scale", scale_v, -2600, 1300, C_TM)

# ---- q = (c*p.x - s*p.y, s*p.x + c*p.y) / scale;  aaQ = aa / scale;  f = abs(q) ----
c_u1 = use("c", -3300, -550)
s_u2 = use("s", -3300, -450)
s_neg = expr(unreal.MaterialExpressionMultiply, -3150, -450, const_b=-1.0)
_connect(s_u2, "", s_neg, "A")
row_x = append(c_u1, s_neg, -3000, -500)    # (c, -s)
s_u3 = use("s", -3300, -300)
c_u2 = use("c", -3300, -200)
row_y = append(s_u3, c_u2, -3000, -250)     # (s, c)
p_u1 = use("p", -2850, -600)
q_x = expr(unreal.MaterialExpressionDotProduct, -2700, -550)
_connect(p_u1, "", q_x, "A")
_connect(row_x, "", q_x, "B")
p_u2 = use("p", -2850, -300)
q_y = expr(unreal.MaterialExpressionDotProduct, -2700, -250)
_connect(p_u2, "", q_y, "A")
_connect(row_y, "", q_y, "B")
q_rot = append(q_x, q_y, -2550, -400)
scale_u1 = use("scale", -2550, -280)
q_div = expr(unreal.MaterialExpressionDivide, -2400, -350)
_connect(q_rot, "", q_div, "A")
_connect(scale_u1, "", q_div, "B")
make_decl("q", q_div, -2250, -350, C_UV)
aa_u1 = use("aa", -2550, -100)
scale_u2 = use("scale", -2550, 0)
aaq_div = expr(unreal.MaterialExpressionDivide, -2400, -50)
_connect(aa_u1, "", aaq_div, "A")
_connect(scale_u2, "", aaq_div, "B")
make_decl("aaQ", aaq_div, -2250, -50, C_SDF)
q_u1 = use("q", -2050, -350)
f_abs = expr(unreal.MaterialExpressionAbs, -1900, -350)
_connect(q_u1, "", f_abs, "")
make_decl("f", f_abs, -1750, -350, C_UV)

# ---- dGlass = min(sdSegment(f, (Neck, 0), (HalfWidth, HalfHeight)),
#                   sdSegment(f, (0, HalfHeight), (HalfWidth + CapExtra, HalfHeight))) - Thickness / 2 ----
neck_u1 = use("Neck", -1500, -1450)
neck_pt = append(neck_u1, const(0.0, -1500, -1350), -1350, -1400)
make_decl("neckPt", neck_pt, -1200, -1400, C_UV)
f_u1 = use("f", -1000, -1500)
neckpt_u1 = use("neckPt", -1000, -1400)
hw_u1 = use("HalfWidth", -1150, -1300)
hh_u1 = use("HalfHeight", -1150, -1200)
side_end = append(hw_u1, hh_u1, -1000, -1250)
seg_side = segment(f_u1, neckpt_u1, side_end, -800, -1400)
hh_u2 = use("HalfHeight", -1150, -1050)
cap_start = append(const(0.0, -1150, -1130), hh_u2, -1000, -1080)
hw_u2 = use("HalfWidth", -1450, -950)
capx_p = scalar_param("CapExtra", 0.1, 3, "How far the caps reach past the glass on each side", -1450, -850)
cap_x = expr(unreal.MaterialExpressionAdd, -1300, -900)
_connect(hw_u2, "", cap_x, "A")
_connect(capx_p, "", cap_x, "B")
hh_u3 = use("HalfHeight", -1150, -800)
cap_end = append(cap_x, hh_u3, -1000, -850)
f_u2 = use("f", -1000, -1180)
seg_cap = segment(f_u2, cap_start, cap_end, -800, -1000)
glass_min = expr(unreal.MaterialExpressionMin, -600, -1200)
_connect(seg_side, "", glass_min, "A")
_connect(seg_cap, "", glass_min, "B")
halft_u1 = use("halfT", -600, -1080)
dglass_v = expr(unreal.MaterialExpressionSubtract, -450, -1150)
_connect(glass_min, "", dglass_v, "A")
_connect(halft_u1, "", dglass_v, "B")
make_decl("dGlass", dglass_v, -300, -1150, C_SDF)

# ---- inset = Thickness / 2 + SandGap;  outward = normalize((HalfHeight, Neck - HalfWidth)) ----
halft_u2 = use("halfT", -1500, -650)
sandgap_p = scalar_param("SandGap", 0.05, 5, "Space between the glass stroke and the sand", -1500, -550)
inset_v = expr(unreal.MaterialExpressionAdd, -1350, -600)
_connect(halft_u2, "", inset_v, "A")
_connect(sandgap_p, "", inset_v, "B")
make_decl("inset", inset_v, -1200, -600, C_SC)
hh_u4 = use("HalfHeight", -1650, -350)
neck_u2 = use("Neck", -1650, -250)
hw_u3 = use("HalfWidth", -1650, -150)
slope_v = expr(unreal.MaterialExpressionSubtract, -1500, -200)
_connect(neck_u2, "", slope_v, "A")
_connect(hw_u3, "", slope_v, "B")
side_vec = append(hh_u4, slope_v, -1350, -280)
side_len = expr(unreal.MaterialExpressionLength, -1200, -220)
_connect(side_vec, "", side_len, "")
outward = expr(unreal.MaterialExpressionDivide, -1050, -280)   # normalize: v / length(v)
_connect(side_vec, "", outward, "A")
_connect(side_len, "", outward, "B")

# ---- dChamber = max(dot(f - (Neck, 0), outward), f.y - HalfHeight) + inset ----
f_u3 = use("f", -1050, -500)
neckpt_u2 = use("neckPt", -1050, -420)
from_neck = expr(unreal.MaterialExpressionSubtract, -900, -460)
_connect(f_u3, "", from_neck, "A")
_connect(neckpt_u2, "", from_neck, "B")
side_d = expr(unreal.MaterialExpressionDotProduct, -750, -380)
_connect(from_neck, "", side_d, "A")
_connect(outward, "", side_d, "B")
f_u4 = use("f", -1050, -100)
f_y = mask_y(expr, -900, -100)
_connect(f_u4, "", f_y, "")
hh_u5 = use("HalfHeight", -900, 0)
cap_d = expr(unreal.MaterialExpressionSubtract, -750, -50)
_connect(f_y, "", cap_d, "A")
_connect(hh_u5, "", cap_d, "B")
chamber_max = expr(unreal.MaterialExpressionMax, -600, -250)
_connect(side_d, "", chamber_max, "A")
_connect(cap_d, "", chamber_max, "B")
inset_u1 = use("inset", -600, -130)
dchamber_v = expr(unreal.MaterialExpressionAdd, -450, -200)
_connect(chamber_max, "", dchamber_v, "A")
_connect(inset_u1, "", dchamber_v, "B")
make_decl("dChamber", dchamber_v, -300, -200, C_SDF)

# ---- level = (HalfHeight - inset) * sqrt(1 - flow) ----
hh_u6 = use("HalfHeight", -1500, 200)
inset_u2 = use("inset", -1500, 300)
room_h = expr(unreal.MaterialExpressionSubtract, -1350, 250)
_connect(hh_u6, "", room_h, "A")
_connect(inset_u2, "", room_h, "B")
flow_u1 = use("flow", -1500, 420)
left_v = expr(unreal.MaterialExpressionOneMinus, -1350, 420)
_connect(flow_u1, "", left_v, "")
left_sqrt = expr(unreal.MaterialExpressionSquareRoot, -1200, 420)
_connect(left_v, "", left_sqrt, "")
level_v = expr(unreal.MaterialExpressionMultiply, -1050, 300)
_connect(room_h, "", level_v, "A")
_connect(left_sqrt, "", level_v, "B")
make_decl("level", level_v, -900, 300, C_TM)

# ---- dSand = min(max(dChamber, q.y - level, -q.y), max(dChamber, q.y + level)) ----
q_u2 = use("q", -700, 150)
q_ycomp = mask_y(expr, -550, 150)
_connect(q_u2, "", q_ycomp, "")
level_u1 = use("level", -550, 250)
top_surf = expr(unreal.MaterialExpressionSubtract, -400, 200)   # below the top bulb's surface
_connect(q_ycomp, "", top_surf, "A")
_connect(level_u1, "", top_surf, "B")
above_neck = expr(unreal.MaterialExpressionMultiply, -400, 100, const_b=-1.0)   # in the top bulb
_connect(q_ycomp, "", above_neck, "A")
top_band = expr(unreal.MaterialExpressionMax, -250, 150)
_connect(top_surf, "", top_band, "A")
_connect(above_neck, "", top_band, "B")
dchamber_u1 = use("dChamber", -250, 50)
d_top = expr(unreal.MaterialExpressionMax, -100, 100)
_connect(dchamber_u1, "", d_top, "A")
_connect(top_band, "", d_top, "B")
level_u2 = use("level", -550, 400)
bottom_surf = expr(unreal.MaterialExpressionAdd, -400, 380)    # below the bottom bulb's surface
_connect(q_ycomp, "", bottom_surf, "A")
_connect(level_u2, "", bottom_surf, "B")
dchamber_u2 = use("dChamber", -400, 480)
d_bottom = expr(unreal.MaterialExpressionMax, -250, 430)
_connect(dchamber_u2, "", d_bottom, "A")
_connect(bottom_surf, "", d_bottom, "B")
dsand_v = expr(unreal.MaterialExpressionMin, 50, 250)
_connect(d_top, "", dsand_v, "A")
_connect(d_bottom, "", dsand_v, "B")
make_decl("dSand", dsand_v, 200, 250, C_SDF)

# ---- wStream = max(StreamWidth, aaQ);  dStream = sdSegment(q, (0, 0), (0, -level)) - wStream / 2 ----
streamw_p = scalar_param("StreamWidth", 0.02, 6, "Width of the falling sand", -1500, 1000)
make_decl("StreamWidth", streamw_p, -1250, 1000, C_SC)
sw_u1 = use("StreamWidth", -1000, 850)
aaq_u1 = use("aaQ", -1000, 950)
wstream_v = expr(unreal.MaterialExpressionMax, -850, 900)
_connect(sw_u1, "", wstream_v, "A")
_connect(aaq_u1, "", wstream_v, "B")
make_decl("wStream", wstream_v, -700, 900, C_SDF)
neck_center = expr(unreal.MaterialExpressionConstant2Vector, -700, 1100, r=0.0, g=0.0)
level_u3 = use("level", -1000, 1250)
level_neg = expr(unreal.MaterialExpressionMultiply, -850, 1250, const_b=-1.0)
_connect(level_u3, "", level_neg, "A")
stream_end = append(const(0.0, -850, 1170), level_neg, -700, 1200)
q_u3 = use("q", -700, 1020)
seg_stream = segment(q_u3, neck_center, stream_end, -500, 1100)
ws_u1 = use("wStream", -500, 1250)
ws_half = expr(unreal.MaterialExpressionMultiply, -350, 1250, const_b=0.5)
_connect(ws_u1, "", ws_half, "A")
dstream_v = expr(unreal.MaterialExpressionSubtract, -200, 1150)
_connect(seg_stream, "", dstream_v, "A")
_connect(ws_half, "", dstream_v, "B")
make_decl("dStream", dstream_v, -50, 1150, C_SDF)

# ---- streamFade = (StreamWidth / wStream) * (1 - step(1, flow))  (thin-line opacity, only while sand runs) ----
flow_u2 = use("flow", -500, 1450)
# UE Step(Y, X) returns 1 when X >= Y, i.e. GLSL step(edge=Y, x=X): 1 once all the sand is down.
ran_out = expr(unreal.MaterialExpressionStep, -350, 1450, const_y=1.0)
_connect(flow_u2, "", ran_out, "X")
running = expr(unreal.MaterialExpressionOneMinus, -200, 1450)
_connect(ran_out, "", running, "")
sw_u2 = use("StreamWidth", -500, 1600)
ws_u2 = use("wStream", -500, 1700)
thin_ratio = expr(unreal.MaterialExpressionDivide, -350, 1650)
_connect(sw_u2, "", thin_ratio, "A")
_connect(ws_u2, "", thin_ratio, "B")
stream_fade = expr(unreal.MaterialExpressionMultiply, -200, 1550)
_connect(running, "", stream_fade, "A")
_connect(thin_ratio, "", stream_fade, "B")
make_decl("streamFade", stream_fade, -50, 1550, C_COL)

# ---- mask = max(glass, sand, stream * streamFade), each saturate(0.5 - d / aaQ) ----
glass_cov = coverage("dGlass", 1200, -1150)
sand_cov = coverage("dSand", 1200, 250)
stream_cov = coverage("dStream", 1200, 1200)
fade_u1 = use("streamFade", 1650, 1320)
stream_v = expr(unreal.MaterialExpressionMultiply, 1800, 1250)
_connect(stream_cov, "", stream_v, "A")
_connect(fade_u1, "", stream_v, "B")
sand_stream = expr(unreal.MaterialExpressionMax, 1950, 700)
_connect(sand_cov, "", sand_stream, "A")
_connect(stream_v, "", sand_stream, "B")
mask_max = expr(unreal.MaterialExpressionMax, 2100, 0)
_connect(glass_cov, "", mask_max, "A")
_connect(sand_stream, "", mask_max, "B")
make_decl("mask", mask_max, 2250, 0, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2450, -150,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUP, sort_priority=10, desc="Color of the glass and the sand (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 2450, 100)
emissive = expr(unreal.MaterialExpressionMultiply, 2700, -100)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 2450, 300)
cov_a = expr(unreal.MaterialExpressionMultiply, 2700, 250)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 2850, 200)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in p units)",
    -4350, -870, 900, 400, C_UV)
smt.create_comment_in_material(
    mat, "Shared parameters -> Named Reroutes; halfT = Thickness / 2.\n"
         "HalfHeight + Thickness / 2 = 0.72 at rest (the material contract's reference square)",
    -4600, -520, 650, 600, C_SC)
smt.create_comment_in_material(
    mat, "u = fract(Time * Speed);  flowEnd = 1 - FlipFraction;  flow = saturate(u / flowEnd)\n"
         "flow = share of the sand already in the bottom bulb. Time ignores pause (real time),\n"
         "so the sand keeps running while the game thread is blocked",
    -4600, 750, 1400, 450, C_TM)
smt.create_comment_in_material(
    mat, "turn = smoothstep(flowEnd, 1, u);  c, s = cos / sin(PI * turn)   (half a turn, clockwise)\n"
         "scale = 1 - FlipShrink * s: smallest sideways. Unshrunk, a cap corner reaches 0.946 along x or y at 45\n"
         "degrees; FlipShrink 0.3 keeps max(|x|, |y|) of the turning glass at 0.794 (square 0.72, circle 0.8)",
    -3850, 1050, 1400, 450, C_TM)
smt.create_comment_in_material(
    mat, "q = (c*p.x - s*p.y, s*p.x + c*p.y) / scale   (the glass turns clockwise and shrinks)\n"
         "aaQ = aa / scale (distances in q are p distances / scale);  f = abs(q): the glass is symmetric in x and y",
    -3350, -700, 1750, 800, C_UV)
smt.create_comment_in_material(
    mat, "dGlass = min(sdSegment(f, (Neck, 0), (HalfWidth, HalfHeight)),\n"
         "              sdSegment(f, (0, HalfHeight), (HalfWidth + CapExtra, HalfHeight))) - Thickness / 2\n"
         "One slanted side and one cap draw the whole frame after the fold (sdSegment = MF_SdSegment2D)",
    -1550, -1600, 1400, 950, C_SDF)
smt.create_comment_in_material(
    mat, "inset = Thickness / 2 + SandGap;  outward = (HalfHeight, Neck - HalfWidth) / length(...)\n"
         "dChamber = max(dot(f - (Neck, 0), outward), f.y - HalfHeight) + inset\n"
         "(inside of the glass, SandGap away from the stroke: two half-planes)",
    -1700, -720, 1550, 820, C_SDF)
smt.create_comment_in_material(
    mat, "level = (HalfHeight - inset) * sqrt(1 - flow): a bulb is nearly a triangle, so the sand below height y\n"
         "grows with y^2 and the top surface and the bottom surface sit at the same height.\n"
         "dSand = min(max(dChamber, q.y - level, -q.y), max(dChamber, q.y + level))",
    -1550, 100, 1900, 500, C_SDF)
smt.create_comment_in_material(
    mat, "Falling sand: dStream = sdSegment(q, (0, 0), (0, -level)) - wStream / 2,  wStream = max(StreamWidth, aaQ)\n"
         "streamFade = (StreamWidth / wStream) * (1 - step(1, flow)): a line thinner than a pixel is drawn one pixel wide\n"
         "at lower opacity (otherwise it shows at half coverage), and only while sand is left on top",
    -1550, 750, 1650, 1050, C_SDF)
smt.create_comment_in_material(
    mat, "Coverage = saturate(0.5 - d / aaQ) for the glass, the sand and the falling sand (times streamFade);\n"
         "mask = max of the three (one color)",
    1150, -1300, 1250, 2700, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    2400, -270, 650, 680, C_COL)

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
def audit(exprs):
    decl_names, usage_count, params, mf_calls = [], {}, [], 0
    for e in exprs:
        if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
            decl_names.append(str(e.get_editor_property("name")))
        elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
            nm = smt.get_named_reroute_usage_display_name(e)
            usage_count[nm] = usage_count.get(nm, 0) + 1
        elif isinstance(e, (unreal.MaterialExpressionScalarParameter,
                            unreal.MaterialExpressionVectorParameter)):
            params.append(str(e.get_editor_property("parameter_name")))
        elif isinstance(e, unreal.MaterialExpressionMaterialFunctionCall):
            mf_calls += 1
    return sorted(decl_names), dict(sorted(usage_count.items())), sorted(params), mf_calls

f_decls, f_usages, _, _ = audit(smt.get_material_function_expressions(fn))
print(f"[TEST] {MF_NAME} decls: {f_decls}")
print(f"[TEST] {MF_NAME} usages: {f_usages}")
mf_ok = (f_decls == ["A", "B", "P", "ba", "pa"]
         and f_usages == {"A": 2, "B": 1, "P": 1, "ba": 3, "pa": 2}
         and len(smt.get_function_comment_texts(fn)) == 2
         and mf_saved)

m_decls, m_usages, m_params, m_calls = audit(smt.get_material_expressions(mat))
print(f"[TEST] {ASSET_NAME} decls: {m_decls}")
print(f"[TEST] {ASSET_NAME} usages: {m_usages}")
print(f"[TEST] {ASSET_NAME} params: {m_params}")
print(f"[TEST] {ASSET_NAME} MF calls: {m_calls}")
expected_decls = sorted(["p", "aa", "HalfHeight", "HalfWidth", "Neck", "halfT", "u", "flowEnd", "flow", "c", "s",
                         "scale", "q", "aaQ", "f", "neckPt", "dGlass", "inset", "dChamber", "level", "dSand",
                         "StreamWidth", "wStream", "dStream", "streamFade", "mask"])
expected_usages = {"p": 2, "aa": 1, "HalfHeight": 6, "HalfWidth": 3, "Neck": 2, "halfT": 2, "u": 2, "flowEnd": 2,
                   "flow": 2, "c": 2, "s": 3, "scale": 2, "q": 3, "aaQ": 4, "f": 4, "neckPt": 2, "dGlass": 1,
                   "inset": 2, "dChamber": 2, "level": 3, "dSand": 1, "StreamWidth": 2, "wStream": 2,
                   "dStream": 1, "streamFade": 1, "mask": 1}
expected_params = sorted(["HalfHeight", "HalfWidth", "Neck", "CapExtra", "Thickness", "SandGap", "StreamWidth",
                          "Speed", "FlipFraction", "FlipShrink", "PrimaryColor"])
mat_ok = (m_decls == expected_decls and m_usages == dict(sorted(expected_usages.items()))
          and m_params == expected_params and m_calls == 4
          and len(smt.get_material_comment_texts(mat)) == 11
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {MF_NAME}: {'OK' if mf_ok else 'NG'} / {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mf_ok and mat_ok else "FAIL"))
