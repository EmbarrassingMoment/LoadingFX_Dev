// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXIconSubsystem.h"

#include "LoadingFX.h"
#include "LoadingFXSettings.h"
#include "SLoadingFXSpinner.h"

#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "MaterialDomain.h"
#include "Materials/Material.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CoreDelegates.h"
#include "Misc/CoreMisc.h"
#include "MoviePlayer.h"
#include "Styling/CoreStyle.h"
#include "UObject/SoftObjectPath.h"
#include "UObject/UObjectGlobals.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SOverlay.h"

#if !UE_BUILD_SHIPPING
namespace LoadingFXIconConsole
{
	static ULoadingFXIconSubsystem* FindSubsystem(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? GameInstance->GetSubsystem<ULoadingFXIconSubsystem>() : nullptr;
	}

	static FAutoConsoleCommandWithWorldAndArgs ShowCommand(
		TEXT("LoadingFX.Icon.Show"),
		TEXT("Shows the loading icon with a console-owned request; each call adds one. Args: [Reason]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXIconSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->ConsoleShow(Args.IsValidIndex(0) ? FName(*Args[0]) : FName(TEXT("Console")));
			}
		}));

	static FAutoConsoleCommandWithWorldAndArgs HideCommand(
		TEXT("LoadingFX.Icon.Hide"),
		TEXT("Releases the newest console-owned request, or every request with 'all'."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULoadingFXIconSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->ConsoleHide(Args.Contains(TEXT("all")));
			}
		}));

	static FAutoConsoleCommandWithWorld DumpCommand(
		TEXT("LoadingFX.Icon.Dump"),
		TEXT("Logs the active loading icon requests."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (ULoadingFXIconSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->DumpRequests();
			}
		}));
}
#endif

bool ULoadingFXIconSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	return !IsRunningDedicatedServer() && !IsRunningCommandlet() && Super::ShouldCreateSubsystem(Outer);
}

void ULoadingFXIconSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	PreloadIconMaterial();

	// In a standalone game the viewport is created after the game instance (UGameEngine::Init), so a request
	// made during startup has to wait for it.
	ViewportCreatedHandle = UGameViewportClient::OnViewportCreated().AddUObject(this, &ThisClass::HandleViewportCreated);

	// PlayMovie() broadcasts this when nobody has set up a loading screen: from MoviePlayer's own PreLoadMap hook,
	// or from a manual PlayMovie() around a sync load. Binding here rather than to PreLoadMap (whose call order
	// against MoviePlayer is not guaranteed) lets the icon take over exactly when it is visible.
	if (IGameMoviePlayer* MoviePlayer = GetMoviePlayer())
	{
		PrepareLoadingScreenHandle = MoviePlayer->OnPrepareLoadingScreen().AddUObject(this, &ThisClass::HandlePrepareLoadingScreen);
	}

	if (!IsMoviePlayerEnabled())
	{
		UE_LOG(LogLoadingFX, Log, TEXT("MoviePlayer is unavailable in this process (editor/PIE, commandlet or -NoLoadingScreen): the loading icon will not animate during blocking loads."));
	}
}

void ULoadingFXIconSubsystem::Deinitialize()
{
	if (IGameMoviePlayer* MoviePlayer = GetMoviePlayer())
	{
		MoviePlayer->OnPrepareLoadingScreen().Remove(PrepareLoadingScreenHandle);
	}
	PrepareLoadingScreenHandle.Reset();
	UGameViewportClient::OnViewportCreated().Remove(ViewportCreatedHandle);
	ViewportCreatedHandle.Reset();

	if (OwnerWatchTickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(OwnerWatchTickerHandle);
		OwnerWatchTickerHandle.Reset();
	}

	if (Requests.Num() > 0)
	{
		UE_LOG(LogLoadingFX, Log, TEXT("Loading icon subsystem shut down with %d active request(s)."), Requests.Num());
		Requests.Reset();
	}
	ConsoleHandles.Reset();
	CancelPendingShow();
	CancelPendingHide();
	bIconVisible = false;
	HideViewportIcon();

	// A load request cannot be cancelled: its completion is ignored from now on.
	bIconMaterialPreloadPending = false;
	IconMaterialPreloadRequestId = INDEX_NONE;

	if (BlockingSectionDepth > 0)
	{
		UE_LOG(LogLoadingFX, Log, TEXT("Loading icon subsystem shut down inside blocking section '%s'."), *BlockingSectionReason.ToString());
		BlockingSectionDepth = 0;
		bBlockingSectionPlaysMovie = false;
		FCoreDelegates::OnEndFrame.Remove(BlockingSectionEndFrameHandle);
		BlockingSectionEndFrameHandle.Reset();
	}

	Super::Deinitialize();
}

