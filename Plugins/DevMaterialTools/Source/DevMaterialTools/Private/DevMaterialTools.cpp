// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#include "DevMaterialTools.h"

#include "MaterialEditingLibrary.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionComment.h"
#include "Materials/MaterialExpressionNamedReroute.h"
#include "Materials/MaterialFunction.h"

UMaterialExpressionNamedRerouteUsage* UDevMaterialTools::CreateNamedRerouteUsage(
	UMaterial* Material,
	UMaterialExpressionNamedRerouteDeclaration* Declaration,
	int32 NodePosX,
	int32 NodePosY)
{
	if (!Material || !Declaration)
	{
		return nullptr;
	}

	UMaterialExpression* Expression = UMaterialEditingLibrary::CreateMaterialExpression(
		Material, UMaterialExpressionNamedRerouteUsage::StaticClass(), NodePosX, NodePosY);

	UMaterialExpressionNamedRerouteUsage* Usage = Cast<UMaterialExpressionNamedRerouteUsage>(Expression);
	if (!Usage)
	{
		return nullptr;
	}

	Usage->Declaration = Declaration;
	Usage->DeclarationGuid = Declaration->VariableGuid;
	Usage->MarkPackageDirty();
	return Usage;
}

UMaterialExpressionNamedRerouteUsage* UDevMaterialTools::CreateNamedRerouteUsageInFunction(
	UMaterialFunction* MaterialFunction,
	UMaterialExpressionNamedRerouteDeclaration* Declaration,
	int32 NodePosX,
	int32 NodePosY)
{
	if (!MaterialFunction || !Declaration)
	{
		return nullptr;
	}

	UMaterialExpression* Expression = UMaterialEditingLibrary::CreateMaterialExpressionInFunction(
		MaterialFunction, UMaterialExpressionNamedRerouteUsage::StaticClass(), NodePosX, NodePosY);

	UMaterialExpressionNamedRerouteUsage* Usage = Cast<UMaterialExpressionNamedRerouteUsage>(Expression);
	if (!Usage)
	{
		return nullptr;
	}

	Usage->Declaration = Declaration;
	Usage->DeclarationGuid = Declaration->VariableGuid;
	Usage->MarkPackageDirty();
	return Usage;
}

FString UDevMaterialTools::GetNamedRerouteUsageDisplayName(UMaterialExpressionNamedRerouteUsage* Usage)
{
	if (!Usage || !IsValid(Usage->Declaration))
	{
		return FString();
	}
	return Usage->Declaration->Name.ToString();
}

UMaterialExpressionComment* UDevMaterialTools::CreateCommentInMaterial(
	UMaterial* Material,
	const FString& Text,
	int32 X, int32 Y, int32 SizeX, int32 SizeY,
	FLinearColor Color)
{
	if (!Material)
	{
		return nullptr;
	}

	UMaterialExpressionComment* Comment =
		NewObject<UMaterialExpressionComment>(Material, NAME_None, RF_Transactional);
	Comment->Material = Material;
	Comment->Text = Text;
	Comment->MaterialExpressionEditorX = X;
	Comment->MaterialExpressionEditorY = Y;
	Comment->SizeX = SizeX;
	Comment->SizeY = SizeY;
	Comment->CommentColor = Color;

	Material->GetExpressionCollection().AddComment(Comment);
	Material->MarkPackageDirty();
	return Comment;
}

bool UDevMaterialTools::SetParameterGroupSortPriorities(UMaterial* Material, const TArray<FString>& GroupNames, const TArray<int32>& SortPriorities)
{
	UMaterialEditorOnlyData* EditorOnlyData = Material ? Material->GetEditorOnlyData() : nullptr;
	if (!EditorOnlyData || GroupNames.Num() != SortPriorities.Num())
	{
		return false;
	}

	EditorOnlyData->ParameterGroupData.Reset();
	for (int32 Index = 0; Index < GroupNames.Num(); ++Index)
	{
		FParameterGroupData& GroupData = EditorOnlyData->ParameterGroupData.AddDefaulted_GetRef();
		GroupData.GroupName = GroupNames[Index];
		GroupData.GroupSortPriority = SortPriorities[Index];
	}
	Material->MarkPackageDirty();
	return true;
}

TMap<FString, int32> UDevMaterialTools::GetParameterGroupSortPriorities(UMaterial* Material)
{
	TMap<FString, int32> Priorities;
	if (const UMaterialEditorOnlyData* EditorOnlyData = Material ? Material->GetEditorOnlyData() : nullptr)
	{
		for (const FParameterGroupData& GroupData : EditorOnlyData->ParameterGroupData)
		{
			Priorities.Add(GroupData.GroupName, GroupData.GroupSortPriority);
		}
	}
	return Priorities;
}

TArray<FString> UDevMaterialTools::GetMaterialCommentTexts(UMaterial* Material)
{
	TArray<FString> Texts;
	if (Material)
	{
		for (const TObjectPtr<UMaterialExpressionComment>& Comment : Material->GetEditorComments())
		{
			if (Comment)
			{
				Texts.Add(Comment->Text);
			}
		}
	}
	return Texts;
}

