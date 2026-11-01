// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "DevSampleTools.h"

#include "ActorEditorUtils.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Widget.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraphUtilities.h"
#include "Editor/UnrealEdEngine.h"
#include "Engine/Blueprint.h"
#include "Engine/Level.h"
#include "Engine/LevelScriptActor.h"
#include "Engine/LevelScriptBlueprint.h"
#include "Engine/World.h"
#include "Factories.h"
#include "GameFramework/Actor.h"
#include "GameFramework/WorldSettings.h"
#include "K2Node_FunctionTerminator.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "UObject/Package.h"
#include "UObject/UObjectHash.h"
#include "UnrealEdGlobals.h"
#include "WidgetBlueprint.h"
#include "WidgetBlueprintEditorUtils.h"

namespace DevSampleTools
{
	UEdGraph* FindGraph(UBlueprint* Blueprint, FName GraphName)
	{
		if (!Blueprint)
		{
			return nullptr;
		}

		TArray<UEdGraph*> Graphs;
		Blueprint->GetAllGraphs(Graphs);
		for (UEdGraph* Graph : Graphs)
		{
			if (Graph && Graph->GetFName() == GraphName)
			{
				return Graph;
			}
		}
		return nullptr;
	}

	FArrayProperty* GetNewVariablesProperty()
	{
		return FindFProperty<FArrayProperty>(UBlueprint::StaticClass(), GET_MEMBER_NAME_CHECKED(UBlueprint, NewVariables));
	}

	TArray<FString> SplitLines(const FString& Text)
	{
		TArray<FString> Lines;
		Text.ParseIntoArrayLines(Lines);
		return Lines;
	}

	/** FEdGraphUtilities::ImportNodesFromText's factory, except that a function's entry and result nodes are created
	 *  too (a paste skips nodes that cannot be duplicated): the graph is replaced as a whole, terminators included. */
	struct FGraphTextFactory : public FCustomizableTextObjectFactory
	{
		const UEdGraph* DestinationGraph;
		TSet<UEdGraphNode*> SpawnedNodes;

		explicit FGraphTextFactory(const UEdGraph* InDestinationGraph)
			: FCustomizableTextObjectFactory(GWarn)
			, DestinationGraph(InDestinationGraph)
		{
		}

	protected:
		virtual bool CanCreateClass(UClass* ObjectClass, bool& bOmitSubObjs) const override
		{
			const UEdGraphNode* DefaultNode = Cast<UEdGraphNode>(ObjectClass->GetDefaultObject());
			if (!DefaultNode)
			{
				return false;
			}
			bOmitSubObjs = true;
			return (DefaultNode->CanDuplicateNode() || DefaultNode->IsA<UK2Node_FunctionTerminator>())
				&& DefaultNode->CanCreateUnderSpecifiedSchema(DestinationGraph->GetSchema());
		}

		virtual void ProcessConstructedObject(UObject* CreatedObject) override
		{
			if (UEdGraphNode* Node = Cast<UEdGraphNode>(CreatedObject))
			{
				SpawnedNodes.Add(Node);
				Node->GetGraph()->Nodes.Add(Node);
			}
		}
	};

	TArray<AActor*> GetLevelActors(UWorld* World)
	{
		TArray<AActor*> Actors;
		if (World && World->PersistentLevel)
		{
			for (AActor* Actor : World->PersistentLevel->Actors)
			{
				// The same actors that UUnrealEdEngine::CopyActors leaves out, plus transient ones and the Level
				// Blueprint's actor, which belongs to the level (its Blueprint travels through the graph functions).
				if (Actor && !Actor->HasAnyFlags(RF_Transient) && !Actor->IsA<AWorldSettings>() && !Actor->IsA<ALevelScriptActor>()
					&& !FActorEditorUtils::IsABuilderBrush(Actor))
				{
					Actors.Add(Actor);
				}
			}
		}
		return Actors;
	}
}

