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
	HideViewportIcon();

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
		ShowViewportIcon();
		NotifyVisibilityChanged(true);
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
	HideViewportIcon();
	NotifyVisibilityChanged(false);
}

bool ULoadingFXIconSubsystem::IsHandleActive(const FLoadingFXIconHandle& Handle) const
{
	return Handle.IsValid() && Requests.ContainsByPredicate([&Handle](const FRequest& Request) { return Request.Id == Handle.Id; });
}

void ULoadingFXIconSubsystem::DumpRequests() const
{
	UE_LOG(LogLoadingFX, Display, TEXT("Loading icon: %s, %d active request(s)"), IsIconVisible() ? TEXT("visible") : TEXT("hidden"), Requests.Num());

	const double Now = FPlatformTime::Seconds();
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
		HideViewportIcon();
		NotifyVisibilityChanged(false);
	}
	return true;
}

void ULoadingFXIconSubsystem::NotifyVisibilityChanged(bool bVisible)
{
	OnVisibilityChangedNative.Broadcast(bVisible);
	OnVisibilityChanged.Broadcast(bVisible);
}

UMaterialInterface* ULoadingFXIconSubsystem::GetIconMaterial()
{
	if (IconMaterial || bIconMaterialLoadAttempted)
	{
		return IconMaterial;
	}
	bIconMaterialLoadAttempted = true;

	const TSoftObjectPtr<UMaterialInterface>& MaterialPtr = GetDefault<ULoadingFXSettings>()->LoadingIconMaterial;
	if (MaterialPtr.IsNull())
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("LoadingIconMaterial is not set (Project Settings > Plugins > LoadingFX): the loading icon has nothing to draw."));
		return nullptr;
	}

	IconMaterial = MaterialPtr.LoadSynchronous();
	if (!IconMaterial)
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("LoadingIconMaterial %s could not be loaded (missing, or not cooked): the loading icon has nothing to draw."), *MaterialPtr.ToString());
		return nullptr;
	}

	const UMaterial* BaseMaterial = IconMaterial->GetMaterial();
	if (BaseMaterial && BaseMaterial->MaterialDomain != MD_UI)
	{
		UE_LOG(LogLoadingFX, Warning, TEXT("LoadingIconMaterial %s is not a User Interface domain material: Slate cannot draw it."), *MaterialPtr.ToString());
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
	// travel is over, stays with the caller.
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
