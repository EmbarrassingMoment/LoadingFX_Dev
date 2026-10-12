// Copyright (c) 2026 Kurorekishi (EmbarrassingMoment).

#pragma once

#include "CoreMinimal.h"
#include "UObject/SoftObjectPath.h"
#include "UObject/SoftObjectPtr.h"

/** Shared by the Blueprint entry points, which take soft object and soft class references as two arrays. */
namespace LoadingFXLoaderPaths
{
	/** One path per entry, Assets first, then Classes. */
	inline TArray<FSoftObjectPath> MakePaths(const TArray<TSoftObjectPtr<UObject>>& Assets, const TArray<TSoftClassPtr<UObject>>& Classes)
	{
		TArray<FSoftObjectPath> Paths;
		Paths.Reserve(Assets.Num() + Classes.Num());
		for (const TSoftObjectPtr<UObject>& Asset : Assets)
		{
			Paths.Add(Asset.ToSoftObjectPath());
		}
		for (const TSoftClassPtr<UObject>& Class : Classes)
		{
			Paths.Add(Class.ToSoftObjectPath());
		}
		return Paths;
	}

	/** Splits results made from MakePaths back into the two arrays. */
	inline void SplitLoaded(const TArray<UObject*>& Loaded, int32 NumAssets, TArray<UObject*>& OutAssets, TArray<UClass*>& OutClasses)
	{
		OutAssets.Reset();
		OutClasses.Reset();
		for (int32 Index = 0; Index < Loaded.Num(); ++Index)
		{
			if (Index < NumAssets)
			{
				OutAssets.Add(Loaded[Index]);
			}
			else
			{
				OutClasses.Add(Cast<UClass>(Loaded[Index]));
			}
		}
	}
}
