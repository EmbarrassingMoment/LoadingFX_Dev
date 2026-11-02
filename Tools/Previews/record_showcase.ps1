# Records the -game window of LoadingFX_Dev losslessly with ffmpeg while an LFXProto command runs.
# Usage: record_showcase.ps1 -ExecCmds "LFXProto.Showcase 192 spinners" -Out <file.mkv> [-Warmup 10] [-Seconds 12]
# The window opens at the desktop's top left and must stay uncovered while recording.
param(
    [string]$ExecCmds,
    [string]$Out,
    [int]$Warmup = 10,
    [int]$Seconds = 12,
    [int]$ResX = 1600,
    [int]$ResY = 900,
    [int]$Fps = 60,
    [string]$EngineDir = "C:\Program Files\Epic Games\UE_5.5"
)
$ue = Join-Path $EngineDir "Engine\Binaries\Win64\UnrealEditor.exe"
$proj = (Resolve-Path (Join-Path $PSScriptRoot "..\..\LoadingFX_Dev.uproject")).Path
$p = Start-Process -FilePath $ue -ArgumentList @("`"$proj`"", "-game", "-windowed", "-ResX=$ResX", "-ResY=$ResY", "-WinX=0", "-WinY=0", "-ExecCmds=`"$ExecCmds`"") -PassThru
# Wait for the game window (startup can take a while after a rebuild), then let the showcase settle.
$title = ""
for ($i = 0; $i -lt 300 -and -not $title; $i++) {
    Start-Sleep -Seconds 1
    $title = (Get-Process -Id $p.Id).MainWindowTitle
}
Start-Sleep -Seconds $Warmup
$proc = Get-Process -Id $p.Id
"title=[$($proc.MainWindowTitle)]"
if (-not $proc.MainWindowTitle) { Stop-Process -Id $p.Id -Force; throw "no window" }
# gdigrab's window mode returns a stale image of a flip-model swap chain, so grab the client area from the
# desktop with Desktop Duplication (ddagrab) instead. The window must stay uncovered while recording.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class LfxWin {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
$hwnd = $proc.MainWindowHandle
[void][LfxWin]::SetForegroundWindow($hwnd)
$rect = New-Object LfxWin+RECT
[void][LfxWin]::GetClientRect($hwnd, [ref]$rect)
$origin = New-Object LfxWin+POINT
[void][LfxWin]::ClientToScreen($hwnd, [ref]$origin)
$w = $rect.R - $rect.L; $h = $rect.B - $rect.T
"client=$($origin.X),$($origin.Y) ${w}x${h}"
Start-Sleep -Seconds 1
& ffmpeg -y -loglevel error -f lavfi -i "ddagrab=output_idx=0:framerate=${Fps}:offset_x=$($origin.X):offset_y=$($origin.Y):video_size=${w}x${h}:draw_mouse=0" -t $Seconds -vf "hwdownload,format=bgra" -c:v ffv1 $Out
"recorded $Out"
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
