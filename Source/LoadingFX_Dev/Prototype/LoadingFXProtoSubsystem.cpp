// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXProtoSubsystem.h"

#include "SLoadingFXProtoGallery.h"
#include "SLoadingFXProtoOverlay.h"
#include "SLoadingFXProtoShowcase.h"

#include "LoadingFXIconSubsystem.h"
#include "LoadingFXSpinner.h"

#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/Paths.h"
#include "MoviePlayer.h"
#include "UnrealClient.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

DEFINE_LOG_CATEGORY_STATIC(LogLoadingFXProto, Log, All);

namespace LoadingFXProto
{
	struct FMaterialEntry
	{
		const TCHAR* Path;
		const TCHAR* Caption;
	};

	// Spinner (GameTime) is the same material with the Time node's Ignore Pause off, for an A/B comparison.
	static const FMaterialEntry MaterialEntries[] =
	{
		{ TEXT("/LoadingFX/Materials/M_LoadingSpinner.M_LoadingSpinner"), TEXT("Spinner (RealTime)") },
		{ TEXT("/Game/Prototype/M_LoadingSpinner_GameTime.M_LoadingSpinner_GameTime"), TEXT("Spinner (GameTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingIcon.M_LoadingIcon"), TEXT("Icon (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingBoxes.M_LoadingBoxes"), TEXT("Boxes (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingBars.M_LoadingBars"), TEXT("Bars (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingArc.M_LoadingArc"), TEXT("Arc (RealTime)") },
	};

	static const TCHAR* const TravelTestMap = TEXT("/Engine/Maps/Entry");
	constexpr int32 ViewportOverlayZOrder = 10000;

	ULoadingFXProtoSubsystem* FindSubsystem(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? GameInstance->GetSubsystem<ULoadingFXProtoSubsystem>() : nullptr;
	}

	float ParseFloatArg(const TArray<FString>& Args, int32 Index, float Default)
	{
		return Args.IsValidIndex(Index) ? FCString::Atof(*Args[Index]) : Default;
	}

	static FAutoConsoleCommandWithWorldAndArgs OverlayCommand(
		TEXT("LFXProto.Overlay"),
		TEXT("Verification prototype: toggle the spinner overlay in the game viewport."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->ToggleViewportOverlay();
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs BlockCommand(
		TEXT("LFXProto.Block"),
		TEXT("Verification prototype: block the game thread under MoviePlayer. Args: [Seconds=5] [GC=0] [StartDelay=0]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World);
			if (!Subsystem)
			{
				return;
			}

			const float Seconds = ParseFloatArg(Args, 0, 5.0f);
			const bool bCollectGarbage = ParseFloatArg(Args, 1, 0.0f) != 0.0f;
			const float StartDelay = ParseFloatArg(Args, 2, 0.0f);
			if (StartDelay <= 0.0f)
			{
				Subsystem->RunBlockTest(Seconds, bCollectGarbage);
				return;
			}

			// A start delay leaves time to set up an external capture before the game thread blocks.
			FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateWeakLambda(Subsystem,
				[Subsystem, Seconds, bCollectGarbage](float)
				{
					Subsystem->RunBlockTest(Seconds, bCollectGarbage);
					return false;
				}), StartDelay);
		}));

