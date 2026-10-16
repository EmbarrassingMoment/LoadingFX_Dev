// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXProtoSubsystem.h"

#include "SLoadingFXProtoGallery.h"
#include "SLoadingFXProtoOverlay.h"
#include "SLoadingFXProtoShowcase.h"

#include "LoadingFXIconSubsystem.h"
#include "LoadingFXLoadAssetsAsyncAction.h"
#include "LoadingFXLoaderSubsystem.h"
#include "LoadingFXSettings.h"
#include "LoadingFXSpinner.h"

#include "Algo/Count.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "Kismet/GameplayStatics.h"
#include "MaterialShared.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/CoreDelegates.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "MoviePlayer.h"
#include "PipelineStateCache.h"
#include "PSOPrecacheValidation.h"
#include "RHIFeatureLevel.h"
#include "UnrealClient.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"
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
		{ TEXT("/LoadingFX/Materials/M_LoadingComet.M_LoadingComet"), TEXT("Comet (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingDots.M_LoadingDots"), TEXT("Dots (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingDualArc.M_LoadingDualArc"), TEXT("DualArc (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingSegments.M_LoadingSegments"), TEXT("Segments (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingTimer.M_LoadingTimer"), TEXT("Timer (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingHourglass.M_LoadingHourglass"), TEXT("Hourglass (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingBounce.M_LoadingBounce"), TEXT("Bounce (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingRipple.M_LoadingRipple"), TEXT("Ripple (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingEqualizer.M_LoadingEqualizer"), TEXT("Equalizer (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingGooey.M_LoadingGooey"), TEXT("Gooey (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingMorph.M_LoadingMorph"), TEXT("Morph (RealTime)") },
		{ TEXT("/LoadingFX/Materials/M_LoadingLinear.M_LoadingLinear"), TEXT("Linear (RealTime)") },
	};

	static const TCHAR* const TravelTestMap = TEXT("/Engine/Maps/Entry");
	constexpr int32 ViewportOverlayZOrder = 10000;

	/** LFXProto.Preload compares the icon material with this one, which nothing loads before the test does. */
	static const TCHAR* const PreloadControlMaterialPath = TEXT("/LoadingFX/Materials/M_LoadingArc.M_LoadingArc");

	void RequestScreenshot(const TCHAR* Context, const TCHAR* Name)
	{
		const FString Filename = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots") / Name);
		FScreenshotRequest::RequestScreenshot(Filename, /*bInShowUI*/ true, /*bAddUniqueSuffix*/ false);
		UE_LOG(LogLoadingFXProto, Display, TEXT("[%s] screenshot requested: %s"), Context, *Filename);
	}

	/**
	 * Logs the compile state of every graphics PSO that loading the material asked to precache. PSO precaching is
	 * compiled out of editor builds (PipelineStateCache::IsPSOPrecachingEnabled), so this needs a packaged build.
	 */
	void LogPSOPrecacheState(const TCHAR* Context, const UMaterialInterface* Material)
	{
		if (!Material)
		{
			UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] %s no material"), Context);
			return;
		}

#if PSO_PRECACHING_TRACKING
		if (!PipelineStateCache::IsPSOPrecachingEnabled())
		{
			UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] %s %s: PSO precaching is off (r.PSOPrecaching=0, or not supported by this RHI)"), Context, *Material->GetName());
			return;
		}

		const FMaterialResource* Resource = Material->GetMaterialResource(GMaxRHIFeatureLevel);
		if (!Resource)
		{
			UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] %s %s: no material resource for the current feature level"), Context, *Material->GetName());
			return;
		}

		const TArray<FMaterialPSOPrecacheRequestID> RequestIDs = Resource->GetMaterialPSOPrecacheRequestIDs();
		int32 NumPSOs = 0;
		int32 NumComplete = 0;
		int32 NumActive = 0;
		int32 NumMissed = 0;
		int32 NumOther = 0;
		for (const FMaterialPSOPrecacheRequestID RequestID : RequestIDs)
		{
			for (const FPSOPrecacheData& Data : GetMaterialPSOPrecacheData(RequestID))
			{
				if (Data.Type != FPSOPrecacheData::EType::Graphics)
				{
					continue;
				}
				++NumPSOs;
				switch (PipelineStateCache::CheckPipelineStateInCache(Data.GraphicsPSOInitializer))
				{
				case EPSOPrecacheResult::Complete: ++NumComplete; break;
				case EPSOPrecacheResult::Active:   ++NumActive;   break;
				case EPSOPrecacheResult::Missed:   ++NumMissed;   break;
				default:                           ++NumOther;    break;
				}
			}
		}
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] %s %s: %d PSO precache request(s), %d graphics PSO(s): %d compiled, %d still compiling, %d not requested, %d other (%u precache compiles in flight overall)"),
			Context, *Material->GetName(), RequestIDs.Num(), NumPSOs, NumComplete, NumActive, NumMissed, NumOther, PipelineStateCache::NumActivePrecacheRequests());