FLoadingFXIconHandle ULoadingFXIconSubsystem::Acquire(FName Reason, UObject* Owner)
{
	FLoadingFXIconHandle Handle;
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXIconSubsystem::Acquire must be called from the game thread.")))
	{
		return Handle;
	}
	if (Owner && !IsValid(Owner))
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("Acquire '%s': owner %s is already being destroyed, no request was made."), *Reason.ToString(), *Owner->GetPathName());
		return Handle;
	}

	FRequest& Request = Requests.AddDefaulted_GetRef();
	Request.Id = NextRequestId++;
	if (NextRequestId <= 0)
	{
		NextRequestId = 1;
	}
	Request.Reason = Reason;
	Request.Owner = Owner;
	Request.bHasOwner = Owner != nullptr;
	Request.AcquiredAtSeconds = FPlatformTime::Seconds();
	Handle.Id = Request.Id;

	UE_LOG(LogLoadingFX, Verbose, TEXT("Acquire: loading icon request #%d '%s'%s%s (%d active)."),
		Request.Id, *Reason.ToString(), Owner ? TEXT(" owned by ") : TEXT(""), Owner ? *Owner->GetPathName() : TEXT(""), Requests.Num());

	if (Request.bHasOwner && !OwnerWatchTickerHandle.IsValid())
	{
		OwnerWatchTickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &ThisClass::TickOwnerWatch));
	}

	if (Requests.Num() == 1)
	{
		if (bIconVisible)
		{
			// Still on screen for the minimum display time after the last release: it just stays.
			CancelPendingHide();
		}
		else
		{
			// Read at every first request, so a value changed in the editor applies to the next one.
			const double ShowDelay = FMath::Max(GetDefault<ULoadingFXSettings>()->IconShowDelay, 0.0f);
			if (ShowDelay > 0.0)
			{
				PendingShowAtSeconds = Request.AcquiredAtSeconds + ShowDelay;
				if (!PendingShowTickerHandle.IsValid())
				{
					PendingShowTickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &ThisClass::TickPendingShow));
				}
			}
			else
			{
				ShowIcon(Request.AcquiredAtSeconds);
			}
		}
	}
	return Handle;
}

bool ULoadingFXIconSubsystem::Release(FLoadingFXIconHandle& Handle)
{
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXIconSubsystem::Release must be called from the game thread.")))
	{
		return false;
	}

	const bool bReleased = ReleaseInternal(Handle.Id, TEXT("Release"));
	Handle.Invalidate();
	return bReleased;
}

void ULoadingFXIconSubsystem::ReleaseAll()
{
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXIconSubsystem::ReleaseAll must be called from the game thread.")))
	{
		return;
	}
	if (Requests.Num() == 0)
	{
		return;
	}

	UE_LOG(LogLoadingFX, Verbose, TEXT("ReleaseAll: dropping %d loading icon request(s)."), Requests.Num());
	Requests.Reset();
	HandleLastRelease();
}

bool ULoadingFXIconSubsystem::IsHandleActive(const FLoadingFXIconHandle& Handle) const
{
	return Handle.IsValid() && Requests.ContainsByPredicate([&Handle](const FRequest& Request) { return Request.Id == Handle.Id; });
}

