// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "SLoadingFXProgressBar.h"

#include "HAL/PlatformTime.h"
#include "Materials/MaterialInstanceDynamic.h"

const FName SLoadingFXProgressBar::ProgressParameterName(TEXT("Progress"));

void SLoadingFXProgressBar::Construct(const FArguments& InArgs)
{
	// SNew applies the common arguments (Visibility) from InArgs after this returns; the base only needs its own.
	SLoadingFXSpinner::Construct(SLoadingFXSpinner::FArguments()
		.Material(InArgs._Material)
		.Size(InArgs._Size)
		.ColorAndOpacity(InArgs._ColorAndOpacity));

	DynamicMaterial = InArgs._Material;
	SmoothingTime = FMath::Max(InArgs._SmoothingTime, 0.0f);
	SnapProgress(InArgs._Progress);
}

void SLoadingFXProgressBar::SetDynamicMaterial(UMaterialInstanceDynamic* InMaterial)
{
	DynamicMaterial = InMaterial;
	SetMaterial(InMaterial);
	WriteDisplayedProgress();
}

UMaterialInstanceDynamic* SLoadingFXProgressBar::GetDynamicMaterial() const
{
	return DynamicMaterial.Get();
}

void SLoadingFXProgressBar::SetProgress(float InProgress)
{
	const float NewTarget = FMath::Clamp(InProgress, 0.0f, 1.0f);
	if (NewTarget <= DisplayedProgress || SmoothingTime <= 0.0f)
	{
		// A decrease (a bar reset for the next load) shows at once: a progress bar never runs backwards.
		SnapProgress(NewTarget);
		return;
	}
	if (NewTarget == TargetProgress && ActiveTimerHandle.IsValid())
	{
		return;
	}

	// Restart from what is on screen now, so a new target mid-flight does not jump.
	TargetProgress = NewTarget;
	InterpolationFrom = DisplayedProgress;
	InterpolationStartSeconds = FPlatformTime::Seconds();
	if (!ActiveTimerHandle.IsValid())
	{
		ActiveTimerHandle = RegisterActiveTimer(0.0f, FWidgetActiveTimerDelegate::CreateSP(this, &SLoadingFXProgressBar::TickInterpolation));
	}
}

void SLoadingFXProgressBar::SnapProgress(float InProgress)
{
	StopInterpolation();
	TargetProgress = FMath::Clamp(InProgress, 0.0f, 1.0f);
	DisplayedProgress = TargetProgress;
	WriteDisplayedProgress();
}

void SLoadingFXProgressBar::SetSmoothingTime(float InSmoothingTime)
{
	SmoothingTime = FMath::Max(InSmoothingTime, 0.0f);
	if (SmoothingTime <= 0.0f && ActiveTimerHandle.IsValid())
	{
		SnapProgress(TargetProgress);
	}
}

void SLoadingFXProgressBar::WriteDisplayedProgress()
{
	if (UMaterialInstanceDynamic* Material = DynamicMaterial.Get())
	{
		Material->SetScalarParameterValue(ProgressParameterName, DisplayedProgress);
	}
}

void SLoadingFXProgressBar::StopInterpolation()
{
	if (ActiveTimerHandle.IsValid())
	{
		UnRegisterActiveTimer(ActiveTimerHandle.ToSharedRef());
		ActiveTimerHandle.Reset();
	}
}

EActiveTimerReturnType SLoadingFXProgressBar::TickInterpolation(double /*InCurrentTime*/, float /*InDeltaTime*/)
{
	const float Alpha = SmoothingTime > 0.0f
		? FMath::Clamp(static_cast<float>((FPlatformTime::Seconds() - InterpolationStartSeconds) / SmoothingTime), 0.0f, 1.0f)
		: 1.0f;
	DisplayedProgress = FMath::Lerp(InterpolationFrom, TargetProgress, Alpha);
	WriteDisplayedProgress();

	if (Alpha >= 1.0f)
	{
		// Slate removes a timer that returns Stop; forget the handle without unregistering it again.
		ActiveTimerHandle.Reset();
		return EActiveTimerReturnType::Stop;
	}
	return EActiveTimerReturnType::Continue;
}