#else
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] %s %s: PSO precaching is compiled out of editor builds; run the packaged build to see PSO states"), Context, *Material->GetName());
#endif
	}

	/** Acquires with IconShowDelay at 0 for this one request, so the icon shows at once (as the preload checks expect). */
	FLoadingFXIconHandle AcquireWithoutShowDelay(ULoadingFXIconSubsystem& IconSubsystem, FName Reason)
	{
		ULoadingFXSettings* Settings = GetMutableDefault<ULoadingFXSettings>();
		const float SavedShowDelay = Settings->IconShowDelay;
		Settings->IconShowDelay = 0.0f;
		const FLoadingFXIconHandle Handle = IconSubsystem.Acquire(Reason);
		Settings->IconShowDelay = SavedShowDelay;
		return Handle;
	}

	/** LFXProto.Loader: a bundled material by name. The test expects them not to be loaded yet (M_LoadingSpinner is the preloaded icon). */
	FSoftObjectPath LoaderMaterial(const TCHAR* Name)
	{
		return FSoftObjectPath(FString::Printf(TEXT("/LoadingFX/Materials/%s.%s"), Name, Name));
	}

	static const TCHAR* const LoaderMissingPath = TEXT("/LoadingFX/Materials/M_LoadingMissing.M_LoadingMissing");
	static const TCHAR* const LoaderBlueprintClassPath = TEXT("/Engine/EngineSky/BP_Sky_Sphere.BP_Sky_Sphere_C");

	template <typename ObjectType>
	FString DescribeObjects(const TArray<ObjectType*>& Objects)
	{
		FString Text;
		for (const ObjectType* Object : Objects)
		{
			Text += Text.IsEmpty() ? TEXT("") : TEXT(", ");
			Text += Object ? Object->GetName() : FString(TEXT("null"));
		}
		return Text.IsEmpty() ? FString(TEXT("(none)")) : Text;
	}

	int32 CountAlive(const TArray<TWeakObjectPtr<UObject>>& Objects)
	{
		return Algo::CountIf(Objects, [](const TWeakObjectPtr<UObject>& Object) { return Object.IsValid(); });
	}

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

	static FAutoConsoleCommandWithWorldAndArgs PreloadCommand(
		TEXT("LFXProto.Preload"),
		TEXT("Verification prototype: check the icon material preload (in memory before Acquire, no sync load, PSOs precached in packaged builds). Args: [shot] [quit]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunPreloadTest(Args.Contains(TEXT("shot")), Args.Contains(TEXT("quit")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs MinDisplayCommand(
		TEXT("LFXProto.MinDisplay"),
		TEXT("Verification prototype: check the loading icon's minimum display time (short request, re-acquire while held, long request, ReleaseAll, setting at 0). Args: [quit]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunMinDisplayTest(Args.Contains(TEXT("quit")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs ShowDelayCommand(
		TEXT("LFXProto.ShowDelay"),
		TEXT("Verification prototype: check the loading icon's show delay (short and long requests, two requests, setting at 0, blocking loads within the delay). Args: [quit]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunShowDelayTest(Args.Contains(TEXT("quit")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs LoaderCommand(
		TEXT("LFXProto.Loader"),
		TEXT("Verification prototype: check the asset loader and the Bridge (async and sync loads, retention, cancel, owner, the loading icon, the Blueprint entry points). Run it in a fresh process. Args: [quit]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXProtoSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->RunLoaderTest(Args.Contains(TEXT("quit")));
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

	// The icon subsystem starts its material preload in Initialize; initializing it first makes the early
	// Acquire below land while that load is in flight.
	ULoadingFXIconSubsystem* IconSubsystem = Collection.InitializeDependency<ULoadingFXIconSubsystem>();

	// Every sync load of the icon material's package is counted for LFXProto.Preload (expect none).
	IconPackageName = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial.ToSoftObjectPath().GetLongPackageName();
	SyncLoadPackageHandle = FCoreDelegates::OnSyncLoadPackage.AddUObject(this, &ThisClass::HandleSyncLoadPackage);

	if (IconSubsystem && FParse::Param(FCommandLine::Get(), TEXT("LFXProtoEarlyAcquire")))
	{
		const UObject* IconMaterial = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial.Get();
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] early Acquire during game instance init: icon material in memory=%d, game viewport=%d (expect 0, 0: the icon appears once the viewport exists, waiting for the preload if needed)"),
			IconMaterial ? 1 : 0, GetGameInstance()->GetGameViewportClient() ? 1 : 0);
		EarlyAcquireHandle = LoadingFXProto::AcquireWithoutShowDelay(*IconSubsystem, TEXT("LFXProto.EarlyAcquire"));
	}

	IGameMoviePlayer* MoviePlayer = GetMoviePlayer();
	if (MoviePlayer)
	{
		PrepareLoadingScreenHandle = MoviePlayer->OnPrepareLoadingScreen().AddUObject(this, &ThisClass::HandlePrepareLoadingScreen);
		MoviePlaybackStartedHandle = MoviePlayer->OnMoviePlaybackStarted().AddUObject(this, &ThisClass::HandleMoviePlaybackStarted);
	}
	PostLoadMapHandle = FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(this, &ThisClass::HandlePostLoadMap);

	UE_LOG(LogLoadingFXProto, Display, TEXT("Initialized: MoviePlayer enabled=%d initialized=%d"),
		IsMoviePlayerEnabled() ? 1 : 0, (MoviePlayer && MoviePlayer->IsInitialized()) ? 1 : 0);
}

void ULoadingFXProtoSubsystem::LoadMaterials()
{
	if (bMaterialsLoaded)
	{
		return;
	}
	bMaterialsLoaded = true;

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
	UE_LOG(LogLoadingFXProto, Display, TEXT("Loaded %d prototype materials"), Materials.Num());
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
	FCoreDelegates::OnSyncLoadPackage.Remove(SyncLoadPackageHandle);
	if (ULoadingFXLoaderSubsystem* Loader = GetGameInstance()->GetSubsystem<ULoadingFXLoaderSubsystem>())
	{
		Loader->OnLoadStartedNative.Remove(LoaderStartedHandle);
		Loader->OnLoadEndedNative.Remove(LoaderEndedHandle);
	}

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
		UE_LOG(LogLoadingFXProto, Display, TEXT("[IconTravel] visible=%d requests=%d (expect %d, 2: the icon appears after IconShowDelay); handles active: %d %d (expect 1, 1)"),
			IconSubsystem->IsIconVisible() ? 1 : 0, IconSubsystem->GetRequestCount(), GetDefault<ULoadingFXSettings>()->IconShowDelay > 0.0f ? 0 : 1,
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

TSharedRef<SLoadingFXProtoOverlay> ULoadingFXProtoSubsystem::MakeOverlay(const FString& Label)
{
	LoadMaterials();

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

	LoadMaterials();
	TArray<SLoadingFXProtoGallery::FRow> Rows;
	for (int32 Index = 0; Index < Materials.Num(); ++Index)
	{
		Rows.Add({ Materials[Index], MaterialCaptions[Index] });
	}

	// Each row is about 144 px tall, so from eight materials on the gallery outgrows a 1080 px viewport. Scale it down
	// to fit rather than cut rows off. The materials stay sharp: PixelSize comes from the screen derivatives.
	GalleryRoot = SNew(SBox)
		.Padding(24.0f)
		.Visibility(EVisibility::HitTestInvisible)
		[
			SNew(SScaleBox)
			.Stretch(EStretch::ScaleToFit)
			.StretchDirection(EStretchDirection::DownOnly)
			.HAlign(HAlign_Left)
			.VAlign(VAlign_Top)
			[
				SNew(SLoadingFXProtoGallery).Rows(Rows)
			]
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
	LoadMaterials();
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

void ULoadingFXProtoSubsystem::RunPreloadTest(bool bTakeScreenshot, bool bQuitWhenDone)
{
	ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
	if (!IconSubsystem)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("[Preload] ULoadingFXIconSubsystem not found"));
		return;
	}

	SequenceSteps.Reset();
	SequenceSteps.Add({ 0.0f, [this, IconSubsystem]()
	{
		const TSoftObjectPtr<UMaterialInterface>& IconMaterialPtr = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial;
		UMaterialInterface* IconMaterial = IconMaterialPtr.Get();
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] 1/4 before Acquire: icon material %s in memory=%d (expect 1), sync loads of its package so far=%d (expect 0), early request active=%d"),
			*IconMaterialPtr.ToString(), IconMaterial ? 1 : 0, IconPackageSyncLoads, IconSubsystem->IsHandleActive(EarlyAcquireHandle) ? 1 : 0);
		LoadingFXProto::LogPSOPrecacheState(TEXT("1/4 icon material, before Acquire:"), IconMaterial);

		const int32 SyncLoadsBefore = IconPackageSyncLoads;
		const double AcquireStartSeconds = FPlatformTime::Seconds();
		PreloadTestHandle = LoadingFXProto::AcquireWithoutShowDelay(*IconSubsystem, TEXT("LFXProto.Preload"));
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] 2/4 Acquire took %.2f ms, sync loads of the icon material package during it=%d (expect 0), visible=%d (expect 1)"),
			(FPlatformTime::Seconds() - AcquireStartSeconds) * 1000.0, IconPackageSyncLoads - SyncLoadsBefore, IconSubsystem->IsIconVisible() ? 1 : 0);

		// The control: a material loaded only now, as the icon material was before the preload. Its PSO compiles
		// start at this load, so right after it they are expected to be still in flight (or not collected yet).
		const double ControlLoadStartSeconds = FPlatformTime::Seconds();
		PreloadControlMaterial = LoadObject<UMaterialInterface>(nullptr, LoadingFXProto::PreloadControlMaterialPath);
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] 2/4 control %s loaded on demand in %.2f ms"),
			LoadingFXProto::PreloadControlMaterialPath, (FPlatformTime::Seconds() - ControlLoadStartSeconds) * 1000.0);
		LoadingFXProto::LogPSOPrecacheState(TEXT("2/4 control, right after its load:"), PreloadControlMaterial);
	} });
	SequenceSteps.Add({ 3.0f, [this, bTakeScreenshot]()
	{
		LoadingFXProto::LogPSOPrecacheState(TEXT("3/4 icon material, 3 s later:"), GetDefault<ULoadingFXSettings>()->LoadingIconMaterial.Get());
		LoadingFXProto::LogPSOPrecacheState(TEXT("3/4 control, 3 s later:"), PreloadControlMaterial);
		if (bTakeScreenshot)
		{
			LoadingFXProto::RequestScreenshot(TEXT("Preload"), TEXT("LFXProto_Preload.png"));
		}
	} });
	SequenceSteps.Add({ 1.0f, [this, IconSubsystem]()
	{
		const bool bReleased = IconSubsystem->Release(PreloadTestHandle);
		const bool bReleasedEarly = IconSubsystem->Release(EarlyAcquireHandle);
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] 4/4 release=%d, early release=%d (1 with -LFXProtoEarlyAcquire), visible=%d (expect 0), icon package sync loads in total=%d (expect 0)"),
			bReleased ? 1 : 0, bReleasedEarly ? 1 : 0, IconSubsystem->IsIconVisible() ? 1 : 0, IconPackageSyncLoads);
	} });
	SequenceSteps.Add({ 0.5f, [bQuitWhenDone]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] finished"));
		if (bQuitWhenDone)
		{
			FPlatformMisc::RequestExit(false, TEXT("LFXProto.Preload"));
		}
	} });

	StartSequence();
}

