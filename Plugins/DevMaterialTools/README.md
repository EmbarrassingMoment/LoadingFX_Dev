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
| `build_all.py` | Runs all of the above in dependency order |

Run them with **UE 5.5** so the saved assets stay loadable in 5.5:

```
<UE_5.5>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe <repo>\LoadingFX_Dev.uproject -run=pythonscript -script="<repo>\Plugins\DevMaterialTools\Tools\build_all.py" -unattended -nosplash
```

Each script prints `[TEST] RESULT: PASS` when the graph matches its expected structure.
