// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Engine/CancellableAsyncAction.h"
#include "LoadingFXLoaderSubsystem.h"
#include "UObject/SoftObjectPtr.h"
#include "LoadingFXLoadAssetsAsyncAction.generated.h"

/**
 * The output pins of Load Assets Async, shared by every exec output (the node takes them from the first delegate).
 * LoadedAssets and LoadedClasses are filled on On Completed only.
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_FourParams(FLoadingFXLoadAssetsAsyncEvent,
	FLoadingFXLoadHandle, Handle,
	float, Progress,
	const TArray<UObject*>&, LoadedAssets,
	const TArray<UClass*>&, LoadedClasses);

/**
 * The Load Assets Async Blueprint node: loads soft object and soft class references in the background through
 * ULoadingFXLoaderSubsystem, reporting progress, and returns this action so the load can be canceled.
 *
 * The assets stay loaded after On Completed until Release Loaded Assets is called with the handle, or until Owner (by
 * default the calling object) is destroyed. Cancel only affects a load in flight; once it has completed, release it
 * instead.
 */
UCLASS(MinimalAPI)
class ULoadingFXLoadAssetsAsyncAction : public UCancellableAsyncAction
{
	GENERATED_BODY()

public:
	/**
	 * Starts loading Assets and Classes in the background.
	 * On Progress fires as each requested asset finishes (Progress is finished / requested), On Completed once all of
	 * them have loaded or failed (LoadedAssets and LoadedClasses in request order, null where a load failed), and
	 * On Canceled if the load is canceled or released first.
	 * With Show Loading Icon, the loading icon is shown while the load runs.
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (BlueprintInternalUseOnly = "true", DisplayName = "Load Assets Async", WorldContext = "WorldContextObject", DefaultToSelf = "Owner", AutoCreateRefTerm = "Assets,Classes"))
	static LOADINGFXLOADER_API ULoadingFXLoadAssetsAsyncAction* LoadAssetsAsync(
		UObject* WorldContextObject,
		const TArray<TSoftObjectPtr<UObject>>& Assets,
		const TArray<TSoftClassPtr<UObject>>& Classes,
		FName Reason,
		UObject* Owner,
		bool bShowLoadingIcon);

	/** One more requested asset has finished. */
	UPROPERTY(BlueprintAssignable)
	FLoadingFXLoadAssetsAsyncEvent OnProgress;

	/** Every requested asset has loaded or failed. */
	UPROPERTY(BlueprintAssignable)
	FLoadingFXLoadAssetsAsyncEvent OnCompleted;

	/** The load was canceled or released before it finished. */
	UPROPERTY(BlueprintAssignable)
	FLoadingFXLoadAssetsAsyncEvent OnCanceled;

	//~ Begin UCancellableAsyncAction Interface
	virtual void Activate() override;
	virtual void Cancel() override;
	//~ End UCancellableAsyncAction Interface

private:
	/** The loader of the game instance this action is registered with. */
	ULoadingFXLoaderSubsystem* GetLoaderSubsystem() const;

	void HandleProgressChanged(FLoadingFXLoadHandle InHandle, float Progress);
	void HandleCompleted(FLoadingFXLoadHandle InHandle, const TArray<UObject*>& LoadedObjects);
	void HandleCanceled(FLoadingFXLoadHandle InHandle);
	void FinishCanceled();

	/** Assets first, then Classes. */
	TArray<FSoftObjectPath> Paths;
	int32 NumAssets = 0;
	FName Reason;
	TWeakObjectPtr<UObject> Owner;
	bool bHasOwner = false;
	bool bShowLoadingIcon = false;

	FLoadingFXLoadHandle Handle;
	float LastProgress = 0.0f;
};
