// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

using UnrealBuildTool;
using System.Collections.Generic;

public class LoadingFX_DevEditorTarget : TargetRules
{
	public LoadingFX_DevEditorTarget( TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("LoadingFX_Dev");
	}
}
