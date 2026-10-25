"""
Comet ring spinner -> M_LoadingComet (Material Domain = UI, Translucent)

丸い頭のあとに尾を引く 1 本の線が、リング上を時計回りに回るロードアイコン。尾は頭から 1 周かけて細くなりながら
透明になる。ユーザーのサンドボックスの M_Loading_Icon_UI(2026-10-11 にノードグラフで受領)を材質契約に合わせて移植した。
元のグラフからの変更点:
  - 尾のフェードを色(Color * Progress)から不透明度へ移した。元は尾の先でも中心線の Alpha が 1 のままで、
    明るい背景では黒いリングが一周見えていた。
  - 頭に丸いキャップ(半径 Thickness/2 の円)を足した。元は frac の折り返しでアンチエイリアスなしに平らに切れていた。
    キャップの直径が切れ目にちょうど重なるので、max(tail, cap) は切れ目の前後で連続する。
  - Time は Ignore Pause をオン(元の TimeWithSpeedVariable は GameTime で、ブロッキングロード中に止まる)。
    Time * Speed は先に frac して角度を小さく保つ。
  - 座標は MF_SpinnerCoords(元は TexCoord - 0.5 で、非正方形だと楕円になる)、AA 幅は PixelSize
    (元は UV 固定の Smoothness)、Arctangent2Fast は Arctangent2 に、6.283 は正確な TAU にした。
  - Thickness は線の全幅(元は半幅として使われていた)。

  p      = MF_SpinnerCoords.P                       (中心 (0,0)、y 上向き、短辺が -1..1。非正方形でも中央に収まる)
  aa     = MF_SpinnerCoords.PixelSize               (1 ピクセルを p 単位で)
  h      = fract(Time * Speed)                      (頭の向き。12 時から時計回りの回転数。Speed は回転数/秒、正 = 時計回り)
  a      = atan2(p.x, p.y) / TAU                    (ピクセルの向き。12 時から時計回りの回転数、-0.5..0.5)
  fade   = saturate(1 - fract(h - a))               (頭の直後で 1、反時計回りに 1 周で 0。頭の直前で 0 に折り返す。
                                                     saturate は正常値では何もしない。中心ちょうどで atan2(0, 0) が
                                                     NaN を返した場合に 0 へ落とす保険)
  dTail  = abs(length(p) - Radius) - fade * Thickness / 2
                                                    (尾: 半幅が fade に比例して細くなるリング)
  head   = Radius * (sin(h * TAU), cos(h * TAU))    (頭の中心)
  dHead  = length(p - head) - Thickness / 2         (頭: 丸いキャップ)
  tail   = clamp(0.5 - dTail / aa, 0, 1) * fade     (尾は不透明度もフェード。細い尾の AA は中心線で 0.5 残るので、
                                                     fade を掛けないと 1 周の細い線が残る)
  cap    = clamp(0.5 - dHead / aa, 0, 1)
  mask   = max(tail, cap)

  出力: FinalColor(Emissive) = PrimaryColor.rgb * VertexColor.rgb、
        Opacity = mask * PrimaryColor.a * VertexColor.a(UMG の ColorAndOpacity / RenderOpacity / フェードが乗る)。
  デフォルト値は Radius + Thickness/2 = 0.8(材質契約の基準円。1.0 = 短辺の端)に合わせてある。
  見た目は 2026-10-11 に Python で同じ式を評価した静止画で確認(元のグラフと黒背景では同等、明るい背景で尾が消える)。

  ScalarParameter / VectorParameter のグループは Appearance / Shape / Motion(PARAM_GROUPS、順序は GROUP_ORDER)。
  ローカル変数 -> Named Reroute Declaration、再利用箇所 -> Usage。
  Radius(2 箇所)と Thickness / 2(2 箇所)は Declaration 化、他のパラメータは 1 箇所なので直接配線。

実行例:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_m_loadingcomet.py"
"""
import unreal

# Commandlets start before the asset registry finishes its initial scan. Without a synchronous scan,
# does_asset_exist() misses existing assets and create_asset() opens an overwrite dialog (crashes headless).
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/LoadingFX"], True)

ASSET_PATH = "/LoadingFX/Materials"
ASSET_NAME = "M_LoadingComet"
FULL_PATH = f"{ASSET_PATH}/{ASSET_NAME}"
MF_COORDS_PATH = "/LoadingFX/MaterialFunctions/MF_SpinnerCoords"
TAU = 6.28318530718
# Parameter groups: sections in the material instance editor, in this order (Input only on determinate materials)
GROUP_ORDER = ["Input", "Appearance", "Shape", "Motion"]
PARAM_GROUPS = {  # every parameter of this material -> its group
    "PrimaryColor": "Appearance",
    "Radius": "Shape",
    "Thickness": "Shape",
    "Speed": "Motion",
}