void ULoadingFXIconSubsystem::DumpRequests() const
{
	const double Now = FPlatformTime::Seconds();
	FString State = IsIconVisible() ? TEXT("visible") : TEXT("hidden");
	if (PendingShowTickerHandle.IsValid())
	{
		State += FString::Printf(TEXT(" (show delay, appears in %.2fs)"), FMath::Max(PendingShowAtSeconds - Now, 0.0));
	}
	if (PendingHideTickerHandle.IsValid())
	{
		State += FString::Printf(TEXT(" (minimum display time, hides in %.2fs)"), FMath::Max(PendingHideAtSeconds - Now, 0.0));
	}
	UE_LOG(LogLoadingFX, Display, TEXT("Loading icon: %s, %d active request(s)"), *State, Requests.Num());

	for (const FRequest& Request : Requests)
	{
		FString OwnerName = TEXT("-");
		if (Request.bHasOwner)
		{
			OwnerName = Request.Owner.IsValid() ? Request.Owner->GetPathName() : FString(TEXT("<destroyed>"));
		}
		UE_LOG(LogLoadingFX, Display, TEXT("  #%d  %s  %.1fs  owner: %s"), Request.Id, *Request.Reason.ToString(), Now - Request.AcquiredAtSeconds, *OwnerName);
	}
}

void ULoadingFXIconSubsystem::ConsoleShow(FName Reason)
{
	const FLoadingFXIconHandle Handle = Acquire(Reason);
	if (Handle.IsValid())
	{
		ConsoleHandles.Add(Handle);
	}
	DumpRequests();
}

void ULoadingFXIconSubsystem::ConsoleHide(bool bAll)
{
	if (bAll)
	{
		ReleaseAll();
		ConsoleHandles.Reset();
	}
	else if (ConsoleHandles.Num() > 0)
	{
		FLoadingFXIconHandle Handle = ConsoleHandles.Pop();
		Release(Handle);
	}
	else
	{
		UE_LOG(LogLoadingFX, Display, TEXT("No console-owned loading icon request to release (use 'LoadingFX.Icon.Hide all' for the others)."));
	}
	DumpRequests();
}

bool ULoadingFXIconSubsystem::ReleaseInternal(int32 Id, const TCHAR* Context)
{
	const int32 Index = Requests.IndexOfByPredicate([Id](const FRequest& Request) { return Request.Id == Id; });
	if (Index == INDEX_NONE)
	{
		if (Id != 0)
		{
			UE_LOG(LogLoadingFX, Warning, TEXT("%s: loading icon request #%d is not active (released twice, or a stale copy of the handle)."), Context, Id);
		}
		return false;
	}

	const FRequest Removed = Requests[Index];
	Requests.RemoveAt(Index);
	UE_LOG(LogLoadingFX, Verbose, TEXT("%s: released loading icon request #%d '%s' (%d left)."), Context, Removed.Id, *Removed.Reason.ToString(), Requests.Num());

	if (Requests.Num() == 0)
	{
		HandleLastRelease();
	}
	return true;
}

void ULoadingFXIconSubsystem::NotifyVisibilityChanged(bool bVisible)
{
	OnVisibilityChangedNative.Broadcast(bVisible);
	OnVisibilityChanged.Broadcast(bVisible);
}

void ULoadingFXIconSubsystem::HandleLastRelease()
{
	if (PendingShowTickerHandle.IsValid())
	{
		if (FPlatformTime::Seconds() < PendingShowAtSeconds)
		{
			// Released within the show delay: the icon never appears.
			CancelPendingShow();
			return;
		}

		// The delay is over but the ticker has not run since, because the game thread was blocked (for example a
		// release from BeginPlay inside LoadMap). The icon has been on the loading screen since then, so it counts
		// as shown from that moment and gets the rest of its minimum display time.
		ShowIcon(PendingShowAtSeconds);
		if (Requests.Num() > 0)
		{
			// Acquired again from OnVisibilityChanged.
			return;
		}
	}
	HideAfterMinimumDisplayTime();
}

void ULoadingFXIconSubsystem::ShowIcon(double ShownAtSeconds)
{
	CancelPendingShow();
	bIconVisible = true;
	IconShownAtSeconds = ShownAtSeconds;
	ShowViewportIcon();
	NotifyVisibilityChanged(true);
}

