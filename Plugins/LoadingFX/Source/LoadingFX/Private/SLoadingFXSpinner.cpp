// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "SLoadingFXSpinner.h"

#include "Materials/MaterialInterface.h"
#include "Rendering/DrawElements.h"

void SLoadingFXSpinner::Construct(const FArguments& InArgs)
{
	Brush.DrawAs = ESlateBrushDrawType::Image;
	Brush.Tiling = ESlateBrushTileType::NoTile;
	Brush.ImageSize = InArgs._Size;
	Brush.SetResourceObject(InArgs._Material);
	ColorAndOpacity = InArgs._ColorAndOpacity;
}

void SLoadingFXSpinner::SetMaterial(UMaterialInterface* InMaterial)
{
	if (Brush.GetResourceObject() != InMaterial)
	{
		Brush.SetResourceObject(InMaterial);
		Invalidate(EInvalidateWidgetReason::Paint);
	}
}

void SLoadingFXSpinner::SetSize(FVector2D InSize)
{
	if (Brush.ImageSize != InSize)
	{
		Brush.ImageSize = InSize;
		Invalidate(EInvalidateWidgetReason::Layout);
	}
}

void SLoadingFXSpinner::SetColorAndOpacity(TAttribute<FSlateColor> InColorAndOpacity)
{
	ColorAndOpacity = MoveTemp(InColorAndOpacity);
	Invalidate(EInvalidateWidgetReason::Paint);
}

UMaterialInterface* SLoadingFXSpinner::GetMaterial() const
{
	return Cast<UMaterialInterface>(Brush.GetResourceObject());
}

int32 SLoadingFXSpinner::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	if (Brush.GetResourceObject() == nullptr)
	{
		return LayerId;
	}

	// Same tint chain as SImage: the parent's tint (RenderOpacity, fades), ours, then the brush's. The material
	// multiplies the result in as VertexColor.
	const FLinearColor FinalColorAndOpacity =
		InWidgetStyle.GetColorAndOpacityTint() * ColorAndOpacity.Get().GetColor(InWidgetStyle) * Brush.GetTint(InWidgetStyle);
	const ESlateDrawEffect DrawEffects = ShouldBeEnabled(bParentEnabled) ? ESlateDrawEffect::None : ESlateDrawEffect::DisabledEffect;
	FSlateDrawElement::MakeBox(OutDrawElements, LayerId, AllottedGeometry.ToPaintGeometry(), &Brush, DrawEffects, FinalColorAndOpacity);
	return LayerId;
}

FVector2D SLoadingFXSpinner::ComputeDesiredSize(float) const
{
	return Brush.ImageSize;
}