FString UDevSampleTools::ExportGraphNodes(UBlueprint* Blueprint, FName GraphName)
{
	UEdGraph* Graph = DevSampleTools::FindGraph(Blueprint, GraphName);
	if (!Graph)
	{
		return FString();
	}

	// Same as Ctrl+C in the graph editor (FBlueprintEditor::CopySelectedNodes) with every node selected,
	// plus a function's entry and result nodes, which carry its signature.
	TSet<UObject*> Nodes;
	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if (Node && !Node->IsAutomaticallyPlacedGhostNode() && (Node->CanDuplicateNode() || Node->IsA<UK2Node_FunctionTerminator>()))
		{
			Node->PrepareForCopying();
			Nodes.Add(Node);
		}
	}

	FString Text;
	FEdGraphUtilities::ExportNodesToText(Nodes, Text);
	return Text;
}

int32 UDevSampleTools::ReplaceGraphNodes(UBlueprint* Blueprint, FName GraphName, const FString& Text)
{
	UEdGraph* Graph = DevSampleTools::FindGraph(Blueprint, GraphName);
	if (!Graph)
	{
		return -1;
	}

	// Ghost nodes go too: an imported event identical to a ghost would not compile next to it.
	Graph->Modify();
	for (UEdGraphNode* Node : TArray<UEdGraphNode*>(Graph->Nodes))
	{
		FBlueprintEditorUtils::RemoveNode(Blueprint, Node, /*bDontRecompile*/ true);
	}

	// Same as Ctrl+V (FBlueprintEditor::PasteNodesHere through FEdGraphUtilities::ImportNodesFromText), except that
	// function terminators come along and the nodes keep their positions and GUIDs, so a rebuilt graph matches the
	// one it was exported from.
	DevSampleTools::FGraphTextFactory Factory(Graph);
	Factory.ProcessBuffer(Graph, RF_Transactional, Text);
	FEdGraphUtilities::PostProcessPastedNodes(Factory.SpawnedNodes);
	UEdGraphPin::ResolveAllPinReferences();

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	return Factory.SpawnedNodes.Num();
}

TArray<FName> UDevSampleTools::GetFunctionGraphNames(UBlueprint* Blueprint)
{
	TArray<FName> Names;
	if (Blueprint)
	{
		for (const UEdGraph* Graph : Blueprint->FunctionGraphs)
		{
			if (Graph)
			{
				Names.Add(Graph->GetFName());
			}
		}
	}
	return Names;
}

FString UDevSampleTools::ExportMemberVariables(UBlueprint* Blueprint)
{
	FArrayProperty* Property = DevSampleTools::GetNewVariablesProperty();
	if (!Blueprint || !Property)
	{
		return FString();
	}

	// A full compile copies DefaultValue to the class default object and clears it, so the current
	// defaults live on the CDO. Write them back into the exported copy for the importing compile.
	TArray<FBPVariableDescription> Variables = Blueprint->NewVariables;
	UObject* DefaultObject = Blueprint->GeneratedClass ? Blueprint->GeneratedClass->GetDefaultObject() : nullptr;
	for (FBPVariableDescription& Variable : Variables)
	{
		const FProperty* VariableProperty = DefaultObject ? FindFProperty<FProperty>(Blueprint->GeneratedClass, Variable.VarName) : nullptr;
		if (VariableProperty)
		{
			FBlueprintEditorUtils::PropertyValueToString(VariableProperty, reinterpret_cast<const uint8*>(DefaultObject), Variable.DefaultValue, DefaultObject);
		}
	}

	FString Text;
	Property->ExportText_Direct(Text, &Variables, nullptr, Blueprint, PPF_None);
	return Text;
}

TArray<FString> UDevSampleTools::ReplaceMemberVariables(UBlueprint* Blueprint, const FString& Text)
{
	FArrayProperty* Property = DevSampleTools::GetNewVariablesProperty();
	if (!Blueprint || !Property)
	{
		return { TEXT("Error: no Blueprint.") };
	}

	TArray<FBPVariableDescription> Variables;
	FStringOutputDevice Errors;
	if (!Property->ImportText_Direct(*Text, &Variables, Blueprint, PPF_None, &Errors))
	{
		TArray<FString> Messages = DevSampleTools::SplitLines(Errors);
		Messages.Insert(TEXT("Error: the variables could not be imported."), 0);
		return Messages;
	}

	Blueprint->Modify();
	Blueprint->NewVariables = MoveTemp(Variables);
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	return DevSampleTools::SplitLines(Errors);
}

