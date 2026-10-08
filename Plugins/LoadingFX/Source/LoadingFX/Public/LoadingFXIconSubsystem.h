// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Templates/SharedPointer.h"
#include "UObject/WeakObjectPtr.h"
#include "LoadingFXIconSubsystem.generated.h"

class SWidget;
class UGameViewportClient;
class UMaterialInterface;

/**
 * Identifies one show request made with ULoadingFXIconSubsystem::Acquire. Pass it to Release when done.
 * IsValid() only says whether the handle was issued and not released through this copy; ask the subsystem
 * (IsHandleActive) whether the request is still counted.
 */
USTRUCT(BlueprintType)
struct LOADINGFX_API FLoadingFXIconHandle
{
	GENERATED_BODY()

	bool IsValid() const { return Id != 0; }
	void Invalidate() { Id = 0; }

	bool operator==(const FLoadingFXIconHandle& Other) const { return Id == Other.Id; }
	bool operator!=(const FLoadingFXIconHandle& Other) const { return Id != Other.Id; }

private:
	friend class ULoadingFXIconSubsystem;

	/** 0 is never issued. */
	UPROPERTY()
	int32 Id = 0;
};

/** Fires when the loading icon becomes visible (first request) or hidden (last release). */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FLoadingFXIconVisibilityChanged, bool, bVisible);
DECLARE_MULTICAST_DELEGATE_OneParam(FLoadingFXIconVisibilityChangedNative, bool /*bVisible*/);

/**
 * Shows the project-wide loading icon (Project Settings > Plugins > LoadingFX) over the game viewport.
 *
 * Show and hide are reference counted: every Acquire returns a handle, and the icon stays until each handle
 * has been released, so independent systems can share it. A request may name an owner object and is then
 * released automatically once that object is destroyed.
 *
 * The icon is viewport content (not a UMG widget added to the viewport), so it survives map travel. While it
 * is visible, a blocking map load (OpenLevel, LoadMap) is rendered through MoviePlayer with the icon as the
 * loading screen, so it keeps animating while the game thread is blocked; the screen behind it is black for
 * that time. MoviePlayer is unavailable in the editor and PIE (and with -NoLoadingScreen), so there the icon
 * freezes during blocking loads: run with -game or a packaged build to see the real behavior.
 *
 * Game thread only.
 */
UCLASS()
class LOADINGFX_API ULoadingFXIconSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	//~ Begin USubsystem Interface
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	//~ End USubsystem Interface

	/**
	 * Shows the loading icon and returns the handle of this request. Reason is for logs and LoadingFX.Icon.Dump.
	 * With an Owner, the request is released automatically when Owner is destroyed (for example an actor that
	 * goes away with its level); without one, keep the handle and call Release.
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Acquire Loading Icon"))
	FLoadingFXIconHandle Acquire(FName Reason, UObject* Owner = nullptr);

	/**
	 * Releases a request and invalidates the handle. The icon hides once no request is left.
	 * Returns false if the handle was not active (already released, or never issued).
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Release Loading Icon"))
	bool Release(UPARAM(ref) FLoadingFXIconHandle& Handle);

	/** Releases every request, whoever made it, and hides the icon. For recovery paths such as returning to the main menu. */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Release All Loading Icon Requests"))
	void ReleaseAll();

	/** True while at least one request is active. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	bool IsIconVisible() const { return Requests.Num() > 0; }

	/** Number of active requests. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	int32 GetRequestCount() const { return Requests.Num(); }

	/** True if the handle refers to a request that has not been released yet. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	bool IsHandleActive(const FLoadingFXIconHandle& Handle) const;

	/** Fires when the icon becomes visible (first request) or hidden (last release). */
	UPROPERTY(BlueprintAssignable, Category = "LoadingFX")
	FLoadingFXIconVisibilityChanged OnVisibilityChanged;

	/** C++ counterpart of OnVisibilityChanged; fires first. */
	FLoadingFXIconVisibilityChangedNative OnVisibilityChangedNative;

	/** Logs the active requests (LoadingFX.Icon.Dump). */
	void DumpRequests() const;

	/** Backs LoadingFX.Icon.Show / LoadingFX.Icon.Hide: console-owned requests for testing. */
	void ConsoleShow(FName Reason);
	void ConsoleHide(bool bAll);

private:
	struct FRequest
	{
		int32 Id = 0;
		FName Reason;
		TWeakObjectPtr<const UObject> Owner;
		bool bHasOwner = false;
		double AcquiredAtSeconds = 0.0;
	};

	bool ReleaseInternal(int32 Id, const TCHAR* Context);
	void NotifyVisibilityChanged(bool bVisible);

	UMaterialInterface* GetIconMaterial();
	TSharedRef<SWidget> MakeIconWidget();

	void ShowViewportIcon();
	void HideViewportIcon();
	void HandleViewportCreated();

	void HandlePrepareLoadingScreen();

	bool TickOwnerWatch(float DeltaTime);

	/** Keeps the material alive across garbage collection, including the one inside LoadMap. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> IconMaterial;
	bool bIconMaterialLoadAttempted = false;

	TArray<FRequest> Requests;
	int32 NextRequestId = 1;

	/** The icon shown as viewport content, and the viewport client it was added to. */
	TSharedPtr<SWidget> ViewportIconRoot;
	TWeakObjectPtr<UGameViewportClient> ViewportIconClient;

	FDelegateHandle ViewportCreatedHandle;
	FDelegateHandle PrepareLoadingScreenHandle;

	/** Registered only while some request has an owner to watch. */
	FTSTicker::FDelegateHandle OwnerWatchTickerHandle;

	TArray<FLoadingFXIconHandle> ConsoleHandles;
};
