# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

Reply to the user in Japanese. Code, comments, commit messages and the docs in this repository stay in English (`README.ja.md` is the Japanese README).

## Project

LoadingFX is an Unreal Engine 5 plugin: a library of material-based loading spinners, a loading icon display that keeps animating during blocking loads, and a lightweight asset loader. This repository is the development and sample project (`LoadingFX_Dev`). It is published on GitHub (MIT), and the plugin is distributed **for free** on Fab.

- **Target engines:** UE 5.5 – 5.8 (one Fab package per version).
- **Authoring engine: UE 5.5.** Content (`.uasset` / `.umap`) must stay loadable in 5.5, so never open or save this project's content with a newer engine. Use 5.6 – 5.8 only for compile checks of the plugin (RunUAT `BuildPlugin`).
- **Platform:** Win64 (initial scope).

## Build & Setup

1. Right-click `LoadingFX_Dev.uproject` → **Generate Visual Studio project files**
2. Open `LoadingFX_Dev.uproject` in UE 5.5 and rebuild modules when prompted

Command-line build (UE 5.5):

```
<UE_5.5>\Engine\Build\BatchFiles\Build.bat LoadingFX_DevEditor Win64 Development -Project="<repo>\LoadingFX_Dev.uproject" -WaitMutex
```

## Architecture

| Module | Type | Role |
|--------|------|------|
| `LoadingFX` | Runtime | Spinner Slate/UMG widgets, the loading icon subsystem, blocking-load rendering (MoviePlayer). Excluded from Server targets. |
| `LoadingFXLoader` | Runtime | Lightweight async/sync asset loader subsystem. No UI dependency. |
| `LoadingFXBridge` | Runtime | Optional glue: forwards loader events to the loading icon. Excluded from Server targets. |

**Dependency rule:** `LoadingFX` and `LoadingFXLoader` must never depend on each other. Only `LoadingFXBridge` depends on both.

### Dev-only tooling

`Plugins/DevMaterialTools/` is a local editor plugin (not distributed, excluded from the release zip, not listed in the `.uproject`). It exposes Named Reroute / comment helpers to Python (`unreal.DevMaterialTools`). Its `Tools/` scripts build the material assets from scratch. Always run them with UE 5.5 (see its README); `build_all.py` rebuilds everything in dependency order. To change a material, edit its builder script and regenerate. Don't hand-edit the generated asset.

