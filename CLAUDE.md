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

The current materials (`M_LoadingSpinner`, `M_LoadingIcon`, `M_LoadingBoxes`) were ported from the sandbox project for the prototype. They do **not** follow the material contract below yet: they don't multiply by `VertexColor`, use their own parameter names, read `Time` directly, and assume a square widget.

## Confirmed Design Decisions

### Loading icon (display — the main feature)

- Spinners are procedural (SDF) materials, and many are bundled. The loading icon uses a **project-wide default only** (Project Settings). There is no per-request override and no runtime switching API.
- The loading icon subsystem is a `UGameInstanceSubsystem`. Show and hide use handle-based reference counting (`Acquire(Reason)` / `Release(Handle)`), with optional auto-release when a weakly referenced owner is destroyed.
- The icon is added with `UGameViewportClient::AddViewportWidgetContent` so it survives map travel. Do not use `AddToViewport`, because those widgets are removed on world teardown.
- The icon must keep animating during blocking loads, which requires MoviePlayer. MoviePlayer is unavailable in PIE, so the icon freezes there; document this behavior.
- **v1 scope:** if the icon is visible when LoadMap starts, automatically switch to blocking rendering (`PreLoadMap` / `PostLoadMapWithWorld`). It does **not** auto-show the icon or decide when travel is complete. Map transition management is postponed; users build it with show/hide.
- The spinner is also provided as a standalone UMG widget, and the materials must work on their own on a plain UMG `Image`. Only the subsystem's icon keeps spinning during blocking loads; spinners placed in user widgets do not.

### Material contract

- The default time source is the `Time` node. An optional external time can be passed via vertex data by the LoadingFX widget. The switch goes through a shared time Material Function and a scalar `UseExternalTime` (default 0); a static switch won't work because a MID cannot change static switches. This path is only needed if `Time` turns out not to advance under MoviePlayer.
- Multiply the final output by `VertexColor` (UMG `ColorAndOpacity`, `RenderOpacity` and fades arrive through it).
- Use common parameter names across all spinners (e.g. `PrimaryColor`, `SecondaryColor`, `Speed`, `Thickness`).
- A spinner must look complete with default parameters and must not break when drawn at a non-square size.

### Asset loader (secondary feature)

- It handles generic async and sync asset loading only.
- Sync loads broadcast begin/end events so the Bridge can switch the icon to blocking rendering.

## Next Steps / Open Items

- **Prototype first.** Verify in a packaged build on UE 5.5 and 5.8:
  - whether a UI material brush renders inside the MoviePlayer widget, and whether `Time` advances there
  - whether MoviePlayer can be started and stopped manually around arbitrary sync loads
  - what is drawn behind the icon while the game thread is blocked
  - whether the material survives the GC that runs during LoadMap
- Decide whether sample content ships inside the plugin (for Fab users) or only in this project.

## Conventions

- Copyright header: `// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).`
- `PCHUsage = UseExplicitOrSharedPCHs`; always include the module's own header explicitly.
- Use `Category = "LoadingFX"` for `UFUNCTION` / `UPROPERTY`.
- The plugin must work in both Blueprint-only and C++ projects.
