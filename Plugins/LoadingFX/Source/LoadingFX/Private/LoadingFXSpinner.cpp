// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXSpinner.h"

#include "LoadingFX.h"
#include "LoadingFXSettings.h"
#include "SLoadingFXSpinner.h"

#include "MaterialDomain.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

#define LOCTEXT_NAMESPACE "LoadingFX"

ULoadingFXSpinner::ULoadingFXSpinner(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

UMaterialInterface* ULoadingFXSpinner::GetMaterial() const
{
	return Material;
}

void ULoadingFXSpinner::SetMaterial(UMaterialInterface* InMaterial)
{
	Material = InMaterial;
	ApplyMaterial();
}

FLinearColor ULoadingFXSpinner::GetColorAndOpacity() const
{
	return ColorAndOpacity;
}

void ULoadingFXSpinner::SetColorAndOpacity(FLinearColor InColorAndOpacity)
{
	ColorAndOpacity = InColorAndOpacity;
	if (MySpinner.IsValid())
	{
		MySpinner->SetColorAndOpacity(ColorAndOpacity);
	}
}

void ULoadingFXSpinner::SetOpacity(float InOpacity)
{
	ColorAndOpacity.A = InOpacity;
	if (MySpinner.IsValid())
	{
		MySpinner->SetColorAndOpacity(ColorAndOpacity);
	}
}

FVector2D ULoadingFXSpinner::GetSize() const
{
	return Size;
}

void ULoadingFXSpinner::SetSize(FVector2D InSize)
{
	Size = InSize;
	if (MySpinner.IsValid())
	{
		MySpinner->SetSize(Size);
	}
}

UMaterialInstanceDynamic* ULoadingFXSpinner::GetDynamicMaterial()
{
	if (UMaterialInstanceDynamic* Existing = Cast<UMaterialInstanceDynamic>(Material.Get()))
	{
		return Existing;
	}

	UMaterialInterface* BaseMaterial = ResolveMaterial();
	if (!BaseMaterial)
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("%s: no material to make dynamic (none set, and no project loading icon material)."), *GetPathName());
		return nullptr;
	}

	// As UImage does: the dynamic instance replaces the material on this widget.
	UMaterialInstanceDynamic* DynamicMaterial = UMaterialInstanceDynamic::Create(BaseMaterial, this);
	Material = DynamicMaterial;
	ApplyMaterial();
	return DynamicMaterial;
}

void ULoadingFXSpinner::SynchronizeProperties()
{
	Super::SynchronizeProperties();

	ApplyMaterial();
	if (MySpinner.IsValid())
	{
		MySpinner->SetSize(Size);
		MySpinner->SetColorAndOpacity(ColorAndOpacity);
	}
}

void ULoadingFXSpinner::ReleaseSlateResources(bool bReleaseChildren)
{
	Super::ReleaseSlateResources(bReleaseChildren);
	MySpinner.Reset();
}

#if WITH_EDITOR
const FText ULoadingFXSpinner::GetPaletteCategory()
{
	return LOCTEXT("PaletteCategory", "LoadingFX");
}
#endif

TSharedRef<SWidget> ULoadingFXSpinner::RebuildWidget()
{
	MySpinner = SNew(SLoadingFXSpinner)
		.Material(ResolveMaterial())
		.Size(Size)
		.ColorAndOpacity(ColorAndOpacity);
	return MySpinner.ToSharedRef();
}

UMaterialInterface* ULoadingFXSpinner::ResolveMaterial()
{
	UMaterialInterface* Resolved = Material;
	if (!Resolved)
	{
		const TSoftObjectPtr<UMaterialInterface>& ProjectDefault = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial;
		Resolved = ProjectDefault.IsNull() ? nullptr : ProjectDefault.LoadSynchronous();
	}

	if (Resolved != DrawnMaterial)
	{
		DrawnMaterial = Resolved;

		const UMaterial* BaseMaterial = Resolved ? Resolved->GetMaterial() : nullptr;
		if (BaseMaterial && BaseMaterial->MaterialDomain != MD_UI)
		{
			UE_LOG(LogLoadingFX, Warning, TEXT("%s: %s is not a User Interface domain material, Slate cannot draw it."), *GetPathName(), *Resolved->GetPathName());
		}
	}
	return Resolved;
}

void ULoadingFXSpinner::ApplyMaterial()
{
	UMaterialInterface* Resolved = ResolveMaterial();
	if (MySpinner.IsValid())
	{
		MySpinner->SetMaterial(Resolved);
	}
}

#undef LOCTEXT_NAMESPACE
