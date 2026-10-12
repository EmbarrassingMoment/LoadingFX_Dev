// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXLoaderSubsystem.h"

#include "LoadingFXLoader.h"
#include "LoadingFXLoaderPaths.h"

#include "Engine/GameInstance.h"
#include "Engine/StreamableManager.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "UObject/SoftObjectPath.h"

namespace LoadingFXLoaderPrivate
{
	/**
	 * The paths to hand to the streamable manager: the non-null ones. It would drop nulls itself, but logs every request
	 * that has one, and an unset entry in a Blueprint array is not worth a log line. Results still follow the request.
	 */
	static TArray<FSoftObjectPath> GetTargets(const TArray<FSoftObjectPath>& Paths)
	{
		return Paths.FilterByPredicate([](const FSoftObjectPath& Path) { return !Path.IsNull(); });
	}
}

#if !UE_BUILD_SHIPPING
namespace LoadingFXLoaderConsole
{
	static FAutoConsoleCommandWithWorld DumpCommand(
		TEXT("LoadingFX.Loader.Dump"),
		TEXT("Logs the active loads of the LoadingFX asset loader."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
			if (const ULoadingFXLoaderSubsystem* Subsystem = GameInstance ? GameInstance->GetSubsystem<ULoadingFXLoaderSubsystem>() : nullptr)
			{
				Subsystem->DumpLoads();
			}
		}));
}
#endif

void ULoadingFXLoaderSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	StreamableManager = MakeShared<FStreamableManager>();
}

void ULoadingFXLoaderSubsystem::Deinitialize()
{
	if (DeferredCompletionTickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(DeferredCompletionTickerHandle);
		DeferredCompletionTickerHandle.Reset();
	}
	DeferredCompletionIds.Reset();

	if (OwnerWatchTickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(OwnerWatchTickerHandle);
		OwnerWatchTickerHandle.Reset();
	}

	// No callbacks or events from here on: whoever listens is shutting down with the game instance too.
	if (Loads.Num() > 0)
	{
		UE_LOG(LogLoadingFXLoader, Log, TEXT("Asset loader shut down with %d active load(s)."), Loads.Num());
		for (FLoad& Load : Loads)
		{
			if (Load.StreamableHandle.IsValid())
			{
				Load.StreamableHandle->CancelHandle();
			}
		}
		Loads.Reset();
	}
	StreamableManager.Reset();

	Super::Deinitialize();
}

FLoadingFXLoadHandle ULoadingFXLoaderSubsystem::LoadAssetsAsync(
	const TArray<FSoftObjectPath>& Paths,
	FName Reason,
	UObject* Owner,
	bool bShowLoadingIcon,
	FLoadingFXLoadCompleted OnCompleted,
	FLoadingFXLoadProgressChanged OnProgressChanged,
	FLoadingFXLoadCanceled OnCanceled)
{
	FLoadingFXLoadHandle Handle;
	if (!CanStartLoad(TEXT("LoadAssetsAsync"), Reason, Owner))
	{
		return Handle;
	}

	FLoad& NewLoad = AddLoad(Paths, Reason, Owner, /*bSync*/ false, bShowLoadingIcon);
	NewLoad.OnCompleted = MoveTemp(OnCompleted);
	NewLoad.OnProgressChanged = MoveTemp(OnProgressChanged);
	NewLoad.OnCanceled = MoveTemp(OnCanceled);
	const int32 Id = NewLoad.Id;
	Handle.Id = Id;

	OnLoadStartedNative.Broadcast(MakeInfo(NewLoad, /*bCanceled*/ false));

	// Look the load up again after anything that may run other code: a listener may have released it, or added loads.
	FLoad* Load = FindLoad(Id);
	if (!Load)
	{
		return Handle;
	}

	TArray<FSoftObjectPath> Targets = LoadingFXLoaderPrivate::GetTargets(Load->Paths);
	TSharedPtr<FStreamableHandle> StreamableHandle;
	if (Targets.Num() > 0)
	{
		// The completion delegate runs inside RequestAsyncLoad when everything is in memory and
		// s.StreamableDelegateDelayFrames is 0; it is deferred then, so no callback runs inside this call.
		Load->bRequesting = true;
		StreamableHandle = StreamableManager->RequestAsyncLoad(
			MoveTemp(Targets),
			FStreamableDelegate::CreateUObject(this, &ThisClass::HandleStreamableCompleted, Id),
			FStreamableManager::DefaultAsyncLoadPriority,
			/*bManageActiveHandle*/ false,
			/*bStartStalled*/ false,
			MakeDebugName(*Load));
		Load = FindLoad(Id);
		if (!Load)
		{
			if (StreamableHandle.IsValid())
			{
				StreamableHandle->CancelHandle();
			}
			return Handle;
		}
		Load->bRequesting = false;
		Load->StreamableHandle = StreamableHandle;
	}

	if (!StreamableHandle.IsValid() || Load->bCompletedDuringRequest)
	{
		// Nothing valid to load (empty, null or malformed paths: the results are all null), or already complete.
		QueueDeferredCompletion(Id);
	}
	else
	{
		StreamableHandle->BindUpdateDelegate(FStreamableUpdateDelegate::CreateUObject(this, &ThisClass::HandleStreamableUpdated, Id));
	}
	return Handle;
}

