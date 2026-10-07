// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Containers/ArrayView.h"
#include "Modules/ModuleManager.h"

class ITargetPlatform;

DECLARE_LOG_CATEGORY_EXTERN(LogLoadingFX, Log, All);

/**
 * Module class for the LoadingFX module.
 * Spinner widgets (Slate/UMG), the loading icon subsystem and blocking-load rendering.
 */
class FLoadingFXModule : public IModuleInterface
{
public:

	/** Called when the module is loaded into memory. */
	virtual void StartupModule() override;

	/** Called when the module is unloaded from memory. */
	virtual void ShutdownModule() override;

private:
#if WITH_EDITOR
	/**
	 * FGameDelegates::ModifyCookDelegate handler. Cook-by-the-book calls it when collecting the packages to cook;
	 * it adds the loading icon material from ULoadingFXSettings, which is otherwise referenced only by config.
	 */
	static void OnModifyCook(TConstArrayView<const ITargetPlatform*> TargetPlatforms, TArray<FName>& PackagesToCook, TArray<FName>& PackagesToNeverCook);

	FDelegateHandle ModifyCookHandle;
#endif
};
