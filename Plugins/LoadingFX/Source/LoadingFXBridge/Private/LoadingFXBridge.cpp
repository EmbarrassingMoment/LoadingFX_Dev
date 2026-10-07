// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXBridge.h"

#define LOCTEXT_NAMESPACE "FLoadingFXBridgeModule"

DEFINE_LOG_CATEGORY(LogLoadingFXBridge);

/** Called when the LoadingFXBridge module is loaded into memory. */
void FLoadingFXBridgeModule::StartupModule()
{
}

/** Called when the LoadingFXBridge module is unloaded from memory. */
void FLoadingFXBridgeModule::ShutdownModule()
{
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FLoadingFXBridgeModule, LoadingFXBridge)
