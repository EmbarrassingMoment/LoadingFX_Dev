// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

class UMaterialInterface;

/**
 * Verification prototype only (not part of the LoadingFX plugin).
 * Draws each spinner material at several sizes and with a tint, to check the material contract:
 * non-square widgets keep the shape round and centered, and ColorAndOpacity reaches the material via VertexColor.
 */
class SLoadingFXProtoGallery : public SCompoundWidget
{
public:
	struct FRow
	{
		/** Not referenced by the widget: the caller keeps it alive. */
		UMaterialInterface* Material = nullptr;
		FString Caption;
	};

	SLATE_BEGIN_ARGS(SLoadingFXProtoGallery) {}
		SLATE_ARGUMENT(TArray<FRow>, Rows)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TArray<TSharedRef<FSlateBrush>> Brushes;
};