ULoadingFXIconSubsystem* ULoadingFXProtoSubsystem::BeginIconTest(const TCHAR* Tag)
{
	ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
	if (!IconSubsystem)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("%s ULoadingFXIconSubsystem not found"), Tag);
		return nullptr;
	}
	if (IconSubsystem->IsIconVisible() || IconSubsystem->GetRequestCount() > 0)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("%s the loading icon is in use: release its requests first (LoadingFX.Icon.Hide all)"), Tag);
		return nullptr;
	}
	if (!IconVisibilityChangedHandle.IsValid())
	{
		IconVisibilityChangedHandle = IconSubsystem->OnVisibilityChangedNative.AddUObject(this, &ThisClass::HandleIconVisibilityChanged);
	}
	return IconSubsystem;
}

void ULoadingFXProtoSubsystem::EndIconTest(const TCHAR* Tag, bool bQuitWhenDone)
{
	if (ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>())
	{
		IconSubsystem->OnVisibilityChangedNative.Remove(IconVisibilityChangedHandle);
	}
	IconVisibilityChangedHandle.Reset();
	UE_LOG(LogLoadingFXProto, Display, TEXT("%s finished"), Tag);
	if (bQuitWhenDone)
	{
		FPlatformMisc::RequestExit(false, Tag);
	}
}

void ULoadingFXProtoSubsystem::StartIconCase(const TCHAR* Tag, const FString& Description)
{
	UE_LOG(LogLoadingFXProto, Display, TEXT("%s %s"), Tag, *Description);
	IconTestEvents.Reset();
	IconTestCaseStartSeconds = FPlatformTime::Seconds();
	IconTestHandle = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>()->Acquire(TEXT("LFXProto.IconTest"));
}

void ULoadingFXProtoSubsystem::ReportIconCase(const TCHAR* Tag, const TCHAR* Step, const FString& Expect) const
{
	const ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
	FString Events;
	for (const TPair<bool, double>& Event : IconTestEvents)
	{
		Events += FString::Printf(TEXT(" %s@%.2fs"), Event.Key ? TEXT("show") : TEXT("hide"), Event.Value - IconTestCaseStartSeconds);
	}
	UE_LOG(LogLoadingFXProto, Display, TEXT("%s   %s at %.2fs: visible=%d requests=%d events:%s (expect %s)"),
		Tag, Step, FPlatformTime::Seconds() - IconTestCaseStartSeconds, IconSubsystem->IsIconVisible() ? 1 : 0, IconSubsystem->GetRequestCount(),
		Events.IsEmpty() ? TEXT(" none") : *Events, *Expect);
}

void ULoadingFXProtoSubsystem::StartIconTestTravel(float Seconds)
{
	// The IconTravel path: HandleMoviePlaybackStarted simulates the load inside LoadMap, HandlePostLoadMap logs its duration.
	bIconTravelPending = true;
	TravelExtraLoadSeconds = Seconds;
	TravelStartSeconds = FPlatformTime::Seconds();
	OpenLevel(LoadingFXProto::TravelTestMap);
}

