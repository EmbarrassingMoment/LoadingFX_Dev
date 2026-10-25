// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "DevSampleTools.generated.h"

class UBlueprint;
class UWidgetBlueprint;

/** Helpers that let Python move Blueprint content between engine versions as text: the UE 5.8 workbench
 *  exports what was drafted there, and the UE 5.5 sample builder imports it. Graphs and widget trees use
 *  the text that Ctrl+C / Ctrl+V use in the graph editor and the UMG designer; member variables use the
 *  property text of UBlueprint::NewVariables. Python cannot reach FEdGraphUtilities,
 *  FWidgetBlueprintEditorUtils or NewVariables, so that is done here. No engine modification is required. */
UCLASS()
class DEVSAMPLETOOLS_API UDevSampleTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Returns every node of the Blueprint's graph as copy text, leaving out disabled ghost nodes
	 *  (the greyed-out events a new Blueprint starts with) and nodes that cannot be copied
	 *  (a function's entry and result nodes, so only event graphs round-trip for now).
	 *  Empty if the Blueprint has no graph of that name. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static FString ExportGraphNodes(UBlueprint* Blueprint, FName GraphName);

	/** Deletes every node in the Blueprint's graph and imports the nodes in Text, keeping their positions and GUIDs.
	 *  Returns how many nodes were imported, or -1 if the Blueprint has no graph of that name. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static int32 ReplaceGraphNodes(UBlueprint* Blueprint, FName GraphName, const FString& Text);

	/** Returns the Blueprint's member variables (UBlueprint::NewVariables) as property text, with each
	 *  DefaultValue taken from the compiled class default object. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static FString ExportMemberVariables(UBlueprint* Blueprint);

	/** Replaces the Blueprint's member variables with the ones in Text.
	 *  Returns what the import reported (empty on a clean import), with "Error:" first if nothing was imported. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static TArray<FString> ReplaceMemberVariables(UBlueprint* Blueprint, const FString& Text);

	/** Returns the widget tree (the root widget and everything under it) as copy text. Empty if the tree is empty. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static FString ExportWidgetTree(UWidgetBlueprint* WidgetBlueprint);

	/** Replaces the widget tree with the widgets in Text; the one without a parent becomes the root.
	 *  Returns false, leaving the tree empty, if Text does not hold exactly one root widget. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static bool ReplaceWidgetTree(UWidgetBlueprint* WidgetBlueprint, const FString& Text);

	/** Compiles the Blueprint and returns its errors and warnings as "Error: ..." / "Warning: ..." lines
	 *  (empty when it compiled cleanly). */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static TArray<FString> CompileBlueprintWithMessages(UBlueprint* Blueprint);
};
