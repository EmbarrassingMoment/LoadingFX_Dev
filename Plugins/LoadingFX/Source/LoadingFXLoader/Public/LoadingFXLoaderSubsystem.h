// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Templates/SharedPointer.h"
#include "UObject/SoftObjectPtr.h"
#include "UObject/WeakObjectPtr.h"
#include "LoadingFXLoaderSubsystem.generated.h"

struct FStreamableHandle;
struct FStreamableManager;

/**
 * Identifies one load made with ULoadingFXLoaderSubsystem. Its assets stay in memory until the handle is released
 * (Release), or until the load's owner is destroyed.
 * IsValid() only says whether the handle was issued and not released through this copy; ask the subsystem
 * (IsHandleActive) whether the load is still held.
 */
USTRUCT(BlueprintType)
struct LOADINGFXLOADER_API FLoadingFXLoadHandle
{
	GENERATED_BODY()

	bool IsValid() const { return Id != 0; }
	void Invalidate() { Id = 0; }

	bool operator==(const FLoadingFXLoadHandle& Other) const { return Id == Other.Id; }
	bool operator!=(const FLoadingFXLoadHandle& Other) const { return Id != Other.Id; }

private:
	friend class ULoadingFXLoaderSubsystem;

	/** 0 is never issued. */
	UPROPERTY()
	int32 Id = 0;
};

/** What OnLoadStartedNative and OnLoadEndedNative report about a load. */
struct FLoadingFXLoadInfo
{
	FLoadingFXLoadHandle Handle;
	FName Reason;

	/** True for LoadAssetsSync: the game thread is blocked from OnLoadStartedNative until OnLoadEndedNative. */
	bool bSync = false;

	/** The request's bShowLoadingIcon. The loader does nothing with it; LoadingFXBridge shows the loading icon for it. */
	bool bShowLoadingIcon = false;

	/** OnLoadEndedNative only: true if the load was released before it finished, false if it completed. */
	bool bCanceled = false;
};

/** LoadAssetsAsync: every requested asset has loaded or failed. LoadedAssets is in request order, null where a load failed. */
DECLARE_DELEGATE_TwoParams(FLoadingFXLoadCompleted, FLoadingFXLoadHandle /*Handle*/, const TArray<UObject*>& /*LoadedAssets*/);

/** LoadAssetsAsync: one more requested asset has finished. Progress is finished / requested, 0 to 1. */
DECLARE_DELEGATE_TwoParams(FLoadingFXLoadProgressChanged, FLoadingFXLoadHandle /*Handle*/, float /*Progress*/);

/** LoadAssetsAsync: the load was released before it finished (Release, ReleaseAll, or its owner was destroyed). */
DECLARE_DELEGATE_OneParam(FLoadingFXLoadCanceled, FLoadingFXLoadHandle /*Handle*/);

/** OnLoadStartedNative / OnLoadEndedNative. */
DECLARE_MULTICAST_DELEGATE_OneParam(FLoadingFXLoadEventNative, const FLoadingFXLoadInfo& /*Info*/);

/**
 * Loads assets asynchronously (with progress and cancel) or synchronously, and keeps them in memory until the load is
 * released.
 *
 * Every load returns a handle, and its assets stay referenced until Release(Handle) or ReleaseAll. A load that names an
 * owner is also released once that object is destroyed; the Blueprint nodes default the owner to the calling object,
 * so assets loaded from a Blueprint go away with it. To keep assets longer, pass a longer-lived owner (the game
 * instance, for example) and release by hand. Releasing a load that is still in flight cancels it: its completion
 * callback never fires, although packages already being read finish loading.
 *
 * Progress counts requested assets: the number that have finished divided by the number requested. A request for one
 * asset goes from 0 straight to 1, and an asset's own dependencies are not counted. The engine reports nothing finer.
 *
 * bShowLoadingIcon asks for the loading icon while the load runs. This module has no UI: LoadingFXBridge acts on the
 * flag through OnLoadStartedNative / OnLoadEndedNative. Without the flag, a sync load still keeps a loading icon that
 * is already requested animating.
 *
 * Blueprint: the Load Assets Async node (ULoadingFXLoadAssetsAsyncAction) and Load Assets Sync.
 *
 * Game thread only.
 */
