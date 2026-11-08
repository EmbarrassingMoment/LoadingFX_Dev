# LoadingFX FAQ

Frequently asked questions about the LoadingFX plugin. Whether LoadingFX works with UEFN is answered in the [README](../README.md#faq).

---

## Table of Contents

- [Troubleshooting](#troubleshooting)
- [Specifications & Behavior](#specifications--behavior)
- [Advanced Usage & Best Practices](#advanced-usage--best-practices)

---

## Troubleshooting

### Q: The loading icon stops moving during map loads in the editor (PIE).

That is expected. The icon keeps moving through a blocking load because the engine's MoviePlayer draws it on another thread, and MoviePlayer is unavailable in the editor, in PIE and with `-NoLoadingScreen`. Everything else (the show delay, the minimum display time, the widgets, the asset loader) works in PIE. To see the icon spin through a load, use *Standalone Game*, `-game` or a packaged build. When the current process cannot show the loading screen, the log says so at startup: `MoviePlayer is unavailable in this process`.

### Q: The loading icon does not appear for short loads.

That is the show delay. The icon appears only once the first request has been active for **Icon Show Delay** (0.5 s by default), so a load shorter than that shows nothing at all. Set it to 0 in *Project Settings > Plugins > LoadingFX* to show the icon at once, or for a single test run pass `-ini:Game:[/Script/LoadingFX.LoadingFXSettings]:IconShowDelay=0` on the command line.

### Q: The loading icon stays on screen after the load has finished.

For up to a second, that is the minimum display time: once the icon appears, it stays for at least **Icon Minimum Display Time** (1 s by default), so a load that just crossed the show delay does not flicker. Set it to 0 to hide the icon at the last release.

If it stays longer, a request has not been released. Run `LoadingFX.Icon.Dump` in the console to list the active requests with their reason, age and owner. Every *Acquire Loading Icon* needs a *Release Loading Icon* with its handle, or an `Owner` whose lifetime matches the request. *Release All Loading Icon Requests* (or `LoadingFX.Icon.Hide all` in the console) releases every request, for example on the way back to the main menu.

### Q: The loading icon disappears as soon as the new level has loaded, before my level is ready.

The travel released the request. An `Owner` from the level being left (one of its actors, or the player controller) is destroyed by the travel, and its request is released right after the load. When the destination needs time to get ready, acquire the icon without an owner, keep the handle in the GameInstance (or a GameInstance subsystem) and release it from the destination once it is ready. Level Blueprint variables do not survive the travel, so the handle cannot be kept there.

### Q: A spinner in my own widget stops moving during map loads.

Only the loading icon keeps moving through a blocking load. While the game thread is blocked, the game's widgets are not painted; the plugin hands the loading icon to MoviePlayer, which draws it on another thread. Spinners in your own widgets (a *LoadingFX Spinner*, or an *Image* with a bundled material) move again once the load is over. Use the loading icon for anything that must keep moving during the load.

### Q: The loading icon freezes during blocking work started from a widget's Event Tick.

MoviePlayer cannot draw while the game thread is inside the Slate tick, where a widget's *Event Tick* and everything it calls run. A blocking section started there, and a synchronous load with *Show Loading Icon*, take nothing over: the log says `BeginBlockingSection '<Reason>': called inside the Slate tick`, and the icon stands still until the work is done. Start blocking work from an actor, a timer or a button's *On Clicked* instead.

### Q: The loading icon is hidden behind a full-screen widget.

The icon sits at **Icon Z-Order** 10010 among the viewport widgets: above HUD widgets added with the usual small values, and above TransitionFX's widget-layer transitions (10000). A widget with a higher Z-order covers it; raise *Icon Z-Order* above that widget. *Add to Viewport* adds 10 to the Z-order you give it.

### Q: The materials do not show in a packaged build.

Only two bundled materials are cooked automatically: the material set as **Loading Icon Material** and `M_LoadingBarFill` (the progress bar's default). Any other bundled material is cooked when a cooked asset references it: a widget blueprint, a Material Instance, an *Image* brush. A material that your game loads only by path at runtime needs an entry in *Project Settings > Packaging > Additional Asset Directories to Cook* (an advanced setting), such as `/LoadingFX/Materials`.

### Q: The bundled materials are missing from an asset picker.

The plugin's own pickers always list them: **Loading Icon Material** in Project Settings, and **Material** on the *LoadingFX Spinner* and *LoadingFX Progress Bar* widgets. Other pickers, such as an *Image* brush or a material variable of your own, follow the editor's **Show Plugin Content** setting, which is off by default before UE 5.8. Turn it on from the Content Browser's **Settings** menu. The materials are in `/LoadingFX/Materials`.

### Q: The log says `Compiled the shaders of the loading icon material`.

That is normal in uncooked runs (*Standalone Game*, `-game`). The engine compiles a material's shaders when it is first drawn, which it cannot finish while the game thread is blocked, so the plugin compiles the loading icon material's shaders as soon as it loads the material. Otherwise the icon would be missing from the first loading screen. Expect a few tens of milliseconds, or a second or two on the first run after the plugin was added or the material changed. Cooked builds and PIE skip this.

---

## Specifications & Behavior

### Q: Can I use LoadingFX in a commercial project?

Yes. LoadingFX is released under the **MIT License**, which permits commercial use, modification, and distribution with no restrictions beyond including the license notice. See the `LICENSE` file in the repository root. The Fab package is free.

### Q: Do I need C++?

No. Everything you need is available in Blueprint, and the plugin works in Blueprint-only projects. Only a few conveniences are C++-only: the `FLoadingFXBlockingScope` scope, the loader's C++ callbacks, and its `OnLoadStartedNative` / `OnLoadEndedNative` events. The Fab package ships prebuilt binaries for each engine version. When you copy the plugin from this repository instead, a C++ project builds it with the project, and a Blueprint-only project needs binaries for its engine version.

### Q: Which engine versions are supported? Can I use UE 5.4 or earlier?

UE 5.5 to 5.8, with one Fab package per version. Earlier versions are not supported: the bundled assets are saved with UE 5.5, and an older engine cannot load them.

### Q: Which platforms are supported?

Win64 (tested) and Linux (compiled with the UE 5.5 and 5.8 cross-compile toolchains, not yet run). Those two are in every module's `PlatformAllowList`. On any other platform, such as Mac, Android, iOS or consoles, the modules are not built, and Blueprints that use the plugin fail to cook for it. The code has nothing platform-specific: to try another platform, add it to the `PlatformAllowList` of each module in `LoadingFX.uplugin` (untested).

### Q: Does it work on dedicated servers and in multiplayer games?

A dedicated server shows no UI, so the `LoadingFX` and `LoadingFXBridge` modules are excluded from Server targets, and the loading icon subsystem is not created on a dedicated server. The asset loader (`LoadingFXLoader`) is built for servers too. Nothing is replicated: the loading icon and the loader belong to each game instance, so every client shows the icon for its own loads. A C++ game module that has a server target should add the `LoadingFX` dependency for non-server targets only; see *C++ setup* in [AGENTS.md](../Plugins/LoadingFX/AGENTS.md#c-setup).

### Q: Does the plugin show the loading icon on map travel by itself?

No. The plugin cannot tell when a travel starts or when your destination is ready, so it never shows or hides the icon on its own. Acquire the icon before *Open Level*, and release it in the destination once it is ready. What the plugin does by itself: if the icon is requested when the map load starts, it draws the icon on the engine's loading screen, so it keeps moving while the game thread is blocked. Keep the handle somewhere that survives the travel, such as the GameInstance.

### Q: Can I show a progress bar for map travel?

No. The engine reports no progress for a map load, or for any other load that blocks the game thread, and no widget can be updated while the game thread is blocked anyway. Use a spinner, or an indeterminate bar (`M_LoadingBarSlide`, `M_LoadingBarStripes`), which also works as the loading icon with a wide *Icon Size* such as 192 × 12. The *LoadingFX Progress Bar* is for asset loads you start yourself, such as *Load Assets Async*.

### Q: Why does the screen turn black during a map load? Can I show an image, or fade in and out?

While the game thread is blocked, MoviePlayer draws the loading screen on another thread, and it keeps nothing of the last game frame. The plugin draws the icon over a full-screen color, **Loading Screen Background Color** (black by default, always opaque), which you can change in the settings. The switch to that color and back is instant. A background image and fades in and out of the loading screen are not available yet.

### Q: Can I use a different loading icon in different places?

The loading icon has one material for the whole project (**Loading Icon Material**). There is no per-request override and no way to switch it at runtime. To change its look, make a Material Instance of a bundled material and set it as the *Loading Icon Material*; *Icon Tint* colors it. Where your own UI needs another spinner, place a *LoadingFX Spinner* widget with any material (it stops during blocking loads, like any widget of yours).

### Q: Can I use LoadingFX with my own loading screen or another loading screen plugin?

Yes. LoadingFX takes over MoviePlayer only while the loading icon is requested, and leaves a loading screen that is already set up alone, so that screen is shown without the icon. To show a LoadingFX spinner on a MoviePlayer loading screen of your own, put an `SLoadingFXSpinner` (C++, Slate) with a bundled material in it: the materials run on real time, so they keep moving there.

### Q: Can I use LoadingFX with TransitionFX?

Yes, with no setup. The loading icon's *Icon Z-Order* (10010) is just above TransitionFX's widget-layer transitions (`WidgetZOrder` 10000), so the icon shows over a screen that TransitionFX holds covered while loading. During a blocking map load the screen switches to *Loading Screen Background Color*; set it to the transition's color (black by default in both plugins), and the switch to the loading screen and back does not show.

### Q: Do I need the asset loader to use the loading icon, or the other way round?

No. The loading icon (the `LoadingFX` module) and the asset loader (`LoadingFXLoader`) do not depend on each other; use either one alone. The `LoadingFXBridge` module connects them, so that *Show Loading Icon* on a load request shows the icon. It needs no setup.

### Q: How is *Load Assets Async* different from the engine's *Async Load Asset*?

- It loads several assets and classes in one request, and returns them in the order you requested them (null where a load failed).
- It reports progress (*On Progress*) and can be canceled (*Cancel* on the action the node returns, or *Release Loaded Assets*).
- It keeps the loaded assets in memory until you release the handle or the `Owner` is destroyed. The engine's node keeps nothing, so an asset you did not store anywhere can be unloaded by the next garbage collection.
- *Show Loading Icon* shows the loading icon while the load runs.

### Q: Why does the progress jump from 0 to 1?

Progress is the number of requested assets that finished loading, divided by the number requested. A request for one asset goes from 0 straight to 1: the engine reports nothing finer, and an asset's dependencies are not counted. In uncooked runs, a large load can also report 0 for most of its time and then climb to 1 in a few steps, because the first load of an asset builds and caches derived data.

---

## Advanced Usage & Best Practices

### Q: How do I change a spinner's color or speed?

- **In the editor:** make a Material Instance of a bundled material in your project's `Content` and change its parameters (`PrimaryColor`, `Speed`, ...). Do not edit the assets in the plugin folder; an update overwrites them.
- **At runtime:** call *Get Dynamic Material* on a *LoadingFX Spinner* widget, then *Set Vector Parameter Value* / *Set Scalar Parameter Value* on the instance it returns.
- **The loading icon:** set a Material Instance as *Loading Icon Material*, and use *Icon Tint* for the color. The loading icon has no runtime parameter API.

The widget's *Color and Opacity*, *Render Opacity* and animations multiply into every material. The parameters of each material are listed in [AGENTS.md](../Plugins/LoadingFX/AGENTS.md#bundled-materials-loadingfxmaterials).

### Q: Can I use the materials without the LoadingFX widgets?

Yes. Every bundled material is a User Interface material: set it as the brush of a plain UMG *Image*. The widget's *Color and Opacity*, *Render Opacity* and fades reach the material through the vertex color. The plugin must stay enabled, because the materials and their material functions are its content.

### Q: How do I keep the loading icon moving through my own blocking work?

Wrap the work in a blocking section. In Blueprint: *Acquire Loading Icon* (unless the icon is already requested) → **Begin Blocking Section** → the nodes that block, such as *Load Asset Blocking* → **End Blocking Section** → *Release Loading Icon*, all in one chain of execution. Begin and End must run in the same frame, so put no latent node (*Delay*, an async node's outputs) between them. In C++, `FLoadingFXBlockingScope` ends the section when it goes out of scope. See [Blocking sections](../README.md#blocking-sections) in the README.

### Q: Can I make my own spinner material?

Yes. A material for the loading icon, the spinner widget or an *Image* should use the User Interface material domain, take time from the `Time` node with **Ignore Pause** enabled (or it stops during blocking loads), multiply its output by `VertexColor`, and build its coordinates with `MF_SpinnerCoords` so that it stays round in a non-square widget. A determinate bar reads a scalar parameter named `Progress`. See [Contract for a custom material](../Plugins/LoadingFX/AGENTS.md#contract-for-a-custom-material) in AGENTS.md; the material functions in `/LoadingFX/MaterialFunctions` are building blocks for your own shapes.

### Q: How do I let an AI coding agent use LoadingFX?

The plugin folder ships `AGENTS.md`, a usage guide written for AI coding agents. Agents only read files inside your project, so add a pointer to it in the instruction file at your project's root. See [Using LoadingFX with AI coding agents](../README.md#using-loadingfx-with-ai-coding-agents) in the README.
