// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "LoadingFXIconSubsystem.h"
#include "LoadingFXLoaderSubsystem.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "UObject/WeakObjectPtr.h"
#include "LoadingFXBridgeSubsystem.generated.h"

/**
 * Forwards ULoadingFXLoaderSubsystem's loads to ULoadingFXIconSubsystem:
 * - a load with bShowLoadingIcon acquires the loading icon from its start until it ends (completed or canceled);
 * - every sync load runs inside the icon's blocking section, so an icon that is requested (by the load itself or by
 *   anyone else) keeps animating while the game thread is blocked.
 *
 * Private to this module: it has no API of its own.
 */
UCLASS()
class ULoadingFXBridgeSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	//~ Begin USubsystem Interface
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	//~ End USubsystem Interface

private:
	void HandleLoadStarted(const FLoadingFXLoadInfo& Info);
	void HandleLoadEnded(const FLoadingFXLoadInfo& Info);

	/** Both live as long as this subsystem, but the order in which a game instance deinitializes them is not fixed. */
	TWeakObjectPtr<ULoadingFXLoaderSubsystem> LoaderSubsystem;
	TWeakObjectPtr<ULoadingFXIconSubsystem> IconSubsystem;

	/** The icon requests made for loads with bShowLoadingIcon, released when their load ends. */
	TArray<TPair<FLoadingFXLoadHandle, FLoadingFXIconHandle>> IconRequests;

	/** The sync loads whose blocking section was started, so each end matches a start. */
	TArray<FLoadingFXLoadHandle> BlockingLoads;

	FDelegateHandle LoadStartedHandle;
	FDelegateHandle LoadEndedHandle;
};