FLoadingFXLoadHandle ULoadingFXLoaderSubsystem::LoadAssetsSync(
	const TArray<FSoftObjectPath>& Paths,
	FName Reason,
	UObject* Owner,
	bool bShowLoadingIcon,
	TArray<UObject*>& OutLoadedAssets)
{
	// One entry per requested path whatever happens, so callers can index the results.
	OutLoadedAssets.Reset();
	OutLoadedAssets.SetNumZeroed(Paths.Num());

	FLoadingFXLoadHandle Handle;
	if (!CanStartLoad(TEXT("LoadAssetsSync"), Reason, Owner))
	{
		return Handle;
	}

	FLoad& NewLoad = AddLoad(Paths, Reason, Owner, /*bSync*/ true, bShowLoadingIcon);
	const int32 Id = NewLoad.Id;
	Handle.Id = Id;
	const FString DebugName = MakeDebugName(NewLoad);

	// LoadingFXBridge starts the loading icon's blocking section here, before the game thread blocks.
	OnLoadStartedNative.Broadcast(MakeInfo(NewLoad, /*bCanceled*/ false));

	TSharedPtr<FStreamableHandle> StreamableHandle;
	if (const FLoad* Load = FindLoad(Id))
	{
		TArray<FSoftObjectPath> Targets = LoadingFXLoaderPrivate::GetTargets(Load->Paths);
		if (Targets.Num() > 0)
		{
			StreamableHandle = StreamableManager->RequestSyncLoad(MoveTemp(Targets), /*bManageActiveHandle*/ false, FString(DebugName));
		}
	}

	FLoad* Load = FindLoad(Id);
	if (!Load || !Load->bInProgress)
	{
		// Released while it ran (from a listener of OnLoadStartedNative, for example): it was canceled, nothing is kept.
		if (StreamableHandle.IsValid())
		{
			StreamableHandle->ReleaseHandle();
		}
		Handle.Invalidate();
		return Handle;
	}

	Load->StreamableHandle = StreamableHandle;
	Load->bInProgress = false;
	Load->ReportedProgress = 1.0f;
	OutLoadedAssets = ResolveLoadedAssets(*Load);
	UE_LOG(LogLoadingFXLoader, Verbose, TEXT("LoadAssetsSync: load #%d '%s' completed in %.1f ms (%d asset(s))."),
		Id, *Load->Reason.ToString(), (FPlatformTime::Seconds() - Load->StartedAtSeconds) * 1000.0, Load->Paths.Num());

	// LoadingFXBridge ends the blocking section here.
	OnLoadEndedNative.Broadcast(MakeInfo(*Load, /*bCanceled*/ false));
	return Handle;
}

FLoadingFXLoadHandle ULoadingFXLoaderSubsystem::K2_LoadAssetsSync(
	const TArray<TSoftObjectPtr<UObject>>& Assets,
	const TArray<TSoftClassPtr<UObject>>& Classes,
	FName Reason,
	UObject* Owner,
	bool bShowLoadingIcon,
	TArray<UObject*>& LoadedAssets,
	TArray<UClass*>& LoadedClasses)
{
	TArray<UObject*> Loaded;
	const FLoadingFXLoadHandle Handle = LoadAssetsSync(LoadingFXLoaderPaths::MakePaths(Assets, Classes), Reason, Owner, bShowLoadingIcon, Loaded);
	LoadingFXLoaderPaths::SplitLoaded(Loaded, Assets.Num(), LoadedAssets, LoadedClasses);
	return Handle;
}

bool ULoadingFXLoaderSubsystem::Release(FLoadingFXLoadHandle& Handle)
{
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXLoaderSubsystem::Release must be called from the game thread.")))
	{
		return false;
	}

	const bool bReleased = ReleaseInternal(Handle.Id, TEXT("Release"));
	Handle.Invalidate();
	return bReleased;
}

