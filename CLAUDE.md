# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

The current materials (`M_LoadingSpinner`, `M_LoadingIcon`, `M_LoadingBoxes`) were ported from the sandbox project and follow the material contract below.

## Confirmed Design Decisions

### Loading icon (display — the main feature)

- Spinners are procedural (SDF) materials, and many are bundled. The loading icon uses a **project-wide default only** (Project Settings). There is no per-request override and no runtime switching API.
- The loading icon subsystem is a `UGameInstanceSubsystem`. Show and hide use handle-based reference counting (`Acquire(Reason)` / `Release(Handle)`), with optional auto-release when a weakly referenced owner is destroyed.
- The icon is added with `UGameViewportClient::AddViewportWidgetContent` so it survives map travel. Do not use `AddToViewport`, because those widgets are removed on world teardown.
- The icon must keep animating during blocking loads, which requires MoviePlayer. MoviePlayer is unavailable in PIE, so the icon freezes there; document this behavior.
- **v1 scope:** if the icon is visible when LoadMap starts, automatically switch to blocking rendering (`PreLoadMap` / `PostLoadMapWithWorld`). It does **not** auto-show the icon or decide when travel is complete. Map transition management is postponed; users build it with show/hide.
- The spinner is also provided as a standalone UMG widget, and the materials must work on their own on a plain UMG `Image`. Only the subsystem's icon keeps spinning during blocking loads; spinners placed in user widgets do not.

### Material contract

- The time source is the `Time` node with **Ignore Pause enabled** (real time), so spinners keep animating while the game thread is blocked (confirmed, see Verification Prototype). No external time path is needed.
- Multiply the final output by `VertexColor` (UMG `ColorAndOpacity`, `RenderOpacity` and fades arrive through it): Emissive = `PrimaryColor.rgb * VertexColor.rgb`, Opacity = `coverage * PrimaryColor.a * VertexColor.a`.
- Use common parameter names across all spinners (e.g. `PrimaryColor`, `SecondaryColor`, `Speed`, `Thickness`). `Speed` is in cycles per second (revolutions per second for rotating spinners); positive turns clockwise.
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

### Findings (UE 5.5 `-game`, packaged builds on 5.5 and 5.8; engine code read for 5.5 and 5.8)

- **Material time:** Slate gives UI materials `View.RealTime = FPlatformTime::Seconds()` at draw time and `View.GameTime = FApp::CurrentTime`, which only the game thread advances (`SlateRHIRenderer.cpp`, same in 5.8). The `Time` node uses GameTime unless **Ignore Pause** is on, so spinner materials must enable Ignore Pause. Confirmed visually (5.5 `-game`, 30 s block): the RealTime spinners animate under MoviePlayer and the GameTime variant freezes.
- **Manual MoviePlayer around a sync load works:** `SetupLoadingScreen` → `PlayMovie()` → blocking work → `WaitForMovieToFinish()`. The widget was painted about 60 times per second, all off the game thread. The engine loop also calls `WaitForMovieToFinish(true)` right after `GEngine->Tick()` every frame, which restores the game viewport afterwards.
- **LoadMap:** MoviePlayer hooks `PreLoadMap` itself and calls `PlayMovie()`, which broadcasts `OnPrepareLoadingScreen` when nothing is set up. Binding that event (not `PreLoadMap`, whose call order is not guaranteed) gives the v1 behavior: take over only when the icon is visible. Loading screen attributes are cleared after every playback.
- **Background:** the MoviePlayer root is `SDefaultMovieBorder` with `BlackBrush`, so the screen behind the icon is black while blocked. The last game frame is not shown.
- **GC:** materials held by a `UPROPERTY` survived a `CollectGarbage` run in the middle of the blocked section, and LoadMap's own GC.
- **Packaged builds:** `LFXProto.RunAll` gives the same results in packaged Development builds on 5.5 and 5.8 (the 5.8 build was made from a copy of the project, so this project's content was never saved with 5.8). Plugin assets loaded only by path are not cooked on their own; this project lists `/LoadingFX` in `DirectoriesToAlwaysCook` (`DefaultGame.ini`).

### Still open

- How the project-wide default spinner material gets cooked in user projects without `DirectoriesToAlwaysCook`.
- Decide whether sample content ships inside the plugin (for Fab users) or only in this project.

## Conventions

- Copyright header: `// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).`
- `PCHUsage = UseExplicitOrSharedPCHs`; always include the module's own header explicitly.
- Use `Category = "LoadingFX"` for `UFUNCTION` / `UPROPERTY`.
- The plugin must work in both Blueprint-only and C++ projects.
