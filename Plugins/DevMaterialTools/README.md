# Dev Material Tools (Local)

Local-only editor plugin for developing LoadingFX. It is **not** part of the LoadingFX distribution and is excluded from the sample project release zip.

## What it does

`UDevMaterialTools` (`unreal.DevMaterialTools` in Python) exposes the material graph operations that `MaterialEditingLibrary` can't do from Python:

- Create Named Reroute Usage nodes linked to a Declaration (in materials and Material Functions)
- Create, list and delete comment boxes

## Material builder scripts

`Tools/` holds Python scripts that build the LoadingFX material assets from scratch. They write to the LoadingFX plugin content (`/LoadingFX/...`).

| Script | Output |
|--------|--------|
| `build_mf_glslmod.py` | `/LoadingFX/MaterialFunctions/MF_GLSLMod` |
| `build_mf_spinnercoords.py` | `/LoadingFX/MaterialFunctions/MF_SpinnerCoords` (shared centered, aspect-corrected coordinates) |
| `build_m_loadingspinner.py` | `/LoadingFX/Materials/M_LoadingSpinner` |
| `build_m_loadingicon.py` | `/LoadingFX/Materials/M_LoadingIcon` |
| `build_m_loadingboxes.py` | `/LoadingFX/MaterialFunctions/MF_SdRoundBox2D`, `/LoadingFX/Materials/M_LoadingBoxes` |
| `build_m_loadingbars.py` | `/LoadingFX/Materials/M_LoadingBars` (radial bars, AA width from `fwidth(d)`) |
| `build_m_loadingarc.py` | `/LoadingFX/Materials/M_LoadingArc` (stretching arc, iq's `sdArc`) |
| `build_m_loadingcomet.py` | `/LoadingFX/Materials/M_LoadingComet` (round head with a tail that thins and fades over one turn) |
| `build_m_loadingdots.py` | `/LoadingFX/Materials/M_LoadingDots` (a row of dots that swell and brighten in turn) |
| `build_m_loadingdualarc.py` | `/LoadingFX/Materials/M_LoadingDualArc` (two counter-rotating pairs of arcs, one color) |
| `build_m_loadingsegments.py` | `/LoadingFX/Materials/M_LoadingSegments` (a segmented ring that fills and drains one segment at a time) |
| `build_m_loadingtimer.py` | `/LoadingFX/Materials/M_LoadingTimer` (a pie that fills and empties inside a thin ring) |
| `build_m_loadinghourglass.py` | `/LoadingFX/MaterialFunctions/MF_SdSegment2D`, `/LoadingFX/Materials/M_LoadingHourglass` (sand runs out, then the glass turns over) |
| `build_m_loadingbounce.py` | `/LoadingFX/MaterialFunctions/MF_SdEllipse2D`, `/LoadingFX/Materials/M_LoadingBounce` (a ball that bounces and flattens on landing) |
| `build_m_loadingripple.py` | `/LoadingFX/Materials/M_LoadingRipple` (rings that spread from the center, slow down and fade out) |
| `build_m_loadingequalizer.py` | `/LoadingFX/Materials/M_LoadingEqualizer` (a row of rounded bars that grow and shrink in turn) |
| `build_m_loadinggooey.py` | `/LoadingFX/Materials/M_LoadingGooey` (droplets that bud off a core and melt back while turning) |
| `build_m_loadingmorph.py` | `/LoadingFX/Materials/M_LoadingMorph` (a rounded square that turns a quarter and rounds into a circle on the way) |
| `build_m_loadinglinear.py` | `/LoadingFX/Materials/M_LoadingLinear` (a bar that grows from the left of a thin track and leaves to the right) |
| `build_m_loadingchase.py` | `/LoadingFX/Materials/M_LoadingChase` (dots that chase each other around a ring and melt together where they bunch up) |
| `build_all.py` | Runs all of the above in dependency order |

Run them with **UE 5.5** so the saved assets stay loadable in 5.5:

```
<UE_5.5>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe <repo>\LoadingFX_Dev.uproject -run=pythonscript -script="<repo>\Plugins\DevMaterialTools\Tools\build_all.py" -unattended -nosplash
```

Each script prints `[TEST] RESULT: PASS` when the graph matches its expected structure.
