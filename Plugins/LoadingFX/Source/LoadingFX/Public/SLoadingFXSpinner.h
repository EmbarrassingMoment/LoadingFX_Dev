// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "Styling/SlateColor.h"
#include "Widgets/SLeafWidget.h"

class UMaterialInterface;

/**
 * Draws a spinner material (a UI-domain material that follows the LoadingFX material contract) over the
 * widget's whole area. Used by the loading icon, and by the UMG spinner widget.
 *
 * The widget does not keep the material alive: the owner must reference it (for example from a UPROPERTY).
 * OnPaint also runs on the Slate loading thread while MoviePlayer shows the widget, so call the setters only
 * while the game thread owns it.
 */
class LOADINGFX_API SLoadingFXSpinner : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SLoadingFXSpinner)
		: _Material(nullptr)
		, _Size(64.0f, 64.0f)
		, _ColorAndOpacity(FLinearColor::White)
	{
		// Purely visual: never take input away from what is underneath.
		_Visibility = EVisibility::HitTestInvisible;
	}
		/** UI-domain material to draw. Nothing is drawn while it is null. */
		SLATE_ARGUMENT(UMaterialInterface*, Material)
		/** Desired size in Slate units. */
		SLATE_ARGUMENT(FVector2D, Size)
		/** Reaches the material as VertexColor (see the material contract); alpha fades the spinner. */
		SLATE_ATTRIBUTE(FSlateColor, ColorAndOpacity)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	void SetMaterial(UMaterialInterface* InMaterial);
	void SetSize(FVector2D InSize);
	void SetColorAndOpacity(TAttribute<FSlateColor> InColorAndOpacity);

	UMaterialInterface* GetMaterial() const;

	//~ Begin SWidget Interface
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;
	//~ End SWidget Interface

private:
	FSlateBrush Brush;
	TAttribute<FSlateColor> ColorAndOpacity;
};
