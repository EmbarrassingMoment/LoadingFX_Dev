// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

using UnrealBuildTool;
using System.Collections.Generic;

public class LoadingFX_DevTarget : TargetRules
{
	public LoadingFX_DevTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("LoadingFX_Dev");
	}
}
