// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "LoadingFXProtoSubsystem.generated.h"

class SLoadingFXProtoOverlay;
class SWidget;
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
 *
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

private:
	struct FSequenceStep
	{
		float DelayBefore = 0.0f;
		TFunction<void()> Action;
	};

	TSharedRef<SLoadingFXProtoOverlay> MakeOverlay(const FString& Label) const;
	void ShowViewportOverlay();
	void HideViewportOverlay();
	void ShowGallery();
	void HideGallery();
	void StartSequence();
	void SimulateBlockingWork(float Seconds, bool bCollectGarbage) const;
	void OpenLevel(const FString& MapName);
	void LogOverlayStats(const TCHAR* Context, double ElapsedSeconds) const;

	void HandlePrepareLoadingScreen();
	void HandleMoviePlaybackStarted();
	void HandlePostLoadMap(UWorld* LoadedWorld);
	bool TickSequence(float DeltaTime);

	/** Keeps the spinner materials alive across the GC that runs during LoadMap. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInterface>> Materials;
	TArray<FString> MaterialCaptions;

	TSharedPtr<SWidget> ViewportOverlayRoot;
	TSharedPtr<SLoadingFXProtoOverlay> ViewportOverlay;
	TSharedPtr<SWidget> GalleryRoot;

	/** The overlay handed to MoviePlayer for the current / last test. Only replaced while MoviePlayer is idle. */
	TSharedPtr<SLoadingFXProtoOverlay> LoadingScreenOverlay;

	bool bTravelPending = false;
	float TravelExtraLoadSeconds = 0.0f;
	double TravelStartSeconds = 0.0;

	TArray<FSequenceStep> SequenceSteps;
	int32 NextSequenceStep = 0;
	double NextSequenceStepTime = 0.0;
	FTSTicker::FDelegateHandle SequenceTickerHandle;

	FDelegateHandle PrepareLoadingScreenHandle;
	FDelegateHandle MoviePlaybackStartedHandle;
	FDelegateHandle PostLoadMapHandle;
};
