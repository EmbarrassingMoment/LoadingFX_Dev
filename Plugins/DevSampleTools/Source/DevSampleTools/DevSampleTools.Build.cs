// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

using UnrealBuildTool;

public class DevSampleTools : ModuleRules
{
	public DevSampleTools(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine"
			}
		);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"UnrealEd",
				"BlueprintGraph",
				"Slate",
				"SlateCore",
				"UMG",
				"UMGEditor"
			}
		);
	}
}
