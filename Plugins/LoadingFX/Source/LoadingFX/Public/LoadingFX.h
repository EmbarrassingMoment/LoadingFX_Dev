// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

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
};
