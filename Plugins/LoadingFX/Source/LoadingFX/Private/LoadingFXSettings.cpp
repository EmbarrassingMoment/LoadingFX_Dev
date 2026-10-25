// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXSettings.h"
#include "Materials/MaterialInterface.h"

ULoadingFXSettings::ULoadingFXSettings()
	: LoadingIconMaterial(FSoftObjectPath(TEXT("/LoadingFX/Materials/M_LoadingDotRing.M_LoadingDotRing")))
{
}

FName ULoadingFXSettings::GetCategoryName() const
{
	return TEXT("Plugins");
}