void ULoadingFXProtoSubsystem::RunMinDisplayTest(bool bQuitWhenDone)
{
	static const TCHAR* const Tag = TEXT("[MinDisplay]");
	ULoadingFXIconSubsystem* IconSubsystem = BeginIconTest(Tag);
	if (!IconSubsystem)
	{
		return;
	}

	// The cases run against the project's setting (case 5 sets it to 0 for a moment), with the show delay off so the
	// icon appears at each request. The expected values assume the minimum is long enough to still be holding the
	// icon 0.6 s after it appeared.
	ULoadingFXSettings* Settings = GetMutableDefault<ULoadingFXSettings>();
	const float MinTime = Settings->IconMinimumDisplayTime;
	const float SavedShowDelay = Settings->IconShowDelay;
	Settings->IconShowDelay = 0.0f;
	UE_LOG(LogLoadingFXProto, Display, TEXT("%s IconMinimumDisplayTime=%.2fs (IconShowDelay set to 0 for the test)"), Tag, MinTime);
	if (MinTime < 0.8f)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("%s the expected values assume IconMinimumDisplayTime >= 0.8 s"), Tag);
	}

	const FString ExpectHeld = FString::Printf(TEXT("visible=1 requests=0, show@0.00s only: held until %.2fs"), MinTime);
	const FString ExpectHidden = FString::Printf(TEXT("visible=0, show@0.00s hide@%.2fs"), MinTime);

	SequenceSteps.Reset();

	SequenceSteps.Add({ 0.5f, [this]() { StartIconCase(Tag, TEXT("1/5 short request: release after 0.2 s")); } });
	SequenceSteps.Add({ 0.2f, [this, IconSubsystem, ExpectHeld]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("released"), ExpectHeld);
	} });
	SequenceSteps.Add({ MinTime, [this, ExpectHidden]() { ReportIconCase(Tag, TEXT("after the minimum display time"), ExpectHidden); } });

	SequenceSteps.Add({ 0.5f, [this]() { StartIconCase(Tag, TEXT("2/5 acquire again while held: release at 0.2 s, acquire at 0.4 s, release at 0.6 s")); } });
	SequenceSteps.Add({ 0.2f, [this, IconSubsystem]() { IconSubsystem->Release(IconTestHandle); } });
	SequenceSteps.Add({ 0.2f, [this, IconSubsystem]()
	{
		IconTestHandle = IconSubsystem->Acquire(TEXT("LFXProto.IconTest (again)"));
		ReportIconCase(Tag, TEXT("acquired again"), TEXT("visible=1 requests=1, show@0.00s only: no hide in between"));
	} });
	SequenceSteps.Add({ 0.2f, [this, IconSubsystem, ExpectHeld]()
	{
		IconSubsystem->Release(IconTestHandle);
		IconSubsystem->DumpRequests();
		ReportIconCase(Tag, TEXT("released again"), ExpectHeld + TEXT(", counted from the first show"));
	} });
	SequenceSteps.Add({ MinTime, [this, ExpectHidden]() { ReportIconCase(Tag, TEXT("after the minimum display time"), ExpectHidden); } });

	SequenceSteps.Add({ 0.5f, [this, MinTime]() { StartIconCase(Tag, FString::Printf(TEXT("3/5 long request: release after %.2f s"), MinTime + 0.3f)); } });
	SequenceSteps.Add({ MinTime + 0.3f, [this, IconSubsystem, MinTime]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("released"), FString::Printf(TEXT("visible=0 requests=0, show@0.00s hide@%.2fs: hidden at the release"), MinTime + 0.3f));
	} });

	SequenceSteps.Add({ 0.5f, [this]() { StartIconCase(Tag, TEXT("4/5 ReleaseAll after 0.2 s")); } });
	SequenceSteps.Add({ 0.2f, [this, IconSubsystem, ExpectHeld]()
	{
		IconSubsystem->ReleaseAll();
		IconTestHandle.Invalidate();
		ReportIconCase(Tag, TEXT("released all"), ExpectHeld);
	} });
	SequenceSteps.Add({ MinTime, [this, ExpectHidden]() { ReportIconCase(Tag, TEXT("after the minimum display time"), ExpectHidden); } });

	SequenceSteps.Add({ 0.5f, [this]()
	{
		GetMutableDefault<ULoadingFXSettings>()->IconMinimumDisplayTime = 0.0f;
		StartIconCase(Tag, TEXT("5/5 IconMinimumDisplayTime=0: release after 0.2 s"));
	} });
	SequenceSteps.Add({ 0.2f, [this, IconSubsystem, MinTime]()
	{
		IconSubsystem->Release(IconTestHandle);
		GetMutableDefault<ULoadingFXSettings>()->IconMinimumDisplayTime = MinTime;
		ReportIconCase(Tag, TEXT("released"), TEXT("visible=0 requests=0, show@0.00s hide@0.20s: hidden at the release"));
	} });

	SequenceSteps.Add({ 0.5f, [this, SavedShowDelay, bQuitWhenDone]()
	{
		GetMutableDefault<ULoadingFXSettings>()->IconShowDelay = SavedShowDelay;
		EndIconTest(Tag, bQuitWhenDone);
	} });

	StartSequence();
}

