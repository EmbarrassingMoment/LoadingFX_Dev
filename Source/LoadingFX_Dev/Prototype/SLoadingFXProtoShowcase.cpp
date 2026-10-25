// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "SLoadingFXProtoShowcase.h"

#include "SLoadingFXSpinner.h"

#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace LoadingFXProtoShowcase
{
	// Material contract footprint (see CLAUDE.md): with default parameters a ring layout touches the reference
	// circle and a grid layout touches the reference square, measured at the largest moment of any pulse.
	constexpr float ReferenceCircleRadius = 0.8f;      // in P units: 1.0 = half the shorter side
	constexpr float ReferenceSquareHalfWidth = 0.72f;  // keyline: 0.9 * the circle radius
	const FLinearColor CircleColor(0.25f, 0.5f, 1.0f, 0.9f);
	const FLinearColor SquareColor(1.0f, 0.55f, 0.2f, 0.9f);

	/** Paints the reference circle and square over a tile. */
	class SReferenceShapes : public SLeafWidget
	{
	public:
		SLATE_BEGIN_ARGS(SReferenceShapes)
		{
			_Visibility = EVisibility::HitTestInvisible;
		}
		SLATE_END_ARGS()

		void Construct(const FArguments& InArgs) {}

		virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
			FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override
		{
			const FVector2f Size = FVector2f(AllottedGeometry.GetLocalSize());
			const FVector2f Center = Size * 0.5f;
			const float Half = FMath::Min(Size.X, Size.Y) * 0.5f;
			const FPaintGeometry PaintGeometry = AllottedGeometry.ToPaintGeometry();

			const float S = Half * ReferenceSquareHalfWidth;
			TArray<FVector2f> Square;
			Square.Add(Center + FVector2f(-S, -S));
			Square.Add(Center + FVector2f(S, -S));
			Square.Add(Center + FVector2f(S, S));
			Square.Add(Center + FVector2f(-S, S));
			Square.Add(Center + FVector2f(-S, -S));
			FSlateDrawElement::MakeLines(OutDrawElements, LayerId, PaintGeometry, MoveTemp(Square), ESlateDrawEffect::None, SquareColor, true, 1.0f);

			const float R = Half * ReferenceCircleRadius;
			constexpr int32 Segments = 96;
			TArray<FVector2f> Circle;
			Circle.Reserve(Segments + 1);
			for (int32 Index = 0; Index <= Segments; ++Index)
			{
				const float Angle = (2.0f * PI) * Index / Segments;
				Circle.Add(Center + FVector2f(FMath::Cos(Angle), FMath::Sin(Angle)) * R);
			}
			FSlateDrawElement::MakeLines(OutDrawElements, LayerId, PaintGeometry, MoveTemp(Circle), ESlateDrawEffect::None, CircleColor, true, 1.0f);

			return LayerId + 1;
		}

		virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override
		{
			return FVector2D::ZeroVector;
		}
	};
}

void SLoadingFXProtoShowcase::Construct(const FArguments& InArgs)
{
	using namespace LoadingFXProtoShowcase;

	const FSlateBrush* WhiteBrush = FCoreStyle::Get().GetBrush("WhiteBrush");
	const FSlateFontInfo CaptionFont = FCoreStyle::GetDefaultFontStyle("Regular", 12);
	const FLinearColor CaptionColor(0.7f, 0.7f, 0.7f, 1.0f);
	// Tiles wrap to the next line when the window is too narrow for one row.
	TSharedRef<SWrapBox> Tiles = SNew(SWrapBox)
		.UseAllottedSize(true)
		.HAlign(HAlign_Center);

	for (const FTile& Tile : InArgs._Tiles)
	{
		const FVector2D TileSize(InArgs._TileSize, InArgs._TileSize / FMath::Max(Tile.AspectRatio, 0.01f));
		TSharedRef<SOverlay> TileContent = SNew(SOverlay)
			+ SOverlay::Slot()
			[
				SNew(SLoadingFXSpinner)
				.Material(Tile.Material)
				.Size(TileSize)
			];
		if (InArgs._ShowReference)
		{
			TileContent->AddSlot()
			[
				SNew(SReferenceShapes)
			];
		}

		Tiles->AddSlot()
		.Padding(16.0f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				// A faint backing shows the tile bounds, so the margin each material leaves is visible.
				SNew(SBorder)
				.BorderImage(WhiteBrush)
				.BorderBackgroundColor(FLinearColor(0.02f, 0.02f, 0.025f, 1.0f))
				.Padding(0.0f)
				[
					TileContent
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(0.0f, 8.0f, 0.0f, 0.0f)
			[
				SNew(STextBlock)
				.Text(FText::FromString(Tile.Caption))
				.Font(CaptionFont)
				.ColorAndOpacity(CaptionColor)
			]
		];
	}

	TSharedRef<SVerticalBox> Content = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			Tiles
		];
	if (InArgs._ShowReference)
	{
		Content->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(0.0f, 16.0f, 0.0f, 0.0f)
		[
			SNew(STextBlock)
			.Text(FText::FromString(FString::Printf(
				TEXT("Reference: circle r = %.2f (ring layouts touch it), square half-width = %.2f (grid layouts touch it); 1.0 = the tile edge"),
				ReferenceCircleRadius, ReferenceSquareHalfWidth)))
			.Font(CaptionFont)
			.ColorAndOpacity(CaptionColor)
		];
	}

	ChildSlot
	[
		// Black like SDefaultMovieBorder: the materials are reviewed on the background they get as a loading screen.
		SNew(SBorder)
		.BorderImage(WhiteBrush)
		.BorderBackgroundColor(FLinearColor::Black)
		.HAlign(HAlign_Fill)
		.VAlign(VAlign_Center)
		.Padding(24.0f)
		[
			Content
		]
	];
}
