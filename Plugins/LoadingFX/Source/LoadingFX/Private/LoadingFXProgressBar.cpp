// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXProgressBar.h"

#include "LoadingFX.h"
#include "SLoadingFXProgressBar.h"

#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/SoftObjectPath.h"

ULoadingFXProgressBar::ULoadingFXProgressBar(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	Size = FVector2D(200.0, 12.0);
}

const TCHAR* ULoadingFXProgressBar::GetDefaultMaterialPath()
{
	return TEXT("/LoadingFX/Materials/M_LoadingBarFill.M_LoadingBarFill");
}

float ULoadingFXProgressBar::GetProgress() const
{
	return Progress;
}

void ULoadingFXProgressBar::SetProgress(float InProgress)
{
	Progress = FMath::Clamp(InProgress, 0.0f, 1.0f);
	if (MyProgressBar.IsValid())
	{
		MyProgressBar->SetProgress(Progress);
	}
}

float ULoadingFXProgressBar::GetDisplayedProgress() const
{
	return MyProgressBar.IsValid() ? MyProgressBar->GetDisplayedProgress() : Progress;
}

float ULoadingFXProgressBar::GetSmoothingTime() const
{
	return SmoothingTime;
}

void ULoadingFXProgressBar::SetSmoothingTime(float InSmoothingTime)
{
	SmoothingTime = FMath::Max(InSmoothingTime, 0.0f);
	if (MyProgressBar.IsValid())
	{
		MyProgressBar->SetSmoothingTime(SmoothingTime);
	}
}

UMaterialInstanceDynamic* ULoadingFXProgressBar::GetDynamicMaterial()
{
	return Cast<UMaterialInstanceDynamic>(ResolveMaterial());
}

void ULoadingFXProgressBar::SynchronizeProperties()
{
	// The base applies the material (through our ResolveMaterial), size and tint.
	Super::SynchronizeProperties();

	if (MyProgressBar.IsValid())
	{
		MyProgressBar->SetSmoothingTime(SmoothingTime);
		// In the designer a property edit shows at once; at runtime the first value is also set without animation.
		MyProgressBar->SnapProgress(Progress);
	}
}

void ULoadingFXProgressBar::ReleaseSlateResources(bool bReleaseChildren)
{
	Super::ReleaseSlateResources(bReleaseChildren);
	MyProgressBar.Reset();
}

TSharedRef<SWidget> ULoadingFXProgressBar::RebuildWidget()
{
	MyProgressBar = SNew(SLoadingFXProgressBar)
		.Material(Cast<UMaterialInstanceDynamic>(ResolveMaterial()))
		.Size(Size)
		.ColorAndOpacity(ColorAndOpacity)
		.Progress(Progress)
		.SmoothingTime(SmoothingTime);
	// The base class drives size, tint and material through this pointer.
	MySpinner = MyProgressBar;
	return MyProgressBar.ToSharedRef();
}

UMaterialInterface* ULoadingFXProgressBar::ResolveMaterial()
{
	UMaterialInterface* Base = Material;
	if (!Base)
	{
		Base = Cast<UMaterialInterface>(FSoftObjectPath(GetDefaultMaterialPath()).TryLoad());
		if (!Base && !bWarnedMissingDefault)
		{
			bWarnedMissingDefault = true;
			UE_LOG(LogLoadingFX, Warning, TEXT("%s: the default progress bar material %s could not be loaded (missing or not cooked); set Material."), *GetPathName(), GetDefaultMaterialPath());
		}
	}

	// A dynamic instance handed in (made by the caller, or by GetDynamicMaterial on another widget) is written directly.
	UMaterialInstanceDynamic* Resolved = Cast<UMaterialInstanceDynamic>(Base);
	if (!Resolved && Base)
	{
		if (ProgressMaterial && ProgressMaterial->Parent == Base)
		{
			Resolved = ProgressMaterial;
		}
		else
		{
			// Transient (UMaterialInstanceDynamic::Create sets RF_Transient), outered to this widget: it is never saved with a
			// widget blueprint, and GC keeps it as long as ProgressMaterial references it.
			ProgressMaterial = UMaterialInstanceDynamic::Create(Base, this);
			Resolved = ProgressMaterial;
		}
	}

	if (Resolved != DrawnMaterial)
	{
		DrawnMaterial = Resolved;
		CheckMaterialDomain(Resolved);
	}
	return Resolved;
}

void ULoadingFXProgressBar::ApplyMaterial()
{
	UMaterialInstanceDynamic* Resolved = Cast<UMaterialInstanceDynamic>(ResolveMaterial());
	if (MyProgressBar.IsValid() && MyProgressBar->GetDynamicMaterial() != Resolved)
	{
		MyProgressBar->SetDynamicMaterial(Resolved);
	}
}