void ULoadingFXIconSubsystem::CancelPendingShow()
{
	if (PendingShowTickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(PendingShowTickerHandle);
		PendingShowTickerHandle.Reset();
	}
}

bool ULoadingFXIconSubsystem::TickPendingShow(float /*DeltaTime*/)
{
	if (FPlatformTime::Seconds() < PendingShowAtSeconds)
	{
		return true;
	}

	// Reset before showing, so ShowIcon does not remove the ticker that is running now. The display time counts
	// from the end of the delay rather than from now: after a blocking load the icon has been on the loading screen
	// since then.
	PendingShowTickerHandle.Reset();
	ShowIcon(PendingShowAtSeconds);
	return false;
}

void ULoadingFXIconSubsystem::HideAfterMinimumDisplayTime()
{
	// Read at every release, so a value changed in the editor applies to the next one.
	const double MinimumDisplayTime = FMath::Max(GetDefault<ULoadingFXSettings>()->IconMinimumDisplayTime, 0.0f);
	PendingHideAtSeconds = IconShownAtSeconds + MinimumDisplayTime;
	const double Now = FPlatformTime::Seconds();
	if (Now >= PendingHideAtSeconds)
	{
		HideIcon();
		return;
	}

	UE_LOG(LogLoadingFX, Verbose, TEXT("Last loading icon request released after %.2fs: keeping the icon for another %.2fs (minimum display time)."),
		Now - IconShownAtSeconds, PendingHideAtSeconds - Now);

	// The core ticker, not a world timer: it keeps running while the game is paused and across map travel.
	if (!PendingHideTickerHandle.IsValid())
	{
		PendingHideTickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &ThisClass::TickPendingHide));
	}
}

void ULoadingFXIconSubsystem::HideIcon()
{
	CancelPendingHide();
	bIconVisible = false;
	HideViewportIcon();
	NotifyVisibilityChanged(false);
}

void ULoadingFXIconSubsystem::CancelPendingHide()
{
	if (PendingHideTickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(PendingHideTickerHandle);
		PendingHideTickerHandle.Reset();
	}
}

bool ULoadingFXIconSubsystem::TickPendingHide(float /*DeltaTime*/)
{
	// Compared with the platform clock rather than summing DeltaTime: the time a blocking load took counts too.
	if (FPlatformTime::Seconds() < PendingHideAtSeconds)
	{
		return true;
	}

	// Reset before hiding, so HideIcon does not remove the ticker that is running now.
	PendingHideTickerHandle.Reset();
	HideIcon();
	return false;
}

void ULoadingFXIconSubsystem::PreloadIconMaterial()
{
	const TSoftObjectPtr<UMaterialInterface>& MaterialPtr = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial;
	if (MaterialPtr.IsNull())
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("LoadingIconMaterial is not set (Project Settings > Plugins > LoadingFX): the loading icon has nothing to draw."));
		return;
	}

	// Already in memory (in the editor, or loaded by something else): nothing to wait for.
	if (UMaterialInterface* LoadedMaterial = MaterialPtr.Get())
	{
		SetIconMaterial(LoadedMaterial, MaterialPtr.ToSoftObjectPath());
		return;
	}

	// Loading a UI-domain material also starts precaching its PSOs (UMaterial::PostLoad, collected by Slate), so
	// the load and the PSO compiles both happen now rather than when the icon has to appear. The flag is set
	// first because the delegate may run before LoadAsync returns, for a path that cannot be loaded at all.
	bIconMaterialPreloadPending = true;
	IconMaterialPreloadStartSeconds = FPlatformTime::Seconds();
	const int32 RequestId = MaterialPtr.ToSoftObjectPath().LoadAsync(
		FLoadSoftObjectPathAsyncDelegate::CreateUObject(this, &ThisClass::HandleIconMaterialPreloaded));
	if (bIconMaterialPreloadPending)
	{
		IconMaterialPreloadRequestId = RequestId;
		UE_LOG(LogLoadingFX, Verbose, TEXT("Preloading the loading icon material %s (request %d)."), *MaterialPtr.ToString(), RequestId);
	}
}

