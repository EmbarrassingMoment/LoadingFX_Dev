# LoadingFX

[![Unreal Engine](https://img.shields.io/badge/Unreal%20Engine-5.5%2B-black?style=flat&logo=unrealengine&logoColor=white)](https://www.unrealengine.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Win64-blue?style=flat&logo=windows&logoColor=white)](#requirements)

> 日本語版はこちら → [README.ja.md](README.ja.md)

> **Work in progress** — this plugin is under active development and has not been released yet.

## Description

LoadingFX is a loading indicator plugin for Unreal Engine 5. It ships a library of procedural, material-based spinners, a loading icon you can show and hide from anywhere, and a lightweight asset loader. The loading icon and the asset loader are independent — use either one on its own, or both together.

## Planned Features

- **Spinner material library** — procedural (SDF) spinner materials with no textures. Use them on a plain UMG `Image`, through the bundled UMG spinner widget, or as the project-wide loading icon.
- **Loading icon subsystem** — show and hide the loading icon from Blueprint or C++ anywhere in your game. Requests are reference-counted, so multiple systems can share the icon safely, and the icon survives map travel.
- **Keeps spinning during blocking loads** — the icon keeps animating while the game thread is blocked (for example during `OpenLevel`). This relies on the engine's MoviePlayer, which is unavailable in the editor and PIE, so the icon freezes there during blocking loads; check it with `-game` or a packaged build.
- **Lightweight asset loader** — async and sync asset loading with completion callbacks and progress. It can drive the loading icon automatically, or be used on its own.

## Requirements

- Unreal Engine 5.5 – 5.8
- Windows (Win64)

## Repository Layout

| Path | Contents |
|------|----------|
| `Plugins/LoadingFX/` | The LoadingFX plugin (what is distributed on Fab) |
| `Source/LoadingFX_Dev/`, `Content/` | Sample project and implementation samples |

## License

[MIT](LICENSE)
