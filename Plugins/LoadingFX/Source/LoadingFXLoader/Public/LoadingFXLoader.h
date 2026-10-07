// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

DECLARE_LOG_CATEGORY_EXTERN(LogLoadingFXLoader, Log, All);

/**
 * Module class for the LoadingFXLoader module.
 * Lightweight async/sync asset loader. Must not depend on any UI module.
 */
class FLoadingFXLoaderModule : public IModuleInterface
{
public:

	/** Called when the module is loaded into memory. */
	virtual void StartupModule() override;

	/** Called when the module is unloaded from memory. */
	virtual void ShutdownModule() override;
};
