# ore-music-player 設計書

この文書は、現在の実装状況、合意した製品要件、アーキテクチャを記録する。未検証の技術選択は確定事項として扱わない。

## ステータス

- ドメイン層、再生制御、プレイリスト管理のアプリケーション層は実装済み。
- 実音声バックエンド、永続化、UI、起動処理は未実装。
- 現時点ではアプリを起動して音声を再生することはできない。
- 対象はデスクトップとタブレットでのタッチ操作。
- 画面上の各要素は大きくし、ホバー操作や小さなアイコンだけに依存しない。

## 実装状況

| 領域 | 状態 | 内容 |
| --- | --- | --- |
| ドメインモデル | 実装済み | `Track`、`LoopRegion`、`PlaybackSettings`、速度と位置の検証 |
| 再生状態 | 実装済み | 再生、一時停止、停止、シーク、A/Bポイント、ループ状態 |
| 再生サービス | 実装済み | `PlaybackService` と `PlaybackBackend` 契約の同期 |
| ドメイン・サービスのテスト | 実装済み | pytest 20件。再生状態、再生サービス、プレイリスト、プレイリストサービスを検証 |
| プレイリスト | 一部実装済み | `Playlist` モデル、曲順操作、`PlaylistService`、ユニットテスト。キュー統合と永続化は未実装 |
| 永続化 | 未実装 | SQLiteスキーマ、リポジトリ、統合テスト |
| 音声再生 | 未実装 | バックエンド選定、実音声、シーク、タイムストレッチ |
| アプリ起動 | 未実装 | `app.py`、`bootstrap.py`、`__main__.py` |
| UI | 未実装 | PySide6の再生画面とプレイリスト画面 |
| 分析 | 未実装 | 音源分離、パート音量、コード進行分析 |

## 現在のスキャフォールド

```text
ore-music-player/
├── AGENTS.md
├── DESIGN.md
├── README.md
├── pyproject.toml
├── .gitignore
├── src/
│   └── ore_music_player/
│       ├── __init__.py
│       ├── app.py
│       ├── bootstrap.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   └── playback_state.py
│       ├── application/
│       │   ├── __init__.py
│       │   ├── playback_service.py
│       │   ├── playlist_service.py
│       │   └── ports.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── audio/
│       │   │   ├── __init__.py
│       │   │   └── playback_backend.py
│       │   ├── persistence/
│       │   │   ├── __init__.py
│       │   │   └── sqlite_repository.py
│       │   └── analysis/
│       │       ├── __init__.py
│       │       ├── separation.py
│       │       └── chord_analysis.py
│       └── ui/
│           ├── __init__.py
│           ├── main_window.py
│           └── playlist_view.py
└── tests/
    ├── unit/
    │   ├── test_playback_state.py
  │   ├── test_playback_service.py
    │   ├── test_playlist.py
    │   └── test_playlist_service.py
    └── integration/
        └── test_sqlite_repository.py
```

`.venv/` と `.git/` はローカル環境・Git管理用であり、アプリケーションの構成には含めない。空のファイルは未実装のプレースホルダーであり、実装済みのファイルは上記の実装状況に従う。

## ソースファイルの責務