	static FAutoConsoleCommandWithWorldAndArgs TravelCommand(
		TEXT("LFXProto.Travel"),
		TEXT("Verification prototype: OpenLevel with the overlay as loading screen. Args: [Map=/Engine/Maps/Entry] [ExtraSeconds=3]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunTravelTest(Args.IsValidIndex(0) ? Args[0] : FString(TravelTestMap), ParseFloatArg(Args, 1, 3.0f));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs RunAllCommand(
		TEXT("LFXProto.RunAll"),
		TEXT("Verification prototype: run every case in order. Pass 'quit' to exit when done."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunAll(Args.Contains(TEXT("quit")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs GalleryCommand(
		TEXT("LFXProto.Gallery"),
		TEXT("Verification prototype: toggle the material contract gallery. Pass 'shot' to save screenshots, 'quit' to exit afterwards."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunGallery(Args.Contains(TEXT("shot")), Args.Contains(TEXT("quit")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs IconTravelCommand(
		TEXT("LFXProto.IconTravel"),
		TEXT("Verification prototype: exercise ULoadingFXIconSubsystem (acquire, owner auto-release, OpenLevel under the icon, release). Args: [Map=/Engine/Maps/Entry] [ExtraSeconds=4] [quit]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunIconTravelTest(Args.IsValidIndex(0) ? Args[0] : FString(TravelTestMap), ParseFloatArg(Args, 1, 4.0f), Args.Contains(TEXT("quit")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs UmgSpinnerCommand(
		TEXT("LFXProto.UmgSpinner"),
		TEXT("Verification prototype: toggle a row of ULoadingFXSpinner UMG widgets (project default, explicit material + tint, dynamic parameters, opacity, non-square). 'shot' saves a screenshot, 'quit' exits afterwards."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunUmgSpinnerTest(Args.Contains(TEXT("shot")), Args.Contains(TEXT("quit")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs ShowcaseCommand(
		TEXT("LFXProto.Showcase"),
		TEXT("Verification prototype: toggle a full-screen showcase of every bundled spinner material on black. Args: [Size=256] [ref] [shot] [quit]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				// The size is the only numeric argument; 'shot' and 'quit' can come in any order.
				float TileSize = 256.0f;
				for (const FString& Arg : Args)
				{
					if (Arg.IsNumeric())
					{
						TileSize = FCString::Atof(*Arg);
					}
				}
				Subsystem->RunShowcase(TileSize, Args.Contains(TEXT("ref")), Args.Contains(TEXT("shot")), Args.Contains(TEXT("quit")));
			}
		}));
}

bool ULoadingFXProtoSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	return !IsRunningDedicatedServer() && Super::ShouldCreateSubsystem(Outer);
}

void ULoadingFXProtoSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	for (const LoadingFXProto::FMaterialEntry& Entry : LoadingFXProto::MaterialEntries)
	{
		if (UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, Entry.Path))
		{
			Materials.Add(Material);
			MaterialCaptions.Add(Entry.Caption);
		}
		else
		{
			UE_LOG(LogLoadingFXProto, Warning, TEXT("Material not found: %s"), Entry.Path);
		}
	}

	IGameMoviePlayer* MoviePlayer = GetMoviePlayer();
	if (MoviePlayer)
	{
		PrepareLoadingScreenHandle = MoviePlayer->OnPrepareLoadingScreen().AddUObject(this, &ThisClass::HandlePrepareLoadingScreen);
		MoviePlaybackStartedHandle = MoviePlayer->OnMoviePlaybackStarted().AddUObject(this, &ThisClass::HandleMoviePlaybackStarted);
	}
	PostLoadMapHandle = FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(this, &ThisClass::HandlePostLoadMap);

	UE_LOG(LogLoadingFXProto, Display, TEXT("Initialized: %d materials, MoviePlayer enabled=%d initialized=%d"),
		Materials.Num(), IsMoviePlayerEnabled() ? 1 : 0, (MoviePlayer && MoviePlayer->IsInitialized()) ? 1 : 0);
}

void ULoadingFXProtoSubsystem::Deinitialize()
{
	if (SequenceTickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(SequenceTickerHandle);
		SequenceTickerHandle.Reset();
	}

	if (IGameMoviePlayer* MoviePlayer = GetMoviePlayer())
	{
		MoviePlayer->OnPrepareLoadingScreen().Remove(PrepareLoadingScreenHandle);
		MoviePlayer->OnMoviePlaybackStarted().Remove(MoviePlaybackStartedHandle);
	}
	FCoreUObjectDelegates::PostLoadMapWithWorld.Remove(PostLoadMapHandle);

	HideViewportOverlay();
	HideGallery();
	HideUmgSpinners();
	HideShowcase();
	LoadingScreenOverlay.Reset();

	Super::Deinitialize();
}

void ULoadingFXProtoSubsystem::ToggleViewportOverlay()
{
	if (ViewportOverlay.IsValid())
	{
		HideViewportOverlay();
	}
	else
	{
		ShowViewportOverlay();
	}
}

void ULoadingFXProtoSubsystem::RunBlockTest(float Seconds, bool bCollectGarbage)
{
	const FString Label = FString::Printf(TEXT("Block %.1fs%s"), Seconds, bCollectGarbage ? TEXT(" + GC") : TEXT(""));
	LoadingScreenOverlay = MakeOverlay(Label);

	IGameMoviePlayer* MoviePlayer = GetMoviePlayer();
	bool bStarted = false;
	if (MoviePlayer && IsMoviePlayerEnabled())
	{
		FLoadingScreenAttributes Attributes;
		Attributes.WidgetLoadingScreen = LoadingScreenOverlay;
		Attributes.bAutoCompleteWhenLoadingCompletes = true;
		MoviePlayer->SetupLoadingScreen(Attributes);
		bStarted = MoviePlayer->PlayMovie();
	}
	UE_LOG(LogLoadingFXProto, Display, TEXT("[%s] start: PlayMovie=%s"), *Label, bStarted ? TEXT("true") : TEXT("false (MoviePlayer unavailable)"));

	const double StartSeconds = FPlatformTime::Seconds();
	SimulateBlockingWork(Seconds, bCollectGarbage);

	if (bStarted)
	{
		MoviePlayer->WaitForMovieToFinish();
	}
	LogOverlayStats(*Label, FPlatformTime::Seconds() - StartSeconds);
}

void ULoadingFXProtoSubsystem::RunTravelTest(const FString& MapName, float ExtraLoadSeconds)
{
	LoadingScreenOverlay.Reset();
	bTravelPending = true;
	TravelExtraLoadSeconds = ExtraLoadSeconds;
	TravelStartSeconds = FPlatformTime::Seconds();
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Travel] OpenLevel %s (+%.1fs simulated load)"), *MapName, ExtraLoadSeconds);
	OpenLevel(MapName);
}

void ULoadingFXProtoSubsystem::RunAll(bool bQuitWhenDone)
{
	const UWorld* World = GetWorld();
	const FString StartMap = World ? World->GetPackage()->GetName() : FString();

	SequenceSteps.Reset();
	SequenceSteps.Add({ 0.5f, [this]() { UE_LOG(LogLoadingFXProto, Display, TEXT("[RunAll] 1/6 viewport overlay (baseline)")); ShowViewportOverlay(); } });
	SequenceSteps.Add({ 3.0f, [this]() { UE_LOG(LogLoadingFXProto, Display, TEXT("[RunAll] 2/6 block")); RunBlockTest(4.0f, false); } });
	SequenceSteps.Add({ 2.0f, [this]() { UE_LOG(LogLoadingFXProto, Display, TEXT("[RunAll] 3/6 block + GC")); RunBlockTest(4.0f, true); } });
	SequenceSteps.Add({ 2.0f, [this]() { UE_LOG(LogLoadingFXProto, Display, TEXT("[RunAll] 4/6 travel test")); RunTravelTest(LoadingFXProto::TravelTestMap, 3.0f); } });
	SequenceSteps.Add({ 6.0f, [this, StartMap]()
	{
		// v1 behavior: the icon is visible when LoadMap starts, so the loading screen takes over automatically.
		UE_LOG(LogLoadingFXProto, Display, TEXT("[RunAll] 5/6 plain OpenLevel with the overlay visible (expect loading screen)"));
		LoadingScreenOverlay.Reset();
		TravelStartSeconds = FPlatformTime::Seconds();
		OpenLevel(StartMap);
	} });
	SequenceSteps.Add({ 5.0f, [this]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[RunAll] 6/6 plain OpenLevel with the overlay hidden (expect no loading screen)"));
		HideViewportOverlay();
		LoadingScreenOverlay.Reset();
		TravelStartSeconds = FPlatformTime::Seconds();
		OpenLevel(LoadingFXProto::TravelTestMap);
	} });
	SequenceSteps.Add({ 4.0f, [this, bQuitWhenDone]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[RunAll] finished"));
		if (bQuitWhenDone)
		{
			FPlatformMisc::RequestExit(false, TEXT("LFXProto.RunAll"));
		}
	} });

	StartSequence();
}

void ULoadingFXProtoSubsystem::RunGallery(bool bTakeScreenshots, bool bQuitWhenDone)
{
	if (GalleryRoot.IsValid() && !bTakeScreenshots && !bQuitWhenDone)
	{
		HideGallery();
		return;
	}

	ShowGallery();
	if (!bTakeScreenshots && !bQuitWhenDone)
	{
		return;
	}

	// Two shots a moment apart: the animated materials should differ between them.
	auto RequestShot = [](const TCHAR* Name)
	{
		const FString Filename = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots") / Name);
		FScreenshotRequest::RequestScreenshot(Filename, /*bInShowUI*/ true, /*bAddUniqueSuffix*/ false);
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Gallery] screenshot requested: %s"), *Filename);
	};

	SequenceSteps.Reset();
	if (bTakeScreenshots)
	{
		// The first delay leaves time for the materials' shaders to finish compiling.
		SequenceSteps.Add({ 4.0f, [RequestShot]() { RequestShot(TEXT("LFXProto_Gallery_A.png")); } });
		// The first capture can hitch for seconds; this empty step restarts the clock once it is through.
		SequenceSteps.Add({ 0.1f, []() {} });
		SequenceSteps.Add({ 0.5f, [RequestShot]() { RequestShot(TEXT("LFXProto_Gallery_B.png")); } });
	}
	if (bQuitWhenDone)
	{
		SequenceSteps.Add({ 1.0f, []() { FPlatformMisc::RequestExit(false, TEXT("LFXProto.Gallery")); } });
	}
	StartSequence();
}

void ULoadingFXProtoSubsystem::RunIconTravelTest(const FString& MapName, float ExtraLoadSeconds, bool bQuitWhenDone)
{
	ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
	if (!IconSubsystem)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("[IconTravel] ULoadingFXIconSubsystem not found"));
		return;
	}

	auto RequestShot = [](const TCHAR* Name)
	{
		const FString Filename = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots") / Name);
		FScreenshotRequest::RequestScreenshot(Filename, /*bInShowUI*/ true, /*bAddUniqueSuffix*/ false);
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] screenshot requested: %s"), *Filename);
	};

	// Exercises the real subsystem instead of the prototype overlay: the prototype's own loading screen stays out
	// of the way (bTravelPending is false and the overlay is hidden).
	SequenceSteps.Reset();
	SequenceSteps.Add({ 0.5f, [this, IconSubsystem]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] 1/5 acquire twice: a plain request and one owned by a throwaway actor"));
		IconTravelHandle = IconSubsystem->Acquire(TEXT("LFXProto.IconTravel"));
		AActor* Owner = GetWorld()->SpawnActor<AActor>();
		IconTravelOwner = Owner;
		const FLoadingFXIconHandle OwnedHandle = IconSubsystem->Acquire(TEXT("LFXProto.IconTravel (owned)"), Owner);
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] visible=%d requests=%d (expect 1, 2); handles active: %d %d (expect 1, 1)"),
			IconSubsystem->IsIconVisible() ? 1 : 0, IconSubsystem->GetRequestCount(),
			IconSubsystem->IsHandleActive(IconTravelHandle) ? 1 : 0, IconSubsystem->IsHandleActive(OwnedHandle) ? 1 : 0);
	} });
	SequenceSteps.Add({ 3.0f, [this, RequestShot]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] 2/5 screenshot of the viewport icon, then Destroy() the owner actor (expect auto-release next tick)"));
		RequestShot(TEXT("LFXProto_Icon_Viewport.png"));
		if (AActor* Owner = Cast<AActor>(IconTravelOwner.Get()))
		{
			Owner->Destroy();
		}
	} });
	SequenceSteps.Add({ 1.0f, [this, IconSubsystem, MapName, ExtraLoadSeconds]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] 3/5 requests=%d (expect 1); OpenLevel %s with +%.1fs simulated load, expecting the icon as loading screen"),
			IconSubsystem->GetRequestCount(), *MapName, ExtraLoadSeconds);
		IconSubsystem->DumpRequests();
		bIconTravelPending = true;
		TravelExtraLoadSeconds = ExtraLoadSeconds;
		TravelStartSeconds = FPlatformTime::Seconds();
		OpenLevel(MapName);
	} });
	SequenceSteps.Add({ ExtraLoadSeconds + 3.0f, [this, IconSubsystem, RequestShot]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] 4/5 after travel: visible=%d requests=%d (expect 1, 1: viewport content survives LoadMap)"),
			IconSubsystem->IsIconVisible() ? 1 : 0, IconSubsystem->GetRequestCount());
		RequestShot(TEXT("LFXProto_Icon_AfterTravel.png"));
	} });
	SequenceSteps.Add({ 1.0f, [this, IconSubsystem]()
	{
		const bool bReleased = IconSubsystem->Release(IconTravelHandle);
		const bool bReleasedAgain = IconSubsystem->Release(IconTravelHandle);
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] 5/5 release=%d, release again=%d, visible=%d (expect 1, 0, 0)"),
			bReleased ? 1 : 0, bReleasedAgain ? 1 : 0, IconSubsystem->IsIconVisible() ? 1 : 0);
	} });
	SequenceSteps.Add({ 1.0f, [bQuitWhenDone]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] finished"));
		if (bQuitWhenDone)
		{
			FPlatformMisc::RequestExit(false, TEXT("LFXProto.IconTravel"));
		}
	} });

	StartSequence();
}

