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
struct FSoftObjectPath;

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

/** Fires when the loading icon appears (after the show delay) or hides (after the last release and the minimum display time). */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FLoadingFXIconVisibilityChanged, bool, bVisible);
DECLARE_MULTICAST_DELEGATE_OneParam(FLoadingFXIconVisibilityChangedNative, bool /*bVisible*/);

/**
 * Shows the project-wide loading icon (Project Settings > Plugins > LoadingFX) over the game viewport.
 *
 * Show and hide are reference counted: every Acquire returns a handle, and the icon stays until each handle
 * has been released, so independent systems can share it. A request may name an owner object and is then
 * released automatically once that object is destroyed.
 *
 * Two settings keep short loads from making the icon flicker (Project Settings). The icon appears only once the
 * first request has been active for IconShowDelay, so a load shorter than that shows nothing. Once it appears, it
 * stays for at least IconMinimumDisplayTime: after an early last release it hides when that time is over. Visibility
 * (IsIconVisible, OnVisibilityChanged) follows what is on screen, not the request count.
 *
 * The icon material is loaded in the background as soon as the subsystem initializes, which also starts precaching
 * its PSOs, so showing the icon later loads and compiles nothing. An Acquire that comes before that load has
 * finished waits for it, so the icon still appears at once. Uncooked processes (-game from the editor binaries)
 * compile a material's shaders only when it is first drawn, and only the game thread can finish that, so there the
 * subsystem also compiles the material's shaders when it arrives (with MoviePlayer only). Otherwise an icon first
 * drawn on the loading screen would stay blank for the whole blocking load.
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
	 * Shows the loading icon (after the show delay, if it is not up yet) and returns the handle of this request.
	 * Reason is for logs and LoadingFX.Icon.Dump.
	 * With an Owner, the request is released automatically when Owner is destroyed (for example an actor that
	 * goes away with its level); without one, keep the handle and call Release.
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Acquire Loading Icon"))
	FLoadingFXIconHandle Acquire(FName Reason, UObject* Owner = nullptr);

	/**
	 * Releases a request and invalidates the handle. Once no request is left, the icon hides when it has been shown
	 * for the minimum display time, or never appears if the show delay is not over yet. Returns false if the handle
	 * was not active (already released, or never issued).
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Release Loading Icon"))
	bool Release(UPARAM(ref) FLoadingFXIconHandle& Handle);

	/**
	 * Releases every request, whoever made it, so the icon hides (with the show delay and the minimum display time
	 * applied as for any last release). For recovery paths such as returning to the main menu.
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX", meta = (DisplayName = "Release All Loading Icon Requests"))
	void ReleaseAll();

	/**
	 * True while the icon is on screen: from the end of the show delay after the first request until it hides, which
	 * is after the last release and the rest of the minimum display time. GetRequestCount tells whether it is requested.
	 */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	bool IsIconVisible() const { return bIconVisible; }

	/** Number of active requests, including those still within the show delay. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	int32 GetRequestCount() const { return Requests.Num(); }

	/** True if the handle refers to a request that has not been released yet. */
	UFUNCTION(BlueprintPure, Category = "LoadingFX")
	bool IsHandleActive(const FLoadingFXIconHandle& Handle) const;

	/**
	 * Marks the start of work that blocks the game thread (a sync load, for example), so the icon keeps animating
	 * through it. If the icon is requested at that moment (also within the show delay), MoviePlayer takes over and draws
	 * it on a black screen until the matching EndBlockingSection; otherwise nothing changes and the game just hitches.
	 * Sections nest, and only the outermost one starts and stops MoviePlayer.
	 * Does nothing where MoviePlayer is unavailable (editor, PIE, -NoLoadingScreen) or while another loading screen is
	 * set up or playing. Prefer FLoadingFXBlockingScope, which cannot miss the end.
	 */
	void BeginBlockingSection(FName Reason);

	/** Ends the section started by the matching BeginBlockingSection. The outermost one waits for MoviePlayer to finish. */
	void EndBlockingSection();

	/** True between the outermost BeginBlockingSection and its EndBlockingSection, whether MoviePlayer took over or not. */
	bool IsInBlockingSection() const { return BlockingSectionDepth > 0; }

	/** Fires when the icon appears (after the show delay) or hides (after the last release and the minimum display time). */
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

	/** Called when no request is left: cancels the icon within the show delay, otherwise hides it (after the minimum display time). */
	void HandleLastRelease();

	/** Shows the icon, counting its display time from ShownAtSeconds. */
	void ShowIcon(double ShownAtSeconds);
	void CancelPendingShow();
	bool TickPendingShow(float DeltaTime);

	/** Hides the icon now, or once it has been shown for the minimum display time. */
	void HideAfterMinimumDisplayTime();
	void HideIcon();
	void CancelPendingHide();
	bool TickPendingHide(float DeltaTime);

	/** Starts loading the icon material asynchronously (Initialize). */
	void PreloadIconMaterial();
	void HandleIconMaterialPreloaded(const FSoftObjectPath& MaterialPath, UObject* LoadedObject);
	/** Takes the result of the load (null if it failed) as the icon material, and warns about unusable ones. */
	void SetIconMaterial(UMaterialInterface* Material, const FSoftObjectPath& MaterialPath);
	/**
	 * Compiles the icon material's missing shaders and waits for them (uncooked processes with MoviePlayer only), so
	 * that its first draw may happen on MoviePlayer's loading thread.
	 */
	void CompileIconMaterialShaders();
	/** The icon material, or null if there is none. Waits for the preload if it is still in flight. */
	UMaterialInterface* GetIconMaterial();
	/** With ShowAtSeconds in the future (platform time), the widget stays hidden until then: a loading screen set up within the show delay. */
	TSharedRef<SWidget> MakeIconWidget(double ShowAtSeconds = 0.0);
	/** The icon over a full-screen LoadingScreenBackgroundColor, for MoviePlayer. The color shows at once, the icon at ShowAtSeconds. */
	TSharedRef<SWidget> MakeLoadingScreenWidget(double ShowAtSeconds);

	void ShowViewportIcon();
	void HideViewportIcon();
	void HandleViewportCreated();

	void HandlePrepareLoadingScreen();

	/**
	 * Hands MoviePlayer a loading screen with the icon, if the icon is visible or requested and nobody else has set one
	 * up. What names the blocking work for the log. Returns true if it did.
	 */
	bool SetUpIconLoadingScreen(const FString& What);

	bool TickOwnerWatch(float DeltaTime);

	/** Keeps the material alive across garbage collection, including the one inside LoadMap. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> IconMaterial;

	/** True while the preload is in flight. Its request id is INDEX_NONE if the loader did not return one. */
	bool bIconMaterialPreloadPending = false;
	int32 IconMaterialPreloadRequestId = INDEX_NONE;
	double IconMaterialPreloadStartSeconds = 0.0;

	TArray<FRequest> Requests;
	int32 NextRequestId = 1;

	/** True while the icon is on screen (see IsIconVisible), and when it appeared. */
	bool bIconVisible = false;
	double IconShownAtSeconds = 0.0;

	/** Registered only while the first request waits for the show delay; shows the icon at PendingShowAtSeconds. */
	FTSTicker::FDelegateHandle PendingShowTickerHandle;
	double PendingShowAtSeconds = 0.0;

	/** Registered only while the icon is kept on screen after the last release; hides it at PendingHideAtSeconds. */
	FTSTicker::FDelegateHandle PendingHideTickerHandle;
	double PendingHideAtSeconds = 0.0;

	/** The icon shown as viewport content, and the viewport client it was added to. */
	TSharedPtr<SWidget> ViewportIconRoot;
	TWeakObjectPtr<UGameViewportClient> ViewportIconClient;

	FDelegateHandle ViewportCreatedHandle;
	FDelegateHandle PrepareLoadingScreenHandle;

	/** Nesting depth of BeginBlockingSection, and whether the outermost section started MoviePlayer. */
	int32 BlockingSectionDepth = 0;
	bool bBlockingSectionPlaysMovie = false;
	FName BlockingSectionReason;
	double BlockingSectionStartSeconds = 0.0;

	/** Registered only while some request has an owner to watch. */
	FTSTicker::FDelegateHandle OwnerWatchTickerHandle;

	TArray<FLoadingFXIconHandle> ConsoleHandles;
};

/**
 * Keeps the loading icon animating through blocking work in C++: runs BeginBlockingSection on construction and
 * EndBlockingSection on destruction, on the loading icon subsystem of WorldContextObject's game instance. Does nothing
 * if there is none.
 *
 *     {
 *         FLoadingFXBlockingScope BlockingScope(this, TEXT("BuildCache"));
 *         // ... work that blocks the game thread ...
 *     }
 */
class LOADINGFX_API FLoadingFXBlockingScope
{
public:
	FLoadingFXBlockingScope(const UObject* WorldContextObject, FName Reason);
	~FLoadingFXBlockingScope();

	UE_NONCOPYABLE(FLoadingFXBlockingScope);

private:
	TWeakObjectPtr<ULoadingFXIconSubsystem> Subsystem;
};