### パッケージ入口

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/__init__.py` | パッケージの公開 API を定義する。必要な場合だけ公開型を再エクスポートする。 | QApplication の生成、ファイル読み込み、再生開始などの副作用。 |
| `src/ore_music_player/__main__.py` | `python -m ore_music_player` の入口。`main()` を定義し、アプリ起動処理を `app.py` へ渡す。 | プレイリスト処理、音声処理、画面部品の詳細。 |
| `src/ore_music_player/app.py` | QApplication の生成、アプリケーションのライフサイクル、終了コードの管理を行う。 | サービスの具体的な組み立て。依存関係の配線は `bootstrap.py` に任せる。 |
| `src/ore_music_player/bootstrap.py` | 再生バックエンド、SQLite リポジトリ、アプリケーションサービス、UI を組み立てて接続する。 | ドメインルール、個別の画面レイアウト、SQLの詳細。 |

### ドメイン層

ドメイン層は PySide6、libmpv、SQLite、ファイルダイアログを import しない。音声デバイスやファイルシステムがなくても単体テストできる状態を保つ。

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/domain/__init__.py` | ドメインモデルの公開 API をまとめる。 | アプリ起動や外部 I/O。 |
| `src/ore_music_player/domain/models.py` | `Track`、`Playlist`、`PlaylistItem`、`PlaybackQueue`、`LoopRegion`、`PlaybackSettings` などの値と不変条件を定義する。 | SQLiteへの保存、音声デコード、Qtウィジェット。 |
| `src/ore_music_player/domain/playback_state.py` | 再生中・一時停止・停止、現在位置、速度、A/B区間、曲の切り替えに関する状態遷移とルールを定義する。 | 実際の音声を再生すること、タイマー、UI更新。 |

### アプリケーション層

アプリケーション層は「ユーザーが何をしたいか」をユースケースとして表現する。UIや具体的な外部ライブラリではなく、ドメインと `ports.py` に依存する。

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/application/__init__.py` | アプリケーションサービスの公開 API をまとめる。 | 起動処理や画面生成。 |
| `src/ore_music_player/application/playback_service.py` | 現在の曲の再生、一時停止、停止、シーク、A/B設定、速度変更を調整する。将来は再生キュー操作を追加する。 | libmpv の API を直接呼ぶこと、ボタンの見た目。 |
| `src/ore_music_player/application/playlist_service.py` | プレイリストの作成、名前変更、削除、曲追加、フォルダ追加、曲削除、並べ替え、保存、読み込みを調整する。 | SQL文、ファイルダイアログ、UIレイアウト。 |
| `src/ore_music_player/application/ports.py` | `PlaybackBackend`、`PlaylistRepository`、音源スキャナー、分析ジョブ実行器など、外部実装が満たす契約を定義する。 | 契約の具体的な実装、QtやSQLiteの import。 |

### インフラストラクチャ層

インフラストラクチャ層は、アプリケーション層が定義した契約の具体的な実装を置く。外部ライブラリや OS の違いはこの層に閉じ込める。

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/infrastructure/__init__.py` | インフラ実装の公開 API をまとめる。 | ドメインルールや画面操作。 |
| `src/ore_music_player/infrastructure/audio/__init__.py` | 音声バックエンド実装の公開 API をまとめる。 | 再生キューやプレイリストの管理。 |
| `src/ore_music_player/infrastructure/audio/playback_backend.py` | 採用した再生エンジンをラップする。デコード、音声出力、シーク、再生位置、A/B境界、ピッチ維持タイムストレッチを扱う。 | プレイリストの保存、Qt画面の操作、分析結果の表示。 |
| `src/ore_music_player/infrastructure/persistence/__init__.py` | 永続化実装の公開 API をまとめる。 | SQLスキーマ以外のドメイン判断。 |
| `src/ore_music_player/infrastructure/persistence/sqlite_repository.py` | SQLiteの接続、テーブル作成、プレイリスト、曲順、音源情報、分析結果の保存・取得を実装する。 | UIイベント、音声デコード、分析モデルの実行。 |
| `src/ore_music_player/infrastructure/analysis/__init__.py` | 分析実装の公開 API をまとめる。 | 再生ボタンの処理。 |
| `src/ore_music_player/infrastructure/analysis/separation.py` | 将来の音源分離モデルをバックグラウンドジョブとして呼び出し、StemSet と生成ファイルのメタデータを返す。 | UIスレッドでの同期実行、プレイリスト画面の表示。 |
| `src/ore_music_player/infrastructure/analysis/chord_analysis.py` | 将来のコード進行分析をバックグラウンドジョブとして実行し、時間軸付きの分析結果を返す。 | 再生制御、UIの直接更新。 |

