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
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon", meta = (ForceShowPluginContent))
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
	 * Time from the first request until the icon appears, so a load shorter than this shows nothing: releasing every
	 * request within it cancels the icon, and IsIconVisible / OnVisibilityChanged report it only once it appears. A
	 * blocking map load that starts within the delay is still rendered through MoviePlayer, and the icon appears on
	 * that screen when the delay is over. 0 shows the icon at the first request.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon", meta = (ClampMin = "0.0", UIMin = "0.0", UIMax = "5.0", ForceUnits = "s"))
	float IconShowDelay = 0.5f;

	/**
	 * Shortest time the icon stays on screen once it appears, so a short load does not make it flicker. If the last
	 * request is released sooner, the icon stays visible (IsIconVisible, OnVisibilityChanged) until this time is over,
	 * and an Acquire in the meantime keeps it up without hiding it in between. 0 hides it at the last release.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon", meta = (ClampMin = "0.0", UIMin = "0.0", UIMax = "5.0", ForceUnits = "s"))
	float IconMinimumDisplayTime = 1.0f;

	/**
	 * Z-order of the icon among viewport widgets. UMG's Add to Viewport uses its ZOrder + 10, so the default
	 * draws above HUD widgets added with the usual small values, and above full-screen overlays at 10000 (such as
	 * TransitionFX's widget-layer transitions), so the icon shows over a screen held covered while loading.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Icon", AdvancedDisplay)
	int32 IconZOrder = 10010;

	/**
	 * Color of the screen behind the icon while MoviePlayer draws it during a blocking load (map travel, a blocking
	 * section). The screen turns this color as soon as MoviePlayer takes over, also within the show delay, and keeps
	 * it until the load is over. Always opaque: the last game frame is not kept behind it. It does not apply to the
	 * icon in the viewport, or to a loading screen set up by someone else.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "LoadingFX|Loading Screen", meta = (HideAlphaChannel))
	FLinearColor LoadingScreenBackgroundColor = FLinearColor::Black;

	//~ Begin UDeveloperSettings Interface
	virtual FName GetCategoryName() const override;
	//~ End UDeveloperSettings Interface
};