void ULoadingFXProtoSubsystem::RunShowDelayTest(bool bQuitWhenDone)
{
	static const TCHAR* const Tag = TEXT("[ShowDelay]");
	ULoadingFXIconSubsystem* IconSubsystem = BeginIconTest(Tag);
	if (!IconSubsystem)
	{
		return;
	}

	// The cases run against the project's settings (case 5 sets the delay to 0 for a moment). The expected values
	// assume a delay of at least 0.4 s, and a delay plus minimum display time that is over before case 6's load is.
	const ULoadingFXSettings* Settings = GetDefault<ULoadingFXSettings>();
	const float Delay = Settings->IconShowDelay;
	const float MinTime = Settings->IconMinimumDisplayTime;
	UE_LOG(LogLoadingFXProto, Display, TEXT("%s IconShowDelay=%.2fs IconMinimumDisplayTime=%.2fs"), Tag, Delay, MinTime);
	if (Delay < 0.4f || Delay + MinTime > 1.8f)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("%s the expected values assume IconShowDelay >= 0.4 s and IconShowDelay + IconMinimumDisplayTime <= 1.8 s"), Tag);
	}

	const FString ExpectHeld = FString::Printf(TEXT("visible=1 requests=0, show@%.2fs only: held until %.2fs"), Delay, Delay + MinTime);
	const FString ExpectHidden = FString::Printf(TEXT("visible=0, show@%.2fs hide@%.2fs"), Delay, Delay + MinTime);

	SequenceSteps.Reset();

	SequenceSteps.Add({ 0.5f, [this, Delay]() { StartIconCase(Tag, FString::Printf(TEXT("1/7 short request: release at %.2f s, within the delay"), Delay * 0.5f)); } });
	SequenceSteps.Add({ Delay * 0.5f, [this, IconSubsystem]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("released"), TEXT("visible=0 requests=0, no events: the icon never appeared"));
	} });
	SequenceSteps.Add({ Delay, [this]() { ReportIconCase(Tag, TEXT("after the delay would have ended"), TEXT("visible=0, no events")); } });

	SequenceSteps.Add({ 0.5f, [this, Delay, MinTime]() { StartIconCase(Tag, FString::Printf(TEXT("2/7 long request: release at %.2f s"), Delay + MinTime + 0.3f)); } });
	SequenceSteps.Add({ Delay - 0.1f, [this]() { ReportIconCase(Tag, TEXT("just before the delay ends"), TEXT("visible=0 requests=1, no events")); } });
	SequenceSteps.Add({ 0.2f, [this, Delay]() { ReportIconCase(Tag, TEXT("just after the delay"), FString::Printf(TEXT("visible=1 requests=1, show@%.2fs"), Delay)); } });
	SequenceSteps.Add({ MinTime + 0.2f, [this, IconSubsystem, Delay, MinTime]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("released"), FString::Printf(TEXT("visible=0 requests=0, show@%.2fs hide@%.2fs: hidden at the release"), Delay, Delay + MinTime + 0.3f));
	} });

	SequenceSteps.Add({ 0.5f, [this, Delay]() { StartIconCase(Tag, FString::Printf(TEXT("3/7 release soon after the icon appears: release at %.2f s"), Delay + 0.2f)); } });
	SequenceSteps.Add({ Delay + 0.2f, [this, IconSubsystem, ExpectHeld]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("released"), ExpectHeld);
	} });
	SequenceSteps.Add({ MinTime, [this, ExpectHidden]() { ReportIconCase(Tag, TEXT("after the minimum display time"), ExpectHidden); } });

	SequenceSteps.Add({ 0.5f, [this, Delay]()
	{
		StartIconCase(Tag, FString::Printf(TEXT("4/7 two requests: second at %.2f s, first released at %.2f s, second at %.2f s"), Delay * 0.5f, Delay * 0.75f, Delay + 0.2f));
	} });
	SequenceSteps.Add({ Delay * 0.5f, [this, IconSubsystem]() { IconTestSecondHandle = IconSubsystem->Acquire(TEXT("LFXProto.IconTest (second)")); } });
	SequenceSteps.Add({ Delay * 0.25f, [this, IconSubsystem]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("first released"), TEXT("visible=0 requests=1, no events"));
	} });
	SequenceSteps.Add({ Delay * 0.25f + 0.1f, [this, Delay]()
	{
		ReportIconCase(Tag, TEXT("after the delay"), FString::Printf(TEXT("visible=1 requests=1, show@%.2fs: the delay counts from the first request"), Delay));
	} });
	SequenceSteps.Add({ 0.1f, [this, IconSubsystem, ExpectHeld]()
	{
		IconSubsystem->Release(IconTestSecondHandle);
		ReportIconCase(Tag, TEXT("second released"), ExpectHeld);
	} });
	SequenceSteps.Add({ MinTime, [this, ExpectHidden]() { ReportIconCase(Tag, TEXT("after the minimum display time"), ExpectHidden); } });

	SequenceSteps.Add({ 0.5f, [this, Delay]()
	{
		GetMutableDefault<ULoadingFXSettings>()->IconShowDelay = 0.0f;
		StartIconCase(Tag, TEXT("5/7 IconShowDelay=0: the icon appears at the request"));
		GetMutableDefault<ULoadingFXSettings>()->IconShowDelay = Delay;
		ReportIconCase(Tag, TEXT("acquired"), TEXT("visible=1 requests=1, show@0.00s"));
	} });
	SequenceSteps.Add({ MinTime + 0.2f, [this, IconSubsystem, MinTime]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("released"), FString::Printf(TEXT("visible=0 requests=0, show@0.00s hide@%.2fs: hidden at the release"), MinTime + 0.2f));
	} });

	// A blocking load that starts within the delay: MoviePlayer takes over at once, and LogLoadingFX should report the
	// icon appearing on the loading screen when the delay is over.
	SequenceSteps.Add({ 0.5f, [this]() { StartIconCase(Tag, TEXT("6/7 blocking load within the delay: OpenLevel at 0.1 s with 2 s of simulated loading")); } });
	SequenceSteps.Add({ 0.1f, [this]()
	{
		ReportIconCase(Tag, TEXT("before OpenLevel"), TEXT("visible=0 requests=1, no events"));
		StartIconTestTravel(2.0f);
	} });
	SequenceSteps.Add({ 3.5f, [this, Delay]()
	{
		ReportIconCase(Tag, TEXT("after the load"), FString::Printf(TEXT("visible=1 requests=1, show once the game thread was back: on the loading screen since %.2fs"), Delay));
	} });
	SequenceSteps.Add({ 0.2f, [this, IconSubsystem]()
	{
		IconSubsystem->Release(IconTestHandle);
		ReportIconCase(Tag, TEXT("released"), TEXT("visible=0 requests=0: hidden at the release, the minimum display time is over"));
	} });

	// The release comes from inside LoadMap, after the delay but before the ticker could show the icon: it is shown
	// then (it was on the loading screen) and held for the rest of the minimum display time. The load is sized to end
	// between the two.
	const float ReleaseInLoadMapLoad = Delay + MinTime * 0.5f - 0.3f;
	SequenceSteps.Add({ 0.5f, [this, ReleaseInLoadMapLoad]()
	{
		StartIconCase(Tag, FString::Printf(TEXT("7/7 release inside LoadMap after the delay: OpenLevel at 0.1 s with %.2f s of simulated loading, release from PostLoadMapWithWorld"), ReleaseInLoadMapLoad));
	} });
	SequenceSteps.Add({ 0.1f, [this, ReleaseInLoadMapLoad, Delay, MinTime]()
	{
		bReleaseIconTestInLoadMap = true;
		IconTestReleaseInLoadMapExpect = FString::Printf(TEXT("visible=1 requests=0, show at the release only: held until %.2fs (if the load ended after %.2fs)"), Delay + MinTime, Delay);
		StartIconTestTravel(ReleaseInLoadMapLoad);
	} });
	SequenceSteps.Add({ Delay + MinTime + 0.3f, [this, Delay, MinTime]()
	{
		ReportIconCase(Tag, TEXT("after the minimum display time"), FString::Printf(TEXT("visible=0, show at the release, hide@%.2fs"), Delay + MinTime));
	} });

	SequenceSteps.Add({ 0.5f, [this, bQuitWhenDone]() { EndIconTest(Tag, bQuitWhenDone); } });

	StartSequence();
}

