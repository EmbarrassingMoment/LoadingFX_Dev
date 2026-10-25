// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "DevSampleTools.generated.h"

class UBlueprint;
class UWidgetBlueprint;

/** Helpers that let Python move Blueprints and levels between engine versions as text: the UE 5.8 workbench
 *  exports what was drafted there, and the UE 5.5 sample builder imports it. Graphs, widget trees and level
 *  actors use the text that Ctrl+C / Ctrl+V use in the graph editor, the UMG designer and the level editor;
 *  member variables use the property text of UBlueprint::NewVariables. Python cannot reach FEdGraphUtilities,
 *  FWidgetBlueprintEditorUtils, UUnrealEdEngine::CopyActors / PasteActors, NewVariables or a level's Level
 *  Blueprint, so that is done here. No engine modification is required. */
UCLASS()
class DEVSAMPLETOOLS_API UDevSampleTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Returns every node of the Blueprint's graph (an event graph or a function) as copy text, including a
	 *  function's entry and result nodes and leaving out disabled ghost nodes (the greyed-out events a new
	 *  Blueprint starts with). Empty if the Blueprint has no graph of that name. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static FString ExportGraphNodes(UBlueprint* Blueprint, FName GraphName);

	/** Deletes every node in the Blueprint's graph and imports the nodes in Text, keeping their positions and GUIDs.
	 *  A function's entry and result nodes are replaced too, so its signature comes from Text.
	 *  Returns how many nodes were imported, or -1 if the Blueprint has no graph of that name. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static int32 ReplaceGraphNodes(UBlueprint* Blueprint, FName GraphName, const FString& Text);

	/** Returns the names of the Blueprint's function graphs (Python cannot list them). */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static TArray<FName> GetFunctionGraphNames(UBlueprint* Blueprint);

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

	/** Returns the Level Blueprint of the world's persistent level, creating it if the level has none yet.
	 *  The graph and variable functions above work on it like on any Blueprint. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static UBlueprint* GetLevelBlueprint(UWorld* World);

	/** Returns the actors of the world's persistent level as level editor copy text (Ctrl+C with every actor selected),
	 *  leaving out World Settings, the builder brush, the Level Blueprint's actor and transient actors. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static FString ExportLevelActors(UWorld* World);

	/** Deletes the actors that ExportLevelActors would export and pastes the actors in Text, at their exported
	 *  locations. Returns how many actors were pasted. */
	UFUNCTION(BlueprintCallable, Category = "Dev|SampleTools")
	static int32 ReplaceLevelActors(UWorld* World, const FString& Text);
};
