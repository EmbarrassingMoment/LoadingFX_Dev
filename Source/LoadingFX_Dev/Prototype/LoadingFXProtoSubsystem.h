// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "LoadingFXIconSubsystem.h"
#include "LoadingFXLoaderSubsystem.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "LoadingFXProtoSubsystem.generated.h"

class AActor;
class SLoadingFXProtoOverlay;
struct FLoadingFXProtoIconFrameProbe;
class SWidget;
class UWidget;
class UMaterialInterface;

/** Which bundled materials LFXProto.Showcase draws. */
enum class ELoadingFXProtoShowcaseSet : uint8
{
	All,
	Spinners,
	Bars,
};

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
 *   LFXProto.IconTravel [Map] [Sec] [cold] [bg] [shot] [quit]  Exercise ULoadingFXIconSubsystem: acquire, owner auto-release, OpenLevel under the icon, release.
 *                                 'cold' acquires in the same frame as OpenLevel instead, with the project's show delay, so the
 *                                 icon is first drawn on MoviePlayer's loading thread (issue #5), and logs how many frames
 *                                 showed it and the loading screen's background, read back from the back buffer (screenshots
 *                                 cannot see MoviePlayer frames). 'bg' sets LoadingScreenBackgroundColor to sRGB (40, 70, 140)
 *                                 for the run. 'shot' with 'cold' reads back one whole frame 0.75 s after the show delay and
 *                                 saves it to Saved/Screenshots/LFXProto_LoadingScreen.png.
 *   LFXProto.UmgSpinner [shot] [quit]  Show a row of ULoadingFXSpinner UMG widgets (project default, tint, dynamic parameters, opacity, non-square).
 *   LFXProto.ProgressBar [shot] [quit]  Show ULoadingFXProgressBar UMG widgets: one driven by a real Load Assets Async of the
 *                                 prototype's material list (run it in a fresh process to see the steps), scripted increases
 *                                 (smoothing), a decrease (applied at once), fixed values near 0 (hairline check), a tinted
 *                                 bar (sheen), a bar drawing an indeterminate material, and the bar materials in spinners.
 *                                 'shot' saves Saved/Screenshots/LFXProto_ProgressBar.png.
 *   LFXProto.Showcase [Size] [ref] [spinners|bars] [shot] [quit]  Toggle a full-screen showcase of every bundled spinner material on
 *                                 black, Size px each (default 256). 'ref' overlays the material contract's reference circle and
 *                                 square, 'spinners' / 'bars' draw only those materials (for larger sizes, which no longer fit
 *                                 all of them on screen), 'shot' saves Saved/Screenshots/LFXProto_Showcase.png, 'quit' exits afterwards.
 *   LFXProto.Preload [shot] [quit]  Check the icon material preload: in memory before the first Acquire, no sync load
 *                                 during Acquire, and its PSOs precached by then, against a material loaded on demand
 *                                 (PSO states only in packaged builds). 'shot' saves Saved/Screenshots/LFXProto_Preload.png.
 *                                 Start with -LFXProtoEarlyAcquire to also acquire during game instance init, before
 *                                 the preload can have finished.
 *   LFXProto.MinDisplay [quit]    Check the icon's minimum display time (IconMinimumDisplayTime, expected >= 0.8 s): short
 *                                 request, re-acquire while held, long request, ReleaseAll, and the setting at 0. Runs with
 *                                 IconShowDelay at 0.
 *   LFXProto.ShowDelay [quit]     Check the icon's show delay (IconShowDelay, expected >= 0.4 s): short and long requests, release
 *                                 soon after the icon appears, two requests, the setting at 0, a blocking load within the delay,
 *                                 and a release from inside LoadMap after the delay.
 *   LFXProto.Loader [quit]        Check the asset loader and the Bridge: async loads (progress, results, retention across GC,
 *                                 release, already loaded, empty, cancel, owner), sync loads with and without the loading icon
 *                                 (the blocking section), the Blueprint sync function and the Load Assets Async action. Run it
 *                                 in a fresh process: it expects its materials not to be loaded yet.
 *   LFXProto.BlockingSection [quit]  Check the blocking section through its UFunctions, as Blueprint calls them: Begin / End in
 *                                 the world tick, a Begin without End there and later in the frame (ended at the end of the
 *                                 frame), the next section taking over again, a nested sync load, Begin / End inside a
 *                                 button's OnClicked (Slate input routing) and on a mouse press from the Windows message queue,
 *                                 and inside the Slate tick (a widget's Tick, a sync load there, a post tick callback), where a
 *                                 section must not take over.
 *   LFXProto.ClickButton Name[+Name...] [ShotDelay] [quit]  Click the UMG buttons named Name (widgets in a Blueprint's widget tree,
 *                                 such as the sample's BlockingTaskButton) through FSlateApplication, one a second, and log how
 *                                 long each OnClicked took. Saves Saved/Screenshots/LFXProto_Click.png ShotDelay seconds after
 *                                 the last click (default 1.5); 'quit' exits 1.5 s after that.
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
	void RunIconTravelTest(const FString& MapName, float ExtraLoadSeconds, bool bCold, bool bTestBackground, bool bSaveLoadingScreenFrame, bool bQuitWhenDone);
	void RunUmgSpinnerTest(bool bTakeScreenshot, bool bQuitWhenDone);
	void RunProgressBarTest(bool bTakeScreenshot, bool bQuitWhenDone);
	void RunShowcase(float TileSize, bool bShowReference, ELoadingFXProtoShowcaseSet Set, bool bTakeScreenshot, bool bQuitWhenDone);
	void RunPreloadTest(bool bTakeScreenshot, bool bQuitWhenDone);
	void RunMinDisplayTest(bool bQuitWhenDone);
	void RunShowDelayTest(bool bQuitWhenDone);
	void RunLoaderTest(bool bQuitWhenDone);
	void RunBlockingSectionTest(bool bQuitWhenDone);
	void RunClickButton(const FString& ButtonNames, float ShotDelay, bool bQuitWhenDone);

private:
	/** LFXProto.Loader: the outputs of the Load Assets Async actions it starts. */
	UFUNCTION()
	void HandleLoaderActionProgress(FLoadingFXLoadHandle Handle, float Progress, const TArray<UObject*>& LoadedAssets, const TArray<UClass*>& LoadedClasses);
	UFUNCTION()
	void HandleLoaderActionCompleted(FLoadingFXLoadHandle Handle, float Progress, const TArray<UObject*>& LoadedAssets, const TArray<UClass*>& LoadedClasses);
	UFUNCTION()
	void HandleLoaderActionCanceled(FLoadingFXLoadHandle Handle, float Progress, const TArray<UObject*>& LoadedAssets, const TArray<UClass*>& LoadedClasses);

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
	void HideProgressBars();
	void ShowShowcase(float TileSize, bool bShowReference, ELoadingFXProtoShowcaseSet Set);
	void HideShowcase();
	void StartSequence();
	void SimulateBlockingWork(float Seconds, bool bCollectGarbage) const;
	void OpenLevel(const FString& MapName);
	void LogOverlayStats(const TCHAR* Context, double ElapsedSeconds) const;

	/** LFXProto.MinDisplay / ShowDelay: the icon subsystem if it is idle (warns otherwise), recording its visibility changes from now on. */
	ULoadingFXIconSubsystem* BeginIconTest(const TCHAR* Tag);
	void EndIconTest(const TCHAR* Tag, bool bQuitWhenDone);
	/** Starts a case: acquires IconTestHandle, and the times in the reports count from now. */
	void StartIconCase(const TCHAR* Tag, const FString& Description);
	void ReportIconCase(const TCHAR* Tag, const TCHAR* Step, const FString& Expect) const;
	/** OpenLevel to the travel test map with Seconds of simulated loading inside LoadMap. */
	void StartIconTestTravel(float Seconds);

	/** LFXProto.Loader: starts a case (times in its logs count from now), and C++ callbacks that log what they get. */
	void StartLoaderCase(const FString& Description);
	double LoaderCaseSeconds() const;
	FLoadingFXLoadHandle LoadAsyncForTest(const TArray<FSoftObjectPath>& Paths, FName Reason, UObject* Owner, bool bShowLoadingIcon);
	void ReportLoaderState(const TCHAR* Step, const FLoadingFXLoadHandle& Handle, const FString& Expect) const;
	void HandleLoaderLoadStarted(const FLoadingFXLoadInfo& Info);
	void HandleLoaderLoadEnded(const FLoadingFXLoadInfo& Info);

	/** LFXProto.BlockingSection: starts a case (times and frames in its reports count from now). */
	void StartSectionCase(const FString& Description);
	void ReportSectionState(const TCHAR* Step, const FString& Expect) const;
	/** Runs Action in the world tick of the next frame, where Blueprint events and timers run. */
	void RunInWorldTick(TFunction<void()> Action);
	/** Posts a mouse press to the game window's message queue and runs Action when Slate receives it. */
	void RunOnPostedMousePress(TFunction<void()> Action);
	/** Runs Action once in the Tick of a widget in the viewport, inside FSlateApplication::Tick. */
	void RunInWidgetTick(TFunction<void()> Action);
	void HideSectionTickWidget();
	/** Calls a UFUNCTION of the icon subsystem by name through ProcessEvent, as Blueprint does ("Name Arg"). */
	void CallIconFunction(const TCHAR* Command);
	/** A button whose OnClicked runs a blocking section, and a click synthesized on it through FSlateApplication. */
	void ShowSectionButton();
	void ClickSectionButton();
	void HideSectionButton();

	/**
	 * LFXProto.IconTravel cold: reads the icon's corner of the back buffer on every presented frame, MoviePlayer's
	 * included (screenshots only see game frames), and logs in which phase of the travel the icon was drawn and
	 * whether the loading screen's background matched LoadingScreenBackgroundColor. A SaveFrameAtSeconds above 0 also
	 * keeps the first whole frame presented from then on.
	 */
	void StartIconFrameProbe(double SaveFrameAtSeconds = 0.0);
	void StopIconFrameProbe();
	void ReportIconFrameProbe() const;

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

	/** LFXProto.MinDisplay / ShowDelay: the requests of the current case, and the icon's visibility changes since it started. */
	FLoadingFXIconHandle IconTestHandle;
	FLoadingFXIconHandle IconTestSecondHandle;
	TArray<TPair<bool, double>> IconTestEvents;
	double IconTestCaseStartSeconds = 0.0;
	FDelegateHandle IconVisibilityChangedHandle;
	/** LFXProto.ShowDelay: release IconTestHandle from PostLoadMapWithWorld (inside LoadMap), and what to expect then. */
	bool bReleaseIconTestInLoadMap = false;
	FString IconTestReleaseInLoadMapExpect;

	/** LFXProto.Loader state. */
	double LoaderCaseStartSeconds = 0.0;
	uint64 LoaderCaseStartFrame = 0;
	/** True while a load call made by the test runs, to catch callbacks fired inside it. */
	bool bLoaderInsideCall = false;
	int32 LoaderCompletedCount = 0;
	int32 LoaderCanceledCount = 0;
	/** The non-null results of the last completed C++ load, to see whether they stay in memory. */
	TArray<TWeakObjectPtr<UObject>> LoaderLoadedAssets;
	FLoadingFXLoadHandle LoaderHandles[4];
	FLoadingFXIconHandle LoaderIconHandle;
	TWeakObjectPtr<AActor> LoaderOwner;
	/** Extra seconds to block inside the next sync load's end event, which runs before the Bridge ends the blocking section. */
	float LoaderSimulatedSyncSeconds = 0.0f;
	FDelegateHandle LoaderStartedHandle;
	FDelegateHandle LoaderEndedHandle;

	/** LFXProto.BlockingSection state. */
	double SectionCaseStartSeconds = 0.0;
	uint64 SectionCaseStartFrame = 0;
	FLoadingFXIconHandle SectionIconHandle;
	TSharedPtr<SWidget> SectionButtonRoot;
	TSharedPtr<SWidget> SectionButton;
	int32 SectionButtonClicks = 0;
	TSharedPtr<class IInputProcessor> SectionMousePress;
	TSharedPtr<SWidget> SectionTickWidget;
	FDelegateHandle SectionPostTickHandle;
	bool bSectionPostTickDone = false;

	TSharedPtr<SWidget> ViewportOverlayRoot;
	TSharedPtr<SLoadingFXProtoOverlay> ViewportOverlay;
	TSharedPtr<SWidget> GalleryRoot;

	/** UMG spinners created by LFXProto.UmgSpinner, kept alive here. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UWidget>> UmgSpinners;
	TSharedPtr<SWidget> UmgRoot;
	TSharedPtr<SWidget> ShowcaseRoot;

	/** UMG widgets created by LFXProto.ProgressBar, kept alive here, and the load that drives the first bar. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UWidget>> ProgressBarWidgets;
	TSharedPtr<SWidget> ProgressBarRoot;
	FLoadingFXLoadHandle ProgressBarLoadHandle;

	/** The overlay handed to MoviePlayer for the current / last test. Only replaced while MoviePlayer is idle. */
	TSharedPtr<SLoadingFXProtoOverlay> LoadingScreenOverlay;

	bool bTravelPending = false;
	bool bIconTravelPending = false;
	FLoadingFXIconHandle IconTravelHandle;
	TWeakObjectPtr<UObject> IconTravelOwner;
	float TravelExtraLoadSeconds = 0.0f;
	double TravelStartSeconds = 0.0;
	/** LFXProto.IconTravel cold: the frames the probe saw, and when the icon was requested, MoviePlayer started and LoadMap ended. */
	TSharedPtr<FLoadingFXProtoIconFrameProbe, ESPMode::ThreadSafe> IconFrameProbe;
	FDelegateHandle BackBufferReadyHandle;
	double IconTravelAcquireSeconds = 0.0;
	double IconTravelMovieStartSeconds = 0.0;
	double IconTravelLoadEndSeconds = 0.0;

	TArray<FSequenceStep> SequenceSteps;
	int32 NextSequenceStep = 0;
	double NextSequenceStepTime = 0.0;
	FTSTicker::FDelegateHandle SequenceTickerHandle;

	FDelegateHandle PrepareLoadingScreenHandle;
	FDelegateHandle MoviePlaybackStartedHandle;
	FDelegateHandle PostLoadMapHandle;
	FDelegateHandle SyncLoadPackageHandle;
};