### UI層

UI層は表示とユーザー入力の変換だけを担当する。SQLiteや再生エンジンを直接呼ばず、アプリケーションサービスを通じて操作する。

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/ui/__init__.py` | UI部品の公開 API をまとめる。 | ドメイン状態の所有、DB接続。 |
| `src/ore_music_player/ui/main_window.py` | 上部タブ、再生画面、タッチしやすい再生コントロール、速度スライダー、現在キューを構成する。 | 音声データの加工、SQL、分析モデルの実行。 |
| `src/ore_music_player/ui/playlist_view.py` | プレイリスト一覧、曲一覧、新規作成、編集、削除、曲順変更、プレイリスト再生の操作画面を構成する。 | プレイリストの保存処理、ファイルの直接走査。 |

### テスト

| ファイル | 担当すること |
| --- | --- |
| `tests/unit/test_playback_state.py` | 速度範囲、刻み、A/B区間、再生状態遷移、曲終了時のルールを外部機器なしで検証する。 |
| `tests/unit/test_playback_service.py` | ダミーバックエンドを使い、再生制御とドメイン状態の同期を検証する。 |
| `tests/unit/test_playlist.py` | プレイリストの作成、順序、追加・削除、重複、キュー生成のルールを検証する。 |
| `tests/unit/test_playlist_service.py` | Fakeリポジトリを使い、プレイリストの作成、取得、更新、削除を検証する。 |
| `tests/integration/test_sqlite_repository.py` | 一時SQLiteデータベースに対する保存、読み込み、更新、再起動後の復元を検証する。 |

音声バックエンドの実機検証は、音声デバイスや再生エンジンが必要になるため、ドメイン単体テストとは分離する。

## 起動と依存関係の流れ

`src` レイアウトを使用するため、開発環境へ editable install してからモジュールとして起動する。

```text
python -m ore_music_player
  -> ore_music_player.__main__.main()
  -> app.run()
  -> bootstrap.build_application()
  -> QApplication と MainWindow を生成
  -> event loop を開始
```

開発後の基本コマンドは次のとおりとする。

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m ore_music_player
```

`__main__.py` が空の間は起動できない。コンソールスクリプト名 `ore-music-player` は、入口の `main()` を実装して動作確認した後に `pyproject.toml` へ登録する。

現在の最小検証コマンドは次のとおりである。

```powershell
python -m pytest -q
python -m ruff check src tests
```

## 依存方向と禁止事項

```text
ui -> application -> domain
                    ^
                    |
          infrastructure implements ports

bootstrap -> ui + application + infrastructure
```

- `domain` は他の層を import しない。
- `application` は `domain` と `application.ports` に依存する。
- `infrastructure` は `ports` の実装を提供する。
- `ui` は `application` を呼び出すだけで、SQLiteや再生バックエンドを直接操作しない。
- `bootstrap` 以外で具体的な実装を手作業で生成しない。
- 音源分離、コード分析、データベース処理で UI スレッドをブロックしない。
- 個人環境の音楽フォルダ、OS固有パス、認証情報をソースにハードコードしない。

## 確定要件

### 最初に必要な機能

- 音楽ファイルを1曲以上読み込んで再生する。
- フォルダを1つ以上読み込んで再生する。
- 保存済みプレイリストを選択して再生する。
- A/B区間を指定してループする。
- 再生速度を変更する。
- 速度を変更しても音程を維持するタイムストレッチを使う。
- プレイリストを作成、編集、保存、削除する。

### 再生速度

- 範囲は `0.50x` から `1.50x`。
- 刻みは `0.05x`。
- 初期値は `1.00x`。
- 再生中に変更できる。
- 速度変更中も音程を維持する。
- A/Bループ中も速度変更を有効にする。

### 再生コントロール