void ULoadingFXProtoSubsystem::RunUmgSpinnerTest(bool bTakeScreenshot, bool bQuitWhenDone)
{
	if (UmgRoot.IsValid() && !bTakeScreenshot && !bQuitWhenDone)
	{
		HideUmgSpinners();
		return;
	}

	UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient();
	if (!ViewportClient)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("No game viewport: cannot show the UMG spinners"));
		return;
	}

	if (!UmgRoot.IsValid())
	{
		TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);

		// Each case is a ULoadingFXSpinner created at runtime (no widget blueprint needed) and hosted as Slate.
		auto AddSpinner = [this, &Row](const TCHAR* Caption, TFunctionRef<void(ULoadingFXSpinner*)> Setup)
		{
			ULoadingFXSpinner* Spinner = NewObject<ULoadingFXSpinner>(this);
			Setup(Spinner);
			UmgSpinners.Add(Spinner);

			Row->AddSlot()
			.AutoWidth()
			.Padding(8.0f)
			.VAlign(VAlign_Top)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				[
					Spinner->TakeWidget()
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

			UE_LOG(LogLoadingFXProto, Display, TEXT("[UmgSpinner] %s: material=%s size=%s desired=%s"), Caption,
				Spinner->GetMaterial() ? *Spinner->GetMaterial()->GetName() : TEXT("<project default>"),
				*Spinner->GetSize().ToString(), *Spinner->GetCachedWidget()->GetDesiredSize().ToString());
		};

		AddSpinner(TEXT("default (project material)"), [](ULoadingFXSpinner*) {});
		AddSpinner(TEXT("M_LoadingBoxes, 96px, orange"), [](ULoadingFXSpinner* Spinner)
		{
			Spinner->SetMaterial(LoadObject<UMaterialInterface>(nullptr, TEXT("/LoadingFX/Materials/M_LoadingBoxes.M_LoadingBoxes")));
			Spinner->SetSize(FVector2D(96.0, 96.0));
			Spinner->SetColorAndOpacity(FLinearColor(1.0f, 0.5f, 0.1f));
		});
		AddSpinner(TEXT("dynamic: PrimaryColor green, Speed 2"), [](ULoadingFXSpinner* Spinner)
		{
			UMaterialInstanceDynamic* Dynamic = Spinner->GetDynamicMaterial();
			if (Dynamic)
			{
				Dynamic->SetVectorParameterValue(TEXT("PrimaryColor"), FLinearColor(0.2f, 1.0f, 0.3f));
				Dynamic->SetScalarParameterValue(TEXT("Speed"), 2.0f);
			}
			UE_LOG(LogLoadingFXProto, Display, TEXT("[UmgSpinner] dynamic material: %s, parent=%s, second call returns the same: %d (expect 1)"),
				Dynamic ? *Dynamic->GetName() : TEXT("<null>"), Dynamic && Dynamic->Parent ? *Dynamic->Parent->GetName() : TEXT("<null>"),
				Spinner->GetDynamicMaterial() == Dynamic ? 1 : 0);
		});
		AddSpinner(TEXT("opacity 0.3"), [](ULoadingFXSpinner* Spinner) { Spinner->SetOpacity(0.3f); });
		AddSpinner(TEXT("wide 160x64"), [](ULoadingFXSpinner* Spinner) { Spinner->SetSize(FVector2D(160.0, 64.0)); });

		UmgRoot = SNew(SBox)
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			.Visibility(EVisibility::HitTestInvisible)
			[
				SNew(SBorder)
				.BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
				.BorderBackgroundColor(FLinearColor(0.0f, 0.0f, 0.0f, 0.6f))
				.Padding(12.0f)
				[
					Row
				]
			];
		ViewportClient->AddViewportWidgetContent(UmgRoot.ToSharedRef(), LoadingFXProto::ViewportOverlayZOrder + 2);
	}

	if (!bTakeScreenshot && !bQuitWhenDone)
	{
		return;
	}

	SequenceSteps.Reset();
	if (bTakeScreenshot)
	{
		SequenceSteps.Add({ 4.0f, []()
		{
			const FString Filename = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("LFXProto_UmgSpinner.png"));
			FScreenshotRequest::RequestScreenshot(Filename, /*bInShowUI*/ true, /*bAddUniqueSuffix*/ false);
			UE_LOG(LogLoadingFXProto, Display, TEXT("[UmgSpinner] screenshot requested: %s"), *Filename);
		} });
	}
	if (bQuitWhenDone)
	{
		SequenceSteps.Add({ 1.5f, []() { FPlatformMisc::RequestExit(false, TEXT("LFXProto.UmgSpinner")); } });
	}
	StartSequence();
}

