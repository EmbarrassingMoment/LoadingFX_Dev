"""
Striped bar -> M_LoadingBarStripes (Material Domain = UI, Translucent)

横に伸びた枝(カプセル)全体を 45° の縞が右へ流れる不定(indeterminate)のロードバー(床屋のサインポール、Bootstrap の
striped progress bar 風)。デザインは 2026-10-16 のローディングバー検討から。WebGL2 のスケッチ(Saved/BarHarness/harness.html)
で確かめてから組んだ。縞は 1 本の三角波の距離で描くのでループも分岐もない。clamp(x, 0, 1) は Saturate で書く。
枝は M_LoadingBarSlide と同じ(MF_SpinnerCoords の Extent で幅いっぱい)。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  ext    = MF_SpinnerCoords.Extent                  (半幅・半高。横長なら (幅/高さ, 1))
  R      = Thickness / 2;  L = max(ext.x - 1, 0)    (枝の半分の太さと直線部の半分の長さ。M_LoadingBarSlide と同じ)
  dTrack = length((max(abs(p.x) - L, 0), p.y)) - R  (横向きのカプセル)
  track  = saturate(0.5 - dTrack / aa)
  t      = (p.x - p.y) / Period - Time * Speed      (縞の座標。p.x - p.y = const の線は y 上向きで "/" の向き。
                                                     Speed は 1 秒に流れる縞の本数、正 = 右へ)
  tc     = fract(t) - 0.5                           (縞 1 本分を -0.5..0.5 に。縞の中心が 0、折り返しはすき間の中央)
  dt     = abs(tc) - Duty / 2                       (縞の縁までの符号付き距離、t 単位。三角波なので折り返しでも連続)
  aat    = aa * sqrt(2) / Period                    (1 ピクセルを t 単位で。|grad t| = sqrt(2) / Period)
  stripe = saturate(0.5 - dt / aat)
  mask   = track * lerp(TrackOpacity, 1, stripe)    (縞の間は枝の色、縞は PrimaryColor)

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルトの外寸は M_LoadingBarSlide と同じ(Thickness 1.6: 上下 ±0.8、両端は ±(ext.x - 0.2))。
  Period は p 単位(枝の高さが 2.0)。既定の 1.6 で縞の周期は高さの 0.8 倍。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(PARAM_GROUPS、表示順は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  R / L / Period は 2 箇所で使うので Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingbarstripes.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingBarStripes"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
SQRT2 = 1.41421356237
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "TrackOpacity": "Appearance",
    "Thickness": "Shape",
    "Period": "Shape",
    "Duty": "Shape",
    "Speed": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / extents = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / stripe motion = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # scalar intermediates / params = gray
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
                parameter_name=name, default_value=default, group=PARAM_GROUPS[name],
                sort_priority=sort, desc=desc)

def binary(cls, a, b, x, y):
    n = expr(cls, x, y)
    _connect(a, "", n, "A")
    _connect(b, "", n, "B")
    return n

def mask_x(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=True, g=False, b=False, a=False)

def mask_y(x, y):
    return expr(unreal.MaterialExpressionComponentMask, x, y, r=False, g=True, b=False, a=False)

# ---- p = MF_SpinnerCoords.P, aa = PixelSize, ext = Extent  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3300, -700, material_function=mf_coords)
make_decl("p", coords, -3000, -800, C_UV, "P")
make_decl("aa", coords, -3000, -680, C_SDF, "PixelSize")
ext_x = mask_x(-3000, -560)
_connect(coords, "Extent", ext_x, "")

# ---- R = Thickness / 2;  L = max(ext.x - 1, 0) ----
# Footprint (material contract): the track is inset by (1 - R) on every side, so with Thickness 1.6 it reaches +-0.8
# across the shorter side and stops 0.2 short of the longer side's edge. Thickness 2 fills the whole widget.
thick_p = scalar_param("Thickness", 1.6, 0,
                       "Height of the bar (half the shorter widget side = 1.0; 2.0 fills the widget). The ends are rounded",
                       -3300, -300)
r_v = expr(unreal.MaterialExpressionMultiply, -3100, -300, const_b=0.5)
_connect(thick_p, "", r_v, "A")
make_decl("R", r_v, -2950, -300, C_SDF)
ext_m1 = expr(unreal.MaterialExpressionSubtract, -2800, -560, const_b=1.0)
_connect(ext_x, "", ext_m1, "A")
l_v = expr(unreal.MaterialExpressionMax, -2650, -560, const_b=0.0)
_connect(ext_m1, "", l_v, "A")
make_decl("L", l_v, -2500, -560, C_SDF)

# ---- dTrack = length((max(abs(p.x) - L, 0), p.y)) - R  (a horizontal capsule) ----
p_u1 = use("p", -2350, -850)
p_x1 = mask_x(-2200, -900)
_connect(p_u1, "", p_x1, "")
p_y1 = mask_y(-2200, -780)
_connect(p_u1, "", p_y1, "")
px_abs = expr(unreal.MaterialExpressionAbs, -2050, -900)
_connect(p_x1, "", px_abs, "")
l_u1 = use("L", -2050, -800)
qx_sub = binary(unreal.MaterialExpressionSubtract, px_abs, l_u1, -1900, -850)
qx_v = expr(unreal.MaterialExpressionMax, -1750, -850, const_b=0.0)
_connect(qx_sub, "", qx_v, "A")
q_v = binary(unreal.MaterialExpressionAppendVector, qx_v, p_y1, -1600, -820)
q_len = expr(unreal.MaterialExpressionLength, -1450, -820)
_connect(q_v, "", q_len, "")
r_u1 = use("R", -1450, -700)
dtrack_v = binary(unreal.MaterialExpressionSubtract, q_len, r_u1, -1300, -780)

# ---- track = saturate(0.5 - dTrack / aa) ----
aa_u1 = use("aa", -1300, -650)
track_div = binary(unreal.MaterialExpressionDivide, dtrack_v, aa_u1, -1150, -720)
track_sub = expr(unreal.MaterialExpressionSubtract, -1000, -720, const_a=0.5)
_connect(track_div, "", track_sub, "B")
track_sat = expr(unreal.MaterialExpressionSaturate, -850, -720)
_connect(track_sub, "", track_sat, "")
make_decl("track", track_sat, -700, -720, C_COL)

# ---- t = (p.x - p.y) / Period - Time * Speed ----
period_p = scalar_param("Period", 1.6, 1,
                        "Distance between stripes along the bar (half the shorter widget side = 1.0; the bar is 2.0 high)",
                        -3300, 500)
make_decl("Period", period_p, -3100, 500, C_SC)
p_u2 = use("p", -2800, 150)
p_x2 = mask_x(-2650, 100)
_connect(p_u2, "", p_x2, "")
p_y2 = mask_y(-2650, 220)
_connect(p_u2, "", p_y2, "")
diag_v = binary(unreal.MaterialExpressionSubtract, p_x2, p_y2, -2500, 150)     # p.x - p.y: "/" stripes
period_u1 = use("Period", -2500, 280)
diag_div = binary(unreal.MaterialExpressionDivide, diag_v, period_u1, -2350, 200)
time_n = expr(unreal.MaterialExpressionTime, -2800, 400)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 1.0, 0, "Stripes passing per second. Positive = the stripes run to the right", -2800, 520)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -2600, 450)
t_v = binary(unreal.MaterialExpressionSubtract, diag_div, t_speed, -2200, 300)

# ---- tc = fract(t) - 0.5;  dt = abs(tc) - Duty / 2 ----
t_frac = expr(unreal.MaterialExpressionFrac, -2050, 300)
_connect(t_v, "", t_frac, "")
tc_v = expr(unreal.MaterialExpressionSubtract, -1900, 300, const_b=0.5)
_connect(t_frac, "", tc_v, "A")
tc_abs = expr(unreal.MaterialExpressionAbs, -1750, 300)
_connect(tc_v, "", tc_abs, "")
duty_p = scalar_param("Duty", 0.5, 2, "Width of a stripe as a fraction of Period (0.5 = stripes and gaps alike)", -1900, 450)
duty_half = expr(unreal.MaterialExpressionMultiply, -1700, 450, const_b=0.5)
_connect(duty_p, "", duty_half, "A")
dt_v = binary(unreal.MaterialExpressionSubtract, tc_abs, duty_half, -1550, 350)

# ---- aat = aa * sqrt(2) / Period;  stripe = saturate(0.5 - dt / aat) ----
aa_u2 = use("aa", -1900, 650)
aa_diag = expr(unreal.MaterialExpressionMultiply, -1750, 650, const_b=SQRT2)
_connect(aa_u2, "", aa_diag, "A")
period_u2 = use("Period", -1750, 770)
aat_v = binary(unreal.MaterialExpressionDivide, aa_diag, period_u2, -1600, 700)
stripe_div = binary(unreal.MaterialExpressionDivide, dt_v, aat_v, -1400, 400)
stripe_sub = expr(unreal.MaterialExpressionSubtract, -1250, 400, const_a=0.5)
_connect(stripe_div, "", stripe_sub, "B")
stripe_sat = expr(unreal.MaterialExpressionSaturate, -1100, 400)
_connect(stripe_sub, "", stripe_sat, "")

# ---- mask = track * lerp(TrackOpacity, 1, stripe) ----
trackop_p = scalar_param("TrackOpacity", 0.25, 1, "Opacity of the bar between the stripes (0 leaves only the stripes)", -1100, 600)
level_v = expr(unreal.MaterialExpressionLinearInterpolate, -900, 450, const_b=1.0)
_connect(trackop_p, "", level_v, "A")
_connect(stripe_sat, "", level_v, "Alpha")
track_u1 = use("track", -900, 250)
mask_v = binary(unreal.MaterialExpressionMultiply, track_u1, level_v, -700, 350)
make_decl("mask", mask_v, -550, 350, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, -300, -300,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Bar color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, -300, -50)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, -50, -250)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", -300, 150)
cov_a = expr(unreal.MaterialExpressionMultiply, -50, 150)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 100, 100)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in p units)\n"
         "ext.x = MF_SpinnerCoords.Extent.x   (half width in p units: the bar spans the widget)",
    -3350, -900, 700, 450, C_UV)
smt.create_comment_in_material(
    mat, "R = Thickness / 2;  L = max(ext.x - 1, 0)\n"
         "The track is inset by (1 - R) on every side: Thickness 1.6 reaches +-0.8 (the contract's reference circle)\n"
         "and leaves 0.2 at the ends; Thickness 2 fills the widget. A square widget gives a circle (L = 0)",
    -3350, -420, 1000, 300, C_SDF)
smt.create_comment_in_material(
    mat, "dTrack = length((max(abs(p.x) - L, 0), p.y)) - R   (horizontal capsule, exact distance)\n"
         "track = saturate(0.5 - dTrack / aa)",
    -2400, -960, 1850, 400, C_SDF)
smt.create_comment_in_material(
    mat, "t = (p.x - p.y) / Period - Time * Speed   (lines p.x - p.y = const lean like '/'; Speed in stripes per second, positive runs right)\n"
         "Time ignores pause (real time), so the stripes keep moving while the game thread is blocked",
    -2850, 50, 1150, 550, C_TM)
smt.create_comment_in_material(
    mat, "tc = fract(t) - 0.5;  dt = abs(tc) - Duty / 2   (signed distance to the stripe in t units; a triangle wave, so continuous at the wrap)\n"
         "aat = aa * sqrt(2) / Period   (one pixel in t units: |grad t| = sqrt(2) / Period)\n"
         "stripe = saturate(0.5 - dt / aat);  mask = track * lerp(TrackOpacity, 1, stripe)",
    -2100, 200, 1650, 650, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    -350, -420, 650, 700, C_COL)

used_groups = [g for g in GROUP_ORDER if g in PARAM_GROUPS.values()]
smt.set_parameter_group_sort_priorities(mat, used_groups, list(range(len(used_groups))))

mel.recompile_material(mat)
saved = lib.save_asset(FULL_PATH)
print(f"[TEST] Saved: {FULL_PATH} -> {saved}")

# ---- Verification ----
decl_names, usage_count, params, param_groups, mf_calls = [], {}, [], {}, 0
for e in smt.get_material_expressions(mat):
    if isinstance(e, unreal.MaterialExpressionNamedRerouteDeclaration):
        decl_names.append(str(e.get_editor_property("name")))
    elif isinstance(e, unreal.MaterialExpressionNamedRerouteUsage):
        nm = smt.get_named_reroute_usage_display_name(e)
        usage_count[nm] = usage_count.get(nm, 0) + 1
    elif isinstance(e, (unreal.MaterialExpressionScalarParameter, unreal.MaterialExpressionVectorParameter)):
        params.append(str(e.get_editor_property("parameter_name")))
        param_groups[params[-1]] = str(e.get_editor_property("group"))
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
expected_decls = sorted(["p", "aa", "R", "L", "track", "Period", "mask"])
expected_usages = {"p": 2, "aa": 2, "R": 1, "L": 1, "track": 1, "Period": 2, "mask": 1}
expected_params = sorted(["Thickness", "Period", "Speed", "Duty", "TrackOpacity", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 6
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
