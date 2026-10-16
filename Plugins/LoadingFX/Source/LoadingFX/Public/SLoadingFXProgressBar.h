// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "SLoadingFXSpinner.h"
#include "Types/SlateEnums.h"
#include "UObject/WeakObjectPtr.h"
#include "Widgets/SWidget.h"

class UMaterialInstanceDynamic;

/**
 * Draws a determinate bar material (one that reads the Progress parameter, see the material contract) and drives
 * its Progress on a dynamic material instance. Used by the UMG progress bar widget.
 *
 * SetProgress moves the displayed value toward the target over SmoothingTime seconds, so coarse progress (the asset
 * loader reports one step per asset) still reads as motion; a decrease is applied at once, so a bar reset for a new
 * load never runs backwards. The interpolation runs on a Slate active timer registered only while it is in flight.
 *
 * The widget does not keep the material alive: the owner must reference it. Game thread only (it writes a material
 * parameter), so it is not for the loading screen, where MoviePlayer paints on its own thread.
 */
class LOADINGFX_API SLoadingFXProgressBar : public SLoadingFXSpinner
{
public:
	/** Name of the scalar parameter the bar writes: the material contract's determinate input. */
	static const FName ProgressParameterName;

	SLATE_BEGIN_ARGS(SLoadingFXProgressBar)
		: _Material(nullptr)
		, _Size(200.0f, 12.0f)
		, _ColorAndOpacity(FLinearColor::White)
		, _Progress(0.0f)
		, _SmoothingTime(0.25f)
	{
		_Visibility = EVisibility::HitTestInvisible;
	}
		/** Dynamic instance of a bar material; its Progress parameter is written by this widget. Nothing is drawn while null. */
		SLATE_ARGUMENT(UMaterialInstanceDynamic*, Material)
		/** Desired size in Slate units. */
		SLATE_ARGUMENT(FVector2D, Size)
		/** Reaches the material as VertexColor; alpha fades the bar. */
		SLATE_ATTRIBUTE(FSlateColor, ColorAndOpacity)
		/** Initial fill, 0 to 1, applied at once. */
		SLATE_ARGUMENT(float, Progress)
		/** Seconds an increase takes to show. 0 applies every change at once. */
		SLATE_ARGUMENT(float, SmoothingTime)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** Replaces the dynamic instance (and the drawn material); the displayed progress is written to it at once. */
	void SetDynamicMaterial(UMaterialInstanceDynamic* InMaterial);
	UMaterialInstanceDynamic* GetDynamicMaterial() const;

	/** Sets the target fill, 0 to 1. An increase is interpolated over SmoothingTime, a decrease applied at once. */
	void SetProgress(float InProgress);
	/** Sets the fill and shows it at once, dropping any interpolation in flight. */
	void SnapProgress(float InProgress);
	void SetSmoothingTime(float InSmoothingTime);

	/** The target fill. */
	float GetProgress() const { return TargetProgress; }
	/** The fill on screen right now (lags the target while an increase is interpolated). */
	float GetDisplayedProgress() const { return DisplayedProgress; }
	float GetSmoothingTime() const { return SmoothingTime; }
	bool IsInterpolating() const { return ActiveTimerHandle.IsValid(); }

private:
	void WriteDisplayedProgress();
	void StopInterpolation();
	EActiveTimerReturnType TickInterpolation(double InCurrentTime, float InDeltaTime);

	/** Held weakly: the owner keeps it alive, and it may be destroyed before this widget on teardown. */
	TWeakObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;

	float TargetProgress = 0.0f;
	float DisplayedProgress = 0.0f;
	float SmoothingTime = 0.25f;

	/** The interpolation in flight: from InterpolationFrom at InterpolationStartSeconds (platform time) to TargetProgress. */
	float InterpolationFrom = 0.0f;
	double InterpolationStartSeconds = 0.0;
	TSharedPtr<FActiveTimerHandle> ActiveTimerHandle;
};