void ULoadingFXIconSubsystem::HandleIconMaterialPreloaded(const FSoftObjectPath& MaterialPath, UObject* LoadedObject)
{
	if (!bIconMaterialPreloadPending)
	{
		// The subsystem was deinitialized meanwhile.
		return;
	}
	bIconMaterialPreloadPending = false;
	IconMaterialPreloadRequestId = INDEX_NONE;

	UMaterialInterface* LoadedMaterial = Cast<UMaterialInterface>(LoadedObject);
	if (LoadedMaterial)
	{
		UE_LOG(LogLoadingFX, Log, TEXT("Preloaded the loading icon material %s (ready %.1f ms after the request)."),
			*MaterialPath.ToString(), (FPlatformTime::Seconds() - IconMaterialPreloadStartSeconds) * 1000.0);
	}
	SetIconMaterial(LoadedMaterial, MaterialPath);
}

void ULoadingFXIconSubsystem::SetIconMaterial(UMaterialInterface* Material, const FSoftObjectPath& MaterialPath)
{
	IconMaterial = Material;
	if (!IconMaterial)
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("LoadingIconMaterial %s could not be loaded as a material (missing, not cooked, or another asset type): the loading icon has nothing to draw."), *MaterialPath.ToString());
		return;
	}

	const UMaterial* BaseMaterial = IconMaterial->GetMaterial();
	if (BaseMaterial && BaseMaterial->MaterialDomain != MD_UI)
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("LoadingIconMaterial %s is not a User Interface domain material: Slate cannot draw it."), *MaterialPath.ToString());
	}
	CompileIconMaterialShaders();
}

void ULoadingFXIconSubsystem::CompileIconMaterialShaders()
{
#if WITH_EDITOR
	// Uncooked processes (the editor's -game, or a standalone game run from the editor binaries) compile a material's
	// shaders when it is first drawn, and only the game thread takes the results in. If that first draw is on
	// MoviePlayer's loading thread while the game thread is blocked, the icon stays blank until the load is over, so
	// the shaders are compiled here instead. Cooked builds load every shader with the material (EnsureIsComplete does
	// nothing there), and without MoviePlayer (editor, PIE) every draw is on the game thread.
	if (!IconMaterial || !IsMoviePlayerEnabled())
	{
		return;
	}
	const double StartSeconds = FPlatformTime::Seconds();
	IconMaterial->EnsureIsComplete();
	const double Milliseconds = (FPlatformTime::Seconds() - StartSeconds) * 1000.0;
	UE_CLOG(Milliseconds >= 1.0, LogLoadingFX, Log, TEXT("Compiled the shaders of the loading icon material %s in %.1f ms, so that MoviePlayer can draw it during blocking loads (uncooked builds compile shaders on first use)."),
		*IconMaterial->GetPathName(), Milliseconds);
#endif
}

UMaterialInterface* ULoadingFXIconSubsystem::GetIconMaterial()
{
	if (bIconMaterialPreloadPending)
	{
		// Needed before the preload finished (an Acquire right at startup, or a blocking load that starts that
		// early). Wait for that one request rather than show the icon late: the wait is at most what is left of
		// loading one small package, and the flush runs the completion delegate.
		const double WaitStartSeconds = FPlatformTime::Seconds();
		if (IconMaterialPreloadRequestId != INDEX_NONE)
		{
			FlushAsyncLoading(IconMaterialPreloadRequestId);
		}
		if (bIconMaterialPreloadPending)
		{
			// No request id to wait for, or the loader did not report back: load it here instead.
			bIconMaterialPreloadPending = false;
			IconMaterialPreloadRequestId = INDEX_NONE;
			const TSoftObjectPtr<UMaterialInterface>& MaterialPtr = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial;
			SetIconMaterial(MaterialPtr.LoadSynchronous(), MaterialPtr.ToSoftObjectPath());
		}
		UE_LOG(LogLoadingFX, Log, TEXT("The loading icon material was needed before its preload finished: waited %.1f ms for it."),
			(FPlatformTime::Seconds() - WaitStartSeconds) * 1000.0);
	}
	return IconMaterial;
}

