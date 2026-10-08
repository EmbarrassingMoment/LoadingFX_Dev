// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

class UMaterialInterface;

/**
 * Verification prototype only (not part of the LoadingFX plugin).
 * Fills the viewport with black (like the MoviePlayer loading screen) and draws every bundled spinner material
 * side by side at one large size, each through the plugin's own SLoadingFXSpinner, to review how they look.
 * With ShowReference the material contract's reference circle and square are drawn over each tile, to check
 * that the default footprints match.
 */
class SLoadingFXProtoShowcase : public SCompoundWidget
{
public:
	struct FTile
	{
		/** Not referenced by the widget: the caller keeps it alive. */
		UMaterialInterface* Material = nullptr;
		FString Caption;
	};

	SLATE_BEGIN_ARGS(SLoadingFXProtoShowcase)
		: _TileSize(256.0f)
		, _ShowReference(false)
	{}
		SLATE_ARGUMENT(TArray<FTile>, Tiles)
		/** Edge length of each square tile in Slate units. */
		SLATE_ARGUMENT(float, TileSize)
		/** Overlay the reference circle (ring layouts) and square (grid layouts) of the material contract. */
		SLATE_ARGUMENT(bool, ShowReference)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
};
