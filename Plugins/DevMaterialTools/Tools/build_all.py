"""
Rebuilds every LoadingFX material asset in dependency order (Material Functions first).
Run it with UE 5.5 so the saved assets stay loadable in 5.5.

Usage:
  UnrealEditor-Cmd.exe LoadingFX_Dev.uproject -run=pythonscript -script="<repo>/Plugins/DevMaterialTools/Tools/build_all.py"
"""
import os
import runpy

import unreal

TOOLS_DIR = os.path.join(
    unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_plugins_dir()),
    "DevMaterialTools", "Tools")

SCRIPTS = [
    "build_mf_glslmod.py",
    "build_mf_spinnercoords.py",
    "build_m_loadingspinner.py",
    "build_m_loadingicon.py",
    "build_m_loadingboxes.py",
    "build_m_loadingbars.py",
]

for name in SCRIPTS:
    print(f"[BUILD] {name}")
    runpy.run_path(os.path.join(TOOLS_DIR, name), run_name="__main__")
