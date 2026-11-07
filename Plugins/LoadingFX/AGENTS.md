# LoadingFX — Guide for AI Coding Agents

This file is for AI coding agents (Claude Code, Codex, Cursor, Copilot, Gemini CLI, etc.) helping a developer **use** the LoadingFX plugin in their own Unreal Engine project. It describes the public API, the settings, the bundled materials and the rules to follow. It is not a guide for modifying the plugin itself.

- Plugin version: see `VersionName` in `LoadingFX.uplugin`
- Engine: Unreal Engine 5.5 – 5.8. Platforms: **Win64** (tested) and **Linux** (compiles, not yet run)
- Works in Blueprint-only and C++ projects; no C++ is needed for standard use
- Full docs: https://github.com/EmbarrassingMoment/LoadingFX_Dev (README in English and Japanese). The public headers under `Source/*/Public` are commented and are the reference for details.

## What the plugin does

Three runtime modules:

| Module | What it is | Public API |
| :--- | :--- | :--- |
| `LoadingFX` | The project-wide **loading icon** (`ULoadingFXIconSubsystem`), the settings, the UMG widgets *LoadingFX Spinner* and *LoadingFX Progress Bar*, and the bundled spinner materials | `LoadingFXIconSubsystem.h`, `LoadingFXSettings.h`, `LoadingFXSpinner.h`, `LoadingFXProgressBar.h`, `SLoadingFXSpinner.h`, `SLoadingFXProgressBar.h` |
| `LoadingFXLoader` | A lightweight **asset loader** (`ULoadingFXLoaderSubsystem`): async with progress and cancel, sync, handle + owner retention. No UI | `LoadingFXLoaderSubsystem.h`, `LoadingFXLoadAssetsAsyncAction.h` |
| `LoadingFXBridge` | Glue that shows the loading icon for loads made with `bShowLoadingIcon`, and keeps it animating through sync loads | none (works on its own once the plugin is enabled) |

`LoadingFX` and `LoadingFXLoader` do not depend on each other; use either one alone. All three are GameInstance-scoped: both subsystems are `UGameInstanceSubsystem`s, so each PIE instance has its own.

```
Acquire(Reason, Owner) ──► ULoadingFXIconSubsystem ──► viewport content (survives map travel)
                                   │
                 blocking map load / blocking section
                                   ▼
                     MoviePlayer loading screen: the icon on a solid color, animated off the game thread

LoadAssetsAsync / LoadAssetsSync (bShowLoadingIcon) ──► ULoadingFXLoaderSubsystem
                                   │ OnLoadStartedNative / OnLoadEndedNative
                                   ▼
                     LoadingFXBridge ──► Acquire / Release, Begin / EndBlockingSection
```

## Rules for agents

1. **Never edit assets under this plugin folder** (`Content/`). To change colors or timing, make a Material Instance of a bundled material in the project's own `Content/`, or change parameters at runtime through `Get Dynamic Material`. Plugin assets are overwritten on update.
2. **Prefer the bundled materials.** `/LoadingFX/Materials` has 18 spinners and 3 bars. Write a new material only when the developer asks for a custom look, and then follow the material contract below.
3. **Release every handle you acquire**, or give the request an `Owner` whose lifetime matches. A forgotten handle keeps the icon on screen forever (recover with `ReleaseAll`, or `LoadingFX.Icon.Hide all` in the console).
4. **For map travel, keep the icon handle somewhere that survives the travel** (the GameInstance, or a GameInstance subsystem), not in a Level Blueprint or an actor of the level being left. See the pattern below.
5. **Do not assume the plugin is in the project folder.** Installed from Fab it may live under the engine's `Plugins/Marketplace` folder. Check that `LoadingFX` is enabled in the project's `.uproject` or the Plugins window before debugging missing nodes or classes.
6. **The loading icon has one project-wide material.** There is no per-request override and no runtime switching API. Choose it in Project Settings (or `DefaultGame.ini`).
7. **Do not test the loading screen in PIE.** MoviePlayer is unavailable there; see *Verifying it*.

