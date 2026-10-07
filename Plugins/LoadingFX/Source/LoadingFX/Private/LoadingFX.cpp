// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFX.h"

#define LOCTEXT_NAMESPACE "FLoadingFXModule"

DEFINE_LOG_CATEGORY(LogLoadingFX);

/** Called when the LoadingFX module is loaded into memory. */
void FLoadingFXModule::StartupModule()
{
}

/** Called when the LoadingFX module is unloaded from memory. */
void FLoadingFXModule::ShutdownModule()
{
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FLoadingFXModule, LoadingFX)
