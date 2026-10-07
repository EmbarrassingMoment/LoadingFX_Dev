// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFX.h"
#include "LoadingFXSettings.h"
#if WITH_EDITOR
#include "GameDelegates.h"
#endif

#define LOCTEXT_NAMESPACE "FLoadingFXModule"

DEFINE_LOG_CATEGORY(LogLoadingFX);

/** Called when the LoadingFX module is loaded into memory. */
void FLoadingFXModule::StartupModule()
{
#if WITH_EDITOR
	// The cooker only cooks what is requested or referenced from cooked packages. The loading icon material is
	// referenced from config alone, so register it here (the hook the cooker documents for plugins, see
	// -helpcookusage). Values the user types into Project Settings are also collected from the ini by the
	// cooker itself; this covers the untouched C++ default as well.
	ModifyCookHandle = FGameDelegates::Get().GetModifyCookDelegate().AddStatic(&FLoadingFXModule::OnModifyCook);
#endif
}

/** Called when the LoadingFX module is unloaded from memory. */
void FLoadingFXModule::ShutdownModule()
{
#if WITH_EDITOR
	if (ModifyCookHandle.IsValid())
	{
		FGameDelegates::Get().GetModifyCookDelegate().Remove(ModifyCookHandle);
		ModifyCookHandle.Reset();
	}
#endif
}

#if WITH_EDITOR
void FLoadingFXModule::OnModifyCook(TConstArrayView<const ITargetPlatform*> TargetPlatforms, TArray<FName>& PackagesToCook, TArray<FName>& PackagesToNeverCook)
{
	const FSoftObjectPath MaterialPath = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial.ToSoftObjectPath();
	if (MaterialPath.IsNull())
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("LoadingIconMaterial is not set (Project Settings > Plugins > LoadingFX); the loading icon has nothing to draw."));
		return;
	}

	const FName PackageName = MaterialPath.GetLongPackageFName();
	PackagesToCook.AddUnique(PackageName);
	UE_LOG(LogLoadingFX, Display, TEXT("Added the loading icon material package %s to the cook."), *PackageName.ToString());
}
#endif

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FLoadingFXModule, LoadingFX)