void ULoadingFXLoaderSubsystem::ReleaseAll()
{
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXLoaderSubsystem::ReleaseAll must be called from the game thread.")))
	{
		return;
	}
	if (Loads.Num() == 0)
	{
		return;
	}

	// Only the loads that exist now: callbacks of canceled loads may start new ones.
	TArray<int32, TInlineAllocator<16>> Ids;
	for (const FLoad& Load : Loads)
	{
		Ids.Add(Load.Id);
	}
	UE_LOG(LogLoadingFXLoader, Verbose, TEXT("ReleaseAll: releasing %d load(s)."), Ids.Num());
	for (const int32 Id : Ids)
	{
		ReleaseInternal(Id, TEXT("ReleaseAll"));
	}
}

bool ULoadingFXLoaderSubsystem::IsHandleActive(const FLoadingFXLoadHandle& Handle) const
{
	return FindLoad(Handle.Id) != nullptr;
}

bool ULoadingFXLoaderSubsystem::IsLoadInProgress(const FLoadingFXLoadHandle& Handle) const
{
	const FLoad* Load = FindLoad(Handle.Id);
	return Load && Load->bInProgress;
}

float ULoadingFXLoaderSubsystem::GetLoadProgress(const FLoadingFXLoadHandle& Handle) const
{
	const FLoad* Load = FindLoad(Handle.Id);
	if (!Load)
	{
		return 0.0f;
	}
	if (!Load->bInProgress)
	{
		return 1.0f;
	}
	return Load->StreamableHandle.IsValid() ? Load->StreamableHandle->GetProgress() : Load->ReportedProgress;
}

void ULoadingFXLoaderSubsystem::DumpLoads() const
{
	const double Now = FPlatformTime::Seconds();
	UE_LOG(LogLoadingFXLoader, Display, TEXT("Asset loader: %d active load(s)"), Loads.Num());

	for (const FLoad& Load : Loads)
	{
		FLoadingFXLoadHandle Handle;
		Handle.Id = Load.Id;
		const FString State = Load.bInProgress
			? FString::Printf(TEXT("loading %.0f%%"), GetLoadProgress(Handle) * 100.0f)
			: FString(TEXT("loaded"));

		FString OwnerName = TEXT("-");
		if (Load.bHasOwner)
		{
			OwnerName = Load.Owner.IsValid() ? Load.Owner->GetPathName() : FString(TEXT("<destroyed>"));
		}
		UE_LOG(LogLoadingFXLoader, Display, TEXT("  #%d  %s  %s  %s, %d asset(s)%s  %.1fs  owner: %s"),
			Load.Id, *Load.Reason.ToString(), Load.bSync ? TEXT("sync") : TEXT("async"), *State, Load.Paths.Num(),
			Load.bShowLoadingIcon ? TEXT("  [icon]") : TEXT(""), Now - Load.StartedAtSeconds, *OwnerName);
	}
}

bool ULoadingFXLoaderSubsystem::CanStartLoad(const TCHAR* Context, FName Reason, const UObject* Owner) const
{
	if (!ensureMsgf(IsInGameThread(), TEXT("ULoadingFXLoaderSubsystem::%s must be called from the game thread."), Context))
	{
		return false;
	}
	if (!StreamableManager.IsValid())
	{
		UE_LOG(LogLoadingFXLoader, Warning, TEXT("%s '%s': the asset loader has shut down, nothing was loaded."), Context, *Reason.ToString());
		return false;
	}
	if (Owner && !IsValid(Owner))
	{
		UE_LOG(LogLoadingFXLoader, Warning, TEXT("%s '%s': owner %s is already being destroyed, nothing was loaded."), Context, *Reason.ToString(), *Owner->GetPathName());
		return false;
	}
	return true;
}

ULoadingFXLoaderSubsystem::FLoad& ULoadingFXLoaderSubsystem::AddLoad(const TArray<FSoftObjectPath>& Paths, FName Reason, UObject* Owner, bool bSync, bool bShowLoadingIcon)
{
	FLoad& Load = Loads.AddDefaulted_GetRef();
	Load.Id = NextLoadId++;
	if (NextLoadId <= 0)
	{
		NextLoadId = 1;
	}
	Load.Reason = Reason;
	Load.Paths = Paths;
	Load.Owner = Owner;
	Load.bHasOwner = Owner != nullptr;
	Load.bSync = bSync;
	Load.bShowLoadingIcon = bShowLoadingIcon;
	Load.StartedAtSeconds = FPlatformTime::Seconds();

	UE_LOG(LogLoadingFXLoader, Verbose, TEXT("%s: load #%d '%s', %d asset(s)%s%s%s (%d active)."),
		bSync ? TEXT("LoadAssetsSync") : TEXT("LoadAssetsAsync"), Load.Id, *Reason.ToString(), Paths.Num(),
		bShowLoadingIcon ? TEXT(", with the loading icon") : TEXT(""),
		Owner ? TEXT(", owned by ") : TEXT(""), Owner ? *Owner->GetPathName() : TEXT(""), Loads.Num());

	if (Load.bHasOwner && !OwnerWatchTickerHandle.IsValid())
	{
		OwnerWatchTickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &ThisClass::TickOwnerWatch));
	}
	return Load;
}

