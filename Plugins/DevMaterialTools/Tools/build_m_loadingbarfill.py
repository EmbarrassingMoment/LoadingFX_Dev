"""
Progress bar -> M_LoadingBarFill (Material Domain = UI, Translucent)

横に伸びた枝(カプセル)を左から Progress(0..1)まで塗る、進捗連動(determinate)のロードバー。塗った部分の上を光の帯
(シーン)が流れるので、ローダーの進捗が段飛びで止まっている間も動いて見える。ライブラリで初めて外部入力のパラメータを
持つマテリアル: ULoadingFXProgressBar が動的インスタンスの Progress を書く(材質契約の「進捗」の項)。
デザインは 2026-10-16 のローディングバー検討から。WebGL2 のスケッチ(Saved/BarHarness/harness.html)で確かめてから組んだ。
clamp(x, 0, 1) は Saturate で書く。枝は M_LoadingBarSlide と同じ(MF_SpinnerCoords の Extent で幅いっぱい)。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  ext    = MF_SpinnerCoords.Extent                  (半幅・半高。横長なら (幅/高さ, 1))
  R      = Thickness / 2;  L = max(ext.x - 1, 0)    (枝の半分の太さと直線部の半分の長さ)
  xEnd   = L + R                                    (枝の右端。左端は xL = -xEnd)
  dTrack = length((max(abs(p.x) - L, 0), p.y)) - R  (横向きのカプセル)
  track  = saturate(0.5 - dTrack / aa)
  pr     = saturate(Progress)
  xF     = lerp(xL, xEnd, pr)                       (塗りの右端。平らな縁: Progress 1 で枝と一致、0 で幅 0)
  dFill  = max(dTrack, p.x - xF)                    (枝を縦線で切る。max の合成でも勾配は 1 以下なので AA は aa)
  fade   = saturate((xF - xL) / aa)                 (Progress が 0 近くで 1 ピクセルより細い塗りが、距離 0 の線として
                                                     0.5 の濃さで残るのを消す。M_LoadingTimer の教訓)
  fill   = saturate(0.5 - dFill / aa) * fade
  u      = fract(Time * Speed)                      (Speed はシーンの通過回数/秒、正 = 左から右へ)
  sx     = lerp(xL - SheenWidth, xEnd + SheenWidth, u)   (シーンの中心。枝の外から入って外へ抜ける)
  s      = saturate(1 - abs(p.x - sx) / SheenWidth)
  sheen  = smoothstep(0, 1, s)                      (= s^2 (3 - 2 s): 幅 2 * SheenWidth の滑らかな山)
  rgb    = lerp(PrimaryColor.rgb, 1, sheen * SheenStrength * fill)   (塗りの上だけ白へ寄せる)
  mask   = max(track * TrackOpacity, fill)

  丸い頭ではなく平らな縁にしたのは、Progress 0 付近で縮む点になるか径を潰す細工が要るため。
  シーンは「白へ寄せる」ので PrimaryColor が白のままでは見えない(色を付けたバー用。SheenStrength 0 で無効)。

  出力: FinalColor(Emissive) = rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルトの外寸は M_LoadingBarSlide と同じ(Thickness 1.6: 上下 ±0.8、両端は ±(ext.x - 0.2))。
  Progress のアセット既定値は 0.65(サムネイルとパレットで形が分かるように)。ウィジェットは実行時に上書きする。
  LoadingIconMaterial には向かない(アイコンサブシステムはパラメータを書かないので 0.65 のまま)。

  ScalarParameter / VectorParameter はグループ Input / Appearance / Shape / Motion(PARAM_GROUPS、表示順は GROUP_ORDER。
  Input は実行時に書き込む Progress だけ)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  R / L / xEnd / xL / dTrack / xF / fill / SheenWidth は 2 箇所以上で使うので Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingbarfill.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingBarFill"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "Progress": "Input",
    "PrimaryColor": "Appearance",
    "TrackOpacity": "Appearance",
    "SheenWidth": "Appearance",
    "SheenStrength": "Appearance",
    "Thickness": "Shape",
    "Speed": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / extents = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / sheen = light blue
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

# ---- R = Thickness / 2;  L = max(ext.x - 1, 0);  xEnd = L + R;  xL = -xEnd ----
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
l_u1 = use("L", -2350, -420)
r_u1 = use("R", -2350, -320)
xend_v = binary(unreal.MaterialExpressionAdd, l_u1, r_u1, -2200, -370)
make_decl("xEnd", xend_v, -2050, -370, C_SDF)
xend_u1 = use("xEnd", -1900, -370)
xneg = expr(unreal.MaterialExpressionMultiply, -1750, -370, const_b=-1.0)
_connect(xend_u1, "", xneg, "A")
make_decl("xL", xneg, -1600, -370, C_SDF)

# ---- dTrack = length((max(abs(p.x) - L, 0), p.y)) - R  (a horizontal capsule) ----
p_u1 = use("p", -2350, -850)
p_x1 = mask_x(-2200, -900)
_connect(p_u1, "", p_x1, "")
p_y1 = mask_y(-2200, -780)
_connect(p_u1, "", p_y1, "")
px_abs = expr(unreal.MaterialExpressionAbs, -2050, -900)
_connect(p_x1, "", px_abs, "")
l_u2 = use("L", -2050, -800)
qx_sub = binary(unreal.MaterialExpressionSubtract, px_abs, l_u2, -1900, -850)
qx_v = expr(unreal.MaterialExpressionMax, -1750, -850, const_b=0.0)
_connect(qx_sub, "", qx_v, "A")
q_v = binary(unreal.MaterialExpressionAppendVector, qx_v, p_y1, -1600, -820)
q_len = expr(unreal.MaterialExpressionLength, -1450, -820)
_connect(q_v, "", q_len, "")
r_u2 = use("R", -1450, -700)
dtrack_v = binary(unreal.MaterialExpressionSubtract, q_len, r_u2, -1300, -780)
make_decl("dTrack", dtrack_v, -1150, -780, C_SDF)

# ---- track = saturate(0.5 - dTrack / aa) ----
dtrack_u1 = use("dTrack", -950, -850)
aa_u1 = use("aa", -950, -750)
track_div = binary(unreal.MaterialExpressionDivide, dtrack_u1, aa_u1, -800, -800)
track_sub = expr(unreal.MaterialExpressionSubtract, -650, -800, const_a=0.5)
_connect(track_div, "", track_sub, "B")
track_sat = expr(unreal.MaterialExpressionSaturate, -500, -800)
_connect(track_sub, "", track_sat, "")
make_decl("track", track_sat, -350, -800, C_COL)

# ---- pr = saturate(Progress);  xF = lerp(xL, xEnd, pr) ----
progress_p = scalar_param("Progress", 0.65, 0,
                          "Filled fraction of the bar, 0 to 1. ULoadingFXProgressBar writes it on a dynamic instance; "
                          "the asset default only shows the shape",
                          -3300, 150)
pr_sat = expr(unreal.MaterialExpressionSaturate, -3100, 150)
_connect(progress_p, "", pr_sat, "")
xl_u1 = use("xL", -2950, 50)
xend_u2 = use("xEnd", -2950, 150)
xf_v = expr(unreal.MaterialExpressionLinearInterpolate, -2800, 100)
_connect(xl_u1, "", xf_v, "A")
_connect(xend_u2, "", xf_v, "B")
_connect(pr_sat, "", xf_v, "Alpha")
make_decl("xF", xf_v, -2650, 100, C_SDF)

# ---- dFill = max(dTrack, p.x - xF);  fade = saturate((xF - xL) / aa);  fill = saturate(0.5 - dFill / aa) * fade ----
p_u2 = use("p", -2450, 250)
p_x2 = mask_x(-2300, 250)
_connect(p_u2, "", p_x2, "")
xf_u1 = use("xF", -2300, 350)
cut_v = binary(unreal.MaterialExpressionSubtract, p_x2, xf_u1, -2150, 300)      # p.x - xF
dtrack_u2 = use("dTrack", -2150, 180)
dfill_v = binary(unreal.MaterialExpressionMax, dtrack_u2, cut_v, -2000, 250)
aa_u2 = use("aa", -2000, 380)
fill_div = binary(unreal.MaterialExpressionDivide, dfill_v, aa_u2, -1850, 300)
fill_sub = expr(unreal.MaterialExpressionSubtract, -1700, 300, const_a=0.5)
_connect(fill_div, "", fill_sub, "B")
fill_sat = expr(unreal.MaterialExpressionSaturate, -1550, 300)
_connect(fill_sub, "", fill_sat, "")
xf_u2 = use("xF", -2000, 550)
xl_u2 = use("xL", -2000, 650)
width_v = binary(unreal.MaterialExpressionSubtract, xf_u2, xl_u2, -1850, 600)
aa_u3 = use("aa", -1850, 720)
fade_div = binary(unreal.MaterialExpressionDivide, width_v, aa_u3, -1700, 650)
fade_sat = expr(unreal.MaterialExpressionSaturate, -1550, 650)
_connect(fade_div, "", fade_sat, "")
fill_v = binary(unreal.MaterialExpressionMultiply, fill_sat, fade_sat, -1400, 450)
make_decl("fill", fill_v, -1250, 450, C_COL)

# ---- u = fract(Time * Speed);  sx = lerp(xL - SheenWidth, xEnd + SheenWidth, u) ----
time_n = expr(unreal.MaterialExpressionTime, -3300, 900)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.5, 0, "Sheen sweeps per second over the filled part. Positive = left to right, 0 = none", -3300, 1020)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3100, 950)
u_frac = expr(unreal.MaterialExpressionFrac, -2950, 950)
_connect(t_speed, "", u_frac, "")
sheenw_p = scalar_param("SheenWidth", 1.5, 2, "Half width of the sheen (half the shorter widget side = 1.0)", -3300, 1200)
make_decl("SheenWidth", sheenw_p, -3100, 1200, C_TM)
xl_u3 = use("xL", -2950, 1080)
sw_u1 = use("SheenWidth", -2950, 1180)
sx_from = binary(unreal.MaterialExpressionSubtract, xl_u3, sw_u1, -2800, 1130)
xend_u3 = use("xEnd", -2950, 1300)
sw_u2 = use("SheenWidth", -2950, 1400)
sx_to = binary(unreal.MaterialExpressionAdd, xend_u3, sw_u2, -2800, 1350)
sx_v = expr(unreal.MaterialExpressionLinearInterpolate, -2650, 1150)
_connect(sx_from, "", sx_v, "A")
_connect(sx_to, "", sx_v, "B")
_connect(u_frac, "", sx_v, "Alpha")

# ---- s = saturate(1 - abs(p.x - sx) / SheenWidth);  sheen = smoothstep(0, 1, s) ----
p_u3 = use("p", -2500, 1000)
p_x3 = mask_x(-2350, 1000)
_connect(p_u3, "", p_x3, "")
dx_v = binary(unreal.MaterialExpressionSubtract, p_x3, sx_v, -2200, 1100)
dx_abs = expr(unreal.MaterialExpressionAbs, -2050, 1100)
_connect(dx_v, "", dx_abs, "")
sw_u3 = use("SheenWidth", -2050, 1220)
s_div = binary(unreal.MaterialExpressionDivide, dx_abs, sw_u3, -1900, 1150)
s_inv = expr(unreal.MaterialExpressionOneMinus, -1750, 1150)
_connect(s_div, "", s_inv, "")
s_sat = expr(unreal.MaterialExpressionSaturate, -1600, 1150)
_connect(s_inv, "", s_sat, "")
sheen_ss = expr(unreal.MaterialExpressionSmoothStep, -1450, 1150, const_min=0.0, const_max=1.0)
_connect(s_sat, "", sheen_ss, "Value")

# ---- rgb = lerp(PrimaryColor.rgb, 1, sheen * SheenStrength * fill) ----
sheens_p = scalar_param("SheenStrength", 0.5, 3,
                        "How far the sheen pushes the fill toward white (0 = no sheen). Invisible on a white PrimaryColor",
                        -1450, 1300)
sheen_amt = binary(unreal.MaterialExpressionMultiply, sheen_ss, sheens_p, -1250, 1200)
fill_u1 = use("fill", -1250, 1320)
sheen_fill = binary(unreal.MaterialExpressionMultiply, sheen_amt, fill_u1, -1100, 1250)
primary_p = expr(unreal.MaterialExpressionVectorParameter, -1100, 900,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Bar color (alpha scales the opacity)")
white_c = expr(unreal.MaterialExpressionConstant3Vector, -1100, 1080, constant=unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
rgb_v = expr(unreal.MaterialExpressionLinearInterpolate, -850, 1050)
_connect(primary_p, "", rgb_v, "A")
_connect(white_c, "", rgb_v, "B")
_connect(sheen_fill, "", rgb_v, "Alpha")

# ---- mask = max(track * TrackOpacity, fill) ----
track_u1 = use("track", -1000, 450)
trackop_p = scalar_param("TrackOpacity", 0.25, 1, "Opacity of the unfilled part of the bar (0 hides it)", -1000, 550)
track_dim = binary(unreal.MaterialExpressionMultiply, track_u1, trackop_p, -800, 500)
fill_u2 = use("fill", -800, 650)
mask_v = binary(unreal.MaterialExpressionMax, track_dim, fill_u2, -650, 550)
make_decl("mask", mask_v, -500, 550, C_COL)

# ---- Output: FinalColor = rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
vcolor = expr(unreal.MaterialExpressionVertexColor, -500, 800)
emissive = binary(unreal.MaterialExpressionMultiply, rgb_v, vcolor, -250, 900)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", -250, 600)
cov_a = expr(unreal.MaterialExpressionMultiply, -50, 650)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 100, 700)
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
    mat, "R = Thickness / 2;  L = max(ext.x - 1, 0);  xEnd = L + R;  xL = -xEnd\n"
         "The track is inset by (1 - R) on every side: Thickness 1.6 reaches +-0.8 (the contract's reference circle)\n"
         "and leaves 0.2 at the ends; Thickness 2 fills the widget. A square widget gives a circle (L = 0)",
    -3350, -420, 1850, 300, C_SDF)
smt.create_comment_in_material(
    mat, "dTrack = length((max(abs(p.x) - L, 0), p.y)) - R   (horizontal capsule, exact distance)\n"
         "track = saturate(0.5 - dTrack / aa)",
    -2400, -960, 2150, 300, C_SDF)
smt.create_comment_in_material(
    mat, "Progress (0..1) is the material contract's determinate input: ULoadingFXProgressBar writes it on a dynamic instance\n"
         "xF = lerp(xL, xEnd, saturate(Progress))   (the fill's flat right edge: exactly the track at 1, nothing at 0)",
    -3350, 0, 900, 300, C_SDF)
smt.create_comment_in_material(
    mat, "dFill = max(dTrack, p.x - xF)   (the track cut at xF; still 1-Lipschitz, so AA = aa)\n"
         "fade = saturate((xF - xL) / aa): a fill thinner than a pixel would keep 0.5 coverage on its line (the Timer lesson)\n"
         "fill = saturate(0.5 - dFill / aa) * fade",
    -2500, 100, 1400, 750, C_COL)
smt.create_comment_in_material(
    mat, "Sheen: u = fract(Time * Speed);  sx = lerp(xL - SheenWidth, xEnd + SheenWidth, u)   (enters from outside, leaves outside)\n"
         "s = saturate(1 - abs(p.x - sx) / SheenWidth);  sheen = smoothstep(0, 1, s)\n"
         "Time ignores pause (real time). Speed 0 turns the sheen off",
    -3350, 820, 1750, 700, C_TM)
smt.create_comment_in_material(
    mat, "rgb = lerp(PrimaryColor.rgb, white, sheen * SheenStrength * fill)   (only the filled part brightens;\n"
         "invisible while PrimaryColor is white)\n"
         "mask = max(track * TrackOpacity, fill)",
    -1500, 820, 900, 700, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    -550, 520, 800, 500, C_COL)

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
expected_decls = sorted(["p", "aa", "R", "L", "xEnd", "xL", "dTrack", "track", "xF", "fill", "SheenWidth", "mask"])
expected_usages = {"p": 3, "aa": 3, "R": 2, "L": 2, "xEnd": 3, "xL": 3, "dTrack": 2, "track": 1, "xF": 2,
                   "fill": 2, "SheenWidth": 3, "mask": 1}
expected_params = sorted(["Progress", "Thickness", "Speed", "SheenWidth", "SheenStrength", "TrackOpacity", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 8
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
