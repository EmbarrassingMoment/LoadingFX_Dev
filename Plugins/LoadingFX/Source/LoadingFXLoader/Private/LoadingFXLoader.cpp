// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXLoader.h"

#define LOCTEXT_NAMESPACE "FLoadingFXLoaderModule"

DEFINE_LOG_CATEGORY(LogLoadingFXLoader);

/** Called when the LoadingFXLoader module is loaded into memory. */
void FLoadingFXLoaderModule::StartupModule()
{
}

/** Called when the LoadingFXLoader module is unloaded from memory. */
void FLoadingFXLoaderModule::ShutdownModule()
{
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FLoadingFXLoaderModule, LoadingFXLoader)
