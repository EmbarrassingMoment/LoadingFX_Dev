// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "LoadingFXIconSubsystem.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "LoadingFXProtoSubsystem.generated.h"

class SLoadingFXProtoOverlay;
class SWidget;
class UWidget;
class UMaterialInterface;

/**
 * Verification prototype only (not part of the LoadingFX plugin).
 * Checks whether UI materials render and animate under MoviePlayer, driven by console commands:
 *
 *   LFXProto.Overlay              Toggle the overlay in the game viewport (baseline: normal rendering)
 *   LFXProto.Block [Sec] [GC] [Delay]  Simulated sync load: block the game thread under a manually started
 *                                 MoviePlayer. GC=1 runs a garbage collection halfway through.
 *   LFXProto.Travel Map [Sec]     OpenLevel with the overlay as loading screen. Sec adds simulated load time.
 *   LFXProto.RunAll [quit]        Run every case in order (e.g. -ExecCmds="LFXProto.RunAll quit").
 *   LFXProto.Gallery [shot] [quit]  Toggle the material contract gallery (non-square sizes, tint). 'shot' saves two
 *                                 screenshots to Saved/Screenshots/LFXProto_Gallery_*.png, 'quit' exits afterwards.
 *   LFXProto.IconTravel [Map] [Sec] [quit]  Exercise ULoadingFXIconSubsystem: acquire, owner auto-release, OpenLevel under the icon, release.
 *   LFXProto.UmgSpinner [shot] [quit]  Show a row of ULoadingFXSpinner UMG widgets (project default, tint, dynamic parameters, opacity, non-square).
 *   LFXProto.Showcase [Size] [ref] [shot] [quit]  Toggle a full-screen showcase of every bundled spinner material on black, Size px
 *                                 each (default 256). 'ref' overlays the material contract's reference circle and square,
 *                                 'shot' saves Saved/Screenshots/LFXProto_Showcase.png, 'quit' exits afterwards.
 *   LFXProto.Preload [shot] [quit]  Check the icon material preload: in memory before the first Acquire, no sync load
 *                                 during Acquire, and its PSOs precached by then, against a material loaded on demand
 *                                 (PSO states only in packaged builds). 'shot' saves Saved/Screenshots/LFXProto_Preload.png.
 *                                 Start with -LFXProtoEarlyAcquire to also acquire during game instance init, before
 *                                 the preload can have finished.
 *   LFXProto.MinDisplay [quit]    Check the icon's minimum display time (IconMinimumDisplayTime, expected >= 0.8 s): short
 *                                 request, re-acquire while held, long request, ReleaseAll, and the setting at 0.
 *
 * The prototype loads its own material list on first use, so that it does not hide the icon material preload.
 * MoviePlayer is disabled in the editor and PIE: run with -game or a packaged build.
 */
UCLASS()
class ULoadingFXProtoSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	void ToggleViewportOverlay();
	void RunBlockTest(float Seconds, bool bCollectGarbage);
	void RunTravelTest(const FString& MapName, float ExtraLoadSeconds);
	void RunAll(bool bQuitWhenDone);
	void RunGallery(bool bTakeScreenshots, bool bQuitWhenDone);
	void RunIconTravelTest(const FString& MapName, float ExtraLoadSeconds, bool bQuitWhenDone);
	void RunUmgSpinnerTest(bool bTakeScreenshot, bool bQuitWhenDone);
	void RunShowcase(float TileSize, bool bShowReference, bool bTakeScreenshot, bool bQuitWhenDone);
	void RunPreloadTest(bool bTakeScreenshot, bool bQuitWhenDone);
	void RunMinDisplayTest(bool bQuitWhenDone);

private:
	struct FSequenceStep
	{
		float DelayBefore = 0.0f;
		TFunction<void()> Action;
	};

	/** Loads the prototype's material list on first use. */
	void LoadMaterials();
	TSharedRef<SLoadingFXProtoOverlay> MakeOverlay(const FString& Label);
	void ShowViewportOverlay();
	void HideViewportOverlay();
	void ShowGallery();
	void HideGallery();
	void HideUmgSpinners();
	void ShowShowcase(float TileSize, bool bShowReference);
	void HideShowcase();
	void StartSequence();
	void SimulateBlockingWork(float Seconds, bool bCollectGarbage) const;
	void OpenLevel(const FString& MapName);
	void LogOverlayStats(const TCHAR* Context, double ElapsedSeconds) const;

	void HandlePrepareLoadingScreen();
	void HandleMoviePlaybackStarted();
	void HandlePostLoadMap(UWorld* LoadedWorld);
	void HandleSyncLoadPackage(const FString& PackageName);
	void HandleIconVisibilityChanged(bool bVisible);
	bool TickSequence(float DeltaTime);

	/** Keeps the spinner materials alive across the GC that runs during LoadMap. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInterface>> Materials;
	TArray<FString> MaterialCaptions;
	bool bMaterialsLoaded = false;

	/** LFXProto.Preload: the icon material's package, sync loads of it seen so far, and the requests made by the test. */
	FString IconPackageName;
	int32 IconPackageSyncLoads = 0;
	FLoadingFXIconHandle EarlyAcquireHandle;
	FLoadingFXIconHandle PreloadTestHandle;
	/** A material nobody preloaded, loaded on demand by LFXProto.Preload to compare its PSO state with the icon's. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> PreloadControlMaterial;

	/** LFXProto.MinDisplay: the request of the current case, and the icon's visibility changes since the case started. */
	FLoadingFXIconHandle MinDisplayHandle;
	TArray<TPair<bool, double>> MinDisplayEvents;
	double MinDisplayCaseStartSeconds = 0.0;
	FDelegateHandle IconVisibilityChangedHandle;

	TSharedPtr<SWidget> ViewportOverlayRoot;
	TSharedPtr<SLoadingFXProtoOverlay> ViewportOverlay;
	TSharedPtr<SWidget> GalleryRoot;

	/** UMG spinners created by LFXProto.UmgSpinner, kept alive here. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UWidget>> UmgSpinners;
	TSharedPtr<SWidget> UmgRoot;
	TSharedPtr<SWidget> ShowcaseRoot;

	/** The overlay handed to MoviePlayer for the current / last test. Only replaced while MoviePlayer is idle. */
	TSharedPtr<SLoadingFXProtoOverlay> LoadingScreenOverlay;

	bool bTravelPending = false;
	bool bIconTravelPending = false;
	FLoadingFXIconHandle IconTravelHandle;
	TWeakObjectPtr<UObject> IconTravelOwner;
	float TravelExtraLoadSeconds = 0.0f;
	double TravelStartSeconds = 0.0;

	TArray<FSequenceStep> SequenceSteps;
	int32 NextSequenceStep = 0;
	double NextSequenceStepTime = 0.0;
	FTSTicker::FDelegateHandle SequenceTickerHandle;

	FDelegateHandle PrepareLoadingScreenHandle;
	FDelegateHandle MoviePlaybackStartedHandle;
	FDelegateHandle PostLoadMapHandle;
	FDelegateHandle SyncLoadPackageHandle;
};
