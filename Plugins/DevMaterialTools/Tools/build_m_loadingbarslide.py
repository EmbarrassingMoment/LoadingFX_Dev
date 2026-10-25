"""
Sliding bar -> M_LoadingBarSlide (Material Domain = UI, Translucent)

横に伸びた枝(カプセル)の中を、短い帯が左端から現れて伸び、右へ走って縮みながら抜ける不定(indeterminate)のロードバー。
Material Design の線形インジケータ風。デザインは 2026-10-16 のローディングバー検討から。WebGL2 のスケッチ
(Saved/BarHarness/harness.html)で確かめてから組んだ。帯の先頭と末尾は M_LoadingArc と同じ 2 本の smoothstep で動くので、
ループも分岐もない。clamp(x, 0, 1) は Saturate で書く。

バー系のマテリアルはウィジェットの幅いっぱいに描くので、MF_SpinnerCoords の Extent(P 単位での半幅・半高)を使う。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  ext    = MF_SpinnerCoords.Extent                  (半幅・半高。横長なら (幅/高さ, 1))
  R      = Thickness / 2                            (枝の半分の太さ = 丸い端の半径)
  L      = max(ext.x - 1, 0)                        (枝の直線部の半分の長さ。四隅とも (1 - R) だけ内側に寄る)
  xEnd   = L + R                                    (枝の右端。左端は -xEnd)
  dTrack = length((max(abs(p.x) - L, 0), p.y)) - R  (横向きのカプセル。M_LoadingEqualizer の縦カプセルと同じ形)
  track  = saturate(0.5 - dTrack / aa)
  u      = fract(Time * Speed)                      (Speed は往復/秒、正 = 左から右へ)
  head   = smoothstep(0, 1 - TailDelay, u)          (帯の先頭。サイクルの前 (1 - TailDelay) で左端から右端へ)
  tail   = smoothstep(TailDelay, 1, u)              (帯の末尾。TailDelay だけ遅れて追いかける)
  xA     = lerp(-xEnd, xEnd, tail),  xB = lerp(-xEnd, xEnd, head)
  dSeg   = max(dTrack, max(xA - p.x, p.x - xB))     (枝と、xA..xB の縦帯の交差。max の合成でも勾配は 1 以下なので AA は aa)
  fade   = saturate((xB - xA) / aa)                 (折り返しで幅 0 になる瞬間、距離 0 の線が 0.5 の濃さで残るのを消す。
                                                     M_LoadingTimer の教訓)
  seg    = saturate(0.5 - dSeg / aa) * fade
  mask   = max(track * TrackOpacity, seg)

  TailDelay が大きいほど帯が長い(0.5 でサイクルの中間に枝全体、既定の 0.35 で枝の約 7 割。0 では幅 0 で何も見えない)。
  M_LoadingLine の TailDelay と同じ意味(末尾が先頭より遅れて動き出す、サイクルに対する割合)。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルトの外寸: Thickness 1.6 なので枝は上下 ±0.8、両端は ±(ext.x - 0.2)。短辺側は材質契約の基準円 0.8 に触れ、
  長辺側は同じ 0.2 の余白を残す(Thickness 2 でウィジェットいっぱい)。正方形や縦長のウィジェットでは L = 0 で直径
  Thickness の円になる。LoadingIconMaterial にするときは IconSize を横長(たとえば 192x12)にする。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(PARAM_GROUPS、表示順は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  R / L / xEnd / dTrack / xA / xB は 2 箇所以上で使うので Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingbarslide.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingBarSlide"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "TrackOpacity": "Appearance",
    "Thickness": "Shape",
    "Speed": "Motion",
    "TailDelay": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / extents = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / segment motion = light blue
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

# ---- R = Thickness / 2;  L = max(ext.x - 1, 0);  xEnd = L + R ----
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

# ---- u = fract(Time * Speed) ----
time_n = expr(unreal.MaterialExpressionTime, -3300, 200)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.6, 0, "Sweeps per second. Positive = the segment runs left to right", -3300, 320)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -3100, 250)
u_frac = expr(unreal.MaterialExpressionFrac, -2950, 250)
_connect(t_speed, "", u_frac, "")
make_decl("u", u_frac, -2800, 250, C_TM)

# ---- head = smoothstep(0, 1 - TailDelay, u);  tail = smoothstep(TailDelay, 1, u) ----
delay_p = scalar_param("TailDelay", 0.35, 1,
                       "Share of a sweep by which the tail starts after the head; higher makes a longer segment "
                       "(0.5 = the whole track halfway through, 0 = nothing visible)",
                       -3300, 500)
make_decl("TailDelay", delay_p, -3100, 500, C_TM)
delay_u1 = use("TailDelay", -2650, 150)
delay_inv = expr(unreal.MaterialExpressionOneMinus, -2500, 150)
_connect(delay_u1, "", delay_inv, "")
u_u1 = use("u", -2500, 250)
head_ss = expr(unreal.MaterialExpressionSmoothStep, -2350, 200, const_min=0.0)
_connect(delay_inv, "", head_ss, "Max")
_connect(u_u1, "", head_ss, "Value")
delay_u2 = use("TailDelay", -2500, 450)
u_u2 = use("u", -2500, 550)
tail_ss = expr(unreal.MaterialExpressionSmoothStep, -2350, 500, const_max=1.0)
_connect(delay_u2, "", tail_ss, "Min")
_connect(u_u2, "", tail_ss, "Value")

# ---- xA = lerp(-xEnd, xEnd, tail);  xB = lerp(-xEnd, xEnd, head) ----
xend_u1 = use("xEnd", -2200, 350)
xneg = expr(unreal.MaterialExpressionMultiply, -2050, 350, const_b=-1.0)
_connect(xend_u1, "", xneg, "A")
make_decl("xL", xneg, -1900, 350, C_SDF)
xl_u1 = use("xL", -1750, 150)
xend_u2 = use("xEnd", -1750, 250)
xb_v = expr(unreal.MaterialExpressionLinearInterpolate, -1600, 200)
_connect(xl_u1, "", xb_v, "A")
_connect(xend_u2, "", xb_v, "B")
_connect(head_ss, "", xb_v, "Alpha")
make_decl("xB", xb_v, -1450, 200, C_TM)
xl_u2 = use("xL", -1750, 450)
xend_u3 = use("xEnd", -1750, 550)
xa_v = expr(unreal.MaterialExpressionLinearInterpolate, -1600, 500)
_connect(xl_u2, "", xa_v, "A")
_connect(xend_u3, "", xa_v, "B")
_connect(tail_ss, "", xa_v, "Alpha")
make_decl("xA", xa_v, -1450, 500, C_TM)

# ---- dSeg = max(dTrack, max(xA - p.x, p.x - xB)) ----
p_u2 = use("p", -1250, 300)
p_x2 = mask_x(-1100, 300)
_connect(p_u2, "", p_x2, "")
xa_u1 = use("xA", -1100, 200)
left_v = binary(unreal.MaterialExpressionSubtract, xa_u1, p_x2, -950, 250)     # xA - p.x
xb_u1 = use("xB", -1100, 450)
right_v = binary(unreal.MaterialExpressionSubtract, p_x2, xb_u1, -950, 400)    # p.x - xB
band_v = binary(unreal.MaterialExpressionMax, left_v, right_v, -800, 320)
dtrack_u2 = use("dTrack", -800, 180)
dseg_v = binary(unreal.MaterialExpressionMax, dtrack_u2, band_v, -650, 250)

# ---- fade = saturate((xB - xA) / aa);  seg = saturate(0.5 - dSeg / aa) * fade ----
xb_u2 = use("xB", -1100, 650)
xa_u2 = use("xA", -1100, 750)
width_v = binary(unreal.MaterialExpressionSubtract, xb_u2, xa_u2, -950, 700)
aa_u2 = use("aa", -950, 820)
fade_div = binary(unreal.MaterialExpressionDivide, width_v, aa_u2, -800, 750)
fade_sat = expr(unreal.MaterialExpressionSaturate, -650, 750)
_connect(fade_div, "", fade_sat, "")
aa_u3 = use("aa", -650, 400)
seg_div = binary(unreal.MaterialExpressionDivide, dseg_v, aa_u3, -500, 300)
seg_sub = expr(unreal.MaterialExpressionSubtract, -350, 300, const_a=0.5)
_connect(seg_div, "", seg_sub, "B")
seg_sat = expr(unreal.MaterialExpressionSaturate, -200, 300)
_connect(seg_sub, "", seg_sat, "")
seg_v = binary(unreal.MaterialExpressionMultiply, seg_sat, fade_sat, -50, 450)

# ---- mask = max(track * TrackOpacity, seg) ----
track_u1 = use("track", -200, -300)
trackop_p = scalar_param("TrackOpacity", 0.25, 1, "Opacity of the track behind the segment (0 hides it)", -200, -200)
track_dim = binary(unreal.MaterialExpressionMultiply, track_u1, trackop_p, 0, -250)
mask_v = binary(unreal.MaterialExpressionMax, track_dim, seg_v, 150, 0)
make_decl("mask", mask_v, 300, 0, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 600, -300,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Bar color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 600, -50)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, 850, -250)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 600, 150)
cov_a = expr(unreal.MaterialExpressionMultiply, 850, 150)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 1000, 100)
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
    mat, "R = Thickness / 2;  L = max(ext.x - 1, 0);  xEnd = L + R\n"
         "The track is inset by (1 - R) on every side: Thickness 1.6 reaches +-0.8 (the contract's reference circle)\n"
         "and leaves 0.2 at the ends; Thickness 2 fills the widget. A square widget gives a circle (L = 0)",
    -3350, -420, 1400, 300, C_SDF)
smt.create_comment_in_material(
    mat, "dTrack = length((max(abs(p.x) - L, 0), p.y)) - R   (horizontal capsule, exact distance)\n"
         "track = saturate(0.5 - dTrack / aa)",
    -2400, -960, 2150, 300, C_SDF)
smt.create_comment_in_material(
    mat, "u = fract(Time * Speed)   (Speed in sweeps per second; positive runs left to right)\n"
         "Time ignores pause (real time), so the bar keeps moving while the game thread is blocked",
    -3350, 100, 700, 300, C_TM)
smt.create_comment_in_material(
    mat, "head = smoothstep(0, 1 - TailDelay, u);  tail = smoothstep(TailDelay, 1, u)   (Arc's trick: two shifted ramps)\n"
         "xB = lerp(-xEnd, xEnd, head);  xA = lerp(-xEnd, xEnd, tail)   (the segment is xA..xB)\n"
         "Larger TailDelay = a longer segment: 0.5 fills the track halfway through, 0 shows nothing",
    -2700, 50, 1400, 650, C_TM)
smt.create_comment_in_material(
    mat, "dSeg = max(dTrack, max(xA - p.x, p.x - xB))   (the track cut to xA..xB; still 1-Lipschitz, so AA = aa)\n"
         "fade = saturate((xB - xA) / aa): a zero-width segment at the wrap would keep 0.5 coverage on its line\n"
         "seg = saturate(0.5 - dSeg / aa) * fade;  mask = max(track * TrackOpacity, seg)",
    -1300, 100, 1750, 800, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    550, -420, 650, 700, C_COL)

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
expected_decls = sorted(["p", "aa", "R", "L", "xEnd", "dTrack", "track", "u", "TailDelay", "xL", "xB", "xA", "mask"])
expected_usages = {"p": 2, "aa": 3, "R": 2, "L": 2, "xEnd": 3, "dTrack": 2, "track": 1, "u": 2, "TailDelay": 2,
                   "xL": 2, "xB": 2, "xA": 2, "mask": 1}
expected_params = sorted(["Thickness", "Speed", "TailDelay", "TrackOpacity", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 7
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