TSharedRef<SWidget> ULoadingFXIconSubsystem::MakeIconWidget(double ShowAtSeconds)
{
	const ULoadingFXSettings* Settings = GetDefault<ULoadingFXSettings>();

	TAttribute<EVisibility> Visibility = EVisibility::HitTestInvisible;
	if (ShowAtSeconds > FPlatformTime::Seconds())
	{
		// Evaluated in MoviePlayer's Slate prepass on its loading thread while the game thread is blocked, so the
		// lambda reads only what it copied.
		const TSharedRef<bool> bAppeared = MakeShared<bool>(false);
		Visibility = TAttribute<EVisibility>::CreateLambda([ShowAtSeconds, bAppeared]()
		{
			if (FPlatformTime::Seconds() < ShowAtSeconds)
			{
				return EVisibility::Hidden;
			}
			if (!*bAppeared)
			{
				*bAppeared = true;
				UE_LOG(LogLoadingFX, Log, TEXT("The show delay ended during a blocking load: the loading icon appears on the loading screen."));
			}
			return EVisibility::HitTestInvisible;
		});
	}

	return SNew(SBox)
		.HAlign(Settings->IconHorizontalAlignment)
		.VAlign(Settings->IconVerticalAlignment)
		.Padding(Settings->IconPadding)
		.Visibility(Visibility)
		[
			SNew(SLoadingFXSpinner)
			.Material(GetIconMaterial())
			.Size(Settings->IconSize)
			.ColorAndOpacity(Settings->IconTint)
		];
}

TSharedRef<SWidget> ULoadingFXIconSubsystem::MakeLoadingScreenWidget(double ShowAtSeconds)
{
	// MoviePlayer paints its root black and puts this widget over the whole screen, so a full-screen color here
	// replaces the black. It stays outside the icon's show-delay visibility: the screen changes the moment MoviePlayer
	// takes over, as the black did. Opaque, because nothing but that black is left underneath.
	const FLinearColor BackgroundColor = GetDefault<ULoadingFXSettings>()->LoadingScreenBackgroundColor.CopyWithNewOpacity(1.0f);

	return SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SImage)
			.Image(FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")))
			.ColorAndOpacity(BackgroundColor)
		]
		+ SOverlay::Slot()
		[
			MakeIconWidget(ShowAtSeconds)
		];
}

void ULoadingFXIconSubsystem::ShowViewportIcon()
{
	if (ViewportIconRoot.IsValid())
	{
		return;
	}

	UGameViewportClient* ViewportClient = GetGameInstance() ? GetGameInstance()->GetGameViewportClient() : nullptr;
	if (!ViewportClient)
	{
		// Not created yet (HandleViewportCreated retries), or no viewport in this process.
		return;
	}
	if (!GetIconMaterial())
	{
		return;
	}

	// Viewport content, not AddToViewport: UMG widgets added to the viewport are removed on world teardown,
	// viewport content stays through LoadMap.
	ViewportIconRoot = MakeIconWidget();
	ViewportClient->AddViewportWidgetContent(ViewportIconRoot.ToSharedRef(), GetDefault<ULoadingFXSettings>()->IconZOrder);
	ViewportIconClient = ViewportClient;
}

void ULoadingFXIconSubsystem::HideViewportIcon()
{
	if (ViewportIconRoot.IsValid())
	{
		if (UGameViewportClient* ViewportClient = ViewportIconClient.Get())
		{
			ViewportClient->RemoveViewportWidgetContent(ViewportIconRoot.ToSharedRef());
		}
	}
	ViewportIconRoot.Reset();
	ViewportIconClient.Reset();
}

void ULoadingFXIconSubsystem::HandleViewportCreated()
{
	if (IsIconVisible())
	{
		ShowViewportIcon();
	}
}

void ULoadingFXIconSubsystem::HandlePrepareLoadingScreen()
{
	// v1 scope: take over the loading screen only while the icon is visible or requested. Showing it, and deciding
	// when the travel is over, stays with the caller.
	SetUpIconLoadingScreen(TEXT("the blocking load"));
}