ULoadingFXLoaderSubsystem::FLoad* ULoadingFXLoaderSubsystem::FindLoad(int32 Id)
{
	return Id != 0 ? Loads.FindByPredicate([Id](const FLoad& Load) { return Load.Id == Id; }) : nullptr;
}

const ULoadingFXLoaderSubsystem::FLoad* ULoadingFXLoaderSubsystem::FindLoad(int32 Id) const
{
	return Id != 0 ? Loads.FindByPredicate([Id](const FLoad& Load) { return Load.Id == Id; }) : nullptr;
}

FLoadingFXLoadInfo ULoadingFXLoaderSubsystem::MakeInfo(const FLoad& Load, bool bCanceled) const
{
	FLoadingFXLoadInfo Info;
	Info.Handle.Id = Load.Id;
	Info.Reason = Load.Reason;
	Info.bSync = Load.bSync;
	Info.bShowLoadingIcon = Load.bShowLoadingIcon;
	Info.bCanceled = bCanceled;
	return Info;
}

FString ULoadingFXLoaderSubsystem::MakeDebugName(const FLoad& Load) const
{
	return FString::Printf(TEXT("LoadingFX #%d %s"), Load.Id, *Load.Reason.ToString());
}

void ULoadingFXLoaderSubsystem::HandleStreamableCompleted(int32 Id)
{
	FLoad* Load = FindLoad(Id);
	if (!Load || !Load->bInProgress)
	{
		return;
	}
	if (Load->bRequesting)
	{
		Load->bCompletedDuringRequest = true;
		return;
	}
	CompleteLoad(Id);
}

void ULoadingFXLoaderSubsystem::HandleStreamableUpdated(TSharedRef<FStreamableHandle> StreamableHandle, int32 Id)
{
	const FLoad* Load = FindLoad(Id);
	if (Load && Load->bInProgress)
	{
		ReportProgress(Id, StreamableHandle->GetProgress());
	}
}

void ULoadingFXLoaderSubsystem::ReportProgress(int32 Id, float Progress)
{
	FLoad* Load = FindLoad(Id);
	if (!Load || Progress <= Load->ReportedProgress)
	{
		return;
	}
	Load->ReportedProgress = Progress;

	// A copy: the callback may add loads, which moves the array.
	const FLoadingFXLoadProgressChanged Callback = Load->OnProgressChanged;
	FLoadingFXLoadHandle Handle;
	Handle.Id = Id;
	Callback.ExecuteIfBound(Handle, Progress);
}

void ULoadingFXLoaderSubsystem::CompleteLoad(int32 Id)
{
	// The last progress report (1) comes first, so a progress bar needs nothing but the progress callback. The engine
	// only reports progress before the last asset finishes.
	ReportProgress(Id, 1.0f);

	FLoad* Load = FindLoad(Id);
	if (!Load || !Load->bInProgress)
	{
		// Released from the progress callback: it was canceled there.
		return;
	}
	Load->bInProgress = false;

	const TArray<UObject*> LoadedAssets = ResolveLoadedAssets(*Load);
	const FLoadingFXLoadCompleted Callback = MoveTemp(Load->OnCompleted);
	Load->OnCompleted.Unbind();
	Load->OnProgressChanged.Unbind();
	Load->OnCanceled.Unbind();
	const FLoadingFXLoadInfo Info = MakeInfo(*Load, /*bCanceled*/ false);
	UE_LOG(LogLoadingFXLoader, Verbose, TEXT("LoadAssetsAsync: load #%d '%s' completed in %.1f ms (%d asset(s))."),
		Id, *Load->Reason.ToString(), (FPlatformTime::Seconds() - Load->StartedAtSeconds) * 1000.0, Load->Paths.Num());

	OnLoadEndedNative.Broadcast(Info);
	Callback.ExecuteIfBound(Info.Handle, LoadedAssets);
}

