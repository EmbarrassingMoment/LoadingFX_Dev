// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

DECLARE_LOG_CATEGORY_EXTERN(LogLoadingFXBridge, Log, All);

/**
 * Module class for the LoadingFXBridge module.
 * Optional glue that forwards LoadingFXLoader events to the LoadingFX loading icon.
 */
class FLoadingFXBridgeModule : public IModuleInterface
{
public:

	/** Called when the module is loaded into memory. */
	virtual void StartupModule() override;

	/** Called when the module is unloaded from memory. */
	virtual void ShutdownModule() override;
};