bool ULoadingFXIconSubsystem::SetUpIconLoadingScreen(const FString& What)
{
	// Visible includes the minimum display time after the last release (the icon is on screen then, and would freeze
	// there for the whole load otherwise). Requested includes the show delay after the first request (the icon then
	// appears on the loading screen when the delay is over, as it would in the game).
	const bool bShowPending = PendingShowTickerHandle.IsValid();
	if ((!IsIconVisible() && !bShowPending) || !GetIconMaterial())
	{
		return false;
	}

	IGameMoviePlayer* MoviePlayer = GetMoviePlayer();
	if (!MoviePlayer || MoviePlayer->LoadingScreenIsPrepared())
	{
		// Someone else set up a loading screen first: leave it alone.
		return false;
	}

	// Done when the material arrived; this catches a material that became incomplete since (a new quality level).
	CompileIconMaterialShaders();

	// MoviePlayer needs its own widget instance: the viewport one keeps its parent. The attributes are cleared
	// by MoviePlayer after every playback, so this runs again for the next load.
	FLoadingScreenAttributes Attributes;
	Attributes.WidgetLoadingScreen = MakeLoadingScreenWidget(bShowPending ? PendingShowAtSeconds : 0.0);
	Attributes.bAutoCompleteWhenLoadingCompletes = true;
	Attributes.bMoviesAreSkippable = false;
	Attributes.bWaitForManualStop = false;
	Attributes.MinimumLoadingScreenDisplayTime = -1.0f;
	MoviePlayer->SetupLoadingScreen(Attributes);

	if (bShowPending)
	{
		UE_LOG(LogLoadingFX, Log, TEXT("Loading icon is requested (%d request(s)) and appears in %.2fs (show delay): rendering %s through MoviePlayer."),
			Requests.Num(), FMath::Max(PendingShowAtSeconds - FPlatformTime::Seconds(), 0.0), *What);
	}
	else
	{
		UE_LOG(LogLoadingFX, Log, TEXT("Loading icon is visible (%d request(s)): rendering %s through MoviePlayer."), Requests.Num(), *What);
	}
	return true;
}

void ULoadingFXIconSubsystem::BeginBlockingSection(FName Reason)
{
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXIconSubsystem::BeginBlockingSection must be called from the game thread.")))
	{
		return;
	}
	if (BlockingSectionDepth++ > 0)
	{
		UE_LOG(LogLoadingFX, Verbose, TEXT("BeginBlockingSection '%s': nested in '%s' (depth %d)."), *Reason.ToString(), *BlockingSectionReason.ToString(), BlockingSectionDepth);
		return;
	}
	BlockingSectionReason = Reason;
	BlockingSectionStartSeconds = FPlatformTime::Seconds();
	bBlockingSectionPlaysMovie = false;
	BlockingSectionEndFrameHandle = FCoreDelegates::OnEndFrame.AddUObject(this, &ThisClass::HandleEndFrameInBlockingSection);

	if (!IsIconVisible() && !PendingShowTickerHandle.IsValid())
	{
		UE_LOG(LogLoadingFX, Verbose, TEXT("BeginBlockingSection '%s': the loading icon is not requested, so nothing takes over."), *Reason.ToString());
		return;
	}

	IGameMoviePlayer* MoviePlayer = GetMoviePlayer();
	if (!MoviePlayer || !IsMoviePlayerEnabled())
	{
		// Logged at Initialize: the icon freezes for the section.
		return;
	}
	if (MoviePlayer->IsMovieCurrentlyPlaying())
	{
		// A loading screen is already drawing (a sync load inside LoadMap, for example): it covers the section.
		UE_LOG(LogLoadingFX, Verbose, TEXT("BeginBlockingSection '%s': MoviePlayer is already playing."), *Reason.ToString());
		return;
	}

	// Set up here rather than through PlayMovie's OnPrepareLoadingScreen broadcast, which would also ask every other
	// listener (a project's own loading screen for map travel, for example) to set one up for this section.
	if (!SetUpIconLoadingScreen(FString::Printf(TEXT("blocking section '%s'"), *Reason.ToString())))
	{
		return;
	}

	bBlockingSectionPlaysMovie = MoviePlayer->PlayMovie();
	if (!bBlockingSectionPlaysMovie)
	{
		// Do not leave the screen set up for the next map load.
		MoviePlayer->SetupLoadingScreen(FLoadingScreenAttributes());
		UE_LOG(LogLoadingFX, Warning, TEXT("BeginBlockingSection '%s': MoviePlayer did not start, so the loading icon freezes for this section."), *Reason.ToString());
	}
}