void ULoadingFXProtoSubsystem::HideUmgSpinners()
{
	if (UmgRoot.IsValid())
	{
		if (UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient())
		{
			ViewportClient->RemoveViewportWidgetContent(UmgRoot.ToSharedRef());
		}
	}
	UmgRoot.Reset();

	for (UWidget* Spinner : UmgSpinners)
	{
		if (Spinner)
		{
			Spinner->ReleaseSlateResources(true);
		}
	}
	UmgSpinners.Reset();
}

void ULoadingFXProtoSubsystem::StartSequence()
{
	NextSequenceStep = 0;
	NextSequenceStepTime = FPlatformTime::Seconds() + SequenceSteps[0].DelayBefore;
	if (!SequenceTickerHandle.IsValid())
	{
		SequenceTickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &ThisClass::TickSequence));
	}
}

TSharedRef<SLoadingFXProtoOverlay> ULoadingFXProtoSubsystem::MakeOverlay(const FString& Label) const
{
	TArray<SLoadingFXProtoOverlay::FTile> Tiles;
	for (int32 Index = 0; Index < Materials.Num(); ++Index)
	{
		Tiles.Add({ Materials[Index], MaterialCaptions[Index] });
	}
	return SNew(SLoadingFXProtoOverlay).Label(Label).Tiles(Tiles);
}

