// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXLoadAssetsAsyncAction.h"

#include "LoadingFXLoader.h"
#include "LoadingFXLoaderPaths.h"

#include "Engine/GameInstance.h"

ULoadingFXLoadAssetsAsyncAction* ULoadingFXLoadAssetsAsyncAction::LoadAssetsAsync(
	UObject* WorldContextObject,
	const TArray<TSoftObjectPtr<UObject>>& Assets,
	const TArray<TSoftClassPtr<UObject>>& Classes,
	FName Reason,
	UObject* Owner,
	bool bShowLoadingIcon)
{
	ULoadingFXLoadAssetsAsyncAction* Action = NewObject<ULoadingFXLoadAssetsAsyncAction>();
	Action->Paths = LoadingFXLoaderPaths::MakePaths(Assets, Classes);
	Action->NumAssets = Assets.Num();
	Action->Reason = Reason;
	Action->Owner = Owner;
	Action->bHasOwner = Owner != nullptr;
	Action->bShowLoadingIcon = bShowLoadingIcon;

	// Keeps the action alive until it finishes, even if the calling Blueprint goes away first.
	Action->RegisterWithGameInstance(WorldContextObject);
	return Action;
}

void ULoadingFXLoadAssetsAsyncAction::Activate()
{
	ULoadingFXLoaderSubsystem* Subsystem = GetLoaderSubsystem();
	if (!Subsystem)
	{
		UE_LOG(LogLoadingFXLoader, Warning, TEXT("Load Assets Async '%s': no game instance to load with (the world context has none), nothing was loaded."), *Reason.ToString());
		FinishCanceled();
		return;
	}

	// The owner was valid when the node ran; it can only be gone now if it was destroyed in between.
	UObject* OwnerObject = Owner.Get();
	if (bHasOwner && !OwnerObject)
	{
		UE_LOG(LogLoadingFXLoader, Warning, TEXT("Load Assets Async '%s': the owner was destroyed before the load started, nothing was loaded."), *Reason.ToString());
		FinishCanceled();
		return;
	}

	Handle = Subsystem->LoadAssetsAsync(Paths, Reason, OwnerObject, bShowLoadingIcon,
		FLoadingFXLoadCompleted::CreateUObject(this, &ThisClass::HandleCompleted),
		FLoadingFXLoadProgressChanged::CreateUObject(this, &ThisClass::HandleProgressChanged),
		FLoadingFXLoadCanceled::CreateUObject(this, &ThisClass::HandleCanceled));
	if (!Handle.IsValid())
	{
		// The loader refused it and logged why.
		FinishCanceled();
	}
}

void ULoadingFXLoadAssetsAsyncAction::Cancel()
{
	// Only a load in flight is canceled (On Canceled fires from the release). A completed load stays loaded with its
	// handle. Not while this action is being garbage collected: nothing may run Blueprint code then, and the load
	// still has its owner.
	if (!HasAnyFlags(RF_BeginDestroyed))
	{
		ULoadingFXLoaderSubsystem* Subsystem = GetLoaderSubsystem();
		if (Subsystem && Subsystem->IsLoadInProgress(Handle))
		{
			FLoadingFXLoadHandle HandleToRelease = Handle;
			Subsystem->Release(HandleToRelease);
		}
	}

	Super::Cancel();
}

ULoadingFXLoaderSubsystem* ULoadingFXLoadAssetsAsyncAction::GetLoaderSubsystem() const
{
	const UGameInstance* GameInstance = RegisteredWithGameInstance.Get();
	return GameInstance ? GameInstance->GetSubsystem<ULoadingFXLoaderSubsystem>() : nullptr;
}

void ULoadingFXLoadAssetsAsyncAction::HandleProgressChanged(FLoadingFXLoadHandle InHandle, float Progress)
{
	LastProgress = Progress;
	if (ShouldBroadcastDelegates())
	{
		OnProgress.Broadcast(InHandle, Progress, TArray<UObject*>(), TArray<UClass*>());
	}
}

void ULoadingFXLoadAssetsAsyncAction::HandleCompleted(FLoadingFXLoadHandle InHandle, const TArray<UObject*>& LoadedObjects)
{
	if (ShouldBroadcastDelegates())
	{
		TArray<UObject*> LoadedAssets;
		TArray<UClass*> LoadedClasses;
		LoadingFXLoaderPaths::SplitLoaded(LoadedObjects, NumAssets, LoadedAssets, LoadedClasses);
		OnCompleted.Broadcast(InHandle, 1.0f, LoadedAssets, LoadedClasses);
	}
	SetReadyToDestroy();
}

void ULoadingFXLoadAssetsAsyncAction::HandleCanceled(FLoadingFXLoadHandle InHandle)
{
	if (ShouldBroadcastDelegates())
	{
		OnCanceled.Broadcast(InHandle, LastProgress, TArray<UObject*>(), TArray<UClass*>());
	}
	SetReadyToDestroy();
}

void ULoadingFXLoadAssetsAsyncAction::FinishCanceled()
{
	HandleCanceled(FLoadingFXLoadHandle());
}
