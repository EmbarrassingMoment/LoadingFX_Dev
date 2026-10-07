// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

#include <atomic>

class UMaterialInterface;

/**
 * Verification prototype only (not part of the LoadingFX plugin).
 * Draws the spinner materials next to a Slate-native throbber with a live status line, to check whether
 * UI materials render and animate while MoviePlayer paints on the Slate loading thread.
 */
class SLoadingFXProtoOverlay : public SCompoundWidget
{
public:
	struct FTile
	{
		/** Not referenced by the widget: the caller keeps it alive. */
		UMaterialInterface* Material = nullptr;
		FString Caption;
	};

	SLATE_BEGIN_ARGS(SLoadingFXProtoOverlay) {}
		/** Shown in the status line to tell the test cases apart. */
		SLATE_ARGUMENT(FString, Label)
		SLATE_ARGUMENT(TArray<FTile>, Tiles)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;

	const FString& GetLabel() const { return Label; }
	int32 GetPaintCount() const { return PaintCount.load(); }
	int32 GetOffGameThreadPaintCount() const { return OffGameThreadPaintCount.load(); }

private:
	FText GetStatusText() const;

	FString Label;
	double StartRealSeconds = 0.0;
	double StartAppSeconds = 0.0;
	TArray<TSharedRef<FSlateBrush>> Brushes;

	// Painted from the game thread normally, and from the Slate loading thread while MoviePlayer is active.
	mutable std::atomic<int32> PaintCount{0};
	mutable std::atomic<int32> OffGameThreadPaintCount{0};
	mutable std::atomic<bool> bLastPaintOnGameThread{true};
};
