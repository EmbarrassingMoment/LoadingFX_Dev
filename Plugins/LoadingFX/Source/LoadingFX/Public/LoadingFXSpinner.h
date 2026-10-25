// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "Components/Widget.h"
#include "LoadingFXSpinner.generated.h"

class SLoadingFXSpinner;
class UMaterialInstanceDynamic;
class UMaterialInterface;

/**
 * UMG spinner: draws a LoadingFX spinner material (any UI-domain material that follows the material contract)
 * at a given size and tint. With no material set it draws the project's loading icon material
 * (Project Settings > Plugins > LoadingFX).
 *
 * Unlike the loading icon subsystem, a spinner placed in a user widget stops during blocking loads: user
 * widgets are not painted while the game thread is blocked.
 */
UCLASS(meta = (DisplayName = "LoadingFX Spinner"))
class LOADINGFX_API ULoadingFXSpinner : public UWidget
{
	GENERATED_BODY()

public:
	ULoadingFXSpinner(const FObjectInitializer& ObjectInitializer);

	UFUNCTION(BlueprintGetter, Category = "LoadingFX")
	UMaterialInterface* GetMaterial() const;

	/** Sets the material to draw. Null falls back to the project's loading icon material. */
	UFUNCTION(BlueprintSetter, Category = "LoadingFX")
	void SetMaterial(UMaterialInterface* InMaterial);

	UFUNCTION(BlueprintGetter, Category = "LoadingFX")
	FLinearColor GetColorAndOpacity() const;

	UFUNCTION(BlueprintSetter, Category = "LoadingFX")
	void SetColorAndOpacity(FLinearColor InColorAndOpacity);

	/** Sets only the alpha of ColorAndOpacity. */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX")
	void SetOpacity(float InOpacity);

	UFUNCTION(BlueprintGetter, Category = "LoadingFX")
	FVector2D GetSize() const;

	UFUNCTION(BlueprintSetter, Category = "LoadingFX")
	void SetSize(FVector2D InSize);

	/**
	 * Returns a dynamic instance of the drawn material, creating it on the first call and drawing it from then
	 * on, so parameters such as PrimaryColor or Speed can be changed per widget at runtime.
	 */
	UFUNCTION(BlueprintCallable, Category = "LoadingFX")
	virtual UMaterialInstanceDynamic* GetDynamicMaterial();

	//~ Begin UWidget Interface
	virtual void SynchronizeProperties() override;
	virtual void ReleaseSlateResources(bool bReleaseChildren) override;
#if WITH_EDITOR
	virtual const FText GetPaletteCategory() override;
#endif
	//~ End UWidget Interface

protected:
	//~ Begin UWidget Interface
	virtual TSharedRef<SWidget> RebuildWidget() override;
	//~ End UWidget Interface

	/** Material, or the project's loading icon material when none is set. Records it in DrawnMaterial. */
	virtual UMaterialInterface* ResolveMaterial();
	/** Hands the resolved material to the Slate widget. */
	virtual void ApplyMaterial();
	/** Warns once per material if it is not a UI-domain material, which Slate cannot draw. */
	void CheckMaterialDomain(const UMaterialInterface* Resolved) const;

	/**
	 * Spinner material: any UI-domain material that follows the material contract. Leave empty to draw the
	 * project's loading icon material (Project Settings > Plugins > LoadingFX).
	 */
	UPROPERTY(EditAnywhere, BlueprintGetter = GetMaterial, BlueprintSetter = SetMaterial, Category = "LoadingFX")
	TObjectPtr<UMaterialInterface> Material;

	/** Reaches the material as VertexColor; alpha fades the spinner. */
	UPROPERTY(EditAnywhere, BlueprintGetter = GetColorAndOpacity, BlueprintSetter = SetColorAndOpacity, Category = "LoadingFX", meta = (sRGB = "true"))
	FLinearColor ColorAndOpacity = FLinearColor::White;

	/** Desired size in Slate units. The slot may still stretch the widget; the material stays round and centered. */
	UPROPERTY(EditAnywhere, BlueprintGetter = GetSize, BlueprintSetter = SetSize, Category = "LoadingFX")
	FVector2D Size = FVector2D(64.0, 64.0);

	/** What is drawn right now (Material, the project default or the dynamic instance), kept referenced here. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> DrawnMaterial;

	TSharedPtr<SLoadingFXSpinner> MySpinner;
};
