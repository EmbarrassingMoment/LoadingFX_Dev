<#
.SYNOPSIS
Opens the UE 5.8 workbench: the git worktree that has branch workbench/ue58 checked out,
in UE 5.8 with the engine's MCP server running (http://127.0.0.1:8000/mcp).

.DESCRIPTION
The plugins are enabled on the command line, so the .uproject stays as it is. Content
saved in the workbench is 5.8-only and must never be committed; the pre-commit hook in
Tools/GitHooks rejects it. See "UE 5.8 workbench" in CLAUDE.md.

  powershell -ExecutionPolicy Bypass -File Tools\Open-Workbench.ps1 [-Build]

-Build compiles the editor target with that engine first (needed after C++ changes).
#>
param(
	[string]$Version = '5.8',
	[string]$Branch = 'workbench/ue58',
	[int]$Port = 8000,
	[switch]$Build
)
$ErrorActionPreference = 'Stop'

# The worktree that has the branch checked out.
$worktree = $null
$current = $null
foreach ($line in (git -C $PSScriptRoot worktree list --porcelain)) {
	if ($line -like 'worktree *') { $current = $line.Substring(9) }
	elseif ($line -eq "branch refs/heads/$Branch") { $worktree = $current }
}
if (-not $worktree) { throw "No worktree has $Branch checked out. Create one with: git worktree add -b $Branch ..\LoadingFX_Dev_UE58 origin/main" }

# The engine as installed by the Epic Games Launcher.
$installed = Get-Content (Join-Path $env:ProgramData 'Epic\UnrealEngineLauncher\LauncherInstalled.dat') -Raw | ConvertFrom-Json
$engine = ($installed.InstallationList | Where-Object { $_.AppName -eq "UE_$Version" } | Select-Object -First 1).InstallLocation
if (-not $engine) { throw "UE $Version is not installed through the Epic Games Launcher." }

$uproject = (Get-ChildItem $worktree -Filter *.uproject | Select-Object -First 1).FullName
if ($Build) {
	$target = [IO.Path]::GetFileNameWithoutExtension($uproject) + 'Editor'
	& (Join-Path $engine 'Engine\Build\BatchFiles\Build.bat') $target Win64 Development "-Project=$uproject" -WaitMutex
	if ($LASTEXITCODE -ne 0) { throw "Build failed ($LASTEXITCODE)." }
}

$editorArgs = @("`"$uproject`"", '-EnablePlugins=ModelContextProtocol,AllToolsets', '-ModelContextProtocolStartServer', "-ModelContextProtocolPort=$Port")
Start-Process -FilePath (Join-Path $engine 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList $editorArgs
"Opened $uproject in UE $Version. MCP: http://127.0.0.1:$Port/mcp"