FString UDevSampleTools::ExportWidgetTree(UWidgetBlueprint* WidgetBlueprint)
{
	UWidget* Root = WidgetBlueprint && WidgetBlueprint->WidgetTree ? WidgetBlueprint->WidgetTree->RootWidget.Get() : nullptr;
	if (!Root)
	{
		return FString();
	}

	// Same as Ctrl+C in the UMG designer with the root widget selected (FWidgetBlueprintEditorUtils::CopyWidgetsInternal).
	TArray<UWidget*> Widgets = { Root };
	UWidgetTree::GetChildWidgets(Root, Widgets);

	FString Text;
	FWidgetBlueprintEditorUtils::ExportWidgetsToText(Widgets, Text);
	return Text;
}

bool UDevSampleTools::ReplaceWidgetTree(UWidgetBlueprint* WidgetBlueprint, const FString& Text)
{
	UWidgetTree* Tree = WidgetBlueprint ? WidgetBlueprint->WidgetTree.Get() : nullptr;
	if (!Tree)
	{
		return false;
	}

	// Move the old widgets out of the tree, so that the imported ones keep their names
	// (ImportWidgetsFromText renames a widget whose name is taken).
	Tree->Modify();
	Tree->RootWidget = nullptr;
	Tree->NamedSlotBindings.Empty();
	// Widgets are outered to the tree; the nested objects (panel slots) are skipped by the cast.
	TArray<UObject*> OldObjects;
	GetObjectsWithOuter(Tree, OldObjects);
	for (UObject* Object : OldObjects)
	{
		if (UWidget* Widget = Cast<UWidget>(Object))
		{
			Widget->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional);
		}
	}

	TSet<UWidget*> ImportedWidgets;
	TMap<FName, UWidgetSlotPair*> ExtraSlotData;
	FWidgetBlueprintEditorUtils::ImportWidgetsFromText(WidgetBlueprint, Text, ImportedWidgets, ExtraSlotData);

	// The root is the one widget without a parent; the rest came in through their panels.
	TArray<UWidget*> Roots;
	for (UWidget* Widget : ImportedWidgets)
	{
		if (Widget && !Widget->GetParent())
		{
			Roots.Add(Widget);
		}
	}

	if (Roots.Num() == 1)
	{
		Tree->RootWidget = Roots[0];
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WidgetBlueprint);
	return Roots.Num() == 1;
}

TArray<FString> UDevSampleTools::CompileBlueprintWithMessages(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		return { TEXT("Error: no Blueprint.") };
	}

	FCompilerResultsLog Results;
	Results.SetSourcePath(Blueprint->GetPathName());
	FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::SkipGarbageCollection, &Results);

	TArray<FString> Messages;
	for (const TSharedRef<FTokenizedMessage>& Message : Results.Messages)
	{
		const EMessageSeverity::Type Severity = Message->GetSeverity();
		if (Severity == EMessageSeverity::Error)
		{
			Messages.Add(TEXT("Error: ") + Message->ToText().ToString());
		}
		else if (Severity == EMessageSeverity::Warning || Severity == EMessageSeverity::PerformanceWarning)
		{
			Messages.Add(TEXT("Warning: ") + Message->ToText().ToString());
		}
	}
	return Messages;
}

UBlueprint* UDevSampleTools::GetLevelBlueprint(UWorld* World)
{
	return World && World->PersistentLevel ? World->PersistentLevel->GetLevelScriptBlueprint(/*bDontCreate*/ false) : nullptr;
}

FString UDevSampleTools::ExportLevelActors(UWorld* World)
{
	if (!GUnrealEd || !World)
	{
		return FString();
	}

	FString Text;
	GUnrealEd->CopyActors(DevSampleTools::GetLevelActors(World), World, &Text);
	return Text;
}

int32 UDevSampleTools::ReplaceLevelActors(UWorld* World, const FString& Text)
{
	if (!GUnrealEd || !World)
	{
		return 0;
	}

	for (AActor* Actor : DevSampleTools::GetLevelActors(World))
	{
		World->EditorDestroyActor(Actor, /*bShouldModifyLevel*/ true);
	}

	TArray<AActor*> PastedActors;
	GUnrealEd->PasteActors(PastedActors, World, FVector::ZeroVector, /*bDuplicate*/ false, /*bWarnIfHidden*/ false, &Text);
	return PastedActors.Num();
}