UCLASS()
class LOADINGFXLOADER_API ULoadingFXLoaderSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	//~ Begin USubsystem Interface
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	//~ End USubsystem Interface

	/**
	 * Starts loading Paths in the background and returns the handle of this load.
	 * OnCompleted fires once every asset has loaded or failed, OnProgressChanged as each one finishes, and OnCanceled
	 * if the load is released first. None of them fires inside this call, even when everything is already in memory.
	 * Reason is for logs and LoadingFX.Loader.Dump. With an Owner, the load is released when Owner is destroyed.
	 */
	FLoadingFXLoadHandle LoadAssetsAsync(
		const TArray<FSoftObjectPath>& Paths,
		FName Reason,
		UObject* Owner,
		bool bShowLoadingIcon,
		FLoadingFXLoadCompleted OnCompleted,
		FLoadingFXLoadProgressChanged OnProgressChanged = FLoadingFXLoadProgressChanged(),
		FLoadingFXLoadCanceled OnCanceled = FLoadingFXLoadCanceled());

	/**
	 * Loads Paths now, blocking the game thread, and returns the handle of this load. OutLoadedAssets receives the
	 * assets in request order, null where a load failed.
	 * With bShowLoadingIcon, the loading icon is shown and keeps animating through the load on a black screen
	 * (MoviePlayer), even if the load is short; without it, only an icon that is already requested keeps animating.
	 * Reason is for logs and LoadingFX.Loader.Dump. With an Owner, the load is released when Owner is destroyed.
	 */
	FLoadingFXLoadHandle LoadAssetsSync(
		const TArray<FSoftObjectPath>& Paths,
		FName Reason,
		UObject* Owner,
		bool bShowLoadingIcon,
		TArray<UObject*>& OutLoadedAssets);

	/**
	 * Loads Assets and Classes now, blocking the game thread, and returns the handle of this load. LoadedAssets and
	 * LoadedClasses are in request order, null where a load failed.
	 * With Show Loading Icon, the loading icon is shown and keeps animating through the load on a black screen, even if
	 * the load is short; without it, only an icon that is already requested keeps animating.
	 * The assets stay loaded until Release Loaded Assets, or until Owner (by default the calling object) is destroyed.
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Load Assets Sync", DefaultToSelf = "Owner", AutoCreateRefTerm = "Assets,Classes"))
	FLoadingFXLoadHandle K2_LoadAssetsSync(
		const TArray<TSoftObjectPtr<UObject>>& Assets,
		const TArray<TSoftClassPtr<UObject>>& Classes,
		FName Reason,
		UObject* Owner,
		bool bShowLoadingIcon,
		TArray<UObject*>& LoadedAssets,
		TArray<UClass*>& LoadedClasses);

	/**
	 * Releases a load and invalidates the handle, so its assets can be unloaded by the next garbage collection unless
	 * something else references them. A load still in flight is canceled. Returns false if the handle was not active.
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Release Loaded Assets"))
	bool Release(UPARAM(ref) FLoadingFXLoadHandle& Handle);

	/** Releases every load, whoever made it, canceling those still in flight. For recovery paths such as returning to the main menu. */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Release All Loaded Assets"))
	void ReleaseAll();

	/** True if the handle refers to a load that has not been released yet, whether it is still loading or done. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	bool IsHandleActive(const FLoadingFXLoadHandle& Handle) const;

	/** True while the load is still in flight. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	bool IsLoadInProgress(const FLoadingFXLoadHandle& Handle) const;

	/** Finished requested assets / requested assets, 0 to 1 (1 once complete). 0 for a handle that is not active. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	float GetLoadProgress(const FLoadingFXLoadHandle& Handle) const;

	/**
	 * Fires when any load starts. For a sync load it fires right before the game thread blocks; listeners that want to
	 * draw during the load must set that up here (LoadingFXBridge starts the icon's blocking section).
	 */
	FLoadingFXLoadEventNative OnLoadStartedNative;

	/** Fires when any load completes, or is released while still in flight (Info.bCanceled). Releasing a completed load fires nothing. */
	FLoadingFXLoadEventNative OnLoadEndedNative;

	/** Logs the active loads (LoadingFX.Loader.Dump). */
	void DumpLoads() const;

private:
	struct FLoad
	{
		int32 Id = 0;
		FName Reason;
		/** As requested, so results come back in request order (only non-null paths are requested, and the streamable manager drops duplicates). */
		TArray<FSoftObjectPath> Paths;
		TWeakObjectPtr<const UObject> Owner;
		bool bHasOwner = false;
		bool bSync = false;
		bool bShowLoadingIcon = false;
		/** True until the load completes; a load released before that is canceled. */
		bool bInProgress = true;
		/** True while RequestAsyncLoad runs, so a completion that comes back inside it is deferred. */
		bool bRequesting = false;
		bool bCompletedDuringRequest = false;
		float ReportedProgress = 0.0f;
		double StartedAtSeconds = 0.0;
		/** Keeps the loaded assets referenced. Null if there was nothing valid to load. */
		TSharedPtr<FStreamableHandle> StreamableHandle;
		FLoadingFXLoadCompleted OnCompleted;
		FLoadingFXLoadProgressChanged OnProgressChanged;
		FLoadingFXLoadCanceled OnCanceled;
	};

	/** Checks what every load needs (game thread, an initialized subsystem, an owner that is not being destroyed). */
	bool CanStartLoad(const TCHAR* Context, FName Reason, const UObject* Owner) const;
	FLoad& AddLoad(const TArray<FSoftObjectPath>& Paths, FName Reason, UObject* Owner, bool bSync, bool bShowLoadingIcon);
	FLoad* FindLoad(int32 Id);
	const FLoad* FindLoad(int32 Id) const;
	FLoadingFXLoadInfo MakeInfo(const FLoad& Load, bool bCanceled) const;
	FString MakeDebugName(const FLoad& Load) const;

	void HandleStreamableCompleted(int32 Id);
	void HandleStreamableUpdated(TSharedRef<FStreamableHandle> StreamableHandle, int32 Id);
	void ReportProgress(int32 Id, float Progress);
	void CompleteLoad(int32 Id);
	/** The loaded asset of each requested path, in request order (null where a load failed). Warns once about failures. */
	TArray<UObject*> ResolveLoadedAssets(const FLoad& Load) const;

	/** Completes a load on the next tick of the core ticker instead of now (see LoadAssetsAsync). */
	void QueueDeferredCompletion(int32 Id);
	bool TickDeferredCompletions(float DeltaTime);

	bool ReleaseInternal(int32 Id, const TCHAR* Context);
	bool TickOwnerWatch(float DeltaTime);

	/** Separate from the AssetManager's, so this subsystem's handles are its own. */
	TSharedPtr<FStreamableManager> StreamableManager;

	TArray<FLoad> Loads;
	int32 NextLoadId = 1;

	/** Registered only while some completion waits for the next tick. */
	TArray<int32> DeferredCompletionIds;
	FTSTicker::FDelegateHandle DeferredCompletionTickerHandle;

	/** Registered only while some load has an owner to watch. */
	FTSTicker::FDelegateHandle OwnerWatchTickerHandle;
};