void ULoadingFXProtoSubsystem::ShowViewportOverlay()
{
	if (ViewportOverlay.IsValid())
	{
		return;
	}

	UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient();
	if (!ViewportClient)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("No game viewport: cannot show the overlay"));
		return;
	}

	ViewportOverlay = MakeOverlay(TEXT("Viewport"));
	ViewportOverlayRoot = SNew(SBox)
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Top)
		.Padding(24.0f)
		.Visibility(EVisibility::HitTestInvisible)
		[
			ViewportOverlay.ToSharedRef()
		];

	// Viewport content (not AddToViewport) survives map travel.
	ViewportClient->AddViewportWidgetContent(ViewportOverlayRoot.ToSharedRef(), LoadingFXProto::ViewportOverlayZOrder);
}

void ULoadingFXProtoSubsystem::HideViewportOverlay()
{
	if (ViewportOverlayRoot.IsValid())
	{
		if (UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient())
		{
			ViewportClient->RemoveViewportWidgetContent(ViewportOverlayRoot.ToSharedRef());
		}
	}
	ViewportOverlayRoot.Reset();
	ViewportOverlay.Reset();
}

void ULoadingFXProtoSubsystem::ShowGallery()
{
	if (GalleryRoot.IsValid())
	{
		return;
	}

	UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient();
	if (!ViewportClient)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("No game viewport: cannot show the gallery"));
		return;
	}

	TArray<SLoadingFXProtoGallery::FRow> Rows;
	for (int32 Index = 0; Index < Materials.Num(); ++Index)
	{
		Rows.Add({ Materials[Index], MaterialCaptions[Index] });
	}

	GalleryRoot = SNew(SBox)
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Top)
		.Padding(24.0f)
		.Visibility(EVisibility::HitTestInvisible)
		[
			SNew(SLoadingFXProtoGallery).Rows(Rows)
		];
	ViewportClient->AddViewportWidgetContent(GalleryRoot.ToSharedRef(), LoadingFXProto::ViewportOverlayZOrder + 1);
}