mel = unreal.MaterialEditingLibrary
lib = unreal.EditorAssetLibrary
smt = unreal.DevMaterialTools
tools = unreal.AssetToolsHelpers.get_asset_tools()

C_UV  = unreal.LinearColor(1.0, 0.6, 0.1, 1.0)   # coordinates / angles = orange
C_SDF = unreal.LinearColor(0.6, 1.0, 0.2, 1.0)   # SDF / AA = green
C_TM  = unreal.LinearColor(0.3, 0.8, 1.0, 1.0)   # time / fade = light blue
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
coords = expr(unreal.MaterialExpressionMaterialFunctionCall, -3100, -650, material_function=mf_coords)
make_decl("p", coords, -2800, -700, C_UV, "P")
make_decl("aa", coords, -2800, -580, C_SDF, "PixelSize")

# ---- h = fract(Time * Speed)  (head direction, turns clockwise from 12 o'clock) ----
time_n = expr(unreal.MaterialExpressionTime, -3250, 350)
# Ignore Pause -> View.RealTime (FPlatformTime at draw time). The default GameTime is FApp::CurrentTime,
# which only the game thread advances, so it freezes during blocking loads even while MoviePlayer keeps drawing.
time_n.set_editor_property("ignore_pause", True)
speed_p = scalar_param("Speed", 0.5, 0, "Revolutions per second. Positive = clockwise", -3250, 470)
h_mul = expr(unreal.MaterialExpressionMultiply, -3050, 400)
_connect(time_n, "", h_mul, "A")
_connect(speed_p, "", h_mul, "B")
h_frac = expr(unreal.MaterialExpressionFrac, -2900, 400)
_connect(h_mul, "", h_frac, "")
make_decl("h", h_frac, -2750, 400, C_TM)

# ---- a = atan2(p.x, p.y) / TAU  (pixel direction, turns clockwise from 12 o'clock, -0.5..0.5) ----
p_u1 = use("p", -2450, -350)
p_x = mask_x(-2300, -400)
_connect(p_u1, "", p_x, "")
p_y = mask_y(-2300, -280)
_connect(p_u1, "", p_y, "")
# atan2(Y = p.x, X = p.y): 0 at 12 o'clock, growing clockwise (p is y-up).
a_atan = expr(unreal.MaterialExpressionArctangent2, -2100, -350)
_connect(p_x, "", a_atan, "Y")
_connect(p_y, "", a_atan, "X")
a_div = expr(unreal.MaterialExpressionDivide, -1900, -350, const_b=TAU)
_connect(a_atan, "", a_div, "A")
make_decl("a", a_div, -1750, -350, C_UV)

# ---- fade = saturate(1 - fract(h - a))  (1 right behind the head, 0 one full turn behind) ----
h_u1 = use("h", -1450, 0)
a_u1 = use("a", -1450, 100)
behind = expr(unreal.MaterialExpressionSubtract, -1300, 50)
_connect(h_u1, "", behind, "A")
_connect(a_u1, "", behind, "B")
behind_frac = expr(unreal.MaterialExpressionFrac, -1150, 50)
_connect(behind, "", behind_frac, "")
fade_inv = expr(unreal.MaterialExpressionOneMinus, -1000, 50)
_connect(behind_frac, "", fade_inv, "")
# A no-op for valid input; maps a NaN from atan2(0, 0) at the exact center to 0.
fade_sat = expr(unreal.MaterialExpressionSaturate, -850, 50)
_connect(fade_inv, "", fade_sat, "")
make_decl("fade", fade_sat, -700, 50, C_TM)

# Footprint (material contract): Radius + Thickness / 2 = 0.8, the reference circle.
radius_p = scalar_param("Radius", 0.75, 0,
                        "Distance from the center to the middle of the stroke (half the shorter widget side = 1.0)",
                        -1450, 650)
make_decl("Radius", radius_p, -1200, 650, C_SC)
thick_p = scalar_param("Thickness", 0.1, 1,
                       "Stroke width at the head. The tail thins to zero one full turn behind it",
                       -1450, 800)
thick_half = expr(unreal.MaterialExpressionMultiply, -1250, 800, const_b=0.5)
_connect(thick_p, "", thick_half, "A")
make_decl("halfT", thick_half, -1100, 800, C_SC)

