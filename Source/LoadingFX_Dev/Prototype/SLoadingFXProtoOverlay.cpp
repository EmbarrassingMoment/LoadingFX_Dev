// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "SLoadingFXProtoOverlay.h"

#include "Materials/MaterialInterface.h"
#include "Misc/App.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Images/SThrobber.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace LoadingFXProto
{
	constexpr float TileSize = 128.0f;
}

void SLoadingFXProtoOverlay::Construct(const FArguments& InArgs)
{
	Label = InArgs._Label;
	StartRealSeconds = FPlatformTime::Seconds();
	StartAppSeconds = FApp::GetCurrentTime();

	TSharedRef<SHorizontalBox> TileRow = SNew(SHorizontalBox);

	auto AddTile = [&TileRow](const TSharedRef<SWidget>& Content, const FString& Caption)
	{
		TileRow->AddSlot()
		.AutoWidth()
		.Padding(8.0f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(SBox)
				.WidthOverride(LoadingFXProto::TileSize)
				.HeightOverride(LoadingFXProto::TileSize)
				.HAlign(HAlign_Center)
				.VAlign(VAlign_Center)
				[
					Content
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(0.0f, 4.0f, 0.0f, 0.0f)
			[
				SNew(STextBlock)
				.Text(FText::FromString(Caption))
				.Font(FCoreStyle::GetDefaultFontStyle("Regular", 10))
			]
		];
	};

	for (const FTile& Tile : InArgs._Tiles)
	{
		TSharedRef<FSlateBrush> Brush = MakeShared<FSlateBrush>();
		Brush->SetResourceObject(Tile.Material);
		Brush->ImageSize = FVector2D(LoadingFXProto::TileSize);
		Brush->DrawAs = ESlateBrushDrawType::Image;
		Brushes.Add(Brush);

		AddTile(SNew(SImage).Image(&Brush.Get()), Tile.Caption);
	}

	// Reference animation driven by Slate's own clock, not by the material Time node.
	AddTile(SNew(SCircularThrobber).Radius(LoadingFXProto::TileSize * 0.4f), TEXT("Slate throbber (reference)"));

	ChildSlot
	[
		SNew(SBorder)
		.BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
		.BorderBackgroundColor(FLinearColor(0.0f, 0.0f, 0.0f, 0.6f))
		.Padding(12.0f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				TileRow
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(8.0f, 4.0f)
			[
				SNew(STextBlock)
				.Text(this, &SLoadingFXProtoOverlay::GetStatusText)
				.Font(FCoreStyle::GetDefaultFontStyle("Mono", 12))
			]
		]
	];
}

int32 SLoadingFXProtoOverlay::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	const bool bOnGameThread = IsInGameThread();
	++PaintCount;
	if (!bOnGameThread)
	{
		++OffGameThreadPaintCount;
	}
	bLastPaintOnGameThread = bOnGameThread;

	return SCompoundWidget::OnPaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId, InWidgetStyle, bParentEnabled);
}

FText SLoadingFXProtoOverlay::GetStatusText() const
{
	// "app" is FApp::CurrentTime, which feeds the material Time node when Ignore Pause is off (View.GameTime).
	const double RealElapsed = FPlatformTime::Seconds() - StartRealSeconds;
	const double AppElapsed = FApp::GetCurrentTime() - StartAppSeconds;
	return FText::FromString(FString::Printf(
		TEXT("[%s]  real +%.2fs  app +%.2fs  paints %d (off game thread %d)  last paint: %s"),
		*Label, RealElapsed, AppElapsed, PaintCount.load(), OffGameThreadPaintCount.load(),
		bLastPaintOnGameThread.load() ? TEXT("game thread") : TEXT("other thread")));
}