void ULoadingFXProtoSubsystem::RunLoaderTest(bool bQuitWhenDone)
{
	static const TCHAR* const Tag = TEXT("[Loader]");
	using LoadingFXProto::LoaderMaterial;

	ULoadingFXLoaderSubsystem* Loader = GetGameInstance()->GetSubsystem<ULoadingFXLoaderSubsystem>();
	ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
	if (!Loader || !IconSubsystem)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("%s ULoadingFXLoaderSubsystem or ULoadingFXIconSubsystem not found"), Tag);
		return;
	}
	if (IconSubsystem->IsIconVisible() || IconSubsystem->GetRequestCount() > 0)
	{
		UE_LOG(LogLoadingFXProto, Warning, TEXT("%s the loading icon is in use: release its requests first (LoadingFX.Icon.Hide all)"), Tag);
		return;
	}

	// Bound after the Bridge, so these run before it (multicast delegates call the last bound first): the end event of
	// a sync load arrives here while the Bridge's blocking section is still on.
	if (!LoaderStartedHandle.IsValid())
	{
		LoaderStartedHandle = Loader->OnLoadStartedNative.AddUObject(this, &ThisClass::HandleLoaderLoadStarted);
		LoaderEndedHandle = Loader->OnLoadEndedNative.AddUObject(this, &ThisClass::HandleLoaderLoadEnded);
	}

	const ULoadingFXSettings* Settings = GetDefault<ULoadingFXSettings>();
	UE_LOG(LogLoadingFXProto, Display, TEXT("%s IconShowDelay=%.2fs IconMinimumDisplayTime=%.2fs, MoviePlayer enabled=%d"),
		Tag, Settings->IconShowDelay, Settings->IconMinimumDisplayTime, IsMoviePlayerEnabled() ? 1 : 0);

	TArray<FSoftObjectPath> MainPaths =
	{
		LoaderMaterial(TEXT("M_LoadingBars")),
		LoaderMaterial(TEXT("M_LoadingComet")),
		LoaderMaterial(TEXT("M_LoadingDots")),
		LoaderMaterial(TEXT("M_LoadingTimer")),
		FSoftObjectPath(LoadingFXProto::LoaderMissingPath),
		FSoftObjectPath(),
	};
	const TSharedRef<TArray<TWeakObjectPtr<UObject>>> FirstLoadAssets = MakeShared<TArray<TWeakObjectPtr<UObject>>>();

	SequenceSteps.Reset();

	SequenceSteps.Add({ 0.5f, [this, MainPaths]()
	{
		StartLoaderCase(TEXT("1/13 async: 4 materials, a missing path and a null entry"));
		LoaderHandles[0] = LoadAsyncForTest(MainPaths, TEXT("LFXProto.Loader 1"), nullptr, false);
		ReportLoaderState(TEXT("after the call"), LoaderHandles[0], TEXT("active=1 in progress=1, nothing fired inside the call"));
	} });
	SequenceSteps.Add({ 2.0f, [this, FirstLoadAssets]()
	{
		ReportLoaderState(TEXT("2 s later"), LoaderHandles[0], TEXT("active=1 in progress=0 progress=1.00 completed=1: 4 materials, null, null, one warning for the missing path"));
		*FirstLoadAssets = LoaderLoadedAssets;
		CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS, true);
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   after a GC: %d of %d loaded asset(s) still in memory (expect all: the handle keeps them)"),
			Tag, LoadingFXProto::CountAlive(*FirstLoadAssets), FirstLoadAssets->Num());
	} });

	SequenceSteps.Add({ 0.2f, [this]()
	{
		StartLoaderCase(TEXT("2/13 async: a material that is already loaded (held by load 1)"));
		LoaderHandles[1] = LoadAsyncForTest({ LoaderMaterial(TEXT("M_LoadingBars")) }, TEXT("LFXProto.Loader 2"), nullptr, false);
		ReportLoaderState(TEXT("after the call"), LoaderHandles[1], TEXT("in progress=1: it completes on a later frame, not inside the call"));
	} });

	SequenceSteps.Add({ 0.5f, [this, Loader, FirstLoadAssets]()
	{
		StartLoaderCase(TEXT("3/13 release loads 1 and 2, then GC"));
		FLoadingFXLoadHandle StaleCopy = LoaderHandles[0];
		const bool bReleased1 = Loader->Release(LoaderHandles[0]);
		const bool bReleased2 = Loader->Release(LoaderHandles[1]);
		const bool bReleasedStale = Loader->Release(StaleCopy);
		CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS, true);
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   released=%d,%d stale copy=%d; %d of %d asset(s) of load 1 still in memory (expect 1,1 0 with a warning; 0: unloaded)"),
			Tag, bReleased1 ? 1 : 0, bReleased2 ? 1 : 0, bReleasedStale ? 1 : 0, LoadingFXProto::CountAlive(*FirstLoadAssets), FirstLoadAssets->Num());
	} });

	SequenceSteps.Add({ 0.5f, [this]()
	{
		StartLoaderCase(TEXT("4/13 async: empty request"));
		LoaderHandles[0] = LoadAsyncForTest({}, TEXT("LFXProto.Loader 4"), nullptr, false);
	} });

	SequenceSteps.Add({ 0.5f, [this, Loader]()
	{
		ReportLoaderState(TEXT("0.5 s later"), LoaderHandles[0], TEXT("active=1 in progress=0 completed=1: (none), after the call returned (on the next core ticker pass, which can be the same frame)"));
		Loader->Release(LoaderHandles[0]);

		StartLoaderCase(TEXT("5/13 async: release right after the call (cancel)"));
		LoaderHandles[0] = LoadAsyncForTest({ LoaderMaterial(TEXT("M_LoadingSegments")), LoaderMaterial(TEXT("M_LoadingHourglass")) }, TEXT("LFXProto.Loader 5"), nullptr, false);
		Loader->Release(LoaderHandles[0]);
		ReportLoaderState(TEXT("right after the release"), LoaderHandles[0], TEXT("active=0 canceled=1 completed=0"));
	} });
	SequenceSteps.Add({ 1.0f, [this]()
	{
		ReportLoaderState(TEXT("1 s later"), LoaderHandles[0], TEXT("canceled=1 completed=0: no completion after a cancel"));
	} });

	SequenceSteps.Add({ 0.2f, [this]()
	{
		StartLoaderCase(TEXT("6/13 async with an owner actor that is destroyed after the load completes"));
		AActor* Owner = GetWorld() ? GetWorld()->SpawnActor<AActor>() : nullptr;
		LoaderOwner = Owner;
		LoaderHandles[0] = LoadAsyncForTest({ LoaderMaterial(TEXT("M_LoadingDualArc")) }, TEXT("LFXProto.Loader 6"), Owner, false);
	} });
	SequenceSteps.Add({ 1.0f, [this]()
	{
		ReportLoaderState(TEXT("before the owner is destroyed"), LoaderHandles[0], TEXT("active=1 in progress=0 completed=1"));
		if (AActor* Owner = LoaderOwner.Get())
		{
			Owner->Destroy();
		}
	} });
	SequenceSteps.Add({ 0.2f, [this]()
	{
		ReportLoaderState(TEXT("0.2 s after the owner was destroyed"), LoaderHandles[0], TEXT("active=0: released by the owner watch"));
	} });

	SequenceSteps.Add({ 0.5f, [this, Loader]()
	{
		StartLoaderCase(TEXT("7/13 sync without the icon flag, icon not requested"));
		TArray<UObject*> Loaded;
		LoaderHandles[0] = Loader->LoadAssetsSync({ LoaderMaterial(TEXT("M_LoadingBoxes")) }, TEXT("LFXProto.Loader 7"), nullptr, false, Loaded);
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   returned at %.2fs: %s, active=%d (expect M_LoadingBoxes, 1; ended with blocking section=1 MoviePlayer playing=0)"),
			Tag, LoaderCaseSeconds(), *LoadingFXProto::DescribeObjects(Loaded), Loader->IsHandleActive(LoaderHandles[0]) ? 1 : 0);
		Loader->Release(LoaderHandles[0]);
	} });

	SequenceSteps.Add({ 0.5f, [this, Loader, IconSubsystem]()
	{
		StartLoaderCase(TEXT("8/13 sync without the icon flag while the icon is visible, +1.5 s simulated"));
		LoaderIconHandle = LoadingFXProto::AcquireWithoutShowDelay(*IconSubsystem, TEXT("LFXProto.Loader 8"));
		LoaderSimulatedSyncSeconds = 1.5f;
		TArray<UObject*> Loaded;
		LoaderHandles[0] = Loader->LoadAssetsSync({ LoaderMaterial(TEXT("M_LoadingIcon")) }, TEXT("LFXProto.Loader 8"), nullptr, false, Loaded);
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   returned at %.2fs: %s (expect M_LoadingIcon after ~1.5 s; ended with blocking section=1 MoviePlayer playing=1)"),
			Tag, LoaderCaseSeconds(), *LoadingFXProto::DescribeObjects(Loaded));
		IconSubsystem->Release(LoaderIconHandle);
		Loader->Release(LoaderHandles[0]);
	} });

	SequenceSteps.Add({ 0.5f, [this, Loader, IconSubsystem]()
	{
		StartLoaderCase(TEXT("9/13 sync with the icon flag, icon not requested before, +1.5 s simulated"));
		LoaderSimulatedSyncSeconds = 1.5f;
		TArray<UObject*> Loaded;
		LoaderHandles[0] = Loader->LoadAssetsSync({ LoaderMaterial(TEXT("M_LoadingArc")) }, TEXT("LFXProto.Loader 9"), nullptr, true, Loaded);
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   returned at %.2fs: %s, icon visible=%d requests=%d (expect M_LoadingArc; requests=0, the Bridge released its request; ended with blocking section=1 MoviePlayer playing=1 requests=1)"),
			Tag, LoaderCaseSeconds(), *LoadingFXProto::DescribeObjects(Loaded), IconSubsystem->IsIconVisible() ? 1 : 0, IconSubsystem->GetRequestCount());
		Loader->Release(LoaderHandles[0]);
	} });

	SequenceSteps.Add({ 1.0f, [this, IconSubsystem]()
	{
		StartLoaderCase(TEXT("10/13 async with the icon flag"));
		LoaderHandles[0] = LoadAsyncForTest({ LoaderMaterial(TEXT("M_LoadingSegments")) }, TEXT("LFXProto.Loader 10"), nullptr, true);
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   icon requests=%d right after the call (expect 1; 0 by the completion)"), Tag, IconSubsystem->GetRequestCount());
	} });
	SequenceSteps.Add({ 1.0f, [this, Loader]()
	{
		Loader->Release(LoaderHandles[0]);

		StartLoaderCase(TEXT("11/13 Blueprint sync: one asset and two classes (a Blueprint class and a native class)"));
		const TArray<TSoftObjectPtr<UObject>> Assets = { TSoftObjectPtr<UObject>(LoaderMaterial(TEXT("M_LoadingComet"))) };
		const TArray<TSoftClassPtr<UObject>> Classes =
		{
			TSoftClassPtr<UObject>(FSoftObjectPath(LoadingFXProto::LoaderBlueprintClassPath)),
			TSoftClassPtr<UObject>(FSoftObjectPath(AActor::StaticClass())),
		};
		TArray<UObject*> LoadedAssets;
		TArray<UClass*> LoadedClasses;
		LoaderHandles[0] = Loader->K2_LoadAssetsSync(Assets, Classes, TEXT("LFXProto.Loader 11"), this, false, LoadedAssets, LoadedClasses);
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   assets: %s / classes: %s (expect M_LoadingComet / BP_Sky_Sphere_C, Actor)"),
			Tag, *LoadingFXProto::DescribeObjects(LoadedAssets), *LoadingFXProto::DescribeObjects(LoadedClasses));
		Loader->Release(LoaderHandles[0]);
	} });

	SequenceSteps.Add({ 0.5f, [this]()
	{
		StartLoaderCase(TEXT("12/13 Load Assets Async action: one asset and one class, owned by this subsystem"));
		ULoadingFXLoadAssetsAsyncAction* Action = ULoadingFXLoadAssetsAsyncAction::LoadAssetsAsync(GetGameInstance(),
			{ TSoftObjectPtr<UObject>(LoaderMaterial(TEXT("M_LoadingDots"))) },
			{ TSoftClassPtr<UObject>(FSoftObjectPath(LoadingFXProto::LoaderBlueprintClassPath)) },
			TEXT("LFXProto.Loader 12"), this, false);
		Action->OnProgress.AddDynamic(this, &ThisClass::HandleLoaderActionProgress);
		Action->OnCompleted.AddDynamic(this, &ThisClass::HandleLoaderActionCompleted);
		Action->OnCanceled.AddDynamic(this, &ThisClass::HandleLoaderActionCanceled);
		bLoaderInsideCall = true;
		Action->Activate();
		bLoaderInsideCall = false;
	} });

	SequenceSteps.Add({ 1.0f, [this]()
	{
		StartLoaderCase(TEXT("13/13 Load Assets Async action canceled right after activation"));
		ULoadingFXLoadAssetsAsyncAction* Action = ULoadingFXLoadAssetsAsyncAction::LoadAssetsAsync(GetGameInstance(),
			{ TSoftObjectPtr<UObject>(LoaderMaterial(TEXT("M_LoadingHourglass"))) }, {}, TEXT("LFXProto.Loader 13"), this, false);
		Action->OnProgress.AddDynamic(this, &ThisClass::HandleLoaderActionProgress);
		Action->OnCompleted.AddDynamic(this, &ThisClass::HandleLoaderActionCompleted);
		Action->OnCanceled.AddDynamic(this, &ThisClass::HandleLoaderActionCanceled);
		Action->Activate();
		Action->Cancel();
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   right after Cancel: canceled=%d completed=%d active=%d (expect 1, 0, 1: IsActive stays true after SetReadyToDestroy)"),
			Tag, LoaderCanceledCount, LoaderCompletedCount, Action->IsActive() ? 1 : 0);
	} });

	SequenceSteps.Add({ 1.0f, [this, Loader, bQuitWhenDone]()
	{
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   1 s later: canceled=%d completed=%d (expect 1, 0). Active loads (expect one: load 12, owned by this subsystem):"),
			Tag, LoaderCanceledCount, LoaderCompletedCount);
		Loader->DumpLoads();
		Loader->ReleaseAll();
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s   after ReleaseAll (expect none):"), Tag);
		Loader->DumpLoads();

		Loader->OnLoadStartedNative.Remove(LoaderStartedHandle);
		Loader->OnLoadEndedNative.Remove(LoaderEndedHandle);
		LoaderStartedHandle.Reset();
		LoaderEndedHandle.Reset();
		UE_LOG(LogLoadingFXProto, Display, TEXT("%s finished"), Tag);
		if (bQuitWhenDone)
		{
			FPlatformMisc::RequestExit(false, Tag);
		}
	} });

	StartSequence();
}