void ULoadingFXIconSubsystem::EndBlockingSection()
{
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXIconSubsystem::EndBlockingSection must be called from the game thread.")))
	{
		return;
	}
	if (BlockingSectionDepth <= 0)
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("EndBlockingSection without a matching BeginBlockingSection."));
		return;
	}
	if (--BlockingSectionDepth > 0)
	{
		return;
	}
	FCoreDelegates::OnEndFrame.Remove(BlockingSectionEndFrameHandle);
	BlockingSectionEndFrameHandle.Reset();

	if (bBlockingSectionPlaysMovie)
	{
		bBlockingSectionPlaysMovie = false;
		if (IGameMoviePlayer* MoviePlayer = GetMoviePlayer())
		{
			// Returns once the loading thread has stopped drawing; the game viewport draws again from the next frame.
			MoviePlayer->WaitForMovieToFinish();
		}
		UE_LOG(LogLoadingFX, Log, TEXT("Blocking section '%s' ended after %.2fs: MoviePlayer stopped."),
			*BlockingSectionReason.ToString(), FPlatformTime::Seconds() - BlockingSectionStartSeconds);
	}
	BlockingSectionReason = NAME_None;
}

void ULoadingFXIconSubsystem::HandleEndFrameInBlockingSection()
{
	// Work that blocks the game thread is over by the end of the frame, so a section still open here was never ended: a
	// Blueprint path that skips End Blocking Section, or a Delay before it. Left open, it would make every later section a
	// nested one that takes nothing over. MoviePlayer started in the engine tick has already stopped (the engine loop
	// waits for it right after the tick); started later in the frame, it is still playing and stops here.
	UE_LOG(LogLoadingFX, Warning, TEXT("Blocking section '%s' was not ended in the frame it began (depth %d): ending it now. Call EndBlockingSection in the same frame, right after the blocking work."),
		*BlockingSectionReason.ToString(), BlockingSectionDepth);
	BlockingSectionDepth = 1;
	EndBlockingSection();
}

bool ULoadingFXIconSubsystem::TickOwnerWatch(float /*DeltaTime*/)
{
	TArray<int32, TInlineAllocator<8>> Expired;
	for (const FRequest& Request : Requests)
	{
		if (Request.bHasOwner && !Request.Owner.IsValid())
		{
			Expired.Add(Request.Id);
		}
	}
	for (const int32 Id : Expired)
	{
		ReleaseInternal(Id, TEXT("Owner destroyed"));
	}

	// Keep ticking only while some request still has an owner to watch.
	const bool bKeepTicking = Requests.ContainsByPredicate([](const FRequest& Request) { return Request.bHasOwner; });
	if (!bKeepTicking)
	{
		OwnerWatchTickerHandle.Reset();
	}
	return bKeepTicking;
}

FLoadingFXBlockingScope::FLoadingFXBlockingScope(const UObject* WorldContextObject, FName Reason)
{
	const UGameInstance* GameInstance = Cast<UGameInstance>(WorldContextObject);
	if (!GameInstance && WorldContextObject && GEngine)
	{
		const UWorld* World = GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull);
		GameInstance = World ? World->GetGameInstance() : nullptr;
	}

	if (ULoadingFXIconSubsystem* Found = GameInstance ? GameInstance->GetSubsystem<ULoadingFXIconSubsystem>() : nullptr)
	{
		Subsystem = Found;
		Found->BeginBlockingSection(Reason);
	}
}

FLoadingFXBlockingScope::~FLoadingFXBlockingScope()
{
	if (ULoadingFXIconSubsystem* Found = Subsystem.Get())
	{
		Found->EndBlockingSection();
	}
}
