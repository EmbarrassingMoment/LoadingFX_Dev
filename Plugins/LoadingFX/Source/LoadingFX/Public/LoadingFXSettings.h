// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "UObject/SoftObjectPtr.h"
#include "LoadingFXSettings.generated.h"

class UMaterialInterface;

/**
 * Project-wide LoadingFX settings (Project Settings > Plugins > LoadingFX, saved to DefaultGame.ini).
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "LoadingFX"))
class LOADINGFX_API ULoadingFXSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	ULoadingFXSettings();

	/**
	 * Material drawn by the loading icon. Any UI-domain spinner material works; the bundled ones live in
	 * /LoadingFX/Materials. The effective value is added to every cook by FLoadingFXModule, so projects do
	 * not need a DirectoriesToAlwaysCook entry for it.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX")
	TSoftObjectPtr<UMaterialInterface> LoadingIconMaterial;

	//~ Begin UDeveloperSettings Interface
	virtual FName GetCategoryName() const override;
	//~ End UDeveloperSettings Interface
};
