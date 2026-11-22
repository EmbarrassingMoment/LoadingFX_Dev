# Records the -game window of LoadingFX_Dev losslessly with ffmpeg while an LFXProto command runs.
# Usage: record_showcase.ps1 -ExecCmds "LFXProto.Showcase 192 spinners" -Out <file.mkv> [-Warmup 10] [-Seconds 12]
# The window may stay behind other windows: ffmpeg's gfxcapture (Windows Graphics Capture) reads the window itself.
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
$p = Start-Process -FilePath $ue -ArgumentList @("`"$proj`"", "-game", "-windowed", "-ResX=$ResX", "-ResY=$ResY", "-ForceRes", "-WinX=0", "-WinY=0", "-ExecCmds=`"$ExecCmds`"") -PassThru
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
# gdigrab's window mode returns a stale image of a flip-model swap chain, and ddagrab grabs the desktop, so it
# needs the window on top. gfxcapture needs width and height, or it keeps the size the window had when it began.
$hwnd = [int64]$proc.MainWindowHandle
& ffmpeg -y -loglevel error -f lavfi -i "gfxcapture=hwnd=${hwnd}:capture_cursor=0:max_framerate=${Fps}:width=${ResX}:height=${ResY},hwdownload,format=bgra" -t $Seconds -r $Fps -c:v ffv1 -threads 8 -slices 24 $Out
"recorded $Out"
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
