// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "LoadingFXBridgeSubsystem.h"

#include "LoadingFXBridge.h"

#include "Misc/CoreMisc.h"
#include "Subsystems/SubsystemCollection.h"

bool ULoadingFXBridgeSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	// Same rule as the icon subsystem: without it there is nothing to forward to.
	return !IsRunningDedicatedServer() && !IsRunningCommandlet() && Super::ShouldCreateSubsystem(Outer);
}

void ULoadingFXBridgeSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	IconSubsystem = Collection.InitializeDependency<ULoadingFXIconSubsystem>();
	LoaderSubsystem = Collection.InitializeDependency<ULoadingFXLoaderSubsystem>();
	if (ULoadingFXLoaderSubsystem* Loader = LoaderSubsystem.Get())
	{
		LoadStartedHandle = Loader->OnLoadStartedNative.AddUObject(this, &ThisClass::HandleLoadStarted);
		LoadEndedHandle = Loader->OnLoadEndedNative.AddUObject(this, &ThisClass::HandleLoadEnded);
	}
}

void ULoadingFXBridgeSubsystem::Deinitialize()
{
	if (ULoadingFXLoaderSubsystem* Loader = LoaderSubsystem.Get())
	{
		Loader->OnLoadStartedNative.Remove(LoadStartedHandle);
		Loader->OnLoadEndedNative.Remove(LoadEndedHandle);
	}
	LoadStartedHandle.Reset();
	LoadEndedHandle.Reset();

	// Not released or ended: the icon subsystem is shutting down with the same game instance.
	IconRequests.Reset();
	BlockingLoads.Reset();

	Super::Deinitialize();
}

void ULoadingFXBridgeSubsystem::HandleLoadStarted(const FLoadingFXLoadInfo& Info)
{
	ULoadingFXIconSubsystem* Icon = IconSubsystem.Get();
	const ULoadingFXLoaderSubsystem* Loader = LoaderSubsystem.Get();

	// Multicast delegates run their listeners in reverse order of binding, so one bound later may already have released
	// the load (and its end has been broadcast) before this runs.
	if (!Icon || !Loader || !Loader->IsHandleActive(Info.Handle))
	{
		return;
	}

	// Acquire first: the blocking section takes over only while the icon is requested.
	if (Info.bShowLoadingIcon)
	{
		const FName Reason = Info.Reason.IsNone() ? FName(TEXT("LoadingFXLoader")) : Info.Reason;
		IconRequests.Emplace(Info.Handle, Icon->Acquire(Reason));
	}
	if (Info.bSync)
	{
		BlockingLoads.Add(Info.Handle);
		Icon->BeginBlockingSection(Info.Reason);
	}
}

void ULoadingFXBridgeSubsystem::HandleLoadEnded(const FLoadingFXLoadInfo& Info)
{
	ULoadingFXIconSubsystem* Icon = IconSubsystem.Get();

	const int32 BlockingIndex = BlockingLoads.IndexOfByKey(Info.Handle);
	if (BlockingIndex != INDEX_NONE)
	{
		BlockingLoads.RemoveAtSwap(BlockingIndex);
		if (Icon)
		{
			Icon->EndBlockingSection();
		}
	}

	const int32 Index = IconRequests.IndexOfByPredicate([&Info](const TPair<FLoadingFXLoadHandle, FLoadingFXIconHandle>& Request)
	{
		return Request.Key == Info.Handle;
	});
	if (Index != INDEX_NONE)
	{
		FLoadingFXIconHandle IconHandle = IconRequests[Index].Value;
		IconRequests.RemoveAtSwap(Index);
		if (Icon)
		{
			Icon->Release(IconHandle);
		}
	}
}