void ULoadingFXProtoSubsystem::HideGallery()
{
	if (GalleryRoot.IsValid())
	{
		if (UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient())
		{
			ViewportClient->RemoveViewportWidgetContent(GalleryRoot.ToSharedRef());
		}
	}
	GalleryRoot.Reset();
}

void ULoadingFXProtoSubsystem::RunShowcase(float TileSize, bool bShowReference, bool bTakeScreenshot, bool bQuitWhenDone)
{
	if (ShowcaseRoot.IsValid() && !bTakeScreenshot && !bQuitWhenDone)
	{
		HideShowcase();
		return;
	}

	HideShowcase();
	ShowShowcase(TileSize, bShowReference);
	if (!bTakeScreenshot && !bQuitWhenDone)
	{
		return;
	}

	SequenceSteps.Reset();
	if (bTakeScreenshot)
	{
		// The delay leaves time for the materials' shaders to finish compiling.
		SequenceSteps.Add({ 4.0f, []()
		{
			const FString Filename = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("LFXProto_Showcase.png"));
			FScreenshotRequest::RequestScreenshot(Filename, /*bInShowUI*/ true, /*bAddUniqueSuffix*/ false);
			UE_LOG(LogLoadingFXProto, Display, TEXT("[Showcase] screenshot requested: %s"), *Filename);
		} });
	}
	if (bQuitWhenDone)
	{
		SequenceSteps.Add({ 1.0f, []() { FPlatformMisc::RequestExit(false, TEXT("LFXProto.Showcase")); } });
	}
	StartSequence();
}

