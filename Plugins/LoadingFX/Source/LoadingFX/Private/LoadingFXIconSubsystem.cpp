// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXIconSubsystem.h"

#include "LoadingFX.h"
#include "LoadingFXSettings.h"
#include "SLoadingFXSpinner.h"

#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "MaterialDomain.h"
#include "Materials/Material.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CoreMisc.h"
#include "MoviePlayer.h"
#include "UObject/SoftObjectPath.h"
#include "UObject/UObjectGlobals.h"
#include "Widgets/Layout/SBox.h"

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
	CancelPendingHide();
	bIconVisible = false;
	HideViewportIcon();

	// A load request cannot be cancelled: its completion is ignored from now on.
	bIconMaterialPreloadPending = false;
	IconMaterialPreloadRequestId = INDEX_NONE;

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
			bIconVisible = true;
			IconShownAtSeconds = Request.AcquiredAtSeconds;
			ShowViewportIcon();
			NotifyVisibilityChanged(true);
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
	HideAfterMinimumDisplayTime();
}

bool ULoadingFXIconSubsystem::IsHandleActive(const FLoadingFXIconHandle& Handle) const
{
	return Handle.IsValid() && Requests.ContainsByPredicate([&Handle](const FRequest& Request) { return Request.Id == Handle.Id; });
}

void ULoadingFXIconSubsystem::DumpRequests() const
{
	const double Now = FPlatformTime::Seconds();
	FString State = IsIconVisible() ? TEXT("visible") : TEXT("hidden");
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
		HideAfterMinimumDisplayTime();
	}
	return true;
}

void ULoadingFXIconSubsystem::NotifyVisibilityChanged(bool bVisible)
{
	OnVisibilityChangedNative.Broadcast(bVisible);
	OnVisibilityChanged.Broadcast(bVisible);
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

TSharedRef<SWidget> ULoadingFXIconSubsystem::MakeIconWidget()
{
	const ULoadingFXSettings* Settings = GetDefault<ULoadingFXSettings>();
	return SNew(SBox)
		.HAlign(Settings->IconHorizontalAlignment)
		.VAlign(Settings->IconVerticalAlignment)
		.Padding(Settings->IconPadding)
		.Visibility(EVisibility::HitTestInvisible)
		[
			SNew(SLoadingFXSpinner)
			.Material(GetIconMaterial())
			.Size(Settings->IconSize)
			.ColorAndOpacity(Settings->IconTint)
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
	// v1 scope: take over the loading screen only while the icon is visible. Showing it, and deciding when the
	// travel is over, stays with the caller. That includes the minimum display time after the last release: the
	// icon is on screen then, and would freeze there for the whole load otherwise.
	if (!IsIconVisible() || !GetIconMaterial())
	{
		return;
	}

	IGameMoviePlayer* MoviePlayer = GetMoviePlayer();
	if (!MoviePlayer || MoviePlayer->LoadingScreenIsPrepared())
	{
		// Someone else answered this broadcast first: leave their loading screen alone.
		return;
	}

	// MoviePlayer needs its own widget instance: the viewport one keeps its parent. The attributes are cleared
	// by MoviePlayer after every playback, so this runs again for the next load.
	FLoadingScreenAttributes Attributes;
	Attributes.WidgetLoadingScreen = MakeIconWidget();
	Attributes.bAutoCompleteWhenLoadingCompletes = true;
	Attributes.bMoviesAreSkippable = false;
	Attributes.bWaitForManualStop = false;
	Attributes.MinimumLoadingScreenDisplayTime = -1.0f;
	MoviePlayer->SetupLoadingScreen(Attributes);

	UE_LOG(LogLoadingFX, Log, TEXT("Loading icon is visible (%d request(s)): rendering the blocking load through MoviePlayer."), Requests.Num());
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