- A設定、B設定、A/Bループ切り替えは再生ボタン付近に配置する。
- 再生、停止、一時停止、前後移動、A/B操作をタッチしやすい大きさにする。
- 速度はスライダーで操作する。
- 再生画面とプレイリスト画面は上部の大きなタブで切り替える。

## 音源の読み込み

### ファイル読み込み

- 複数ファイルを選択できる。
- 選択したファイルだけを現在の再生キューにする。

### フォルダ読み込み

- 標準ではフォルダ直下の音楽ファイルを対象にする。
- 読み込み時にサブフォルダも検索するか確認する。
- 複数フォルダを選択できる。
- 対応していないファイルは読み込み対象外にする。

### プレイリスト再生

- 保存済みプレイリストを管理画面から選択する。
- プレイリストの曲を現在の再生キューへ読み込んで再生画面へ移動する。
- 保存済みプレイリストと現在の再生キューは別の状態として扱う。
- 移動・削除された音源は警告表示し、再生時はスキップできるようにする。

## 画面構成

### 再生画面

- 現在の曲名と再生状態
- 再生位置とシーク操作
- 再生、一時停止、停止、前後移動
- A設定、B設定、A/Bループ
- `0.50x`〜`1.50x` の速度スライダー
- 現在の再生キュー

### プレイリスト管理画面

- 左側または上側に保存済みプレイリスト一覧
- 選択したプレイリストの曲一覧
- 新規作成、名前変更、削除
- 曲の追加、フォルダからの追加、曲の削除
- 曲順の変更
- プレイリスト全体の再生

## アーキテクチャ

画面から音声バックエンドを直接操作しない。次の責務を分離する。

```text
UI
  -> Application services
  -> Domain state
  -> Playback controller
  -> Audio source / mixer / time-stretch
  -> Audio output
```

### ドメイン状態

- `Track`
- `Playlist`
- `PlaybackQueue`
- `PlaybackState`
- `LoopRegion`
- `PlaybackSettings`
- 将来の `StemSet` と `AnalysisResult`

A/B区間と速度はウィジェット固有の状態にせず、テスト可能なアプリケーション状態として保持する。

### 音声処理パイプライン

通常の音源:

```text
音源ファイル -> デコード -> ピッチ維持タイムストレッチ -> 音声出力
```

音源分離後:

```text
各パート -> パート別音量調整 -> ミックス -> タイムストレッチ -> 音声出力
```

音源分離とコード分析はバックグラウンドジョブとして実行し、UIスレッドと再生スレッドをブロックしない。

## 保存

SQLite にプレイリスト、曲順、音源情報、分析ジョブ状態、分析結果を保存する。分離済み音源などの生成物はファイルキャッシュに保存し、データベースにはパスとメタデータだけを保存する。

## 技術選択

### 確定している基準

- Python 3.13
- SQLite

### 現在の提案

- GUI: PySide6
- 再生: libmpv 系バックエンド

### 実装前に検証すること

- Python 3.13 用 wheel の有無
- 対応音声形式
- 正確なシーク
- A/Bループ境界
- `0.50x`〜`1.50x` の速度変更
- 速度変更時のピッチ維持
- Windows とタブレット環境での音声出力

未検証の再生バックエンドは、検証が終わるまで実行時必須依存にしない。

## 将来機能

- 音源分離
- パートごとの音量変更
- コード進行分析
- 分析結果の時間軸表示

## 未決定事項

- 対応するタブレット OS
- 最初に対応する音声形式の一覧
- 新しい音源を読み込むとき、現在のキューを置き換えるか追加するか
- 再生順、リピート、シャッフルの詳細
- 音源分離モデルと実行環境

## 受け入れ条件

- 速度を `0.50x` にしても音程が不自然に下がらない。
- A/Bループが速度変更中も指定区間を外れない。
- 大きな操作要素をタッチしても隣の操作が誤作動しない。
- 分析処理中も再生と画面操作が止まらない。
- プレイリストを再起動後も復元できる。