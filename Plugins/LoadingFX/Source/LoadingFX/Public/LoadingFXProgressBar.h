// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "LoadingFXSpinner.h"
#include "LoadingFXProgressBar.generated.h"

class SLoadingFXProgressBar;
class UMaterialInstanceDynamic;

/**
 * UMG progress bar: draws a determinate LoadingFX bar material (one that reads the Progress parameter, see the material
 * contract) and fills it to Progress. With no material set it draws the plugin's default progress bar material.
 *
 * Progress is meant for the asset loader: connect Load Assets Async's On Progress to Set Progress. An increase is shown
 * over SmoothingTime seconds, so the loader's one-step-per-asset progress still reads as motion; a decrease (a reset for
 * the next load) is applied at once. Map travel and blocking loads report no progress in the engine, so use a spinner or
 * an indeterminate bar for those.
 *
 * The material is always drawn through a dynamic instance owned by this widget, so Progress can be written per widget.
 * Unlike the spinner, that instance never replaces Material: Get Material returns what was set, Get Dynamic Material
 * the instance that is drawn (change PrimaryColor on it, for example).
 */
UCLASS(meta = (DisplayName = "LoadingFX Progress Bar"))
class LOADINGFX_API ULoadingFXProgressBar : public ULoadingFXSpinner
{
	GENERATED_BODY()

public:
	ULoadingFXProgressBar(const FObjectInitializer& ObjectInitializer);

	/** Path of the bar material drawn when Material is empty (M_LoadingBarFill). Added to every cook by FLoadingFXModule. */
	static const TCHAR* GetDefaultMaterialPath();

	UFUNCTION(BlueprintGetter, Category = "LoadingFX")
	float GetProgress() const;

	/** Sets the fill, 0 to 1. An increase is interpolated over SmoothingTime, a decrease applied at once. */
	UFUNCTION(BlueprintSetter, Category = "LoadingFX")
	void SetProgress(float InProgress);

	/** The fill on screen right now: lags Progress while an increase is interpolated. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	float GetDisplayedProgress() const;

	UFUNCTION(BlueprintGetter, Category = "LoadingFX")
	float GetSmoothingTime() const;

	UFUNCTION(BlueprintSetter, Category = "LoadingFX")
	void SetSmoothingTime(float InSmoothingTime);

	/** The dynamic instance that is drawn (created from Material or the default bar material). Never replaces Material. */
	virtual UMaterialInstanceDynamic* GetDynamicMaterial() override;

	//~ Begin UWidget Interface
	virtual void SynchronizeProperties() override;
	virtual void ReleaseSlateResources(bool bReleaseChildren) override;
	//~ End UWidget Interface

protected:
	//~ Begin UWidget Interface
	virtual TSharedRef<SWidget> RebuildWidget() override;
	//~ End UWidget Interface

	//~ Begin ULoadingFXSpinner Interface
	/** The dynamic instance to draw: Material itself if it already is one, else an instance of Material or the default bar material. */
	virtual UMaterialInterface* ResolveMaterial() override;
	virtual void ApplyMaterial() override;
	//~ End ULoadingFXSpinner Interface

	/** Filled fraction of the bar, 0 to 1. */
	UPROPERTY(EditAnywhere, BlueprintGetter = GetProgress, BlueprintSetter = SetProgress, Category = "LoadingFX", meta = (ClampMin = "0.0", ClampMax = "1.0", UIMin = "0.0", UIMax = "1.0"))
	float Progress = 0.0f;

	/** Seconds an increase of Progress takes to show. 0 applies every change at once. */
	UPROPERTY(EditAnywhere, BlueprintGetter = GetSmoothingTime, BlueprintSetter = SetSmoothingTime, Category = "LoadingFX", meta = (ClampMin = "0.0", UIMin = "0.0", UIMax = "2.0", ForceUnits = "s"))
	float SmoothingTime = 0.25f;

	/**
	 * The instance Progress is written to, created from the resolved base material and kept here rather than in Material:
	 * dynamic instances are transient, and a widget blueprint saved with one in Material would lose its material.
	 */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> ProgressMaterial;

	TSharedPtr<SLoadingFXProgressBar> MyProgressBar;

	/** The missing-default warning is logged once per widget. */
	bool bWarnedMissingDefault = false;
};