# ---- dTail = abs(length(p) - Radius) - fade * Thickness / 2 ----
p_u2 = use("p", -450, -450)
p_len = expr(unreal.MaterialExpressionLength, -300, -450)
_connect(p_u2, "", p_len, "")
radius_u1 = use("Radius", -300, -350)
ring_sub = expr(unreal.MaterialExpressionSubtract, -150, -400)
_connect(p_len, "", ring_sub, "A")
_connect(radius_u1, "", ring_sub, "B")
ring_abs = expr(unreal.MaterialExpressionAbs, 0, -400)
_connect(ring_sub, "", ring_abs, "")
fade_u1 = use("fade", -300, -200)
halft_u1 = use("halfT", -300, -100)
tail_w = expr(unreal.MaterialExpressionMultiply, -150, -150)
_connect(fade_u1, "", tail_w, "A")
_connect(halft_u1, "", tail_w, "B")
dtail_v = expr(unreal.MaterialExpressionSubtract, 150, -300)
_connect(ring_abs, "", dtail_v, "A")
_connect(tail_w, "", dtail_v, "B")
make_decl("dTail", dtail_v, 300, -300, C_SDF)

# ---- head = Radius * (sin(h * TAU), cos(h * TAU));  dHead = length(p - head) - Thickness / 2 ----
h_u2 = use("h", -450, 250)
h_ang = expr(unreal.MaterialExpressionMultiply, -300, 250, const_b=TAU)
_connect(h_u2, "", h_ang, "A")
h_sin = expr(unreal.MaterialExpressionSine, -150, 200, period=TAU)   # period 2*PI = radians
_connect(h_ang, "", h_sin, "")
h_cos = expr(unreal.MaterialExpressionCosine, -150, 320, period=TAU)
_connect(h_ang, "", h_cos, "")
h_dir = expr(unreal.MaterialExpressionAppendVector, 0, 250)
_connect(h_sin, "", h_dir, "A")
_connect(h_cos, "", h_dir, "B")
radius_u2 = use("Radius", 0, 400)
head_v = expr(unreal.MaterialExpressionMultiply, 150, 300)
_connect(h_dir, "", head_v, "A")
_connect(radius_u2, "", head_v, "B")
p_u3 = use("p", 150, 150)
to_head = expr(unreal.MaterialExpressionSubtract, 300, 200)
_connect(p_u3, "", to_head, "A")
_connect(head_v, "", to_head, "B")
head_len = expr(unreal.MaterialExpressionLength, 450, 200)
_connect(to_head, "", head_len, "")
halft_u2 = use("halfT", 450, 300)
dhead_v = expr(unreal.MaterialExpressionSubtract, 600, 250)
_connect(head_len, "", dhead_v, "A")
_connect(halft_u2, "", dhead_v, "B")
make_decl("dHead", dhead_v, 750, 250, C_SDF)

# ---- tail = clamp(0.5 - dTail / aa, 0, 1) * fade ----
dtail_u1 = use("dTail", 1050, -350)
aa_u1 = use("aa", 1050, -250)
tail_div = expr(unreal.MaterialExpressionDivide, 1200, -300)
_connect(dtail_u1, "", tail_div, "A")
_connect(aa_u1, "", tail_div, "B")
tail_half = expr(unreal.MaterialExpressionSubtract, 1350, -300, const_a=0.5)
_connect(tail_div, "", tail_half, "B")
tail_clamp = expr(unreal.MaterialExpressionClamp, 1500, -300, min_default=0.0, max_default=1.0)
_connect(tail_half, "", tail_clamp, "")
fade_u2 = use("fade", 1500, -150)
tail_v = expr(unreal.MaterialExpressionMultiply, 1700, -250)
_connect(tail_clamp, "", tail_v, "A")
_connect(fade_u2, "", tail_v, "B")

# ---- cap = clamp(0.5 - dHead / aa, 0, 1) ----
dhead_u1 = use("dHead", 1050, 100)
aa_u2 = use("aa", 1050, 200)
cap_div = expr(unreal.MaterialExpressionDivide, 1200, 150)
_connect(dhead_u1, "", cap_div, "A")
_connect(aa_u2, "", cap_div, "B")
cap_half = expr(unreal.MaterialExpressionSubtract, 1350, 150, const_a=0.5)
_connect(cap_div, "", cap_half, "B")
cap_clamp = expr(unreal.MaterialExpressionClamp, 1500, 150, min_default=0.0, max_default=1.0)
_connect(cap_half, "", cap_clamp, "")

# ---- mask = max(tail, cap) ----
mask_max = expr(unreal.MaterialExpressionMax, 1900, -50)
_connect(tail_v, "", mask_max, "A")
_connect(cap_clamp, "", mask_max, "B")
make_decl("mask", mask_max, 2050, -50, C_COL)

# ---- Output: FinalColor = PrimaryColor.rgb * VertexColor.rgb, Opacity = mask * PrimaryColor.a * VertexColor.a ----
primary_p = expr(unreal.MaterialExpressionVectorParameter, 2300, -200,
                 parameter_name="PrimaryColor", default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                 group=PARAM_GROUPS["PrimaryColor"], sort_priority=0, desc="Comet color (alpha scales the opacity)")
