# LoadingFX

[![Unreal Engine](https://img.shields.io/badge/Unreal%20Engine-5.5%2B-black?style=flat&logo=unrealengine&logoColor=white)](https://www.unrealengine.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Win64-blue?style=flat&logo=windows&logoColor=white)](#動作環境)

> English version → [README.md](README.md)

> **開発中** — このプラグインは現在開発中で、まだリリースされていません。

## 概要

LoadingFX は Unreal Engine 5 向けのローディング表示プラグインです。プロシージャルなマテリアル製スピナー集、どこからでも表示・非表示できるローディングアイコン、軽量なアセット読み込み管理を提供します。ローディングアイコンと読み込み管理は独立しており、どちらか片方だけでも、組み合わせても使えます。

## 予定している機能

- **スピナーマテリアル集** — テクスチャを使わないプロシージャル（SDF）なスピナーマテリアル。標準の UMG `Image` に貼る、同梱の UMG スピナーウィジェットで使う、プロジェクト共通のローディングアイコンとして使う、のいずれにも対応します。
- **ローディングアイコン Subsystem** — Blueprint / C++ のどこからでもローディングアイコンを表示・非表示できます。表示要求は参照カウントで管理するので、複数のシステムが同時に使っても安全です。マップ遷移をまたいでも表示が消えません。
- **ブロッキングロード中も回り続ける** — `OpenLevel` などでゲームスレッドが止まっている間も、アイコンのアニメーションが止まりません。エンジンの MoviePlayer を使う仕組みのため、エディタ / PIE では利用できず、その間はアイコンが止まります。`-game` またはパッケージ版で確認してください。
- **軽量なアセット読み込み管理** — 完了コールバックと進捗付きの非同期・同期アセットロード。ローディングアイコンと自動で連携させることも、単体で使うこともできます。

## 動作環境

- Unreal Engine 5.5 – 5.8
- Windows (Win64)

## リポジトリ構成

| パス | 内容 |
|------|------|
| `Plugins/LoadingFX/` | LoadingFX プラグイン本体（Fab で配布するもの） |
| `Source/LoadingFX_Dev/`, `Content/` | サンプルプロジェクトと実装サンプル |

## ライセンス

[MIT](LICENSE)
