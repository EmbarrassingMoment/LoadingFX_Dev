"""
Indeterminate linear bar -> M_LoadingLine (Material Domain = UI, Translucent)

横長のトラック(薄い角丸の棒)の中を、明るい区間が左から伸びて右へ抜けていくロードアイコン(1 色)。
デザインは 2026-10-16 のスピナー案第 4 弾の 1 番。プレビューは区間の両端を smoothstep で動かし、トラックの外まで
行き過ぎていたので、毎サイクルの終わりに何も見えない時間(約 35%)があった。ここでは先端を ease-out、末尾を ease-in にし、
ちょうどトラックに接する位置から出入りさせるので空白がない。トラックの中での動きはプレビューとほぼ同じ
(WebGL2 のスケッチ Saved/LinearHarness/harness.html で 1 サイクルを並べて比べた)。clamp(x, 0, 1) は Saturate で書く。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  r      = Thickness / 2
  dTrack = length((p.x - clamp(p.x, r - HalfWidth, HalfWidth - r), p.y)) - r
                                                    (トラック = 横向きのカプセル。端の丸まで含めて半長 HalfWidth)
  時間側(ピクセルに依存しないスカラー計算):
    u    = fract(Time * Speed)                      (Speed は 1 秒あたりに区間が通り抜ける回数。負なら右から左)
    dur  = 1 - TailDelay
    head = 1 - (1 - saturate(u / dur))^2            (先端: 0 から dur までで 0 -> 1。速く入って右端で減速する)
    tail = saturate((u - TailDelay) / dur)^2        (末尾: TailDelay から 1 までで 0 -> 1。ゆっくり動き出して速く抜ける)
    reach = HalfWidth + r
    x1 = (2 * head - 1) * reach,  x0 = (2 * tail - 1) * reach
                                                    (区間の芯線の両端。±reach では区間の丸い端がトラックの端に外から接する。
                                                     head >= tail なので x0 <= x1)
  dBar   = max(length((p.x - clamp(p.x, x0, x1), p.y)) - r, dTrack)
                                                    (区間のカプセルをトラックで切り取る)
  mask   = max(saturate(0.5 - dBar / aa), saturate(0.5 - dTrack / aa) * TrackOpacity)

  出入りの瞬間: 区間とトラックの重なりは幅 0 から始まり、SDF の AA ではそこが濃さ 0.5 の点になる
  (M_LoadingTimer の細い線と同じ)。先端が入るときと末尾が抜けるときはどちらも最も速いので、残るのは 1 フレーム程度。
  smoothstep のように端で止まる曲線にすると、この点がトラックの端に残る。

  デフォルトの外寸: 横は HalfWidth = 0.72(材質契約の基準正方形の半幅。Dots / Equalizer と同じ)、縦は Thickness / 2 = 0.05。
  横長のウィジェットでも、ほかのスピナーと同じく短辺基準の大きさで中央に描く(幅いっぱいには伸びない)。

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。

  ScalarParameter / VectorParameter はグループ Appearance / Shape / Motion(PARAM_GROUPS、表示順は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  HalfWidth(3 箇所)と TailDelay(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingline.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingLine"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "TrackOpacity": "Appearance",
    "HalfWidth": "Shape",
    "Thickness": "Shape",
    "Speed": "Motion",
    "TailDelay": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / bar ends = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / head and tail progress = light blue
C_SC  = unreal.LinearColor(0.7, 0.7, 0.7, 1.0)   # params / scalar intermediates = gray
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

def capsule_x(lo, hi, x, y):
    """length((px - clamp(px, lo, hi), py)) - r: distance to a horizontal capsule whose centerline runs lo..hi."""
    px_u1 = use("px", x, y - 100)
    px_u2 = use("px", x, y)
    cl = expr(unreal.MaterialExpressionClamp, x + 150, y)
    _connect(px_u2, "", cl, "")   # the main pin of Clamp is unnamed (GetShortenPinName drops "Input")
    _connect(lo, "", cl, "Min")
    _connect(hi, "", cl, "Max")
    dx = binary(unreal.MaterialExpressionSubtract, px_u1, cl, x + 300, y - 50)
    py_u = use("py", x + 300, y + 60)
    v = binary(unreal.MaterialExpressionAppendVector, dx, py_u, x + 450, y)
    ln = expr(unreal.MaterialExpressionLength, x + 600, y)
    _connect(v, "", ln, "")
    r_u = use("r", x + 600, y + 100)
    return binary(unreal.MaterialExpressionSubtract, ln, r_u, x + 750, y + 50)

def coverage(d_name, x, y):
    """saturate(0.5 - d / aa): 1px-wide anti-aliased coverage of the distance declared as d_name."""
    d_u = use(d_name, x, y - 50)
    aa_u = use("aa", x, y + 50)
    div = binary(unreal.MaterialExpressionDivide, d_u, aa_u, x + 150, y)
    half = expr(unreal.MaterialExpressionSubtract, x + 300, y, const_a=0.5)
    _connect(div, "", half, "B")
    sat = expr(unreal.MaterialExpressionSaturate, x + 450, y)
    _connect(half, "", sat, "")
    return sat

# ---- p = MF_SpinnerCoords.P, aa = MF_SpinnerCoords.PixelSize  (centered, y-up, shorter side = -1..1) ----
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3000, -900, material_function=mf_coords)
make_decl("p", coords, -2700, -950, C_UV, "P")
make_decl("aa", coords, -2700, -830, C_SDF, "PixelSize")
p_u1 = use("p", -2500, -950)
p_x = mask_x(-2350, -1000)
_connect(p_u1, "", p_x, "")
make_decl("px", p_x, -2200, -1000, C_UV)
p_u2 = use("p", -2500, -830)
p_y = mask_y(-2350, -880)
_connect(p_u2, "", p_y, "")
make_decl("py", p_y, -2200, -880, C_UV)

# ---- Shape parameters: r = Thickness / 2, reach = HalfWidth + r ----
# Footprint (material contract): HalfWidth = 0.72 across (the reference square, as Dots and Equalizer).
half_p = scalar_param("HalfWidth", 0.72, 0,
                      "Half length of the track including its round ends (half the shorter widget side = 1.0)",
                      -3000, -550)
make_decl("HalfWidth", half_p, -2750, -550, C_SC)
thick_p = scalar_param("Thickness", 0.1, 1, "Thickness of the track and the bar", -3000, -400)
r_half = expr(unreal.MaterialExpressionMultiply, -2750, -400, const_b=0.5)
_connect(thick_p, "", r_half, "A")
make_decl("r", r_half, -2600, -400, C_SDF)
hw_u1 = use("HalfWidth", -2400, -550)
r_u1 = use("r", -2400, -450)
reach_v = binary(unreal.MaterialExpressionAdd, hw_u1, r_u1, -2250, -500)
make_decl("reach", reach_v, -2100, -500, C_UV)

# ---- dTrack = length((px - clamp(px, r - HalfWidth, HalfWidth - r), py)) - r ----
r_u2 = use("r", -1900, -700)
hw_u2 = use("HalfWidth", -1900, -600)
track_lo = binary(unreal.MaterialExpressionSubtract, r_u2, hw_u2, -1750, -650)
hw_u3 = use("HalfWidth", -1900, -500)
r_u3 = use("r", -1900, -400)
track_hi = binary(unreal.MaterialExpressionSubtract, hw_u3, r_u3, -1750, -450)
d_track = capsule_x(track_lo, track_hi, -1550, -600)
make_decl("dTrack", d_track, -650, -550, C_SDF)

# ---- u = fract(Time * Speed);  dur = 1 - TailDelay ----
time_n = expr(unreal.MaterialExpressionTime, -3000, 200)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.6, 0,
                       "Sweeps per second. Positive = left to right, negative = right to left", -3000, 320)
t_speed = binary(unreal.MaterialExpressionMultiply, time_n, speed_p, -2800, 250)
u_frac = expr(unreal.MaterialExpressionFrac, -2650, 250)
_connect(t_speed, "", u_frac, "")
make_decl("u", u_frac, -2500, 250, C_TM)
delay_p = scalar_param("TailDelay", 0.35, 1,
                       "Share of a sweep by which the tail starts after the head; higher makes a longer bar "
                       "(0 to below 1)", -3000, 500)
make_decl("TailDelay", delay_p, -2750, 500, C_SC)
delay_u1 = use("TailDelay", -2500, 500)
dur_v = expr(unreal.MaterialExpressionOneMinus, -2350, 500)
_connect(delay_u1, "", dur_v, "")
make_decl("dur", dur_v, -2200, 500, C_TM)

# ---- head = 1 - (1 - saturate(u / dur))^2   (ease-out: enters fast, slows down at the right end) ----
u_u1 = use("u", -2000, 150)
dur_u1 = use("dur", -2000, 250)
a_div = binary(unreal.MaterialExpressionDivide, u_u1, dur_u1, -1850, 200)
a_sat = expr(unreal.MaterialExpressionSaturate, -1700, 200)
_connect(a_div, "", a_sat, "")
a_inv = expr(unreal.MaterialExpressionOneMinus, -1550, 200)
_connect(a_sat, "", a_inv, "")
a_sq = binary(unreal.MaterialExpressionMultiply, a_inv, a_inv, -1400, 200)
head_v = expr(unreal.MaterialExpressionOneMinus, -1250, 200)
_connect(a_sq, "", head_v, "")
make_decl("head", head_v, -1100, 200, C_TM)

# ---- tail = saturate((u - TailDelay) / dur)^2   (ease-in: starts slowly, leaves fast) ----
u_u2 = use("u", -2000, 450)
delay_u2 = use("TailDelay", -2000, 550)
b_sub = binary(unreal.MaterialExpressionSubtract, u_u2, delay_u2, -1850, 500)
dur_u2 = use("dur", -1850, 600)
b_div = binary(unreal.MaterialExpressionDivide, b_sub, dur_u2, -1700, 550)
b_sat = expr(unreal.MaterialExpressionSaturate, -1550, 550)
_connect(b_div, "", b_sat, "")
tail_v = binary(unreal.MaterialExpressionMultiply, b_sat, b_sat, -1400, 550)
make_decl("tail", tail_v, -1100, 550, C_TM)

# ---- x1 = (2 * head - 1) * reach,  x0 = (2 * tail - 1) * reach ----
def bar_end(t_name, x, y):
    t_u = use(t_name, x, y)
    t2 = expr(unreal.MaterialExpressionMultiply, x + 150, y, const_b=2.0)
    _connect(t_u, "", t2, "A")
    t2m1 = expr(unreal.MaterialExpressionSubtract, x + 300, y, const_b=1.0)
    _connect(t2, "", t2m1, "A")
    reach_u = use("reach", x + 300, y + 100)
    return binary(unreal.MaterialExpressionMultiply, t2m1, reach_u, x + 450, y + 50)

make_decl("x1", bar_end("head", -900, 150), -300, 200, C_UV)
make_decl("x0", bar_end("tail", -900, 500), -300, 550, C_UV)

# ---- dBar = max(length((px - clamp(px, x0, x1), py)) - r, dTrack) ----
x0_u = use("x0", -100, 300)
x1_u = use("x1", -100, 400)
d_cap = capsule_x(x0_u, x1_u, 100, 350)
d_track_u1 = use("dTrack", 850, 500)
d_bar = binary(unreal.MaterialExpressionMax, d_cap, d_track_u1, 1000, 450)
make_decl("dBar", d_bar, 1150, 450, C_SDF)

# ---- mask = max(saturate(0.5 - dBar / aa), saturate(0.5 - dTrack / aa) * TrackOpacity) ----
bar_cov = coverage("dBar", 1350, 450)
track_cov = coverage("dTrack", 1350, -550)
track_op_p = scalar_param("TrackOpacity", 0.2, 1, "Opacity of the track behind the bar (0 hides it)", 1650, -400)
track_mask = binary(unreal.MaterialExpressionMultiply, track_cov, track_op_p, 1950, -500)
mask_max = binary(unreal.MaterialExpressionMax, bar_cov, track_mask, 2100, 0)
make_decl("mask", mask_max, 2250, 0, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2500, -100,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0,
                 desc="Color of the bar and the track (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 2500, 150)
emissive = binary(unreal.MaterialExpressionMultiply, primary_p, vcolor, 2750, -50)
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 2500, 350)
cov_a = expr(unreal.MaterialExpressionMultiply, 2750, 300)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 2900, 250)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

smt.set_material_root_position(mat, 3160, -70)

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "HalfWidth = 0.72 by default: the outer size shared by the square layouts. At x = +-reach the bar's "
         "round end touches the track's end from outside.",
    -3050, -620, 1050, 330, C_SC)
smt.create_comment_in_material(
    mat, "Bar motion\n"
         "The head eases out and the tail eases in. Both cross the track's ends at full speed, so the sliver "
         "where the bar only touches the track (half coverage under anti-aliasing) lasts about a frame.\n"
         "Time has Ignore Pause on (real time), so the bar keeps moving while the game thread is blocked.",
    -3050, 42, 2900, 638, C_TM)

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
expected_decls = sorted(["p", "aa", "px", "py", "HalfWidth", "r", "reach", "dTrack", "u", "TailDelay", "dur",
                         "head", "tail", "x0", "x1", "dBar", "mask"])
expected_usages = {"p": 2, "aa": 2, "px": 4, "py": 2, "HalfWidth": 3, "r": 5, "reach": 2, "dTrack": 2,
                   "u": 2, "TailDelay": 2, "dur": 2, "head": 1, "tail": 1, "x0": 1, "x1": 1, "dBar": 1, "mask": 1}
expected_params = sorted(["HalfWidth", "Thickness", "TrackOpacity", "Speed", "TailDelay", "PrimaryColor"])
mat_ok = (decl_names == expected_decls and usage_count == dict(sorted(expected_usages.items()))
          and params == expected_params and mf_calls == 1
          and param_groups == PARAM_GROUPS and group_prios == expected_prios
          and len(smt.get_material_comment_texts(mat)) == 2
          and mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
          and mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT
          and saved)

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
print(f"[TEST] {ASSET_NAME}: {'OK' if mat_ok else 'NG'}")
print("[TEST] RESULT: " + ("PASS" if all(results) and mat_ok else "FAIL"))