TArray<UObject*> ULoadingFXLoaderSubsystem::ResolveLoadedAssets(const FLoad& Load) const
{
	TArray<UObject*> LoadedAssets;
	LoadedAssets.Reserve(Load.Paths.Num());
	TArray<FString> Failed;
	for (const FSoftObjectPath& Path : Load.Paths)
	{
		// ResolveObject follows redirectors, as the streamable manager does when it loads them.
		UObject* Object = Path.IsNull() ? nullptr : Path.ResolveObject();
		if (!Object && !Path.IsNull())
		{
			Failed.Add(Path.ToString());
		}
		LoadedAssets.Add(Object);
	}

	if (Failed.Num() > 0)
	{
		UE_LOG(LogLoadingFXLoader, Warning, TEXT("Load #%d '%s': %d of %d asset(s) could not be loaded (missing, not cooked, or a malformed path): %s"),
			Load.Id, *Load.Reason.ToString(), Failed.Num(), Load.Paths.Num(), *FString::Join(Failed, TEXT(", ")));
	}
	return LoadedAssets;
}

void ULoadingFXLoaderSubsystem::QueueDeferredCompletion(int32 Id)
{
	DeferredCompletionIds.AddUnique(Id);
	if (!DeferredCompletionTickerHandle.IsValid())
	{
		DeferredCompletionTickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &ThisClass::TickDeferredCompletions));
	}
}

bool ULoadingFXLoaderSubsystem::TickDeferredCompletions(float /*DeltaTime*/)
{
	// Callbacks may queue more: those wait for the next tick.
	const TArray<int32> Ids = MoveTemp(DeferredCompletionIds);
	DeferredCompletionIds.Reset();
	DeferredCompletionTickerHandle.Reset();

	for (const int32 Id : Ids)
	{
		const FLoad* Load = FindLoad(Id);
		if (Load && Load->bInProgress)
		{
			CompleteLoad(Id);
		}
	}

	// A new ticker was added if more were queued meanwhile; this one is done.
	return false;
}

bool ULoadingFXLoaderSubsystem::ReleaseInternal(int32 Id, const TCHAR* Context)
{
	const int32 Index = Loads.IndexOfByPredicate([Id](const FLoad& Load) { return Load.Id == Id; });
	if (Index == INDEX_NONE)
	{
		if (Id != 0)
		{
			UE_LOG(LogLoadingFXLoader, Warning, TEXT("%s: load #%d is not active (released twice, or a stale copy of the handle)."), Context, Id);
		}
		return false;
	}

	FLoad Removed = MoveTemp(Loads[Index]);
	Loads.RemoveAt(Index);

	if (Removed.StreamableHandle.IsValid())
	{
		// CancelHandle also drops a completion callback that is already queued for a later frame.
		if (Removed.bInProgress)
		{
			Removed.StreamableHandle->CancelHandle();
		}
		else
		{
			Removed.StreamableHandle->ReleaseHandle();
		}
	}

	if (!Removed.bInProgress)
	{
		UE_LOG(LogLoadingFXLoader, Verbose, TEXT("%s: released load #%d '%s' (%d left)."), Context, Id, *Removed.Reason.ToString(), Loads.Num());
		return true;
	}

	UE_LOG(LogLoadingFXLoader, Verbose, TEXT("%s: canceled load #%d '%s' at %.0f%% (%d left)."),
		Context, Id, *Removed.Reason.ToString(), Removed.ReportedProgress * 100.0f, Loads.Num());
	const FLoadingFXLoadInfo Info = MakeInfo(Removed, /*bCanceled*/ true);
	OnLoadEndedNative.Broadcast(Info);
	Removed.OnCanceled.ExecuteIfBound(Info.Handle);
	return true;
}

bool ULoadingFXLoaderSubsystem::TickOwnerWatch(float /*DeltaTime*/)
{
	TArray<int32, TInlineAllocator<8>> Expired;
	for (const FLoad& Load : Loads)
	{
		if (Load.bHasOwner && !Load.Owner.IsValid())
		{
			Expired.Add(Load.Id);
		}
	}
	for (const int32 Id : Expired)
	{
		ReleaseInternal(Id, TEXT("Owner destroyed"));
	}

	// Keep ticking only while some load still has an owner to watch. ReleaseInternal may have run callbacks that
	// started new owned loads, which found this ticker still registered.
	const bool bKeepTicking = Loads.ContainsByPredicate([](const FLoad& Load) { return Load.bHasOwner; });
	if (!bKeepTicking)
	{
		OwnerWatchTickerHandle.Reset();
	}
	return bKeepTicking;
}