void ULoadingFXProtoSubsystem::ShowShowcase(float TileSize, bool bShowReference)
{
	if (ShowcaseRoot.IsValid())
	{
		return;
	}

	UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient();
	if (!ViewportClient)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("No game viewport: cannot show the showcase"));
		return;
	}

	// Only the plugin's bundled materials: the prototype's own test variants under /Game look the same as their originals.
	TArray<SLoadingFXProtoShowcase::FTile> Tiles;
	for (UMaterialInterface* Material : Materials)
	{
		if (Material && Material->GetPathName().StartsWith(TEXT("/LoadingFX/")))
		{
			Tiles.Add({ Material, Material->GetName() });
		}
	}
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Showcase] %d materials at %.0f px, reference shapes=%d"), Tiles.Num(), TileSize, bShowReference ? 1 : 0);

	ShowcaseRoot = SNew(SLoadingFXProtoShowcase)
		.Tiles(Tiles)
		.TileSize(TileSize)
		.ShowReference(bShowReference)
		.Visibility(EVisibility::HitTestInvisible);
	ViewportClient->AddViewportWidgetContent(ShowcaseRoot.ToSharedRef(), LoadingFXProto::ViewportOverlayZOrder + 2);
}

void ULoadingFXProtoSubsystem::HideShowcase()
{
	if (ShowcaseRoot.IsValid())
	{
		if (UGameViewportClient* ViewportClient = GetGameInstance()->GetGameViewportClient())
		{
			ViewportClient->RemoveViewportWidgetContent(ShowcaseRoot.ToSharedRef());
		}
	}
	ShowcaseRoot.Reset();
}

void ULoadingFXProtoSubsystem::SimulateBlockingWork(float Seconds, bool bCollectGarbage) const
{
	// Stands in for a synchronous load: the game thread does not return to the engine loop until it is done.
	const double StartSeconds = FPlatformTime::Seconds();
	bool bCollected = false;
	while (FPlatformTime::Seconds() - StartSeconds < Seconds)
	{
		FPlatformProcess::Sleep(0.01f);

		if (bCollectGarbage && !bCollected && FPlatformTime::Seconds() - StartSeconds >= Seconds * 0.5)
		{
			const double GCStartSeconds = FPlatformTime::Seconds();
			CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS, true);
			bCollected = true;
			UE_LOG(LogLoadingFXProto, Display, TEXT("GC during block took %.1f ms"), (FPlatformTime::Seconds() - GCStartSeconds) * 1000.0);
		}
	}
}

