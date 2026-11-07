"""
Stretching arc spinner -> M_LoadingArc (Material Domain = UI, Translucent)

角丸の弧 1 本が回りながら伸び縮みする、定番のロードアイコン。サイクルの前半で先頭が時計回りに伸び(ArcMin -> ArcMax)、
後半で末尾が追いついて縮む。サイクルごとに末尾が ArcMax - ArcMin だけ進むので、伸び縮みしながら全体が先へ進み、
その上に Speed の等速回転が乗る。弧の形は iq の sdArc: 弧の中心が真上に来るよう座標を回転し x を折り返すので、
ループも分岐もなく 1 回の評価で済む。時間側はピクセルに依存しないスカラー計算だけ。
見た目は 2026-10-10 に Python で同じ式を評価した静止画でユーザー確認済み。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  rot    = Time * Speed                             (等速回転、回転数。Speed は回転数/秒、正 = 時計回り)
  cyc    = Time * StretchSpeed                      (StretchSpeed は伸び縮みのサイクル数/秒)
  k, u   = floor(cyc), fract(cyc)
  grow   = smoothstep(0, 0.5, u)                    (前半: 先頭が伸びる)
  shrink = smoothstep(0.5, 1, u)                    (後半: 末尾が追いつく)
  ext    = ArcMax - ArcMin
  len    = ArcMin + ext * (grow - shrink)           (弧の長さ、回転数単位)
  mid    = (k + shrink) * ext + len / 2 + rot       (弧の中心の向き。12 時から時計回りの回転数。
                                                     末尾 = (k + shrink) * ext + rot、先頭 = 末尾 + len)
  ang    = fract(mid) * TAU                         (fract で角度を小さく保つ)
  c, s   = cos(ang), sin(ang)
  q      = (abs(dot(p, (c, -s))), dot(p, (s, c)))   (弧の中心が真上を向くよう回転し、左右を折り返す)
  sc     = (sin(len * PI), cos(len * PI))           (弧の右端の向き。len * PI は半開き角)
  dCap   = length(q - sc * Radius)                  (端点(丸い端)までの距離)
  dRing  = abs(length(q) - Radius)                  (円周までの距離)
  d      = (sc.y * q.x >= sc.x * q.y ? dCap : dRing) - Thickness / 2
                                                    (端点より外側の角度なら端点、内側なら円周。Step + Lerp で分岐なし)
  mask   = clamp(0.5 - d / aa, 0, 1)

  Speed が負なら等速回転は反時計回りになるが、伸びる向きは常に時計回り。ArcMin = ArcMax なら長さ一定の弧が回るだけ。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は Radius + Thickness/2 = 0.8(材質契約の基準円。1.0 = 短辺の端)に合わせてある。

  ScalarParameter / VectorParameter のグループは Appearance / Shape / Motion(PARAM_GROUPS、順序は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Radius(2 箇所)と ArcMin(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingarc.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingArc"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
PI = 3.14159265359
TAU = 6.28318530718
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "Radius": "Shape",
    "Thickness": "Shape",
    "ArcMin": "Shape",
    "ArcMax": "Shape",
    "Speed": "Motion",
    "StretchSpeed": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / rotation = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / arc length = light blue
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
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -4100, -350, material_function=mf_coords)
make_decl("p", coords, -3800, -400, C_UV, "P")
make_decl("aa", coords, -3800, -280, C_SDF, "PixelSize")

# ---- rot = Time * Speed;  cyc = Time * StretchSpeed;  k = floor(cyc), u = fract(cyc) ----
time_n = expr(unreal.MaterialExpressionTime, -4250, 750)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.3, 0,
                       "Revolutions per second of the steady rotation. Positive = clockwise "
                       "(the arc itself always stretches clockwise)", -4250, 600)
rot_v = expr(unreal.MaterialExpressionMultiply, -4050, 650)
_connect(time_n, "", rot_v, "A")
_connect(speed_p, "", rot_v, "B")
make_decl("rot", rot_v, -3900, 650, C_TM)
stretch_p = scalar_param("StretchSpeed", 0.75, 1, "Stretch cycles per second (one grow and one shrink)",
                         -4250, 870)
cyc_v = expr(unreal.MaterialExpressionMultiply, -4050, 820)
_connect(time_n, "", cyc_v, "A")
_connect(stretch_p, "", cyc_v, "B")
k_floor = expr(unreal.MaterialExpressionFloor, -3900, 770)
_connect(cyc_v, "", k_floor, "")
make_decl("k", k_floor, -3750, 770, C_TM)
u_frac = expr(unreal.MaterialExpressionFrac, -3900, 880)
_connect(cyc_v, "", u_frac, "")
make_decl("u", u_frac, -3750, 880, C_TM)

# ---- grow = smoothstep(0, 0.5, u);  shrink = smoothstep(0.5, 1, u) ----
u_u1 = use("u", -3500, 750)
grow_ss = expr(unreal.MaterialExpressionSmoothStep, -3350, 750, const_min=0.0, const_max=0.5)
_connect(u_u1, "", grow_ss, "Value")
u_u2 = use("u", -3500, 900)
shrink_ss = expr(unreal.MaterialExpressionSmoothStep, -3350, 900, const_min=0.5, const_max=1.0)
_connect(u_u2, "", shrink_ss, "Value")
make_decl("shrink", shrink_ss, -3150, 900, C_TM)

# ---- ext = ArcMax - ArcMin ----
# Arc lengths are in turns: 0.06 = 22 degrees, 0.68 = 245 degrees.
arcmin_p = scalar_param("ArcMin", 0.06, 2, "Shortest arc length, in turns (0..1)", -3500, 1100)
make_decl("ArcMin", arcmin_p, -3250, 1100, C_SC)
arcmax_p = scalar_param("ArcMax", 0.68, 3, "Longest arc length, in turns (ArcMin..1)", -3500, 1220)
arcmin_u1 = use("ArcMin", -3100, 1270)
ext_v = expr(unreal.MaterialExpressionSubtract, -2950, 1220)
_connect(arcmax_p, "", ext_v, "A")
_connect(arcmin_u1, "", ext_v, "B")
make_decl("ext", ext_v, -2800, 1220, C_SC)

# ---- len = ArcMin + ext * (grow - shrink)  (arc length in turns) ----
shrink_u1 = use("shrink", -3000, 850)
gs_sub = expr(unreal.MaterialExpressionSubtract, -2850, 800)
_connect(grow_ss, "", gs_sub, "A")
_connect(shrink_u1, "", gs_sub, "B")
ext_u1 = use("ext", -2850, 950)
len_mul = expr(unreal.MaterialExpressionMultiply, -2700, 850)
_connect(gs_sub, "", len_mul, "A")
_connect(ext_u1, "", len_mul, "B")
arcmin_u2 = use("ArcMin", -2700, 1000)
len_add = expr(unreal.MaterialExpressionAdd, -2550, 900)
_connect(arcmin_u2, "", len_add, "A")
_connect(len_mul, "", len_add, "B")
make_decl("len", len_add, -2400, 900, C_TM)

# ---- mid = (k + shrink) * ext + len / 2 + rot;  ang = fract(mid) * TAU ----
k_u1 = use("k", -2150, 650)
shrink_u2 = use("shrink", -2150, 750)
tail_k = expr(unreal.MaterialExpressionAdd, -2000, 700)
_connect(k_u1, "", tail_k, "A")
_connect(shrink_u2, "", tail_k, "B")
ext_u2 = use("ext", -2000, 820)
tail_v = expr(unreal.MaterialExpressionMultiply, -1850, 750)   # tail before the steady rotation
_connect(tail_k, "", tail_v, "A")
_connect(ext_u2, "", tail_v, "B")
len_u1 = use("len", -2000, 950)
len_half = expr(unreal.MaterialExpressionMultiply, -1850, 950, const_b=0.5)
_connect(len_u1, "", len_half, "A")
mid_add = expr(unreal.MaterialExpressionAdd, -1700, 850)
_connect(tail_v, "", mid_add, "A")
_connect(len_half, "", mid_add, "B")
rot_u1 = use("rot", -1700, 1000)
mid_v = expr(unreal.MaterialExpressionAdd, -1550, 900)
_connect(mid_add, "", mid_v, "A")
_connect(rot_u1, "", mid_v, "B")
mid_frac = expr(unreal.MaterialExpressionFrac, -1400, 900)
_connect(mid_v, "", mid_frac, "")
ang_v = expr(unreal.MaterialExpressionMultiply, -1250, 900, const_b=TAU)
_connect(mid_frac, "", ang_v, "A")
make_decl("ang", ang_v, -1100, 900, C_UV)

# ---- c = cos(ang), s = sin(ang) ----
ang_u1 = use("ang", -850, 650)
ang_cos = expr(unreal.MaterialExpressionCosine, -700, 650, period=TAU)   # period 2*PI = radians
_connect(ang_u1, "", ang_cos, "")
make_decl("c", ang_cos, -550, 650, C_UV)
ang_u2 = use("ang", -850, 780)
ang_sin = expr(unreal.MaterialExpressionSine, -700, 780, period=TAU)
_connect(ang_u2, "", ang_sin, "")
make_decl("s", ang_sin, -550, 780, C_UV)

# ---- sc = (sin(len * PI), cos(len * PI))  (direction of the arc's right end; len * PI is the half aperture) ----
len_u2 = use("len", -850, 1000)
half_ap = expr(unreal.MaterialExpressionMultiply, -700, 1000, const_b=PI)
_connect(len_u2, "", half_ap, "A")
ap_sin = expr(unreal.MaterialExpressionSine, -550, 950, period=TAU)
_connect(half_ap, "", ap_sin, "")
ap_cos = expr(unreal.MaterialExpressionCosine, -550, 1070, period=TAU)
_connect(half_ap, "", ap_cos, "")
sc_v = expr(unreal.MaterialExpressionAppendVector, -400, 1000)
_connect(ap_sin, "", sc_v, "A")
_connect(ap_cos, "", sc_v, "B")
make_decl("sc", sc_v, -250, 1000, C_UV)

# ---- q = (abs(dot(p, (c, -s))), dot(p, (s, c)))  (arc center now points up; fold the left half onto the right) ----
c_u1 = use("c", -100, -100)
s_u1 = use("s", -100, 0)
s_neg = expr(unreal.MaterialExpressionMultiply, 50, 0, const_b=-1.0)
_connect(s_u1, "", s_neg, "A")
row_x = expr(unreal.MaterialExpressionAppendVector, 200, -50)    # (c, -s)
_connect(c_u1, "", row_x, "A")
_connect(s_neg, "", row_x, "B")
s_u2 = use("s", -100, 150)
c_u2 = use("c", -100, 250)
row_y = expr(unreal.MaterialExpressionAppendVector, 200, 200)    # (s, c)
_connect(s_u2, "", row_y, "A")
_connect(c_u2, "", row_y, "B")
p_u1 = use("p", 350, -150)
q_x = expr(unreal.MaterialExpressionDotProduct, 500, -100)
_connect(p_u1, "", q_x, "A")
_connect(row_x, "", q_x, "B")
q_xabs = expr(unreal.MaterialExpressionAbs, 650, -100)
_connect(q_x, "", q_xabs, "")
p_u2 = use("p", 350, 150)
q_y = expr(unreal.MaterialExpressionDotProduct, 500, 200)
_connect(p_u2, "", q_y, "A")
_connect(row_y, "", q_y, "B")
q_v = expr(unreal.MaterialExpressionAppendVector, 800, 50)
_connect(q_xabs, "", q_v, "A")
_connect(q_y, "", q_v, "B")
make_decl("q", q_v, 950, 50, C_UV)

# Footprint (material contract): Radius + Thickness / 2 = 0.8, the reference circle.
radius_p = scalar_param("Radius", 0.735, 0,
                        "Distance from the center to the middle of the stroke (half the shorter widget side = 1.0)",
                        900, 450)
make_decl("Radius", radius_p, 1150, 450, C_SC)

# ---- dCap = length(q - sc * Radius)  (distance to the rounded end) ----
q_u1 = use("q", 1350, -350)
sc_u1 = use("sc", 1200, -250)
radius_u1 = use("Radius", 1200, -150)
end_pt = expr(unreal.MaterialExpressionMultiply, 1350, -200)
_connect(sc_u1, "", end_pt, "A")
_connect(radius_u1, "", end_pt, "B")
to_end = expr(unreal.MaterialExpressionSubtract, 1500, -280)
_connect(q_u1, "", to_end, "A")
_connect(end_pt, "", to_end, "B")
d_cap = expr(unreal.MaterialExpressionLength, 1650, -280)
_connect(to_end, "", d_cap, "")

# ---- dRing = abs(length(q) - Radius)  (distance to the full circle) ----
q_u2 = use("q", 1200, 0)
q_len = expr(unreal.MaterialExpressionLength, 1350, 0)
_connect(q_u2, "", q_len, "")
radius_u2 = use("Radius", 1350, 100)
ring_sub = expr(unreal.MaterialExpressionSubtract, 1500, 50)
_connect(q_len, "", ring_sub, "A")
_connect(radius_u2, "", ring_sub, "B")
d_ring = expr(unreal.MaterialExpressionAbs, 1650, 50)
_connect(ring_sub, "", d_ring, "")

# ---- cap = step(sc.x * q.y, sc.y * q.x)  (1 when the pixel's angle is past the arc's end) ----
sc_u2 = use("sc", 1050, 250)
sc_x = mask_x(1200, 250)
_connect(sc_u2, "", sc_x, "")
q_u3 = use("q", 1050, 350)
q_ycomp = mask_y(1200, 350)
_connect(q_u3, "", q_ycomp, "")
edge_y = expr(unreal.MaterialExpressionMultiply, 1350, 300)
_connect(sc_x, "", edge_y, "A")
_connect(q_ycomp, "", edge_y, "B")
sc_u3 = use("sc", 1050, 500)
sc_y = mask_y(1200, 500)
_connect(sc_u3, "", sc_y, "")
q_u4 = use("q", 1050, 600)
q_xcomp = mask_x(1200, 600)
_connect(q_u4, "", q_xcomp, "")
edge_x = expr(unreal.MaterialExpressionMultiply, 1350, 550)
_connect(sc_y, "", edge_x, "A")
_connect(q_xcomp, "", edge_x, "B")
# UE Step(Y, X) returns 1 when X >= Y, i.e. GLSL step(edge=Y, x=X).
cap_step = expr(unreal.MaterialExpressionStep, 1500, 420)
_connect(edge_y, "", cap_step, "Y")
_connect(edge_x, "", cap_step, "X")

# ---- d = lerp(dRing, dCap, cap) - Thickness / 2 ----
d_sel = expr(unreal.MaterialExpressionLinearInterpolate, 1850, 0)
_connect(d_ring, "", d_sel, "A")
_connect(d_cap, "", d_sel, "B")
_connect(cap_step, "", d_sel, "Alpha")
thick_p = scalar_param("Thickness", 0.13, 1,
                       "Stroke width. The ends are rounded, so the arc extends half of this past both ends",
                       1850, 200)
thick_half = expr(unreal.MaterialExpressionMultiply, 2050, 200, const_b=0.5)
_connect(thick_p, "", thick_half, "A")
d_v = expr(unreal.MaterialExpressionSubtract, 2200, 50)
_connect(d_sel, "", d_v, "A")
_connect(thick_half, "", d_v, "B")
make_decl("d", d_v, 2350, 50, C_SDF)

# ---- mask = clamp(0.5 - d / aa, 0, 1)  (anti-aliased mask, 1px-wide edge) ----
d_u1 = use("d", 2550, 0)
aa_u1 = use("aa", 2550, 100)
d_over_aa = expr(unreal.MaterialExpressionDivide, 2700, 50)
_connect(d_u1, "", d_over_aa, "A")
_connect(aa_u1, "", d_over_aa, "B")
half_minus = expr(unreal.MaterialExpressionSubtract, 2850, 50, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_clamp = expr(unreal.MaterialExpressionClamp, 3000, 50, min_default=0.0, max_default=1.0)
_connect(half_minus, "", mask_clamp, "")
make_decl("mask", mask_clamp, 3150, 50, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 3400, -100,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Arc color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 3400, 150)
emissive = expr(unreal.MaterialExpressionMultiply, 3650, -50)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 3400, 350)
cov_a = expr(unreal.MaterialExpressionMultiply, 3650, 300)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 3800, 250)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

smt.set_material_root_position(mat, 4060, -70)

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "Stretch cycle\n"
         "The head stretches in the first half of each cycle, and the tail catches up in the second.\n"
         "Time has Ignore Pause on (real time), so the arc keeps turning while the game thread is blocked.",
    -4300, 500, 2050, 870, C_TM)
smt.create_comment_in_material(
    mat, "Arc direction\n"
         "Each cycle the tail lands ext further on, so the stretching itself carries the arc around.\n"
         "fract keeps the angle small, so Cosine and Sine stay accurate as Time grows.",
    -2200, 520, 2150, 670, C_UV)
smt.create_comment_in_material(
    mat, "Fold\n"
         "Turn the arc's center to 12 o'clock and fold left onto right, so one end cap serves both ends.",
    -150, -230, 1250, 560, C_UV)
smt.create_comment_in_material(
    mat, "Radius + Thickness / 2 = 0.8 by default: the outer size shared by the ring spinners.",
    480, 380, 620, 200, C_SC)
smt.create_comment_in_material(
    mat, "Arc distance (iq's sdArc)\n"
         "sc points at the arc's right end. Past it, the distance is to the rounded end; before it, to the "
         "ring.",
    1000, -430, 1500, 1120, C_SDF)

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

expected_decls = sorted(["p", "aa", "rot", "k", "u", "shrink", "ArcMin", "ext", "len", "ang", "c", "s", "sc",
                         "q", "Radius", "d", "mask"])
expected_usages = {"p": 2, "aa": 1, "rot": 1, "k": 1, "u": 2, "shrink": 2, "ArcMin": 2, "ext": 2, "len": 2,
                   "ang": 2, "c": 2, "s": 2, "sc": 3, "q": 4, "Radius": 2, "d": 1, "mask": 1}
expected_params = sorted(["Radius", "Thickness", "ArcMin", "ArcMax", "Speed", "StretchSpeed", "PrimaryColor"])
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == expected_params
groups_ok = param_groups == PARAM_GROUPS and group_prios == expected_prios
mf_ok = mf_calls == 1
comments_ok = len(smt.get_material_comment_texts(mat)) == 5
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and groups_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
