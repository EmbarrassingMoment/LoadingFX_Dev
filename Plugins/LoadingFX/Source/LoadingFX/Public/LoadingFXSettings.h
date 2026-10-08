// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Layout/Margin.h"
#include "Types/SlateEnums.h"
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
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon")
	TSoftObjectPtr<UMaterialInterface> LoadingIconMaterial;

	/** Size of the loading icon in Slate units (scaled with the viewport DPI). */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon")
	FVector2D IconSize = FVector2D(64.0, 64.0);

	/** Horizontal placement of the icon in the viewport. */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon")
	TEnumAsByte<EHorizontalAlignment> IconHorizontalAlignment = HAlign_Right;

	/** Vertical placement of the icon in the viewport. */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon")
	TEnumAsByte<EVerticalAlignment> IconVerticalAlignment = VAlign_Bottom;

	/** Distance between the icon and the viewport edges. */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon")
	FMargin IconPadding = FMargin(32.0f);

	/** Multiplied into the material as VertexColor; alpha fades the icon. */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon")
	FLinearColor IconTint = FLinearColor::White;

	/**
	 * Z-order of the icon among viewport widgets. UMG's Add to Viewport uses its ZOrder + 10, so the default
	 * draws above HUD widgets added with the usual small values.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon", AdvancedDisplay)
	int32 IconZOrder = 1000;

	//~ Begin UDeveloperSettings Interface
	virtual FName GetCategoryName() const override;
	//~ End UDeveloperSettings Interface
};
