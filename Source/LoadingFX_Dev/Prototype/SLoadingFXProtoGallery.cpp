// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "SLoadingFXProtoGallery.h"

#include "Materials/MaterialInterface.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace LoadingFXProtoGallery
{
	struct FSizeVariant
	{
		const TCHAR* Caption;
		float Width;
		float Height;
		FLinearColor Tint;
	};

	// Tint goes through SImage::ColorAndOpacity, which reaches the material as VertexColor.
	static const FSizeVariant Variants[] =
	{
		{ TEXT("Square 96"), 96.0f, 96.0f, FLinearColor::White },
		{ TEXT("Wide 216x96"), 216.0f, 96.0f, FLinearColor::White },
		{ TEXT("Tall 64x128"), 64.0f, 128.0f, FLinearColor::White },
		{ TEXT("Tint orange, 50%"), 96.0f, 96.0f, FLinearColor(1.0f, 0.45f, 0.1f, 0.5f) },
		{ TEXT("Small 32"), 32.0f, 32.0f, FLinearColor::White },
	};

	constexpr float CaptionWidth = 150.0f;
	constexpr float CellPadding = 8.0f;
}

void SLoadingFXProtoGallery::Construct(const FArguments& InArgs)
{
	using namespace LoadingFXProtoGallery;

	const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Regular", 10);
	const FSlateBrush* WhiteBrush = FCoreStyle::Get().GetBrush("WhiteBrush");

	TSharedRef<SVerticalBox> Table = SNew(SVerticalBox);

	TSharedRef<SHorizontalBox> Header = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			SNew(SBox).WidthOverride(CaptionWidth)
		];
	for (const FSizeVariant& Variant : Variants)
	{
		Header->AddSlot()
		.AutoWidth()
		.Padding(CellPadding, 0.0f)
		[
			SNew(SBox)
			.WidthOverride(FMath::Max(Variant.Width, 96.0f))
			[
				SNew(STextBlock).Text(FText::FromString(Variant.Caption)).Font(Font)
			]
		];
	}
	Table->AddSlot().AutoHeight().Padding(0.0f, 0.0f, 0.0f, 4.0f)[Header];

	for (const FRow& Row : InArgs._Rows)
	{
		TSharedRef<SHorizontalBox> Cells = SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(CaptionWidth)
				[
					SNew(STextBlock).Text(FText::FromString(Row.Caption)).Font(Font)
				]
			];

		for (const FSizeVariant& Variant : Variants)
		{
			TSharedRef<FSlateBrush> Brush = MakeShared<FSlateBrush>();
			Brush->SetResourceObject(Row.Material);
			Brush->ImageSize = FVector2D(Variant.Width, Variant.Height);
			Brush->DrawAs = ESlateBrushDrawType::Image;
			Brushes.Add(Brush);

			// The dark backing shows the widget bounds, so the fit inside non-square sizes is visible.
			Cells->AddSlot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(CellPadding)
			[
				SNew(SBox)
				.WidthOverride(FMath::Max(Variant.Width, 96.0f))
				.HAlign(HAlign_Left)
				[
					SNew(SBorder)
					.BorderImage(WhiteBrush)
					.BorderBackgroundColor(FLinearColor(0.08f, 0.08f, 0.1f, 1.0f))
					.Padding(0.0f)
					[
						SNew(SBox)
						.WidthOverride(Variant.Width)
						.HeightOverride(Variant.Height)
						[
							SNew(SImage)
							.Image(&Brush.Get())
							.ColorAndOpacity(Variant.Tint)
						]
					]
				]
			];
		}

		Table->AddSlot().AutoHeight()[Cells];
	}

	ChildSlot
	[
		SNew(SBorder)
		.BorderImage(WhiteBrush)
		.BorderBackgroundColor(FLinearColor(0.25f, 0.27f, 0.3f, 1.0f))
		.Padding(12.0f)
		[
			Table
		]
	];
}