void ULoadingFXProtoSubsystem::StartLoaderCase(const FString& Description)
{
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader] %s"), *Description);
	LoaderCaseStartSeconds = FPlatformTime::Seconds();
	LoaderCaseStartFrame = GFrameCounter;
	LoaderCompletedCount = 0;
	LoaderCanceledCount = 0;
}

double ULoadingFXProtoSubsystem::LoaderCaseSeconds() const
{
	return FPlatformTime::Seconds() - LoaderCaseStartSeconds;
}

FLoadingFXLoadHandle ULoadingFXProtoSubsystem::LoadAsyncForTest(const TArray<FSoftObjectPath>& Paths, FName Reason, UObject* Owner, bool bShowLoadingIcon)
{
	ULoadingFXLoaderSubsystem* Loader = GetGameInstance()->GetSubsystem<ULoadingFXLoaderSubsystem>();

	bLoaderInsideCall = true;
	const FLoadingFXLoadHandle Handle = Loader->LoadAssetsAsync(Paths, Reason, Owner, bShowLoadingIcon,
		FLoadingFXLoadCompleted::CreateWeakLambda(this, [this, Reason](FLoadingFXLoadHandle, const TArray<UObject*>& LoadedAssets)
		{
			++LoaderCompletedCount;
			LoaderLoadedAssets.Reset();
			for (UObject* Object : LoadedAssets)
			{
				if (Object)
				{
					LoaderLoadedAssets.Add(Object);
				}
			}
			const ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
			UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   '%s' completed at %.2fs (frame +%llu, inside the call=%d): %s; icon requests=%d"),
				*Reason.ToString(), LoaderCaseSeconds(), GFrameCounter - LoaderCaseStartFrame, bLoaderInsideCall ? 1 : 0,
				*LoadingFXProto::DescribeObjects(LoadedAssets), IconSubsystem ? IconSubsystem->GetRequestCount() : -1);
		}),
		FLoadingFXLoadProgressChanged::CreateWeakLambda(this, [this, Reason](FLoadingFXLoadHandle, float Progress)
		{
			UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   '%s' progress %.2f at %.2fs (inside the call=%d)"),
				*Reason.ToString(), Progress, LoaderCaseSeconds(), bLoaderInsideCall ? 1 : 0);
		}),
		FLoadingFXLoadCanceled::CreateWeakLambda(this, [this, Reason](FLoadingFXLoadHandle)
		{
			++LoaderCanceledCount;
			UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   '%s' canceled at %.2fs (inside the call=%d)"),
				*Reason.ToString(), LoaderCaseSeconds(), bLoaderInsideCall ? 1 : 0);
		}));
	bLoaderInsideCall = false;
	return Handle;
}