namespace
{
	// Removes every comment from a collection. Copies the array first because
	// RemoveComment() mutates the array being iterated (the same pitfall that makes
	// MaterialEditingLibrary::DeleteAllMaterialExpressions skip every other node).
	int32 DeleteAllComments(FMaterialExpressionCollection& Collection)
	{
		TArray<TObjectPtr<UMaterialExpressionComment>> Comments = Collection.EditorComments;
		for (const TObjectPtr<UMaterialExpressionComment>& Comment : Comments)
		{
			if (Comment)
			{
				Collection.RemoveComment(Comment);
				Comment->MarkAsGarbage();
			}
		}
		return Comments.Num();
	}
}

int32 UDevMaterialTools::DeleteAllCommentsInMaterial(UMaterial* Material)
{
	if (!Material)
	{
		return 0;
	}
	const int32 Count = DeleteAllComments(Material->GetExpressionCollection());
	if (Count > 0)
	{
		Material->MarkPackageDirty();
	}
	return Count;
}

int32 UDevMaterialTools::DeleteAllCommentsInFunction(UMaterialFunction* MaterialFunction)
{
	if (!MaterialFunction)
	{
		return 0;
	}
	const int32 Count = DeleteAllComments(MaterialFunction->GetExpressionCollection());
	if (Count > 0)
	{
		MaterialFunction->MarkPackageDirty();
	}
	return Count;
}

UMaterialExpressionComment* UDevMaterialTools::CreateCommentInFunction(
	UMaterialFunction* MaterialFunction,
	const FString& Text,
	int32 X, int32 Y, int32 SizeX, int32 SizeY,
	FLinearColor Color)
{
	if (!MaterialFunction)
	{
		return nullptr;
	}

	UMaterialExpressionComment* Comment =
		NewObject<UMaterialExpressionComment>(MaterialFunction, NAME_None, RF_Transactional);
	Comment->Function = MaterialFunction;
	Comment->Text = Text;
	Comment->MaterialExpressionEditorX = X;
	Comment->MaterialExpressionEditorY = Y;
	Comment->SizeX = SizeX;
	Comment->SizeY = SizeY;
	Comment->CommentColor = Color;

	MaterialFunction->GetExpressionCollection().AddComment(Comment);
	MaterialFunction->MarkPackageDirty();
	return Comment;
}

TArray<FString> UDevMaterialTools::GetFunctionCommentTexts(UMaterialFunction* MaterialFunction)
{
	TArray<FString> Texts;
	if (MaterialFunction)
	{
		for (const TObjectPtr<UMaterialExpressionComment>& Comment : MaterialFunction->GetEditorComments())
		{
			if (Comment)
			{
				Texts.Add(Comment->Text);
			}
		}
	}
	return Texts;
}

FVector4 UDevMaterialTools::GetCommentBounds(UMaterialExpressionComment* Comment)
{
	if (!Comment)
	{
		return FVector4(0, 0, 0, 0);
	}
	return FVector4(Comment->MaterialExpressionEditorX, Comment->MaterialExpressionEditorY,
	                Comment->SizeX, Comment->SizeY);
}

TArray<UMaterialExpressionComment*> UDevMaterialTools::GetMaterialComments(UMaterial* Material)
{
	TArray<UMaterialExpressionComment*> Comments;
	if (Material)
	{
		for (const TObjectPtr<UMaterialExpressionComment>& Comment : Material->GetEditorComments())
		{
			if (Comment)
			{
				Comments.Add(Comment);
			}
		}
	}
	return Comments;
}

TArray<UMaterialExpressionComment*> UDevMaterialTools::GetFunctionComments(UMaterialFunction* MaterialFunction)
{
	TArray<UMaterialExpressionComment*> Comments;
	if (MaterialFunction)
	{
		for (const TObjectPtr<UMaterialExpressionComment>& Comment : MaterialFunction->GetEditorComments())
		{
			if (Comment)
			{
				Comments.Add(Comment);
			}
		}
	}
	return Comments;
}

void UDevMaterialTools::SetMaterialRootPosition(UMaterial* Material, int32 X, int32 Y)
{
	if (Material)
	{
		Material->EditorX = X;
		Material->EditorY = Y;
		Material->MarkPackageDirty();
	}
}

FIntPoint UDevMaterialTools::GetMaterialRootPosition(UMaterial* Material)
{
	return Material ? FIntPoint(Material->EditorX, Material->EditorY) : FIntPoint::ZeroValue;
}

TArray<UMaterialExpression*> UDevMaterialTools::GetMaterialExpressions(UMaterial* Material)
{
	TArray<UMaterialExpression*> Expressions;
	if (Material)
	{
		for (const TObjectPtr<UMaterialExpression>& Expression : Material->GetExpressions())
		{
			Expressions.Add(Expression);
		}
	}
	return Expressions;
}

TArray<UMaterialExpression*> UDevMaterialTools::GetMaterialFunctionExpressions(UMaterialFunction* MaterialFunction)
{
	TArray<UMaterialExpression*> Expressions;
	if (MaterialFunction)
	{
		for (const TObjectPtr<UMaterialExpression>& Expression : MaterialFunction->GetExpressions())
		{
			Expressions.Add(Expression);
		}
	}
	return Expressions;
}
