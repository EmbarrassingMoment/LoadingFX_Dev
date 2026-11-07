// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "DevMaterialTools.generated.h"

class UMaterial;
class UMaterialFunction;
class UMaterialExpressionComment;
class UMaterialExpressionNamedRerouteDeclaration;
class UMaterialExpressionNamedRerouteUsage;

/** Helpers that let Python / Blueprint build material graphs with Named Reroutes and comment boxes.
 *  A Usage's Declaration / DeclarationGuid are plain UPROPERTYs that are not exposed to Python,
 *  so only the linking is done in C++. No engine modification is required. */
UCLASS()
class DEVMATERIALTOOLS_API UDevMaterialTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Creates a Named Reroute Usage node in the material, linked to the Declaration. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static UMaterialExpressionNamedRerouteUsage* CreateNamedRerouteUsage(
		UMaterial* Material,
		UMaterialExpressionNamedRerouteDeclaration* Declaration,
		int32 NodePosX = 0,
		int32 NodePosY = 0);

	/** Creates a Named Reroute Usage node in the Material Function, linked to the Declaration. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static UMaterialExpressionNamedRerouteUsage* CreateNamedRerouteUsageInFunction(
		UMaterialFunction* MaterialFunction,
		UMaterialExpressionNamedRerouteDeclaration* Declaration,
		int32 NodePosX = 0,
		int32 NodePosY = 0);

	/** Returns the name the Usage node displays (= the linked Declaration's Name). Empty if the link is broken. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static FString GetNamedRerouteUsageDisplayName(UMaterialExpressionNamedRerouteUsage* Usage);

	/** Creates a comment box in the material. (X, Y) is the top-left corner, (SizeX, SizeY) the enclosed size. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static UMaterialExpressionComment* CreateCommentInMaterial(
		UMaterial* Material,
		const FString& Text,
		int32 X, int32 Y, int32 SizeX, int32 SizeY,
		FLinearColor Color = FLinearColor::White);

	/** Returns the text of every comment in the material (for verification). */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static TArray<FString> GetMaterialCommentTexts(UMaterial* Material);

	/** Deletes every comment box in the material and returns how many were deleted.
	 *  MaterialEditingLibrary's delete functions don't touch the EditorComments array, so call this before rebuilding a graph. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static int32 DeleteAllCommentsInMaterial(UMaterial* Material);

	/** Deletes every comment box in the Material Function and returns how many were deleted. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static int32 DeleteAllCommentsInFunction(UMaterialFunction* MaterialFunction);

	/** Creates a comment box in the Material Function. SizeX / SizeY are not exposed to Python, so they are taken here.
	 *  (X, Y) is the top-left corner, (SizeX, SizeY) the enclosed size. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static UMaterialExpressionComment* CreateCommentInFunction(
		UMaterialFunction* MaterialFunction,
		const FString& Text,
		int32 X, int32 Y, int32 SizeX, int32 SizeY,
		FLinearColor Color = FLinearColor::White);

	/** Returns the comment's position and size as (X, Y, SizeX, SizeY) (for verification). */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static FVector4 GetCommentBounds(UMaterialExpressionComment* Comment);

	/** Returns every comment box in the material (for verification). */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static TArray<UMaterialExpressionComment*> GetMaterialComments(UMaterial* Material);

	/** Returns every comment box in the Material Function (for verification). */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static TArray<UMaterialExpressionComment*> GetFunctionComments(UMaterialFunction* MaterialFunction);

	/** Moves the material's output node. UMaterial::EditorX / EditorY are not exposed to Python,
	 *  and a material that never sets them draws the node at (0, 0), in the middle of the graph. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static void SetMaterialRootPosition(UMaterial* Material, int32 X, int32 Y);

	/** Returns the position of the material's output node as (X, Y) (for verification). */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static FIntPoint GetMaterialRootPosition(UMaterial* Material);

	/** Returns the text of every comment in the Material Function (for verification). */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static TArray<FString> GetFunctionCommentTexts(UMaterialFunction* MaterialFunction);

	/** Returns every expression in the material (for verification).
	 *  MaterialEditingLibrary only gained an equivalent after UE 5.5. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static TArray<UMaterialExpression*> GetMaterialExpressions(UMaterial* Material);

	/** Returns every expression in the Material Function (for verification).
	 *  MaterialEditingLibrary only gained an equivalent after UE 5.5. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static TArray<UMaterialExpression*> GetMaterialFunctionExpressions(UMaterialFunction* MaterialFunction);

	/** Replaces the material's parameter group sort order (UMaterialEditorOnlyData::ParameterGroupData, which the
	 *  material instance editor reads; lower comes first, groups without an entry sort as 0 and then by name).
	 *  UMaterialEditorOnlyData is not exposed to Python, so this is done here. Returns false if the arrays differ in length. */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static bool SetParameterGroupSortPriorities(UMaterial* Material, const TArray<FString>& GroupNames, const TArray<int32>& SortPriorities);

	/** Returns the material's parameter group sort order as group name -> priority (for verification). */
	UFUNCTION(BlueprintCallable, Category = "Dev|MaterialTools")
	static TMap<FString, int32> GetParameterGroupSortPriorities(UMaterial* Material);
};
