"""
4-box loading icon (user's own Shadertoy) -> MF_SdRoundBox2D + M_LoadingBoxes (Material Domain = UI, Translucent)

角丸の箱 4 個を 2x2 に並べ、箱ごとに 1/4 周ずつ位相をずらして明るさを MAX -> MIN へ減衰させるロードアイコン。
最も明るい箱は 右上 -> 右下 -> 左下 -> 左上 と時計回りに巡る。abs で 1 象限に折りたたむので箱の SDF は 1 回だけ。

  p      = (TexCoord0 - 0.5) * (1,-1)                 ((fragCoord - 0.5*iResolution.xy) / iResolution.y。
                                                       Shadertoy は y 上向き。正方形ウィジェット前提)
  q      = step(0, p)
  idx    = 2*(1 - q.y) + abs(q.x - q.y)               (象限番号 0..3、右上から反時計回り)
  d      = sdRoundBox(abs(p) - 0.5*(BoxSize + BoxGap), vec2(0.5*BoxSize), BoxRound)   (MF_SdRoundBox2D)
  aa     = 1.5 * fwidth(p.y)                          (1.5 / iResolution.y。p.y はウィジェット高さで 1.0 進むので
                                                       fwidth(p.y) = 1 ピクセル。fwidth は DDX/DDY で展開)
  mask   = 1 - smoothstep(-aa, aa, d)
  phase  = fract(Time * FadeSpeed + idx * 0.25)
  bright = mix(BrightMax, BrightMin, pow(phase, FadeCurve))

  出力: FinalColor(Emissive) = BoxColor、Opacity = mask * bright。
  背景(BG_COLOR)は不要なので mix(BG, BOX, mask*bright) は BoxColor + アルファに置き換え(黒背景上では同一)。

  const -> ScalarParameter / VectorParameter(グループ "LoadingBoxes"、並びは GLSL の宣言順)
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  BoxSize(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。
  MF_SdRoundBox2D の FunctionInput も同名の Declaration を経由する。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingboxes.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingBoxes"
MF_NAME = "MF_SdRoundBox2D"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_PATH = "/LoadingFX/MaterialFunctions"
MF_FULL_PATH = f"{MF_PATH}/{MF_NAME}"
PARAM_GROUP = "LoadingBoxes"

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / quadrant = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / brightness = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # scalar intermediates / params / MF inputs = gray
C_COL = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)   # coverage / output = white

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
    return new(unreal.MaterialExpressionComponentMask, x, y,
               r=True, g=False, b=False, a=False)

def mask_y(new, x, y):
    return new(unreal.MaterialExpressionComponentMask, x, y,
               r=False, g=True, b=False, a=False)

# ============================================================
#  MF_SdRoundBox2D
#    float sdRoundBox(vec2 p, vec2 b, float r) {
#        vec2 d = abs(p) - b + r;
#        return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - r;
#    }
# ============================================================
fn = tools.create_asset(MF_NAME, MF_PATH, unreal.MaterialFunction, unreal.MaterialFunctionFactoryNew())
fn.set_editor_property("description",
    "Rounded 2D box SDF: d = abs(P) - B + R; returns length(max(d, 0)) + min(max(d.x, d.y), 0) - R. "
    "P = point relative to the box center, B = half extents, R = corner radius (0 = sharp corners). "
    "Negative inside, positive outside.")
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

def finput(name, itype, sort, preview, x, y):
    n = fnode(unreal.MaterialExpressionFunctionInput, x, y,
              input_name=name, input_type=itype, sort_priority=sort, preview_value=preview)
    fdecl(name, n, x + 200, y, C_SC)
    return n

finput("P", unreal.FunctionInputType.FUNCTION_INPUT_VECTOR2, 0, vec4(0.0, 0.0, 0.0, 0.0), -1500, -200)
finput("B", unreal.FunctionInputType.FUNCTION_INPUT_VECTOR2, 1, vec4(0.5, 0.5, 0.0, 0.0), -1500, 0)
finput("R", unreal.FunctionInputType.FUNCTION_INPUT_SCALAR, 2, vec4(0.1, 0.0, 0.0, 0.0), -1500, 200)

# d = abs(P) - B + R
p_fu = fuse("P", -1050, -200)
abs_p = fnode(unreal.MaterialExpressionAbs, -900, -200)
_connect(p_fu, "", abs_p, "")
b_fu = fuse("B", -900, -80)
sub_b = fnode(unreal.MaterialExpressionSubtract, -750, -150)
_connect(abs_p, "", sub_b, "A")
_connect(b_fu, "", sub_b, "B")
r_fu1 = fuse("R", -750, -30)
add_r = fnode(unreal.MaterialExpressionAdd, -600, -100)
_connect(sub_b, "", add_r, "A")
_connect(r_fu1, "", add_r, "B")
fdecl("d", add_r, -450, -100, C_SDF)

# outside = length(max(d, 0))
d_fu1 = fuse("d", -250, -250)
max0 = fnode(unreal.MaterialExpressionMax, -100, -250, const_b=0.0)
_connect(d_fu1, "", max0, "A")
length_n = fnode(unreal.MaterialExpressionLength, 50, -250)
_connect(max0, "", length_n, "")

# inside = min(max(d.x, d.y), 0)
d_fu2 = fuse("d", -250, -80)
d_x = mask_x(fnode, -100, -80)
_connect(d_fu2, "", d_x, "")
d_fu3 = fuse("d", -250, 40)
d_y = mask_y(fnode, -100, 40)
_connect(d_fu3, "", d_y, "")
max_xy = fnode(unreal.MaterialExpressionMax, 50, -20)
_connect(d_x, "", max_xy, "A")
_connect(d_y, "", max_xy, "B")
min0 = fnode(unreal.MaterialExpressionMin, 200, -20, const_b=0.0)
_connect(max_xy, "", min0, "A")

# Result = outside + inside - R
sum_n = fnode(unreal.MaterialExpressionAdd, 350, -150)
_connect(length_n, "", sum_n, "A")
_connect(min0, "", sum_n, "B")
r_fu2 = fuse("R", 350, -30)
res_n = fnode(unreal.MaterialExpressionSubtract, 500, -100)
_connect(sum_n, "", res_n, "A")
_connect(r_fu2, "", res_n, "B")
f_out = fnode(unreal.MaterialExpressionFunctionOutput, 650, -100, output_name="Result")
_connect(res_n, "", f_out, "")

smt.create_comment_in_function(
    fn, "Inputs -> Named Reroute (P, B, R)\n"
        "P = point relative to the box center, B = half extents, R = corner radius",
    -1550, -320, 750, 650, C_SC)
smt.create_comment_in_function(
    fn, "d = abs(P) - B + R   (box shrunk by R, then inflated back by R below)",
    -1100, -320, 820, 400, C_SDF)
smt.create_comment_in_function(
    fn, "sdRoundBox = length(max(d, 0)) + min(max(d.x, d.y), 0) - R\n"
        "outside distance + inside distance, minus R rounds the corners",
    -280, -370, 920, 520, C_SDF)

mel.update_material_function(fn)
mf_saved = lib.save_asset(MF_FULL_PATH)
print(f"[TEST] Saved: {MF_FULL_PATH} -> {mf_saved}")

# ============================================================
#  M_LoadingBoxes
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
def make_decl(name, src, x, y, color):
    dcl = expr(unreal.MaterialExpressionNamedRerouteDeclaration, x, y, name=name, node_color=color)
    _connect(src, "", dcl, "")
    decls[name] = dcl
    return dcl

def use(name, x, y):
    return smt.create_named_reroute_usage(mat, decls[name], x, y)

def scalar_param(name, default, sort, desc, x, y):
    return expr(unreal.MaterialExpressionScalarParameter, x, y,
                parameter_name=name, default_value=default, group=PARAM_GROUP,
                sort_priority=sort, desc=desc)

# ---- const BOX_SIZE (used twice -> Named Reroute) ----
boxsize_p = scalar_param("BoxSize", 0.14, 0, "Box edge length (widget height = 1.0)", -3450, -700)
make_decl("BoxSize", boxsize_p, -3200, -700, C_SC)

# ---- p = (TexCoord0 - 0.5) * (1,-1)  (Shadertoy is y-up; square widget assumed) ----
texc = expr(unreal.MaterialExpressionTextureCoordinate, -3450, 0)
center = expr(unreal.MaterialExpressionSubtract, -3300, 0, const_b=0.5)
_connect(texc, "", center, "A")
yflip_c = expr(unreal.MaterialExpressionConstant2Vector, -3300, 120, r=1.0, g=-1.0)
p_v = expr(unreal.MaterialExpressionMultiply, -3150, 50)
_connect(center, "", p_v, "A")
_connect(yflip_c, "", p_v, "B")
make_decl("p", p_v, -3000, 50, C_UV)

# ---- q = step(0, p)  (per component: 1 when p >= 0) ----
p_u1 = use("p", -2750, 450)
# UE Step(Y, X) returns 1 when X >= Y, i.e. GLSL step(edge=Y, x=X): edge 0 stays in const_y.
q_step = expr(unreal.MaterialExpressionStep, -2600, 450, const_y=0.0)
_connect(p_u1, "", q_step, "X")
make_decl("q", q_step, -2450, 450, C_UV)

# ---- idx = 2*(1 - q.y) + abs(q.x - q.y)  (quadrant 0..3, counter-clockwise from top-right) ----
q_u1 = use("q", -2250, 330)
q_y1 = mask_y(expr, -2100, 330)
_connect(q_u1, "", q_y1, "")
lower = expr(unreal.MaterialExpressionOneMinus, -1950, 330)
_connect(q_y1, "", lower, "")
lower2 = expr(unreal.MaterialExpressionMultiply, -1800, 330, const_b=2.0)
_connect(lower, "", lower2, "A")
q_u2 = use("q", -2250, 480)
q_x = mask_x(expr, -2100, 480)
_connect(q_u2, "", q_x, "")
q_u3 = use("q", -2250, 600)
q_y2 = mask_y(expr, -2100, 600)
_connect(q_u3, "", q_y2, "")
diag = expr(unreal.MaterialExpressionSubtract, -1950, 530)
_connect(q_x, "", diag, "A")
_connect(q_y2, "", diag, "B")
diag_abs = expr(unreal.MaterialExpressionAbs, -1800, 530)
_connect(diag, "", diag_abs, "")
idx_v = expr(unreal.MaterialExpressionAdd, -1650, 430)
_connect(lower2, "", idx_v, "A")
_connect(diag_abs, "", idx_v, "B")
make_decl("idx", idx_v, -1500, 430, C_SC)

# ---- d = sdRoundBox(abs(p) - 0.5*(BoxSize + BoxGap), vec2(0.5*BoxSize), BoxRound) ----
p_u2 = use("p", -2750, -450)
p_abs = expr(unreal.MaterialExpressionAbs, -2600, -450)
_connect(p_u2, "", p_abs, "")
boxsize_u1 = use("BoxSize", -2750, -330)
boxgap_p = scalar_param("BoxGap", 0.04, 1, "Gap between boxes", -2800, -230)
pitch = expr(unreal.MaterialExpressionAdd, -2550, -300)
_connect(boxsize_u1, "", pitch, "A")
_connect(boxgap_p, "", pitch, "B")
offset = expr(unreal.MaterialExpressionMultiply, -2400, -300, const_b=0.5)
_connect(pitch, "", offset, "A")
p_box = expr(unreal.MaterialExpressionSubtract, -2250, -400)
_connect(p_abs, "", p_box, "A")
_connect(offset, "", p_box, "B")
boxsize_u2 = use("BoxSize", -2550, -120)
half = expr(unreal.MaterialExpressionMultiply, -2400, -120, const_b=0.5)
_connect(boxsize_u2, "", half, "A")
half2 = expr(unreal.MaterialExpressionAppendVector, -2250, -120)   # vec2(0.5 * BOX_SIZE)
_connect(half, "", half2, "A")
_connect(half, "", half2, "B")
boxround_p = scalar_param("BoxRound", 0.015, 2, "Corner radius (0 = sharp corners)", -2300, 0)
sd_call = expr(unreal.MaterialExpressionMaterialFunctionCall, -2000, -300, material_function=fn)
_connect(p_box, "", sd_call, "P")
_connect(half2, "", sd_call, "B")
_connect(boxround_p, "", sd_call, "R")
make_decl("d", sd_call, -1750, -300, C_SDF)

# ---- aa = 1.5 / iResolution.y = 1.5 * fwidth(p.y)  (fwidth expanded with DDX/DDY) ----
p_u3 = use("p", -2750, -950)
p_y = mask_y(expr, -2600, -950)
_connect(p_u3, "", p_y, "")
p_ddx = expr(unreal.MaterialExpressionDDX, -2450, -1010)
p_ddy = expr(unreal.MaterialExpressionDDY, -2450, -890)
_connect(p_y, "", p_ddx, "")
_connect(p_y, "", p_ddy, "")
abs_dx = expr(unreal.MaterialExpressionAbs, -2300, -1010)
abs_dy = expr(unreal.MaterialExpressionAbs, -2300, -890)
_connect(p_ddx, "", abs_dx, "")
_connect(p_ddy, "", abs_dy, "")
px = expr(unreal.MaterialExpressionAdd, -2150, -950)
_connect(abs_dx, "", px, "A")
_connect(abs_dy, "", px, "B")
aa_v = expr(unreal.MaterialExpressionMultiply, -2000, -950, const_b=1.5)
_connect(px, "", aa_v, "A")
make_decl("aa", aa_v, -1850, -950, C_SDF)

# ---- mask = 1 - smoothstep(-aa, aa, d)  (anti-aliased mask) ----
aa_u1 = use("aa", -1500, -850)
aa_neg = expr(unreal.MaterialExpressionMultiply, -1350, -900, const_b=-1.0)
_connect(aa_u1, "", aa_neg, "A")
d_u1 = use("d", -1500, -680)
edge = expr(unreal.MaterialExpressionSmoothStep, -1200, -800)
_connect(aa_neg, "", edge, "Min")
_connect(aa_u1, "", edge, "Max")
_connect(d_u1, "", edge, "Value")
inside = expr(unreal.MaterialExpressionOneMinus, -1050, -800)
_connect(edge, "", inside, "")
make_decl("mask", inside, -900, -800, C_COL)

# ---- phase = fract(Time * FadeSpeed + idx * 0.25)  (quarter-cycle offset per box) ----
time_n = expr(unreal.MaterialExpressionTime, -1250, 250)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
fadespeed_p = scalar_param("FadeSpeed", 1.0, 3, "Brightness cycles per second", -1300, 350)
t_speed = expr(unreal.MaterialExpressionMultiply, -1050, 300)
_connect(time_n, "", t_speed, "A")
_connect(fadespeed_p, "", t_speed, "B")
idx_u1 = use("idx", -1250, 500)
idx_off = expr(unreal.MaterialExpressionMultiply, -1100, 500, const_b=0.25)
_connect(idx_u1, "", idx_off, "A")
t_sum = expr(unreal.MaterialExpressionAdd, -900, 400)
_connect(t_speed, "", t_sum, "A")
_connect(idx_off, "", t_sum, "B")
t_frac = expr(unreal.MaterialExpressionFrac, -750, 400)
_connect(t_sum, "", t_frac, "")
make_decl("phase", t_frac, -600, 400, C_TM)

# ---- bright = mix(BrightMax, BrightMin, pow(phase, FadeCurve))  (MAX -> MIN once per cycle) ----
phase_u1 = use("phase", -350, 330)
fadecurve_p = scalar_param(
    "FadeCurve", 0.5, 4,
    "Decay curve (1: linear / < 1: fades quickly / > 1: stays bright longer). Must be > 0", -400, 430)
curve = expr(unreal.MaterialExpressionPower, -150, 360)
_connect(phase_u1, "", curve, "Base")
_connect(fadecurve_p, "", curve, "Exp")
brightmax_p = scalar_param("BrightMax", 1.0, 5, "Brightest box", -150, 130)
brightmin_p = scalar_param("BrightMin", 0.1, 6, "Faintest box (depth of the fade)", -150, 230)
bright_v = expr(unreal.MaterialExpressionLinearInterpolate, 100, 250)
_connect(brightmax_p, "", bright_v, "A")
_connect(brightmin_p, "", bright_v, "B")
_connect(curve, "", bright_v, "Alpha")
make_decl("bright", bright_v, 250, 250, C_TM)

# ---- Output: FinalColor = BoxColor, Opacity = mask * bright  (BG dropped) ----
boxcolor_p = expr(unreal.MaterialExpressionVectorParameter, 450, -500,
                  parameter_name="BoxColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                  group=PARAM_GROUP, sort_priority=7, desc="Box color")
results.append(mel.connect_material_property(boxcolor_p, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 450, -200)
bright_u1 = use("bright", 450, -100)
opacity = expr(unreal.MaterialExpressionMultiply, 600, -150)
_connect(mask_u1, "", opacity, "A")
_connect(bright_u1, "", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "const BOX_SIZE -> ScalarParameter (used twice -> Named Reroute).\n"
         "BoxGap / BoxRound / FadeSpeed / FadeCurve / BrightMax / BrightMin / BoxColor are wired directly",
    -3500, -800, 600, 220, C_SC)
smt.create_comment_in_material(
    mat, "p = (TexCoord0 - 0.5) * (1,-1)   (= (fragCoord - 0.5*iResolution.xy) / iResolution.y)\n"
         "Y flipped (Shadertoy is y-up). Square widget assumed: widget height = 1.0",
    -3500, -100, 700, 350, C_UV)
smt.create_comment_in_material(
    mat, "Quadrant index 0..3 (counter-clockwise from top-right), branch-free\n"
         "q = step(0, p); idx = 2*(1 - q.y) + abs(q.x - q.y)",
    -2800, 230, 1450, 520, C_UV)
smt.create_comment_in_material(
    mat, "Fold into one quadrant with abs -> one box SDF draws all four boxes\n"
         "d = sdRoundBox(abs(p) - 0.5*(BoxSize + BoxGap), vec2(0.5*BoxSize), BoxRound)",
    -2850, -560, 1250, 680, C_SDF)
smt.create_comment_in_material(
    mat, "aa = 1.5 / iResolution.y = 1.5 * fwidth(p.y)\n"
         "p.y spans 1.0 over the widget height, so fwidth(p.y) is one pixel (DDX/DDY expansion)",
    -2800, -1110, 1100, 400, C_SDF)
smt.create_comment_in_material(
    mat, "mask = 1 - smoothstep(-aa, aa, d)   (anti-aliased mask)",
    -1550, -1000, 820, 450, C_COL)
smt.create_comment_in_material(
    mat, "Each box is a quarter cycle ahead of the previous one\n"
         "phase = fract(Time * FadeSpeed + idx * 0.25)",
    -1350, 150, 900, 520, C_TM)
smt.create_comment_in_material(
    mat, "bright = mix(BrightMax, BrightMin, pow(phase, FadeCurve))\n"
         "Decays MAX -> MIN once per cycle; FadeCurve must be > 0",
    -420, 30, 850, 560, C_TM)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = BoxColor, Opacity = mask * bright\n"
         "Background dropped: mix(BG, BoxColor, mask * bright) becomes BoxColor with alpha\n"
         "(identical over a black background)",
    400, -620, 700, 600, C_COL)

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
mf_ok = (f_decls == ["B", "P", "R", "d"]
         and f_usages == {"B": 1, "P": 1, "R": 2, "d": 3}
         and len(smt.get_function_comment_texts(fn)) == 3
         and mf_saved)

m_decls, m_usages, m_params, m_calls = audit(smt.get_material_expressions(mat))
print(f"[TEST] {ASSET_NAME} decls: {m_decls}")
print(f"[TEST] {ASSET_NAME} usages: {m_usages}")
print(f"[TEST] {ASSET_NAME} params: {m_params}")
print(f"[TEST] {ASSET_NAME} MF calls: {m_calls}")
expected_decls = sorted(["BoxSize", "p", "q", "idx", "d", "aa", "mask", "phase", "bright"])
expected_usages = {"BoxSize": 2, "aa": 1, "bright": 1, "d": 1, "idx": 1, "mask": 1,
                   "p": 3, "phase": 1, "q": 3}
expected_params = sorted(["BoxSize", "BoxGap", "BoxRound", "FadeSpeed", "FadeCurve",
                          "BrightMax", "BrightMin", "BoxColor"])
mat_ok = (m_decls == expected_decls and m_usages == dict(sorted(expected_usages.items()))
          and m_params == expected_params and m_calls == 1
          and len(smt.get_material_comment_texts(mat)) == 9
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {MF_NAME}: {'OK' if mf_ok else 'NG'} / {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mf_ok and mat_ok else "FAIL"))