vcolor = expr(unreal.MaterialExpressionVertexColor, 2300, 50)
emissive = expr(unreal.MaterialExpressionMultiply, 2550, -150)
_connect(primary_p, "", emissive, "A")
_connect(vcolor, "", emissive, "B")
results.append(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR))
mask_u1 = use("mask", 2300, 250)
cov_a = expr(unreal.MaterialExpressionMultiply, 2550, 200)
_connect(mask_u1, "", cov_a, "A")
_connect(primary_p, "A", cov_a, "B")
opacity = expr(unreal.MaterialExpressionMultiply, 2700, 150)
_connect(cov_a, "", opacity, "A")
_connect(vcolor, "A", opacity, "B")
results.append(mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY))

# ---- Comments (English) ----
smt.create_comment_in_material(
    mat, "p = MF_SpinnerCoords.P   (centered, y-up, shorter side spans -1..1: fits a non-square widget)\n"
         "aa = MF_SpinnerCoords.PixelSize   (one screen pixel in p units)",
    -3300, -820, 900, 400, C_UV)
smt.create_comment_in_material(
    mat, "h = fract(Time * Speed)   (head direction, turns clockwise from 12 o'clock)\n"
         "Time ignores pause (real time), so the spinner keeps turning while the game thread is blocked",
    -3300, 250, 700, 380, C_TM)
smt.create_comment_in_material(
    mat, "a = atan2(p.x, p.y) / TAU   (pixel direction, turns clockwise from 12 o'clock)",
    -2500, -480, 900, 330, C_UV)
smt.create_comment_in_material(
    mat, "fade = saturate(1 - fract(h - a)): 1 right behind the head, 0 one full turn behind;\n"
         "it wraps to 0 just ahead of the head. saturate only catches a NaN from atan2(0, 0) at the center",
    -1500, -100, 950, 330, C_TM)
smt.create_comment_in_material(
    mat, "Radius + Thickness / 2 = 0.8 by default (the material contract's reference circle)\n"
         "halfT = Thickness / 2 (used by the tail and the head)",
    -1500, 550, 550, 400, C_SC)
smt.create_comment_in_material(
    mat, "dTail = abs(length(p) - Radius) - fade * Thickness / 2\n"
         "A ring whose half-width shrinks with fade",
    -500, -580, 950, 600, C_SDF)
smt.create_comment_in_material(
    mat, "head = Radius * (sin(h * TAU), cos(h * TAU));  dHead = length(p - head) - Thickness / 2\n"
         "The round cap's diameter lies on the wrap of fade, so max(tail, cap) is continuous there",
    -500, 100, 1400, 450, C_SDF)
smt.create_comment_in_material(
    mat, "tail = clamp(0.5 - dTail / aa, 0, 1) * fade   (the tail also fades in opacity: a thin line keeps 0.5\n"
         "coverage on its centerline, so without fade a faint full circle would remain)\n"
         "cap = clamp(0.5 - dHead / aa, 0, 1);  mask = max(tail, cap)",
    1000, -480, 1300, 820, C_COL)
smt.create_comment_in_material(
    mat, "Output (UI domain): FinalColor = PrimaryColor.rgb * VertexColor.rgb\n"
         "Opacity = mask * PrimaryColor.a * VertexColor.a   (UMG ColorAndOpacity / RenderOpacity / fades)",
    2250, -320, 650, 680, C_COL)

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

expected_decls = sorted(["p", "aa", "h", "a", "fade", "Radius", "halfT", "dTail", "dHead", "mask"])
expected_usages = {"p": 3, "aa": 2, "h": 2, "a": 1, "fade": 2, "Radius": 2, "halfT": 2, "dTail": 1,
                   "dHead": 1, "mask": 1}
expected_params = sorted(["Radius", "Thickness", "Speed", "PrimaryColor"])
decls_ok = sorted(decl_names) == expected_decls
usages_ok = usage_count == expected_usages
params_ok = sorted(param_names) == expected_params
groups_ok = param_groups == PARAM_GROUPS and group_prios == expected_prios
mf_ok = mf_calls == 1
comments_ok = len(smt.get_material_comment_texts(mat)) == 9
domain_ok = mat.get_editor_property("material_domain") == unreal.MaterialDomain.MD_UI
blend_ok = mat.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_TRANSLUCENT

print(f"[TEST] Connections: {sum(results)}/{len(results)} succeeded")
passed = (all(results) and decls_ok and usages_ok and params_ok and groups_ok and mf_ok
          and comments_ok and domain_ok and blend_ok and saved)
print("[TEST] RESULT: " + ("PASS" if passed else "FAIL"))