void ULoadingFXProtoSubsystem::OpenLevel(const FString& MapName)
{
	UGameplayStatics::OpenLevel(GetGameInstance(), FName(*MapName));
}

void ULoadingFXProtoSubsystem::LogOverlayStats(const TCHAR* Context, double ElapsedSeconds) const
{
	if (!LoadingScreenOverlay.IsValid())
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[%s] done in %.2fs: no loading screen was shown"), Context, ElapsedSeconds);
		return;
	}

	UE_LOG(LogLoadingFXProto, Display, TEXT("[%s] done in %.2fs: loading screen '%s' painted %d times, %d of them off the game thread"),
		Context, ElapsedSeconds, *LoadingScreenOverlay->GetLabel(),
		LoadingScreenOverlay->GetPaintCount(), LoadingScreenOverlay->GetOffGameThreadPaintCount());
}

void ULoadingFXProtoSubsystem::HandlePrepareLoadingScreen()
{
	// Called by PlayMovie() (e.g. MoviePlayer's own PreLoadMap hook) when nobody set up a loading screen.
	// v1 behavior under test: take over only when our icon is showing, or when a travel test asked for it.
	if (!bTravelPending && !ViewportOverlay.IsValid())
	{
		return;
	}

	LoadingScreenOverlay = MakeOverlay(bTravelPending
		? FString::Printf(TEXT("Travel +%.1fs"), TravelExtraLoadSeconds)
		: FString(TEXT("LoadMap (overlay was visible)")));

	FLoadingScreenAttributes Attributes;
	Attributes.WidgetLoadingScreen = LoadingScreenOverlay;
	Attributes.bAutoCompleteWhenLoadingCompletes = true;
	GetMoviePlayer()->SetupLoadingScreen(Attributes);
	UE_LOG(LogLoadingFXProto, Display, TEXT("Loading screen prepared for LoadMap: %s"), *LoadingScreenOverlay->GetLabel());
}

void ULoadingFXProtoSubsystem::HandleMoviePlaybackStarted()
{
	// Runs inside PlayMovie(), i.e. inside LoadMap for travel: sleeping here lengthens the blocked section.
	if ((bTravelPending || bIconTravelPending) && TravelExtraLoadSeconds > 0.0f)
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("Simulating +%.1fs of map loading%s"), TravelExtraLoadSeconds,
			bIconTravelPending ? TEXT(" (MoviePlayer started, so a loading screen was prepared: see LogLoadingFX)") : TEXT(""));
		SimulateBlockingWork(TravelExtraLoadSeconds, false);
	}
}

void ULoadingFXProtoSubsystem::HandlePostLoadMap(UWorld* LoadedWorld)
{
	if (TravelStartSeconds <= 0.0)
	{
		return;
	}

	const FString MapName = LoadedWorld ? LoadedWorld->GetPackage()->GetName() : FString(TEXT("<none>"));
	if (bIconTravelPending)
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] LoadMap %s done in %.2fs"), *MapName, FPlatformTime::Seconds() - TravelStartSeconds);
	}
	else
	{
		LogOverlayStats(*FString::Printf(TEXT("LoadMap %s"), *MapName), FPlatformTime::Seconds() - TravelStartSeconds);
	}

	bTravelPending = false;
	bIconTravelPending = false;
	TravelStartSeconds = 0.0;
}

bool ULoadingFXProtoSubsystem::TickSequence(float DeltaTime)
{
	if (NextSequenceStep >= SequenceSteps.Num())
	{
		SequenceTickerHandle.Reset();
		return false;
	}

	if (FPlatformTime::Seconds() < NextSequenceStepTime)
	{
		return true;
	}

	// Copy the action: it may block or travel, and RunAll() may rebuild the array.
	const TFunction<void()> Action = SequenceSteps[NextSequenceStep].Action;
	++NextSequenceStep;
	Action();

	if (NextSequenceStep < SequenceSteps.Num())
	{
		NextSequenceStepTime = FPlatformTime::Seconds() + SequenceSteps[NextSequenceStep].DelayBefore;
	}
	return true;
}
