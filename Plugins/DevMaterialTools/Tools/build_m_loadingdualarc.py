"""
Counter-rotating arc pairs -> M_LoadingDualArc (Material Domain = UI, Translucent)

外側と内側の 2 本のリングに、それぞれ向かい合う角丸の弧を 2 本ずつ置き、外側は時計回り、内側は逆向きに回すロードアイコン。
1 色(PrimaryColor)だけで描く(2026-10-11 ユーザー指示。スピナー案の段階では内側が SecondaryColor だった)。
各リングは弧の中心が真上を向くよう座標を回転し、x と y の両方を abs で折り返すので、向かい合う 2 本の弧も
iq の sdArc 1 回で済む。リング 2 本で 2 回評価するだけでループも分岐もない。

  p     = MF_SpinnerCoords.P                        (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa    = MF_SpinnerCoords.PixelSize                (1 ピクセルを p 単位で)
  rotO  = fract(Time * Speed)                       (外側の弧の向き。12 時から時計回りの回転数。Speed は回転数/秒、正 = 時計回り)
  rotI  = fract(Time * Speed * InnerSpeedRatio + 0.25)
                                                    (内側。InnerSpeedRatio が負なら逆回転。+0.25 で開始時に外側と直交)
  sc    = (sin(Arc * PI), cos(Arc * PI))            (弧の右端の向き。Arc * PI は半開き角。Arc は 1 本の弧の長さ、回転数)
  リングごと(rot, R):
    c, s = cos(rot * TAU), sin(rot * TAU)
    q    = abs((c*p.x - s*p.y, s*p.x + c*p.y))      (弧の中心を真上へ回し、左右と上下を折り返す: 向かい合う弧が重なる)
    dArc = (sc.y * q.x >= sc.x * q.y ? length(q - sc * R) : abs(length(q) - R))
                                                    (端点より外側の角度なら端点、内側なら円周。Step + Lerp で分岐なし)
  dO, dI = 外側(rotO, OuterRadius)と内側(rotI, InnerRadius)の dArc
  d     = min(dO, dI) - Thickness / 2
  mask  = clamp(0.5 - d / aa, 0, 1)

  上下の折り返しは弧が半周以内(Arc <= 0.5)なら正しい。Arc = 0.5 で各リングは全周になる。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は OuterRadius + Thickness/2 = 0.8(材質契約の基準円。1.0 = 短辺の端)に合わせてある。

  ScalarParameter / VectorParameter のグループは Appearance / Shape / Motion(PARAM_GROUPS、順序は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  OuterRadius(2 箇所)と InnerRadius(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。
  2 本のリングは同じ構造のノード列(ring() で生成)を上下に並べたもの。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingdualarc.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingDualArc"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
PI = 3.14159265359
TAU = 6.28318530718
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "OuterRadius": "Shape",
    "InnerRadius": "Shape",
    "Thickness": "Shape",
    "Arc": "Shape",
    "Speed": "Motion",
    "InnerSpeedRatio": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles / rotation = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time = light blue
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
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3100, -1100, material_function=mf_coords)
make_decl("p", coords, -2800, -1150, C_UV, "P")
make_decl("aa", coords, -2800, -1030, C_SDF, "PixelSize")

# ---- rotO = fract(Time * Speed);  rotI = fract(Time * Speed * InnerSpeedRatio + 0.25) ----
time_n = expr(unreal.MaterialExpressionTime, -3100, -250)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.7, 0, "Revolutions per second of the outer arcs. Positive = clockwise",
                       -3100, -130)
t_speed = expr(unreal.MaterialExpressionMultiply, -2900, -200)
_connect(time_n, "", t_speed, "A")
_connect(speed_p, "", t_speed, "B")
rot_o = expr(unreal.MaterialExpressionFrac, -2700, -280)
_connect(t_speed, "", rot_o, "")
make_decl("rotO", rot_o, -2550, -280, C_TM)
ratio_p = scalar_param("InnerSpeedRatio", -1.3, 1,
                       "Speed of the inner arcs as a multiple of Speed. Negative = they turn the other way",
                       -2900, 0)
t_inner = expr(unreal.MaterialExpressionMultiply, -2700, -50)
_connect(t_speed, "", t_inner, "A")
_connect(ratio_p, "", t_inner, "B")
t_offset = expr(unreal.MaterialExpressionAdd, -2550, -50, const_b=0.25)   # starts at right angles to the outer pair
_connect(t_inner, "", t_offset, "A")
rot_i = expr(unreal.MaterialExpressionFrac, -2400, -50)
_connect(t_offset, "", rot_i, "")
make_decl("rotI", rot_i, -2250, -50, C_TM)

# ---- sc = (sin(Arc * PI), cos(Arc * PI))  (direction of an arc's right end; Arc * PI is the half aperture) ----
arc_p = scalar_param("Arc", 0.28, 3,
                     "Length of each arc, in turns (0..0.5; 0.5 closes each ring)", -3100, 350)
half_ap = expr(unreal.MaterialExpressionMultiply, -2900, 350, const_b=PI)
_connect(arc_p, "", half_ap, "A")
ap_sin = expr(unreal.MaterialExpressionSine, -2750, 300, period=TAU)   # period 2*PI = radians
_connect(half_ap, "", ap_sin, "")
ap_cos = expr(unreal.MaterialExpressionCosine, -2750, 420, period=TAU)
_connect(half_ap, "", ap_cos, "")
sc_v = expr(unreal.MaterialExpressionAppendVector, -2600, 350)
_connect(ap_sin, "", sc_v, "A")
_connect(ap_cos, "", sc_v, "B")
make_decl("sc", sc_v, -2450, 350, C_UV)

def ring(tag, rot_name, radius_name, radius_default, radius_sort, radius_desc, y0):
    """One ring: rotate so the arc pair's center points up, fold both axes, then iq's sdArc. Declares q<tag>,
    <radius_name> and d<tag> (the unsigned distance to the ring's arcs)."""
    # ---- c, s = cos(rot * TAU), sin(rot * TAU) ----
    rot_u = use(rot_name, -1650, y0 + 200)
    ang = expr(unreal.MaterialExpressionMultiply, -1500, y0 + 200, const_b=TAU)
    _connect(rot_u, "", ang, "A")
    ang_cos = expr(unreal.MaterialExpressionCosine, -1350, y0 + 150, period=TAU)
    _connect(ang, "", ang_cos, "")
    ang_sin = expr(unreal.MaterialExpressionSine, -1350, y0 + 270, period=TAU)
    _connect(ang, "", ang_sin, "")

    # ---- q = abs((c*p.x - s*p.y, s*p.x + c*p.y)) ----
    s_neg = expr(unreal.MaterialExpressionMultiply, -1200, y0 + 270, const_b=-1.0)
    _connect(ang_sin, "", s_neg, "A")
    row_x = expr(unreal.MaterialExpressionAppendVector, -1050, y0 + 180)    # (c, -s)
    _connect(ang_cos, "", row_x, "A")
    _connect(s_neg, "", row_x, "B")
    row_y = expr(unreal.MaterialExpressionAppendVector, -1050, y0 + 320)    # (s, c)
    _connect(ang_sin, "", row_y, "A")
    _connect(ang_cos, "", row_y, "B")
    p_u1 = use("p", -1050, y0 + 30)
    q_x = expr(unreal.MaterialExpressionDotProduct, -900, y0 + 100)
    _connect(p_u1, "", q_x, "A")
    _connect(row_x, "", q_x, "B")
    p_u2 = use("p", -1050, y0 + 450)
    q_y = expr(unreal.MaterialExpressionDotProduct, -900, y0 + 380)
    _connect(p_u2, "", q_y, "A")
    _connect(row_y, "", q_y, "B")
    q_app = expr(unreal.MaterialExpressionAppendVector, -750, y0 + 240)
    _connect(q_x, "", q_app, "A")
    _connect(q_y, "", q_app, "B")
    q_abs = expr(unreal.MaterialExpressionAbs, -600, y0 + 240)
    _connect(q_app, "", q_abs, "")
    q_name = f"q{tag}"
    make_decl(q_name, q_abs, -450, y0 + 240, C_UV)

    radius_p = scalar_param(radius_name, radius_default, radius_sort, radius_desc, -450, y0 + 450)
    make_decl(radius_name, radius_p, -200, y0 + 450, C_SC)

    # ---- dCap = length(q - sc * R)  (distance to the rounded end) ----
    q_u1 = use(q_name, -100, y0)
    sc_u1 = use("sc", -100, y0 + 100)
    r_u1 = use(radius_name, -100, y0 + 200)
    end_pt = expr(unreal.MaterialExpressionMultiply, 50, y0 + 150)
    _connect(sc_u1, "", end_pt, "A")
    _connect(r_u1, "", end_pt, "B")
    to_end = expr(unreal.MaterialExpressionSubtract, 200, y0 + 50)
    _connect(q_u1, "", to_end, "A")
    _connect(end_pt, "", to_end, "B")
    d_cap = expr(unreal.MaterialExpressionLength, 350, y0 + 50)
    _connect(to_end, "", d_cap, "")

    # ---- dRing = abs(length(q) - R)  (distance to the full circle) ----
    q_u2 = use(q_name, -100, y0 + 300)
    q_len = expr(unreal.MaterialExpressionLength, 50, y0 + 300)
    _connect(q_u2, "", q_len, "")
    r_u2 = use(radius_name, 50, y0 + 400)
    ring_sub = expr(unreal.MaterialExpressionSubtract, 200, y0 + 350)
    _connect(q_len, "", ring_sub, "A")
    _connect(r_u2, "", ring_sub, "B")
    d_ring = expr(unreal.MaterialExpressionAbs, 350, y0 + 350)
    _connect(ring_sub, "", d_ring, "")

    # ---- cap = step(sc.x * q.y, sc.y * q.x)  (1 when the pixel's angle is past the arc's end) ----
    sc_u2 = use("sc", -100, y0 + 500)
    sc_x = mask_x(50, y0 + 500)
    _connect(sc_u2, "", sc_x, "")
    q_u3 = use(q_name, -100, y0 + 600)
    q_ycomp = mask_y(50, y0 + 600)
    _connect(q_u3, "", q_ycomp, "")
    edge_y = expr(unreal.MaterialExpressionMultiply, 200, y0 + 550)
    _connect(sc_x, "", edge_y, "A")
    _connect(q_ycomp, "", edge_y, "B")
    sc_u3 = use("sc", -100, y0 + 720)
    sc_y = mask_y(50, y0 + 720)
    _connect(sc_u3, "", sc_y, "")
    q_u4 = use(q_name, -100, y0 + 820)
    q_xcomp = mask_x(50, y0 + 820)
    _connect(q_u4, "", q_xcomp, "")
    edge_x = expr(unreal.MaterialExpressionMultiply, 200, y0 + 770)
    _connect(sc_y, "", edge_x, "A")
    _connect(q_xcomp, "", edge_x, "B")
    # UE Step(Y, X) returns 1 when X >= Y, i.e. GLSL step(edge=Y, x=X).
    cap_step = expr(unreal.MaterialExpressionStep, 350, y0 + 650)
    _connect(edge_y, "", cap_step, "Y")
    _connect(edge_x, "", cap_step, "X")

    # ---- dArc = lerp(dRing, dCap, cap) ----
    d_sel = expr(unreal.MaterialExpressionLinearInterpolate, 550, y0 + 200)
    _connect(d_ring, "", d_sel, "A")
    _connect(d_cap, "", d_sel, "B")
    _connect(cap_step, "", d_sel, "Alpha")
    make_decl(f"d{tag}", d_sel, 700, y0 + 200, C_SDF)

# Footprint (material contract): OuterRadius + Thickness / 2 = 0.8, the reference circle.
ring("O", "rotO", "OuterRadius", 0.745, 0,
     "Distance from the center to the middle of the outer arcs (half the shorter widget side = 1.0)", -950)
ring("I", "rotI", "InnerRadius", 0.47, 1, "Distance from the center to the middle of the inner arcs", 250)

# ---- d = min(dO, dI) - Thickness / 2 ----
do_u1 = use("dO", 1000, -100)
di_u1 = use("dI", 1000, 0)
d_min = expr(unreal.MaterialExpressionMin, 1150, -50)
_connect(do_u1, "", d_min, "A")
_connect(di_u1, "", d_min, "B")
thick_p = scalar_param("Thickness", 0.11, 2,
                       "Stroke width of every arc. The ends are rounded, so each arc extends half of this past both ends",
                       1000, 150)
thick_half = expr(unreal.MaterialExpressionMultiply, 1150, 150, const_b=0.5)
_connect(thick_p, "", thick_half, "A")
d_v = expr(unreal.MaterialExpressionSubtract, 1300, 0)
_connect(d_min, "", d_v, "A")
_connect(thick_half, "", d_v, "B")
make_decl("d", d_v, 1450, 0, C_SDF)

# ---- mask = clamp(0.5 - d / aa, 0, 1)  (anti-aliased mask, 1px-wide edge) ----
d_u1 = use("d", 1650, -50)
aa_u1 = use("aa", 1650, 50)
d_over_aa = expr(unreal.MaterialExpressionDivide, 1800, 0)
_connect(d_u1, "", d_over_aa, "A")
_connect(aa_u1, "", d_over_aa, "B")
half_minus = expr(unreal.MaterialExpressionSubtract, 1950, 0, const_a=0.5)
_connect(d_over_aa, "", half_minus, "B")
mask_clamp = expr(unreal.MaterialExpressionClamp, 2100, 0, min_default=0.0, max_default=1.0)
_connect(half_minus, "", mask_clamp, "")
make_decl("mask", mask_clamp, 2250, 0, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2450, -150,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Color of both rings (alpha scales the opacity)")
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

smt.set_material_root_position(mat, 3110, -120)

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "Rotation\n"
         "The inner pair starts at right angles to the outer one.\n"
         "Time has Ignore Pause on (real time), so the spinner keeps turning while the game thread is blocked.",
    -3150,  - 420, 1050, 580, C_TM)
smt.create_comment_in_material(
    mat, "Outer ring (iq's sdArc)\n"
         "Turn the pair's center to 12 o'clock and fold both axes, so the opposite arc lands on this one.\n"
         "sc points at the arc's right end. Past it, the distance is to the rounded end; before it, to the "
         "ring.\n"
         "OuterRadius + Thickness / 2 = 0.8 by default: the outer size shared by the ring spinners.",
    -1700,  - 1090, 2550, 1060, C_SDF)
smt.create_comment_in_material(
    mat, "Inner ring: the same nodes as the outer ring.",
    -1700, 120, 2550, 1050, C_SDF)
smt.create_comment_in_material(
    mat, "One color, so the rings merge before anti-aliasing.",
    950, -200, 650, 450, C_SDF)

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

expected_decls = sorted(["p", "aa", "rotO", "rotI", "sc", "qO", "OuterRadius", "dO", "qI", "InnerRadius", "dI",
                         "d", "mask"])
expected_usages = {"p": 4, "aa": 1, "rotO": 1, "rotI": 1, "sc": 6, "qO": 4, "OuterRadius": 2, "dO": 1,
                   "qI": 4, "InnerRadius": 2, "dI": 1, "d": 1, "mask": 1}
expected_params = sorted(["OuterRadius", "InnerRadius", "Thickness", "Arc", "Speed", "InnerSpeedRatio",
                          "PrimaryColor"])
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == expected_params
groups_ok = param_groups == PARAM_GROUPS and group_prios == expected_prios
mf_ok = mf_calls == 1
comments_ok = len(smt.get_material_comment_texts(mat)) == 4
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and groups_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