void ULoadingFXProtoSubsystem::ReportLoaderState(const TCHAR* Step, const FLoadingFXLoadHandle& Handle, const FString& Expect) const
{
	const ULoadingFXLoaderSubsystem* Loader = GetGameInstance()->GetSubsystem<ULoadingFXLoaderSubsystem>();
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   %s at %.2fs: active=%d in progress=%d progress=%.2f completed=%d canceled=%d (expect %s)"),
		Step, LoaderCaseSeconds(), Loader->IsHandleActive(Handle) ? 1 : 0, Loader->IsLoadInProgress(Handle) ? 1 : 0, Loader->GetLoadProgress(Handle),
		LoaderCompletedCount, LoaderCanceledCount, *Expect);
}

void ULoadingFXProtoSubsystem::HandleLoaderLoadStarted(const FLoadingFXLoadInfo& Info)
{
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   '%s' started at %.2fs (sync=%d icon=%d)"),
		*Info.Reason.ToString(), LoaderCaseSeconds(), Info.bSync ? 1 : 0, Info.bShowLoadingIcon ? 1 : 0);
}

void ULoadingFXProtoSubsystem::HandleLoaderLoadEnded(const FLoadingFXLoadInfo& Info)
{
	const ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>();
	const IGameMoviePlayer* MoviePlayer = GetMoviePlayer();
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   '%s' ended at %.2fs (canceled=%d sync=%d): blocking section=%d MoviePlayer playing=%d icon visible=%d requests=%d"),
		*Info.Reason.ToString(), LoaderCaseSeconds(), Info.bCanceled ? 1 : 0, Info.bSync ? 1 : 0,
		IconSubsystem && IconSubsystem->IsInBlockingSection() ? 1 : 0, MoviePlayer && MoviePlayer->IsMovieCurrentlyPlaying() ? 1 : 0,
		IconSubsystem && IconSubsystem->IsIconVisible() ? 1 : 0, IconSubsystem ? IconSubsystem->GetRequestCount() : -1);

	if (Info.bSync && LoaderSimulatedSyncSeconds > 0.0f)
	{
		const float Seconds = LoaderSimulatedSyncSeconds;
		LoaderSimulatedSyncSeconds = 0.0f;
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   simulating +%.1fs of loading inside the sync load (watch the icon)"), Seconds);
		SimulateBlockingWork(Seconds, false);
	}
}

void ULoadingFXProtoSubsystem::HandleLoaderActionProgress(FLoadingFXLoadHandle Handle, float Progress, const TArray<UObject*>& LoadedAssets, const TArray<UClass*>& LoadedClasses)
{
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   action On Progress %.2f at %.2fs (inside Activate=%d)"), Progress, LoaderCaseSeconds(), bLoaderInsideCall ? 1 : 0);
}

void ULoadingFXProtoSubsystem::HandleLoaderActionCompleted(FLoadingFXLoadHandle Handle, float Progress, const TArray<UObject*>& LoadedAssets, const TArray<UClass*>& LoadedClasses)
{
	++LoaderCompletedCount;
	const ULoadingFXLoaderSubsystem* Loader = GetGameInstance()->GetSubsystem<ULoadingFXLoaderSubsystem>();
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   action On Completed at %.2fs: progress %.2f, assets: %s / classes: %s, handle active=%d (expect M_LoadingDots / BP_Sky_Sphere_C, 1)"),
		LoaderCaseSeconds(), Progress, *LoadingFXProto::DescribeObjects(LoadedAssets), *LoadingFXProto::DescribeObjects(LoadedClasses), Loader->IsHandleActive(Handle) ? 1 : 0);
}

void ULoadingFXProtoSubsystem::HandleLoaderActionCanceled(FLoadingFXLoadHandle Handle, float Progress, const TArray<UObject*>& LoadedAssets, const TArray<UClass*>& LoadedClasses)
{
	++LoaderCanceledCount;
	UE_LOG(LogLoadingFXProto, Display, TEXT("[Loader]   action On Canceled at %.2fs: progress %.2f"), LoaderCaseSeconds(), Progress);
}

void ULoadingFXProtoSubsystem::HandleIconVisibilityChanged(bool bVisible)
{
	IconTestEvents.Emplace(bVisible, FPlatformTime::Seconds());
}

void ULoadingFXProtoSubsystem::HandleSyncLoadPackage(const FString& PackageName)
{
	if (PackageName == IconPackageName)
	{
		++IconPackageSyncLoads;
		UE_LOG(LogLoadingFXProto, Display, TEXT("[Preload] sync load of the icon material package %s (#%d)"), *PackageName, IconPackageSyncLoads);
	}
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

	if (bReleaseIconTestInLoadMap)
	{
		// Still inside LoadMap: the core ticker has not run since the load started.
		bReleaseIconTestInLoadMap = false;
		if (ULoadingFXIconSubsystem* IconSubsystem = GetGameInstance()->GetSubsystem<ULoadingFXIconSubsystem>())
		{
			IconSubsystem->Release(IconTestHandle);
			ReportIconCase(TEXT("[ShowDelay]"), TEXT("released in PostLoadMapWithWorld"), IconTestReleaseInLoadMapExpect);
		}
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