## Loading icon (`ULoadingFXIconSubsystem`, GameInstance subsystem)

Blueprint: *Get LoadingFXIconSubsystem*, category "LoadingFX". C++:

```cpp
#include "LoadingFXIconSubsystem.h"   // module "LoadingFX"

ULoadingFXIconSubsystem* Icon = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
FLoadingFXIconHandle Handle = Icon->Acquire(TEXT("Inventory"), /*Owner*/ nullptr);
// ... later
Icon->Release(Handle);   // takes the handle by reference and invalidates it
```

| Function (Blueprint name) | Behavior |
| :--- | :--- |
| `Acquire(FName Reason, UObject* Owner = nullptr)` (*Acquire Loading Icon*) | Adds a request and returns its `FLoadingFXIconHandle`. `Reason` is for the log and `LoadingFX.Icon.Dump`. With an `Owner`, the request is released automatically once that object is destroyed (polled every frame while owned requests exist). |
| `Release(FLoadingFXIconHandle& Handle)` (*Release Loading Icon*) | Releases one request and invalidates the handle. Returns false if it was not active. |
| `ReleaseAll()` (*Release All Loading Icon Requests*) | Releases every request, whoever made it. For recovery paths (back to the main menu). |
| `IsIconVisible()` | True while the icon is **on screen**: from the end of the show delay until it hides after the minimum display time. |
| `GetRequestCount()` | Active requests, including those still waiting for the show delay. |
| `IsHandleActive(Handle)` | True if that request has not been released. `FLoadingFXIconHandle::IsValid()` only says the copy was issued and not released through itself. |
| `OnVisibilityChanged(bool bVisible)` (Blueprint-assignable) / `OnVisibilityChangedNative` (C++, fires first) | Fires when the icon appears or hides, i.e. what is on screen, not the request count. |
| `BeginBlockingSection(FName Reason)` / `EndBlockingSection()` / `IsInBlockingSection()` (*Begin Blocking Section* / *End Blocking Section* / *Is In Blocking Section*) | Mark game-thread-blocking work so the icon keeps animating through it (see below). Nested sections are counted. End a section in the frame it began; one still open at the end of the frame is ended then, with a warning. |
| `FLoadingFXBlockingScope(const UObject* WorldContextObject, FName Reason)` (C++ only) | RAII form of a blocking section. Prefer it. |

Requests are reference counted: the icon stays while any request is active, so independent systems can share it. Everything is **game thread only**. The subsystem is not created on dedicated servers or in commandlets, so `GetSubsystem` returns null there; check it.

**Show delay and minimum display time** (both in real time, so they run while paused and through blocking loads):

- The icon appears only once the first request has been active for `IconShowDelay` (0.5 s). **A load shorter than the delay shows nothing at all.** Further requests do not move the deadline.
- Once on screen, it stays for at least `IconMinimumDisplayTime` (1 s), counted from when it appeared. **A short load still keeps the icon on screen for the minimum time**: with the defaults, a 0.6 s load shows the icon from 0.5 s to 1.5 s. An `Acquire` during that hold keeps it up without a hide/show pair.
- Set either to 0 to turn it off. Both are read at each first request / last release.

### Map travel and blocking loads

The icon is added with `UGameViewportClient::AddViewportWidgetContent`, not `AddToViewport`, so it survives map travel. If the icon is visible or requested (also within the show delay) when a blocking map load starts, the plugin takes over the engine's MoviePlayer loading screen and draws the icon there, so it keeps animating while the game thread is blocked. The screen behind it is one opaque color for the whole block, `LoadingScreenBackgroundColor` (**black** by default; the last game frame is not kept, so it cannot be translucent). The switch to it and back is instant; there are no fades. If the icon is not requested, nothing changes and the game simply hitches. If another loading screen is already set up (the project's own MoviePlayer screen, for example), the plugin leaves it alone.

The plugin does **not** show the icon by itself for travel and does not decide when travel is over:

```
[GameInstance or GameInstance subsystem]
  Handle = Acquire Loading Icon (Reason = "Travel")   // store Handle in the GameInstance
  Open Level (Destination)
[Destination level, once it is ready (BeginPlay, streaming done, ...)]
  Release Loading Icon (GameInstance.Handle)
```

- Do not pass an actor of the old level as `Owner`: it is destroyed by the travel, and its request is released right after the load, possibly before the destination is ready. Level Blueprint variables are lost on travel too.
- Acquiring in the same frame as `Open Level` is fine: the load starts later in that frame, with the request already active, so the icon appears on the loading screen at the show delay.

**Your own blocking work** (a *Load Asset Blocking* node, another plugin's synchronous load, a heavy loop):

```
[Blueprint: one chain of execution, all in the same frame]
  Handle = Acquire Loading Icon (Reason = "BuildCache")   // unless the icon is already requested
  Begin Blocking Section (Reason = "BuildCache")
  ... nodes that block the game thread ...
  End Blocking Section
  Release Loading Icon (Handle)
```

```cpp
{
    FLoadingFXBlockingScope BlockingScope(this, TEXT("BuildCache"));
    // ... work that blocks the game thread ...
}
```

The section starts MoviePlayer only if the icon is requested at that moment (acquire first), and does nothing where MoviePlayer is unavailable (editor, PIE, `-NoLoadingScreen`) or while another loading screen is set up or playing. The screen turns to `LoadingScreenBackgroundColor` (black by default) as soon as the section starts, even for very short work.

Begin and End must run in the same frame. Never put a latent node (*Delay*, the output pins of an async node) between them: it does not block, it lets the frame end. A section still open at the end of its frame is ended there and logs `Blocking section '<Reason>' was not ended in the frame it began`. Loads that do not block (*Load Assets Async*, the engine's *Async Load Asset*) need no section; acquire the icon around them instead.

Do not start blocking work inside the Slate tick, such as a widget's *Event Tick* or anything it calls. MoviePlayer cannot draw there, so a section (and a sync load through the loader) takes nothing over: it logs `BeginBlockingSection '<Reason>': called inside the Slate tick` and the icon freezes until the work is done. Start the work from an actor, a timer or a button's *On Clicked*.

## Settings (`ULoadingFXSettings`)

**Edit > Project Settings > Plugins > LoadingFX**, saved to the project's `Config/DefaultGame.ini`:

```ini
[/Script/LoadingFX.LoadingFXSettings]
LoadingIconMaterial=/LoadingFX/Materials/M_LoadingDotRing.M_LoadingDotRing  ; UI-domain material the icon draws
IconSize=(X=64.000000,Y=64.000000)          ; Slate units, scaled with DPI. Bars want something wide, e.g. (X=192,Y=12)
IconHorizontalAlignment=HAlign_Right
IconVerticalAlignment=VAlign_Bottom
IconPadding=(Left=32.000000,Top=32.000000,Right=32.000000,Bottom=32.000000)
IconTint=(R=1.000000,G=1.000000,B=1.000000,A=1.000000)  ; multiplied into the material (VertexColor); alpha fades it
IconShowDelay=0.500000            ; seconds from the first request until the icon appears; 0 = at once
IconMinimumDisplayTime=1.000000   ; seconds the icon stays once it appeared; 0 = hide at the last release
IconZOrder=10010                  ; among viewport widgets (UMG Add to Viewport uses ZOrder + 10)
LoadingScreenBackgroundColor=(R=0.000000,G=0.000000,B=0.000000,A=1.000000)  ; behind the icon on the MoviePlayer screen; linear, alpha ignored
```

The values above are the defaults; write only the keys you change. A one-off override for a test run: `-ini:Game:[/Script/LoadingFX.LoadingFXSettings]:IconShowDelay=0`.

## Bundled materials (`/LoadingFX/Materials`)

All are UI-domain, procedural (no textures), anti-aliased at any size, keep their shape centered at any aspect ratio, and animate in real time (they keep moving while the game is paused). With default parameters every spinner has the same visual size, so they can be swapped without touching the layout.

| Material | Look | Parameters (Shape · Motion; every material also has `PrimaryColor`) |
| :--- | :--- | :--- |
| `M_LoadingDotRing` | Ring of dots shrinking toward the tail, turning. **Default icon** | `Count` 8, `Radius` 0.64, `Arc` 0.75, `DotRadiusMax` 0.16, `DotRadiusMin` 0.035 · `Speed` 0.64 |
| `M_LoadingDotGrid` | Eight dots on a square, a pulse swells them in turn | `Spacing` 0.54, `DotRadiusMin` 0.06, `DotRadiusMax` 0.18 · `Speed` 0.8, `Attack` 0.5, `Trail` 4 |
| `M_LoadingBoxes` | Four rounded boxes brightening in turn | `BoxSize` 0.315, `BoxGap` 0.09, `BoxRound` 0.035 · `Speed` 1, `FadeCurve` 0.5; `OpacityMin` 0.1, `OpacityMax` 1 |
| `M_LoadingSpokes` | Classic radial spokes with a running fade | `Count` 8, `InnerRadius` 0.29, `OuterRadius` 0.715, `Thickness` 0.17 · `Speed` 1; `OpacityMin` 0.12 |
| `M_LoadingArc` | One arc stretching and shrinking while it turns | `Radius` 0.735, `Thickness` 0.13, `ArcMin` 0.06, `ArcMax` 0.68 · `Speed` 0.3, `StretchSpeed` 0.75 |
| `M_LoadingComet` | Round head with a fading tail | `Radius` 0.75, `Thickness` 0.1 · `Speed` 0.5 |
| `M_LoadingDotRow` | Row of dots swelling left to right (buttons, small wide places) | `Count` 3, `Spacing` 0.52, `DotRadiusMin` 0.1, `DotRadiusMax` 0.2 · `Speed` 1.1, `Stagger` 0.16, `PulseWidth` 0.55; `OpacityMin` 0.35 |
| `M_LoadingDualArc` | Two arc pairs on two rings, counter-rotating | `OuterRadius` 0.745, `InnerRadius` 0.47, `Thickness` 0.11, `Arc` 0.28 · `Speed` 0.7, `InnerSpeedRatio` -1.3 |
| `M_LoadingSegments` | Ring segments light up one by one, then go out | `Count` 10, `Radius` 0.735, `Thickness` 0.13, `Gap` 0.15 · `Speed` 0.45; `OpacityMin` 0.15 |
| `M_LoadingTimer` | Pie filling and emptying inside a ring | `Radius` 0.77, `Thickness` 0.06, `PieRadius` 0.6 · `Speed` 0.5; `RingOpacity` 1 |
| `M_LoadingHourglass` | Sand runs out, the glass turns over | `HalfHeight` 0.685, `HalfWidth` 0.5, `Neck` 0.07, `CapOverhang` 0.1, `Thickness` 0.07, `SandGap` 0.05, `StreamWidth` 0.02 · `Speed` 0.35, `FlipFraction` 0.2, `FlipShrink` 0.3 |
| `M_LoadingBounce` | Bouncing, squashing ball over a shadow | `BallRadius` 0.2, `Floor` -0.62, `BounceHeight` 0.94, `Squash` 0.3, `ShadowWidth` 0.26, `ShadowHeight` 0.035, `ShadowGap` 0.06 · `Speed` 0.9, `ContactFraction` 0.12; `ShadowOpacity` 0.35 |
| `M_LoadingRipple` | Rings spreading out and fading | `Count` 3, `Radius` 0.77, `Thickness` 0.06 · `Speed` 0.5, `Easing` 2 |
| `M_LoadingEqualizer` | Bars growing and shrinking in turn | `Count` 5, `Spacing` 0.32, `Thickness` 0.16, `HeightMin` 0.16, `HeightMax` 0.72 · `Speed` 1, `Stagger` 0.12, `PulseWidth` 1 |
| `M_LoadingGooey` | Droplets budding off a core and melting back | `Count` 3 (2 or more), `CoreRadius` 0.22, `DropletRadius` 0.15, `Radius` 0.65, `Smoothness` 0.3 · `Speed` 0.25, `SpreadSpeed` 0.5 |
| `M_LoadingMorph` | Rounded square turning a quarter, rounding into a circle | `HalfSize` 0.72, `CornerRadius` 0.13, `Roundness` 1 · `Speed` 0.5, `TurnFraction` 0.6 |
| `M_LoadingLine` | Thin indeterminate line at spinner size | `HalfWidth` 0.72, `Thickness` 0.1 · `Speed` 0.6, `TailDelay` 0.35; `TrackOpacity` 0.2 |
| `M_LoadingChase` | Dots chasing around a ring, melting into a blob at the top | `Count` 5 (1–8), `Radius` 0.672, `DotRadius` 0.09, `Smoothness` 0.12 · `Speed` 0.55, `Stagger` 0.075, `Easing` 0.85 |
| `M_LoadingBarSlide` | **Bar**, indeterminate: a segment slides across | `Thickness` 1.6 · `Speed` 0.6, `TailDelay` 0.35; `TrackOpacity` 0.25 |
| `M_LoadingBarStripes` | **Bar**, indeterminate: diagonal stripes running right | `Thickness` 1.6, `Period` 1.6, `Duty` 0.5 · `Speed` 1; `TrackOpacity` 0.25 |
| `M_LoadingBarFill` | **Bar**, determinate: fills to `Progress` with a sheen | `Progress` 0.65 in the asset (Input) · `Thickness` 1.6 · `Speed` 0.5, `SheenWidth` 1.5, `SheenStrength` 0.5; `TrackOpacity` 0.25 |

- Units: `P` space, where 1.0 is the edge of the widget's **shorter** side (so `Radius` 0.5 is half way to the edge). `Speed` is cycles per second (revolutions per second for anything that turns); positive is clockwise, negative reverses.
- Parameter groups in the material instance editor: **Input** (`Progress`), **Appearance** (`PrimaryColor`, every `*Opacity`, `OpacityMin` / `OpacityMax`), **Shape** (layout and sizes), **Motion** (`Speed` and timing).
- Raising `Count` on a row (`M_LoadingDotRow`, `M_LoadingEqualizer`) needs a smaller `Spacing`, or the row leaves the widget.
- Bars span the widget: draw them in something wide such as 320 × 16 (a square widget gives a circle). `Thickness` 2 fills the widget's height. `M_LoadingBarFill`'s sheen is invisible while `PrimaryColor` is white.
- Material functions in `/LoadingFX/MaterialFunctions` (`MF_SpinnerCoords`, `MF_Sd*2D`, `MF_GLSLMod`) are building blocks for custom spinners.

### Contract for a custom material

A material used as the loading icon, in the spinner widget or on a UMG `Image` should:

- use the **User Interface** material domain (Slate cannot draw anything else; the plugin logs a warning),
- take time from the `Time` node with **Ignore Pause** enabled (real time), or it freezes during blocking loads and pauses,
- multiply its output by `VertexColor` (Emissive = `PrimaryColor.rgb * VertexColor.rgb`, Opacity = `coverage * PrimaryColor.a * VertexColor.a`), so tint, `ColorAndOpacity`, `RenderOpacity` and fades reach it,
- build coordinates with `MF_SpinnerCoords` (`P` centered and y-up, `PixelSize` for anti-aliasing, `Extent` for shapes spanning the widget) so it stays round in non-square widgets,
- for a determinate bar, read a scalar parameter named **`Progress`** (0..1) and saturate it. The loading icon never sets parameters, so a determinate material is not for `LoadingIconMaterial`.

## UMG widgets (palette category *LoadingFX*)

| Widget | Properties and functions |
| :--- | :--- |
| **LoadingFX Spinner** (`ULoadingFXSpinner`) | `Material` (empty = the project's loading icon material), `ColorAndOpacity`, `Size` (64 × 64), `Set Opacity`, `Get Dynamic Material` (creates a dynamic instance that is drawn from then on; set `PrimaryColor`, `Speed`, ... on it). |
| **LoadingFX Progress Bar** (`ULoadingFXProgressBar`, derived from the spinner) | `Material` (empty = `M_LoadingBarFill`; any material with a `Progress` parameter), `Progress` (0..1), `Set Progress`, `Get Displayed Progress`, `SmoothingTime` (0.25 s), `Get Dynamic Material` (the drawn instance; it never replaces `Material`). An increase is interpolated over `SmoothingTime`; **a decrease is applied at once**, so a bar reset for the next load never runs backwards. |

Spinners placed in your own widgets **stop during blocking loads** (user widgets are not painted while the game thread is blocked). Only the subsystem's loading icon keeps animating through them. A plain UMG `Image` with a bundled material as its brush works too.

## Asset loader (`ULoadingFXLoaderSubsystem`, GameInstance subsystem, module `LoadingFXLoader`)

**Blueprint (category "LoadingFX")**

| Node | Behavior |
| :--- | :--- |
| **Load Assets Async** `(Assets[], Classes[], Reason, Owner = self, Show Loading Icon)` | Async action node. Exec outputs **On Progress**, **On Completed**, **On Canceled**, all with `Handle`, `Progress`, `LoadedAssets`, `LoadedClasses` (the arrays are filled on On Completed only, in request order, null where a load failed). Returns the action (`Cancel`, `Is Active`). |
| **Load Assets Sync** `(Assets[], Classes[], Reason, Owner = self, Show Loading Icon)` | Blocks the game thread; returns `Handle`, `LoadedAssets`, `LoadedClasses`. |
| **Release Loaded Assets** `(Handle)` / **Release All Loaded Assets** | Lets the assets be garbage collected. Releasing a load in flight cancels it (On Canceled fires). |
| **Is Handle Active**, **Is Load In Progress**, **Get Load Progress** | Queries. |

`Assets` takes soft object references and `Classes` soft class references; arrays of soft references to subclasses connect directly.

**C++**

```cpp
#include "LoadingFXLoaderSubsystem.h"   // module "LoadingFXLoader"

ULoadingFXLoaderSubsystem* Loader = GetGameInstance()->GetSubsystem<ULoadingFXLoaderSubsystem>();
TArray<FSoftObjectPath> Paths = { FSoftObjectPath(TEXT("/Game/UI/T_Portrait.T_Portrait")) };

FLoadingFXLoadHandle Handle = Loader->LoadAssetsAsync(
    Paths, TEXT("Portrait"), /*Owner*/ this, /*bShowLoadingIcon*/ true,
    FLoadingFXLoadCompleted::CreateUObject(this, &UMyWidget::HandleLoaded),        // (Handle, const TArray<UObject*>&)
    FLoadingFXLoadProgressChanged::CreateUObject(this, &UMyWidget::HandleProgress), // (Handle, float Progress), optional
    FLoadingFXLoadCanceled::CreateUObject(this, &UMyWidget::HandleCanceled));       // (Handle), optional

TArray<UObject*> Loaded;
FLoadingFXLoadHandle SyncHandle = Loader->LoadAssetsSync(Paths, TEXT("Portrait"), this, /*bShowLoadingIcon*/ false, Loaded);
// ... Loader->Release(Handle);  Loader->ReleaseAll();
```

`OnLoadStartedNative` / `OnLoadEndedNative` (`FLoadingFXLoadInfo`: `Handle`, `Reason`, `bSync`, `bShowLoadingIcon`, `bCanceled`) report every load to C++ listeners.

**Behavior to rely on:**

- **Retention:** loaded assets stay referenced until `Release(Handle)`, `ReleaseAll`, or until the `Owner` is destroyed. The Blueprint nodes default `Owner` to the calling object, so assets loaded from a widget go away with it. To keep assets longer, pass the GameInstance as `Owner` and release by hand. (This differs from the engine's *Async Load Asset*, which keeps nothing.)
- **Progress** is finished requested assets / requested assets. A one-asset request jumps from 0 to 1; dependencies are not counted, and the engine reports nothing finer. Progress 1 is reported right before completion.
- **No callback fires inside the load call**, even when everything is already in memory: completion comes on a later tick.
- **Cancel** stops the callbacks; packages already being read still finish loading.
- **`bShowLoadingIcon`** (default false): an async load acquires the loading icon from start to completion or cancel (so the show delay applies: a fast load shows nothing). A sync load acquires it around the call, and MoviePlayer takes over at once: the screen turns to the loading screen color (black by default) for the load, even a short one, with the icon appearing at the show delay. A sync load **without** the flag only keeps an icon that is already requested animating. Async loads without the flag (background preloads) never show the icon.
- Requires the `LoadingFXBridge` module for the flag to do anything; it is part of the plugin and needs no setup.

**Progress bar wiring (Blueprint):** *Load Assets Async* → *On Progress* → *Set Progress* (Progress pin) on a *LoadingFX Progress Bar*. That is all; no C++ glue.

## Cooking

Only two bundled materials are added to every cook automatically: the configured `LoadingIconMaterial` (default or override, through a ModifyCook hook) and `M_LoadingBarFill` (the progress bar's default). Any other bundled material is cooked when a cooked asset references it (a widget blueprint, a Material Instance, an `Image` brush). A material **loaded only by path at runtime** needs a hard reference or a *Directories to Always Cook* entry (`+DirectoriesToAlwaysCook=(Path="/LoadingFX/Materials")` under `[/Script/UnrealEd.ProjectPackagingSettings]` in `DefaultGame.ini`).

## C++ setup

Add the modules you use to the game module's `Build.cs`. `LoadingFX` (and `LoadingFXBridge`) are excluded from Server targets and every module's `PlatformAllowList` is Win64 and Linux, so guard the dependency if the project builds a dedicated server or other platforms:

```csharp
PrivateDependencyModuleNames.Add("LoadingFXLoader");
if (Target.Type != TargetType.Server)
{
    PrivateDependencyModuleNames.Add("LoadingFX");
}
```

Never depend on `LoadingFXBridge`; it has no API.

## Verifying it

- **MoviePlayer is unavailable in the editor, in PIE and with `-NoLoadingScreen`**, so there the icon freezes during blocking loads. Everything else (show delay, minimum time, widgets, the loader) works in PIE. Test blocking loads with *Standalone Game*, `-game`, or a packaged build:
  `UnrealEditor.exe <Project>.uproject -game -windowed -ResX=1280 -ResY=720`
- **Check the log first; it needs no other tool.** Log categories: `LogLoadingFX` (icon, MoviePlayer takeover), `LogLoadingFXLoader`, `LogLoadingFXBridge`. Requests and releases are logged at Verbose (`-LogCmds="LogLoadingFX Verbose"`). What a blocking load carried by the icon logs:
  - At startup, `MoviePlayer is unavailable in this process ...` means this run cannot show the loading screen (editor, PIE, `-NoLoadingScreen`).
  - `Compiled the shaders of the loading icon material ... in N ms`: uncooked runs only (see *Pitfalls*), and only when shaders were missing.
  - The takeover. Every form ends in `through MoviePlayer.`, so search for that. A map load logs `Loading icon is visible (N request(s)): rendering the blocking load through MoviePlayer.`; a blocking section, including any sync load from the loader while the icon is requested (the section takes the load's `Reason`), logs `... rendering blocking section '<Reason>' through MoviePlayer.` Within the show delay the line begins `Loading icon is requested (N request(s)) and appears in ...s (show delay):` instead.
  - `The show delay ended during a blocking load: the loading icon appears on the loading screen.`, logged by the loading screen itself. Missing when the load ended within the delay, or when the icon was already visible at the takeover.
  - The end: `Blocking section '<Reason>' ended after ...s: MoviePlayer stopped.` for a section, and the engine's own `LogLoad: Took ... seconds to LoadMap(...)` for a map load.
- **Seeing the loading screen takes the developer's eyes or a screen recording.** Screenshots and `-DumpMovie` do not capture MoviePlayer frames. Before recording, check that a recorder is installed (`ffmpeg -version`, for example). If none is, do not install one without asking the developer; rely on the log and ask them to watch. A desktop capture (ffmpeg `ddagrab`) records whatever is on top, and a `-game` window started from a script or an agent's shell often opens behind the active window, so keep the game window uncovered. ffmpeg 8.0 and later on Windows can capture the window itself, even when covered, with the `gfxcapture` source (`hwnd=<window handle>`; check that the build has it with `ffmpeg -hide_banner -h filter=gfxcapture`).
- **Size test loads well above `IconShowDelay`**, or set it to 0 for the run (the `-ini:` switch under *Settings*). In uncooked runs the first load of an asset can take several times longer than later ones (derived data such as compressed textures is built and cached on first use), so a test load that showed the icon once may finish within the delay on the next run and show nothing. Progress also arrives in coarse steps there: a large async load can report 0 for most of its time and then climb to 1 in a few steps. That is the engine, not the wiring.
- Console commands (not in Shipping builds):
  - `LoadingFX.Icon.Show [Reason]`: adds a console-owned request (each call adds one).
  - `LoadingFX.Icon.Hide [all]`: releases the newest console-owned request, or every request with `all`.
  - `LoadingFX.Icon.Dump`: logs the state and the active icon requests (id, reason, age, owner).
  - `LoadingFX.Loader.Dump`: logs the active loads.

## Pitfalls

- **Full-screen overlays above the icon.** The icon sits at `IconZOrder` 10010 among viewport widgets, just above TransitionFX's widget-layer presets (`WidgetZOrder` 10000), so it shows over a held fade. Anything added at a higher Z-order covers it (a preset whose `WidgetZOrder` was raised, or another plugin's overlay): raise `IconZOrder` above that overlay.
- **A short wait at startup in uncooked runs** (`-game`, Standalone Game): the engine compiles a material's shaders only when it is first drawn, which a blocked game thread cannot finish, so the icon subsystem compiles the icon material's shaders when it loads it and logs `Compiled the shaders of the loading icon material ... in N ms`. Expect a few tens of ms, or a second or two on the first run after the plugin is added or the material changed. Cooked builds and PIE skip this.
- **An `Owner` from the level being left** releases the request right after the travel (see *Map travel*).
- **A blocking section left open** (a branch that skips *End Blocking Section*, or a *Delay* before it) is ended at the end of the frame with a warning; the work after that point is not covered. Fix the graph so that every path reaches End in the same frame.
- **Blocking work in a widget's *Event Tick*** freezes the icon and logs `called inside the Slate tick`: MoviePlayer cannot draw there (see *Map travel and blocking loads*). Move the work out of the widget's Tick.
- **`IsIconVisible` is false within the show delay** although the icon is requested; use `GetRequestCount` to know whether it is requested.
- **A spinner in your own widget freezes during blocking loads**; only the loading icon keeps moving.

## Limitations

- Win64 and Linux only (`PlatformAllowList` of each module); Linux is compile-checked, not yet run. On a platform where the modules are not built, Blueprints that use the plugin fail to cook. To try another platform, add it to each module's allow list in `LoadingFX.uplugin`.
- No progress for map travel or blocking loads: the engine reports none, and nothing can update a widget while the game thread is blocked. Use a spinner or an indeterminate bar there; the progress bar is for asset loads started with the loader.
- One project-wide loading icon material; no per-request override.
- The MoviePlayer loading screen behind the icon is one opaque color (`LoadingScreenBackgroundColor`); there is no background image and no fade in or out yet.
- No replication; everything is local to the GameInstance.
- Report issues at https://github.com/EmbarrassingMoment/LoadingFX_Dev/issues.
