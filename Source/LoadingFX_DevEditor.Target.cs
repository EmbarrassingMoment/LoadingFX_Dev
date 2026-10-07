// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

using UnrealBuildTool;
using System.Collections.Generic;

public class LoadingFX_DevEditorTarget : TargetRules
{
	public LoadingFX_DevEditorTarget( TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("LoadingFX_Dev");
	}
}