The current materials (`M_LoadingSpinner`, `M_LoadingIcon`, `M_LoadingBoxes`, `M_LoadingBars`, `M_LoadingArc`, `M_LoadingComet`) follow the material contract below. The first three were ported from the sandbox project; `M_LoadingBars` was ported from the user's Shadertoy with the AA width taken from `fwidth(d)` (DDX/DDY of the distance field) instead of `PixelSize`, which is only valid when `d` is continuous across cells (every bar has the same shape). `M_LoadingArc` (one rounded arc that stretches and shrinks while it turns) was designed here: the look was approved from stills rendered in Python with the same formulas, and the shape is iq's `sdArc` (loop-free and branch-free; `Step` + `Lerp` select the end cap). It has two rates: `Speed` (steady rotation, rev/s) and `StretchSpeed` (grow/shrink cycles per second). With the defaults (0.3, 0.75) each cycle advances about 1.02 turns, so every stretch starts near 12 o'clock. `M_LoadingComet` (a round head with a tail that thins and fades over one turn) was ported from the user's sandbox `M_Loading_Icon_UI`. The original faded the tail by darkening its color while its centerline alpha stayed 1, so a dark full circle showed on light backgrounds; the port fades opacity instead. It also adds a round head cap whose diameter covers the `frac` wrap, so `max(tail, cap)` is continuous there, and uses real time (the original's `TimeWithSpeedVariable` uses GameTime).

## 1.0 Scope (decided 2026-10-11)

What users reference by name is frozen at 1.0: asset paths and names, material parameter names, Blueprint / C++ API names, ini keys, module names. Additive changes (new spinners, settings or modules) can ship in 1.x.

- **Display:** the implemented icon subsystem, settings, Slate / UMG spinner and bundled materials.
- **Show delay and minimum display time** for the loading icon (project settings), so short loads do not flicker. The minimum display time is done (see Loading icon below); the show delay is not.
- **Preload the icon material** (done, see Loading icon below) asynchronously when the subsystem initializes, instead of `LoadSynchronous` on the first `Acquire`. Loading a UI-domain material starts its PSO precaching (UE 5.5: `UMaterial::PostLoad` → `PrecachePSOs`, collected by Slate's `SlateMaterialPSOCollector`; `r.PSOPrecaching` and `r.PSOPrecache.SlateMaterials` default to 1), so the preload moves both the load and the PSO work away from the moment the icon must appear, and avoids a sync load while the loader's async loads run. Shaders need nothing extra (they are cooked with the material). A recorded PSO cache (`.upipelinecache`) is per project, so the plugin does not ship one.
- **Asset loader and Bridge:** generic async loading (progress, cancel) and sync loading in `LoadingFXLoader`. Through the Bridge, the icon keeps animating during the loader's sync loads. This needs a blocking-section API on the icon subsystem (manual MoviePlayer playback, verified by the prototype).
- **More spinners** are still to be added before 1.0.
- **Naming pass before the freeze, as the last material task** (after the spinner set is final, so names change only once): rename the materials by shape (`M_LoadingIcon` clashes with the "loading icon" feature; `M_LoadingSpinner` names one particular design, a dot ring) and unify parameter names (`Ring` vs `Radius`; `RMax` / `RMin` vs `RBase` / `RGrow`). `M_LoadingIcon`'s builder still uses the old `scalar_param` form, so its parameters have no descriptions or sort priorities. Do all of it in the builder scripts, then update the settings default, the prototype and this file.
- **Release checks:** BuildPlugin on 5.5 – 5.8 (5.6 and 5.7 are not installed yet), a packaged Shipping build, and a fresh Blueprint-only project with the plugin installed as an engine plugin, as Fab installs it (settings page, UMG palette, Acquire / Release nodes, default material cooked without `DirectoriesToAlwaysCook`).
- **Docs and listing:** README (English and Japanese) rewritten, CHANGELOG 1.0.0, `VersionName` 1.0.0, Fab description and media.
- **Samples:** only in this project, as a Blueprint sample map and widget kept apart from the C++ prototype. The plugin ships no sample content.

After 1.0: a background color for the blocking screen, fades, platforms other than Win64.

### Still open (1.0)

- Loader API: request shape (soft object / class references), Blueprint async action nodes, how long loaded assets stay referenced, and whether the Bridge also shows the icon during async loads.
- Show delay semantics: what `IsIconVisible` / `OnVisibilityChanged` report during the delay (today they mean "from the first request until the icon hides", which includes the minimum display time), whether a blocking load that starts during the delay shows the icon at once, and the defaults.
- The new material and parameter names.

## Confirmed Design Decisions

### Loading icon (display — the main feature)

- Spinners are procedural (SDF) materials, and many are bundled. The loading icon uses a **project-wide default only** (Project Settings). There is no per-request override and no runtime switching API.
- The loading icon subsystem is a `UGameInstanceSubsystem`. Show and hide use handle-based reference counting (`Acquire(Reason)` / `Release(Handle)`), with optional auto-release when a weakly referenced owner is destroyed.
- The icon is added with `UGameViewportClient::AddViewportWidgetContent` so it survives map travel. Do not use `AddToViewport`, because those widgets are removed on world teardown.
- The icon must keep animating during blocking loads, which requires MoviePlayer. MoviePlayer is unavailable in PIE, so the icon freezes there; document this behavior.
- **v1 scope:** if the icon is visible when LoadMap starts, automatically switch to blocking rendering (`PreLoadMap` / `PostLoadMapWithWorld`). It does **not** auto-show the icon or decide when travel is complete. Map transition management is postponed; users build it with show/hide.
- The spinner is also provided as a standalone UMG widget, and the materials must work on their own on a plain UMG `Image`. Only the subsystem's icon keeps spinning during blocking loads; spinners placed in user widgets do not.
- **Implemented:** `ULoadingFXIconSubsystem` (`Acquire` / `Release` / `ReleaseAll`, `IsHandleActive`, `OnVisibilityChanged`; owner auto-release is polled by a core ticker that runs only while owned requests exist; the viewport widget is created lazily and also on `UGameViewportClient::OnViewportCreated`, because the game viewport is created after the game instance) and `SLoadingFXSpinner` (leaf Slate widget drawing a material brush, to be reused by the UMG widget). The MoviePlayer takeover is `HandlePrepareLoadingScreen`; it checks `LoadingScreenIsPrepared()` first, so a loading screen set up by someone else wins. Console: `LoadingFX.Icon.Show` / `Hide` / `Dump`.
- **Implemented (UMG):** `ULoadingFXSpinner` wraps `SLoadingFXSpinner`. Properties use `BlueprintGetter` / `BlueprintSetter` so Blueprint sees one Get/Set pair each. `Material` empty means the project's loading icon material, resolved in `ResolveMaterial` (the result is held in the transient `DrawnMaterial` so the fallback stays referenced). `GetDynamicMaterial` follows `UImage`: the dynamic instance replaces `Material` on that widget. Verified at runtime with `LFXProto.UmgSpinner shot quit` (no widget blueprint; the widgets are created with `NewObject` and hosted through `TakeWidget`).
- **Implemented (preload):** `Initialize` starts `FSoftObjectPath::LoadAsync` for the effective `LoadingIconMaterial` (a material already in memory, as in the editor, is taken directly; `FindObject` skips objects still being async loaded). The result is held in the `IconMaterial` UPROPERTY. If the material is needed while the preload is still in flight (an `Acquire` during startup, or a blocking load that starts that early), `GetIconMaterial` waits for that one request with `FlushAsyncLoading(RequestId)`, which also runs the completion delegate, so the icon still appears at once. Decided over "show the icon when the material arrives" because MoviePlayer needs a drawable widget at the moment `OnPrepareLoadingScreen` fires, and the wait is at most what is left of one small package. A missing or wrong-typed material logs one warning at load time and the icon draws nothing. Checked with `LFXProto.Preload` (see Verification Prototype).
- **Implemented (minimum display time):** `ULoadingFXSettings::IconMinimumDisplayTime` (seconds, default 1, 0 = none), counted from the moment the icon became visible (the first `Acquire` while it was hidden). When the last request goes sooner (`Release`, owner auto-release, and also `ReleaseAll`), the icon stays until that time is over. A core ticker, registered only for that hold, compares `FPlatformTime::Seconds()` with the deadline, so it runs while the game is paused and across travel, and the time of a blocking load counts. `IsIconVisible` / `OnVisibilityChanged` follow what is on screen: still visible during the hold. An `Acquire` during the hold only cancels it (no hide/show pair, and the time still counts from the first show). A blocking load that starts during the hold is taken over by MoviePlayer as usual, because the icon is on screen and would freeze there otherwise. The setting is read at each last release, so editor changes apply at once. Checked with `LFXProto.MinDisplay`.

### Material contract

- The time source is the `Time` node with **Ignore Pause enabled** (real time), so spinners keep animating while the game thread is blocked (confirmed, see Verification Prototype). No external time path is needed.
- Multiply the final output by `VertexColor` (UMG `ColorAndOpacity`, `RenderOpacity` and fades arrive through it): Emissive = `PrimaryColor.rgb * VertexColor.rgb`, Opacity = `coverage * PrimaryColor.a * VertexColor.a`.
- Use common parameter names across all spinners (e.g. `PrimaryColor`, `SecondaryColor`, `Speed`, `Thickness`). `Speed` is in cycles per second (revolutions per second for rotating spinners); positive turns clockwise.
- **Default footprint:** with default parameters a ring layout touches the reference circle of radius 0.8 (`P` units: 1.0 = the widget edge on the shorter side) and a grid layout touches the reference square of half-width 0.72 (keyline, 0.9 × 0.8, so circles and squares look the same size), measured at the largest moment of any pulse. The margin keeps pulses and the anti-aliased edge off the widget border. Per material: Spinner `Ring + RMax = 0.8`, Bars `OuterRadius + Thickness / 2 = 0.8`, Arc and Comet `Radius + Thickness / 2 = 0.8`, Icon `Spacing + RBase + RGrow = 0.72`, Boxes `BoxSize + BoxGap / 2 = 0.36` in its half-scale `p`. Check with `LFXProto.Showcase ref`.
- A spinner must look complete with default parameters and must not break when drawn at a non-square size. Build coordinates with `MF_SpinnerCoords`: `P` is centered and y-up, and the shorter side spans -1..1, so the shape stays round and centered. `PixelSize` is one screen pixel in `P` units, for anti-aliasing. It derives the widget size from UV screen derivatives, so no size parameter is needed.

### Asset loader (secondary feature)

- It handles generic async and sync asset loading only.
- Sync loads broadcast begin/end events so the Bridge can switch the icon to blocking rendering.

## Verification Prototype

`Source/LoadingFX_Dev/Prototype/` (throwaway, not part of the plugin): `ULoadingFXProtoSubsystem` + `SLoadingFXProtoOverlay`, driven by the `LFXProto.*` console commands (see the header). Run it outside the editor, because MoviePlayer is disabled when `GIsEditor`, in commandlets, and with `-NoLoadingScreen`:

```
<UE_5.5>\Engine\Binaries\Win64\UnrealEditor.exe <repo>\LoadingFX_Dev.uproject -game -windowed -ResX=1280 -ResY=720 -ExecCmds="LFXProto.RunAll"
```

`/Game/Prototype/M_LoadingSpinner_GameTime` (built by `build_proto_gametime_variant.py`) is the spinner with Ignore Pause off, for an A/B comparison. Rebuild it after rebuilding `M_LoadingSpinner`.

`LFXProto.Gallery shot quit` draws every material square, wide, tall, tinted and small (`SLoadingFXProtoGallery`) and saves two screenshots to `Saved/Screenshots/LFXProto_Gallery_{A,B}.png`, to check the material contract visually.

`LFXProto.IconTravel [Map] [Sec] [quit]` exercises the real `ULoadingFXIconSubsystem`: acquire (one plain request, one owned by a throwaway object that is then marked garbage), OpenLevel with `Sec` seconds of simulated load (expect the icon as loading screen), release. Saves `Saved/Screenshots/LFXProto_Icon_{Viewport,AfterTravel}.png`.

`LFXProto.Showcase [Size] [ref] [shot] [quit]` is the quick visual review: every material under `/LoadingFX/Materials` side by side on a black full-screen background (the loading screen's background), `Size` px each (default 256), drawn through `SLoadingFXSpinner` (`SLoadingFXProtoShowcase`). Without `quit` it stays open so the animation can be watched; `ref` overlays the contract's reference circle (blue) and square (orange) on every tile; `shot` saves `Saved/Screenshots/LFXProto_Showcase.png`. Run `LFXProto.Showcase` again to hide it.

`LFXProto.UmgSpinner [shot] [quit]` shows a row of runtime-created `ULoadingFXSpinner` widgets (project default, `M_LoadingBoxes` tinted at 96 px, dynamic material with `PrimaryColor` / `Speed` changed, opacity 0.3, wide 160x64) and saves `Saved/Screenshots/LFXProto_UmgSpinner.png`.

`LFXProto.Preload [shot] [quit]` checks the icon material preload: the material is in memory before the first `Acquire`, `Acquire` causes no sync load of its package (counted through `FCoreDelegates::OnSyncLoadPackage` from game instance init on), and the PSO state of every graphics PSO the material asked to precache (`FMaterial::GetMaterialPSOPrecacheRequestIDs` → `GetMaterialPSOPrecacheData` → `PipelineStateCache::CheckPipelineStateInCache`), compared with `M_LoadingArc` loaded on demand at the same moment. PSO states need a packaged build: `PipelineStateCache::IsPSOPrecachingEnabled()` returns false under `WITH_EDITOR`, so `UnrealEditor.exe -game` never precaches. Add `-LFXProtoEarlyAcquire` to the command line to also acquire inside the prototype subsystem's `Initialize` (it initializes the icon subsystem first), which hits the in-flight preload. The prototype loads its own material list on first use, so that it does not hide the preload.

`LFXProto.MinDisplay [quit]` checks the minimum display time against the project's `IconMinimumDisplayTime` (the expected values assume at least 0.8 s) and logs the `OnVisibilityChangedNative` events of each case: a 0.2 s request (held until the minimum), an `Acquire` again while held (no hide in between, hidden at the minimum counted from the first show), a request longer than the minimum (hidden at the release), `ReleaseAll` (held as well), and the setting at 0 for a moment (hidden at the release). In 5.5 `-game` (2026-10-11) every case matched, with the held icon hidden 1.00 to 1.02 s after it appeared.

### Findings (UE 5.5 `-game`, packaged builds on 5.5 and 5.8; engine code read for 5.5 and 5.8)

- **Material time:** Slate gives UI materials `View.RealTime = FPlatformTime::Seconds()` at draw time and `View.GameTime = FApp::CurrentTime`, which only the game thread advances (`SlateRHIRenderer.cpp`, same in 5.8). The `Time` node uses GameTime unless **Ignore Pause** is on, so spinner materials must enable Ignore Pause. Confirmed visually (5.5 `-game`, 30 s block): the RealTime spinners animate under MoviePlayer and the GameTime variant freezes.
- **Manual MoviePlayer around a sync load works:** `SetupLoadingScreen` → `PlayMovie()` → blocking work → `WaitForMovieToFinish()`. The widget was painted about 60 times per second, all off the game thread. The engine loop also calls `WaitForMovieToFinish(true)` right after `GEngine->Tick()` every frame, which restores the game viewport afterwards.
- **LoadMap:** MoviePlayer hooks `PreLoadMap` itself and calls `PlayMovie()`, which broadcasts `OnPrepareLoadingScreen` when nothing is set up. Binding that event (not `PreLoadMap`, whose call order is not guaranteed) gives the v1 behavior: take over only when the icon is visible. Loading screen attributes are cleared after every playback.
- **Background:** the MoviePlayer root is `SDefaultMovieBorder` with `BlackBrush`, so the screen behind the icon is black while blocked. The last game frame is not shown.
- **GC:** materials held by a `UPROPERTY` survived a `CollectGarbage` run in the middle of the blocked section, and LoadMap's own GC.
- **Packaged builds:** `LFXProto.RunAll` gives the same results in packaged Development builds on 5.5 and 5.8 (the 5.8 build was made from a copy of the project, so this project's content was never saved with 5.8). Plugin assets loaded only by path are not cooked on their own; this project lists `/LoadingFX` in `DirectoriesToAlwaysCook` (`DefaultGame.ini`).
- **Icon material preload (2026-10-11, 5.5):** in a packaged Development build (D3D12) the preload was ready 5.9 ms after the request, before the startup LoadMap. At the first `Acquire` all 10 Slate graphics PSOs of `M_LoadingSpinner` were compiled, and `Acquire` took 0.03 ms with no sync load. `M_LoadingArc`, loaded on demand at the same moment, had none of its PSOs collected yet right after the load (the collection runs asynchronously after PostLoad); its 10 were compiled 3 s later. With `-LFXProtoEarlyAcquire` the wait for the in-flight preload took 0.1 ms packaged and 4.6 ms in `-game`, and the icon then took over the startup LoadMap through MoviePlayer. In `-game` (uncooked) the completion delegate only runs at the first async-loading tick, which during engine init is the startup LoadMap, so the log shows it 0.7 to 1 s after the request although the load itself takes a few ms. A missing material path logs one warning and draws nothing (also with an early `Acquire`); a material already in memory (tested with the non-UI `WorldGridMaterial`, which also warns) is taken without a load.

Packaged build used for these checks (about 2 minutes, staged to `Saved/StagedBuilds/Windows/LoadingFX_Dev.exe`, screenshots under `Saved/StagedBuilds/Windows/LoadingFX_Dev/Saved/Screenshots`):

```
<UE_5.5>\Engine\Build\BatchFiles\RunUAT.bat BuildCookRun -project="<repo>\LoadingFX_Dev.uproject" -platform=Win64 -clientconfig=Development -build -cook -stage -pak -unattended -utf8output -nop4 -nocompileeditor -skipbuildeditor
```

### Cooking the default material (UE 5.5 `-run=Cook`; engine source read for 5.5)

Verified 2026-10-08 with a throwaway probe (a `UDeveloperSettings` class holding two `TSoftObjectPtr<UMaterialInterface>` properties, plus a `FGameDelegates::GetModifyCookDelegate()` handler in the game module) while `/LoadingFX` was removed from `DirectoriesToAlwaysCook`. The probe was reverted; the log is `Saved/Logs/CookProbe_Cook.log` (local only). Instigators are printed with `-dpcvars=cook.displaymode=6`.

- **Soft references read from an ini are cooked automatically.** `FSoftObjectPath::ImportTextItem` reports the value to `GRedirectCollector` ("Consider this a load, so Config string references get cooked"), and `StartCookByTheBook` requests those packages with instigator `StartupSoftObjectPath`. Confirmed: `M_LoadingIcon`, referenced only by a `DefaultGame.ini` line, was cooked. So a material the user picks in Project Settings is cooked with no extra setup.
- **A C++ constructor default is not cooked.** Only ini text is collected; the CDO holding `M_LoadingSpinner` as its constructor default did not get it cooked (negative control). This is exactly the untouched-default case.
- **`FGameDelegates::Get().GetModifyCookDelegate()` is the official plugin hook.** Multicast, listed by `-helpcookusage` ("Subscribe to this delegate during your module startup"), called from `UCookOnTheFlyServer::CollectFilesToCook` right after `UAssetManager::ModifyCook`. Confirmed: `M_LoadingBoxes` added by the handler was cooked with instigator `ModifyCookDelegate`; its material functions followed as `HardDependency`.
- **Implemented:** `ULoadingFXSettings::LoadingIconMaterial` (`Config=Game`, `DefaultConfig`, constructor default `M_LoadingSpinner`; Project Settings > Plugins > LoadingFX) and `FLoadingFXModule::OnModifyCook`, bound to `GetModifyCookDelegate()` in `StartupModule` under `WITH_EDITOR` and removed in `ShutdownModule`. It adds the package of the effective material (default or user override) to `PackagesToCook`, so user projects need no `DirectoriesToAlwaysCook` entry.
- **Alternatives considered.** A plugin-shipped `Config/Game.ini` with `+DirectoriesToAlwaysCook=(Path="/LoadingFX")` works and has Epic precedent (`Engine/Plugins/NNE/NNEDenoiser/Config/Game.ini`), but cooks every bundled spinner. Plugin ini files are dynamic config layers applied *after* the project's `Default*.ini` (`FConfigBranch::AddDynamicLayersToHierarchy`), so never put a scalar default such as the material path in one: it would override the user's choice. `UPrimaryAssetLabel` needs project-side `PrimaryAssetTypesToScan` edits (the default type is `bIsEditorOnly=True`, `CookRule=Unknown`, scans `/Game` only, and only one entry per type is allowed). Loading the material at startup (hard reference in a native CDO) is cooked as `StartupPackage` but forces an eager load in every process. `GetCookModificationDelegate` is deprecated since 5.0.
- `SkipOnlyEditorOnly=true` is the 5.5 default (`BaseEditor.ini`), so packages merely loaded during the cook are not cooked unless a cooked package references them.
- This project keeps `+DirectoriesToAlwaysCook=(Path="/LoadingFX")` because the prototype loads every spinner by path at runtime.

## Conventions

- Copyright header: `// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).`
- `PCHUsage = UseExplicitOrSharedPCHs`; always include the module's own header explicitly.
- Use `Category = "LoadingFX"` for `UFUNCTION` / `UPROPERTY`.
- The plugin must work in both Blueprint-only and C++ projects.
