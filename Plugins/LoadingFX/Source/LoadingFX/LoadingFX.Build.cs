// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

using UnrealBuildTool;

public class LoadingFX : ModuleRules
{
	public LoadingFX(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
				"Slate",
				"SlateCore",
				"UMG",
				"DeveloperSettings"
			}
		);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"MoviePlayer"
			}
		);
	}
}
