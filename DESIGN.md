# ore-music-player 設計書

この文書は、現在の実装状況、合意した製品要件、アーキテクチャを記録する。未検証の技術選択は確定事項として扱わない。

## ステータス

- ドメイン層、再生制御、プレイリスト管理、SQLite永続化、PySide6 UI、起動処理は実装済み。
- Windows上のmpv共有DLLを `vendor/mpv` に配置した環境で、アプリを起動して音声を再生できる。
- 音源分離、パート別音量変更、コード進行分析、イコライザ、スリープタイマーは未実装で、今回の対象外とする。
- 対象はデスクトップとタブレットでのタッチ操作。
- 画面上の操作ボタンは正方形タイルとし、最大5列で配置する。

## 実装状況

| 領域 | 状態 | 内容 |
| --- | --- | --- |
| ドメインモデル | 実装済み | `Track`、`LoopRegion`、`PlaybackSettings`、速度・音量・位置の検証 |
| 再生状態 | 実装済み | 再生、一時停止、停止、シーク、A/Bポイント、ループ状態 |
| 再生サービス | 実装済み | `PlaybackService` と `PlaybackBackend` 契約の同期 |
| ドメイン・サービス・UIのテスト | 実装済み | 再生状態、再生サービス、プレイリスト、SQLite、MainWindow、PlaylistViewを検証 |
| プレイリスト | 実装済み | `Playlist`、`PlaylistService`、CRUD、複数曲追加・削除、ドラッグによる曲順変更、SQLite保存 |
| 永続化 | 実装済み | SQLiteスキーマ、プレイリストと曲順の保存・復元、統合テスト |
| 音声再生 | 実装済み | `python-mpv` と libmpv による再生、停止、シーク、速度変更、A/Bループ |
| アプリ起動 | 実装済み | `app.py`、`bootstrap.py`、`__main__.py`、`python -m ore_music_player` |
| UI | 実装済み | PySide6の左右分割画面。ファイルツリー検索、複数ファイル・フォルダ読み込み、登録解除、再生操作、プレイリスト、A/B操作、音量、再生履歴に対応 |
| 設定管理 | 実装済み | INIファイルへの保存・復元。旧レジストリ設定からの自動移行 |
| 自動アップデート | 実装済み | GitHub Releases からダウンロードして適用。404時（Releases未公開）は無視 |
| 再生トレース | 実装済み | 操作履歴を `data/playback-trace.jsonl` へ記録 |
| 分析 | 未実装 | 音源分離、パート音量、コード進行分析 |

## 現在のスキャフォールド

```text
ore-music-player/
├── AGENTS.md
├── DESIGN.md
├── README.md
├── pyproject.toml
├── build.ps1
├── ore_music_player.spec
├── .github/
│   └── workflows/
│       └── windows-release.yml
├── src/
│   └── ore_music_player/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py
│       ├── bootstrap.py
│       ├── version.py
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
│       │   ├── settings.py
│       │   ├── update_service.py
│       │   ├── playback_trace.py
│       │   ├── apply_update.ps1
│       │   ├── audio/
│       │   │   ├── __init__.py
│       │   │   ├── metadata.py
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
│           ├── playlist_view.py
│           └── utils.py
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_playback_state.py
    │   ├── test_playback_service.py
    │   ├── test_playback_backend.py
    │   ├── test_playlist.py
    │   ├── test_playlist_service.py
    │   ├── test_bootstrap.py
    │   ├── test_main_window.py
    │   ├── test_playlist_view.py
    │   └── test_update_service.py
    └── integration/
        └── test_sqlite_repository.py
```

`.venv/`、`.git/`、`vendor/mpv/` はローカル環境または実行用ランタイムであり、アプリケーションのソース構成には含めない。`vendor/mpv/` は `.gitignore` 対象で、実行時には利用者が対応するmpv共有DLLを配置する。空の分析ファイルは未実装のプレースホルダーであり、実装済みのファイルは上記の実装状況に従う。

## ソースファイルの責務

### パッケージ入口

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/__init__.py` | パッケージの公開 API を定義する。必要な場合だけ公開型を再エクスポートする。 | QApplication の生成、ファイル読み込み、再生開始などの副作用。 |
| `src/ore_music_player/__main__.py` | `python -m ore_music_player` の入口。`main()` を定義し、アプリ起動処理を `app.py` へ渡す。 | プレイリスト処理、音声処理、画面部品の詳細。 |
| `src/ore_music_player/app.py` | QApplication の生成、アプリケーションのライフサイクル、終了コードの管理を行う。 | サービスの具体的な組み立て。依存関係の配線は `bootstrap.py` に任せる。 |
| `src/ore_music_player/bootstrap.py` | 再生バックエンド、SQLite リポジトリ、アプリケーションサービス、UI を組み立てて接続する。 | ドメインルール、個別の画面レイアウト、SQLの詳細。 |
| `src/ore_music_player/version.py` | アプリのバージョン文字列 `__version__` を定義する。 | アップデート判定ロジック、UI 表示。 |

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
| `src/ore_music_player/application/playback_service.py` | 現在の曲の再生、一時停止、停止、シーク、A/B設定、ループ、速度変更を調整する。 | libmpv の API を直接呼ぶこと、ボタンの見た目。 |
| `src/ore_music_player/application/playlist_service.py` | プレイリストの作成、名前変更、削除、曲追加、曲削除、並べ替え、保存、読み込みを調整する。 | SQL文、ファイルダイアログ、UIレイアウト。 |
| `src/ore_music_player/application/ports.py` | `PlaybackBackend`、`PlaylistRepository`、音源スキャナー、分析ジョブ実行器など、外部実装が満たす契約を定義する。 | 契約の具体的な実装、QtやSQLiteの import。 |

### インフラストラクチャ層

インフラストラクチャ層は、アプリケーション層が定義した契約の具体的な実装を置く。外部ライブラリや OS の違いはこの層に閉じ込める。

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/infrastructure/__init__.py` | インフラ実装の公開 API をまとめる。 | ドメインルールや画面操作。 |
| `src/ore_music_player/infrastructure/settings.py` | INI ファイル形式で `QSettings` を生成する。旧レジストリ設定（`OreMusicPlayer\OreMusicPlayer`）からの一回限りの移行を担当する。 | UI イベント、再生制御。 |
| `src/ore_music_player/infrastructure/update_service.py` | GitHub Releases API で最新バージョンを確認し、ZIP アーカイブをダウンロード・展開・検証する。PowerShell スクリプト経由でアプリを差し替える。Releases が存在しない場合（404）は更新なしとして扱う。 | UI ダイアログの表示、再生制御。 |
| `src/ore_music_player/infrastructure/apply_update.ps1` | 旧プロセスの終了を待ってから実行ファイルを差し替え、新バージョンを起動する PowerShell スクリプト。 | バージョン比較、ダウンロード。 |
| `src/ore_music_player/infrastructure/playback_trace.py` | 再生操作イベントを JSONL 形式で `data/playback-trace.jsonl` へ記録する。デバッグ用途。 | 再生制御、UI 表示。 |
| `src/ore_music_player/infrastructure/audio/__init__.py` | 音声バックエンド実装の公開 API をまとめる。 | 再生キューやプレイリストの管理。 |
| `src/ore_music_player/infrastructure/audio/metadata.py` | mutagen 等を使って音声ファイルから再生時間を読み取る。 | 再生制御、プレイリスト保存。 |
| `src/ore_music_player/infrastructure/audio/playback_backend.py` | `python-mpv` と libmpv をラップする。音声出力、シーク、A/B境界、速度変更、ピッチ補正を扱う。 | プレイリストの保存、Qt画面の操作、分析結果の表示。 |
| `src/ore_music_player/infrastructure/persistence/__init__.py` | 永続化実装の公開 API をまとめる。 | SQLスキーマ以外のドメイン判断。 |
| `src/ore_music_player/infrastructure/persistence/sqlite_repository.py` | SQLiteの接続、テーブル作成、プレイリスト、曲順、音源情報、分析結果の保存・取得を実装する。 | UIイベント、音声デコード、分析モデルの実行。 |
| `src/ore_music_player/infrastructure/analysis/separation.py` | 将来の音源分離モデルをバックグラウンドジョブとして呼び出し、StemSet と生成ファイルのメタデータを返す。 | UIスレッドでの同期実行、プレイリスト画面の表示。 |
| `src/ore_music_player/infrastructure/analysis/chord_analysis.py` | 将来のコード進行分析をバックグラウンドジョブとして実行し、時間軸付きの分析結果を返す。 | 再生制御、UIの直接更新。 |

### UI層

UI層は表示とユーザー入力の変換だけを担当する。SQLiteや再生エンジンを直接呼ばず、アプリケーションサービスを通じて操作する。

| ファイル | 担当すること | 担当しないこと |
| --- | --- | --- |
| `src/ore_music_player/ui/__init__.py` | UI部品の公開 API をまとめる。 | ドメイン状態の所有、DB接続。 |
| `src/ore_music_player/ui/main_window.py` | 左右分割画面、`QFileSystemModel` と `QTreeView` によるファイルツリー、検索、ファイル名・再生時間表示、登録解除、再生操作、キュー移動、再生方法、音量、再生履歴を構成する。 | 音声データの加工、SQL、分析モデルの実行。 |
| `src/ore_music_player/ui/playlist_view.py` | プレイリスト一覧、曲一覧、新規作成、名前変更、削除、複数曲追加、曲削除、ドラッグによる曲順変更、プレイリスト再生の操作画面を構成する。 | プレイリストの保存処理、再生エンジンの直接操作。 |
| `src/ore_music_player/ui/utils.py` | UI間で共有する再生時間表示を提供する。 | 再生状態やQtウィジェットを所有すること。 |

### テスト

| ファイル | 担当すること |
| --- | --- |
| `tests/conftest.py` | UI・サービステストで共有するFakeリポジトリを提供する。 |
| `tests/unit/test_playback_state.py` | 速度範囲、刻み、A/B区間、再生状態遷移、曲終了時のルールを外部機器なしで検証する。 |
| `tests/unit/test_playback_service.py` | ダミーバックエンドを使い、再生制御とドメイン状態の同期を検証する。 |
| `tests/unit/test_playback_backend.py` | `LibMpvPlaybackBackend` のロードと制御を検証する。 |
| `tests/unit/test_playlist.py` | プレイリストの作成、順序、追加・削除、重複、キュー生成のルールを検証する。 |
| `tests/unit/test_playlist_service.py` | Fakeリポジトリを使い、プレイリストの作成、取得、更新、削除を検証する。 |
| `tests/unit/test_bootstrap.py` | アプリケーション起動時の依存関係組み立てを検証する。 |
| `tests/unit/test_main_window.py` | ファイルツリー、音声メタデータ表示、左ペイン設定の保存・復元、登録解除、再生・シーク・速度・A/B操作を検証する。 |
| `tests/unit/test_playlist_view.py` | Qtをオフスクリーンで起動し、PlaylistViewの表示、曲追加・削除、再生要求を検証する。 |
| `tests/unit/test_update_service.py` | バージョン比較、アーカイブ検証、GitHub 404 時の無視を検証する。 |
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

`__main__.py` と `app.py` は実装済みで、`python -m ore_music_player` で起動する。現在はコンソールスクリプト名を登録せず、モジュール起動を標準コマンドとする。

現在の最小検証コマンドは次のとおりである。

```powershell
python -m pytest -q
python -m ruff check src tests
```

Qt画面を表示できない環境では、次のようにオフスクリーンでテストする。

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
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
- 音源分離、コード分析、データベース処理で UI スレッドをブロックしない。音源分離とコード分析は未実装のため、現段階では再生とプレイリスト機能の範囲に限定する。
- 個人環境の音楽フォルダ、OS固有パス、認証情報をソースにハードコードしない。

## 確定要件

### 現在実装している機能

- 音楽ファイルを1曲以上読み込んで再生する。
- フォルダを1つ以上読み込んで再生する。
- 保存済みプレイリストを選択して再生する。
- A/B区間を指定してループする。
- 再生速度を変更する。
- 速度を変更しても音程を維持するタイムストレッチを使う。
- プレイリストを作成、編集、保存、削除する。
- 複数の音声ファイルを選択して再生キューへ読み込む。
- フォルダ以下の対応音声ファイルを再帰的に読み込む。
- 全曲ループ、ランダム再生、1曲ループを切り替える。
- 音量と最近再生した曲（最大10件）を保存・復元する。
- ファイルツリーをファイル名で検索する。
- キーボードショートカットで再生、一時停止、シーク、曲移動を操作する。
- キューの前後の曲へ移動する。
- 位置を秒単位で指定してシークする。
- 再生位置スライダーにA地点・B地点のマーカーを表示する。
- 左右分割レイアウトで、左側に現在のファイルツリー、右側に再生・プレイリスト画面を表示する。
- ファイルツリーにファイル名と再生時間を表示する。
- 左ペインで複数の音声ファイルを選択し、アプリへの登録を解除する。登録解除では実ファイルを削除しない。
- 左ペインの表示ルート、分割位置、列状態を次回起動時に復元する。
- GitHub Releases から最新版を確認してアプリ内で更新する（Windows限定）。

### 未実装または制限のある機能

- プレイリスト画面からのフォルダ追加。
- 移動・削除された音源の警告と再生時スキップ。
- イコライザ、スリープタイマー、音源分離、パート別音量変更、コード進行分析。

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

## 音源の読み込み

### ファイル読み込み

- 複数ファイルを選択できる。
- 選択したファイルだけを現在の再生キューにする。
- 複数ファイルを選択した場合、最初のファイルの親フォルダを左ペインの表示ルートにする。

### フォルダ読み込み

- フォルダを1つ選択できる。
- 選択したフォルダ以下を再帰的に検索する。
- 対応していないファイルは読み込み対象外にする。

対応形式は `.mp3`、`.wav`、`.flac`、`.m4a`、`.ogg` とする。

### 左ペインからの登録解除

- ファイルツリーで1つ以上の音声ファイルを選択できる。
- 「削除」ボタンで確認ダイアログを表示する。
- 確認後、選択ファイルを左ペインから非表示にし、現在の再生キューからも外す。
- 登録解除では実ファイルを削除せず、ファイルシステム上の内容を変更しない。

### プレイリスト再生

- 保存済みプレイリストを管理画面から選択する。
- プレイリストの曲を現在の再生キューへ読み込んで再生画面へ移動する。
- 保存済みプレイリストと現在の再生キューは別の状態として扱う。
- 移動・削除された音源は警告表示し、再生時はスキップできるようにする。

## 画面構成

### 再生画面

- ウィンドウ全体を左右のペインに分割する。
- 左ペインにファイルツリーを表示し、ファイル名と再生時間を2列で表示する。
- 左ペイン上部に表示ルートと「削除」ボタンを配置する。
- 現在の曲名と再生状態を表示する。
- 再生位置とシーク操作を表示する。スライダー上にA地点・B地点をマーキングする。
- 再生、一時停止、停止、前後移動を表示する。
- A設定、B設定、A/Bループを表示する。
- `0.50x`〜`1.50x` の速度スライダーを表示する。
- 音量スライダーを表示する。

### プレイリスト管理画面

- 左側または上側に保存済みプレイリスト一覧
- 選択したプレイリストの曲一覧
- 新規作成、名前変更、削除
- 曲の追加、フォルダからの追加、曲の削除
- 曲順の変更

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

左ペインの表示状態はINIファイル（`data/settings.ini`）に保存する。保存対象は次のとおりとする。

- ファイルツリーの表示ルート
- 左右ペインの分割位置
- ファイルツリーの列幅・列状態
- 音量
- 最近再生した曲（最大10件）

旧バージョンで `QSettings`（Windows レジストリ、`HKCU\Software\OreMusicPlayer\OreMusicPlayer`）に保存されていた設定は、初回起動時に INI ファイルへ自動移行する。

左ペインから登録解除しても、音声ファイル本体は削除しない。登録解除状態は現在のアプリ実行中の左ペインと再生キューに反映する。

## 技術選択

### 確定している基準

- Python 3.13
- GUI: PySide6
- 再生バックエンド: `python-mpv` + libmpv（Windows共有DLL `vendor/mpv/libmpv-2.dll`）
- 設定保存: INI ファイル形式（`QSettings.Format.IniFormat`）
- データベース: SQLite
- ビルド: PyInstaller（`ore_music_player.spec`、`build.ps1`）、1ファイル EXE
- 配布: GitHub Releases（`yesmenjoker3104/ore-music-player`、アセット名 `ore-music-player-windows-x64.zip`）
- 速度変更時のピッチ維持: `audio_pitch_correction=True`（mpv オプション）

### 実装前に検証が必要なもの

- 新しい音声バックエンドへの乗り換えを検討する場合は、正確なシーク、A/Bループ境界、`0.50x`〜`1.50x` の速度変更、速度変更時のピッチ維持、Windows での音声出力を disposable probe で検証すること。

## 将来機能

- 音源分離（設計確定、未実装）
- パートごとの音量変更（設計確定、未実装）
- コード進行分析
- 分析結果の時間軸表示

## 音源分離の設計

### 方針

- リアルタイム分離はしない。事前にバックグラウンドで分離してキャッシュする。
- 分離エンジンは Demucs（Meta製）を使う。
- 分離機能はオプションの Plugin 扱いとし、未インストール時はメイン EXE に影響しない。

### UI

- ファイルツリーとプレイリスト曲一覧の右クリックメニューに「音源を分離」を追加する。
  - ステムがない曲にだけ「音源を分離」を有効にする。
  - ステムがある曲にだけ「分離キャッシュを削除」を有効にする。
- 分離状態はプレイリスト曲一覧に列（分離）として表示する（未分離: ─、処理中: 処理中…、完了: ✓）。
- ステムがある曲の再生中、音量スライダーの右側スペースにパート別の縦スライダーを表示する。
  - ステムの種類: ボーカル・ドラム・ベース・ギター・ピアノ・その他（Demucs htdemucs_6s の6分割）
  - ステムがない曲の再生中は縦スライダーを非表示にする。

### 再生

- ステム再生は `sounddevice` を使ったリアルタイムミックスで行う。
- 各ステムの音量スライダーを動かすと即座にミックス比率が変わる。
- シーク・A/B ループ・速度変更は sounddevice ベースの再生エンジンで再実装する。
- 通常再生（mpv）とステム再生（sounddevice）は `PlaybackBackend` の切り替えで吸収する。

### キャッシュ

- ステムファイルは `data/stems/{track_id}/{stem}.wav` に保存する。
- SQLite の `stems` テーブルにパスとステム名を記録する（バイナリは DB に入れない）。
- アプリ起動時に DB にレコードがあるがファイルが存在しない場合は不整合として DB レコードを削除する。

### Demucs 環境の構築

- 初回「音源を分離」実行時に「追加セットアップが必要です（約1GB）、インストールしますか？」を表示する。
- ユーザーが承諾したら以下をバックグラウンドで実行し、進捗ダイアログを表示する。
  1. python.org から embeddable Python をダウンロード・展開
  2. get-pip.py を取得して pip を有効化
  3. `pip install demucs` を実行
- 環境の格納先は `vendor/demucs-env/` を優先し、書き込み権限がない場合は `%APPDATA%\OreMusicPlayer\demucs-env\` にフォールバックする。
- Demucs のモデルは初回分離時に自動ダウンロードされる（約200MB、`htdemucs_6s`）。
- 「分離機能を削除」メニューで環境フォルダごと削除できる。

### 実装前に確認すること（Probe）

| Probe | 内容 |
| --- | --- |
| ① | Demucs で実際に分離できるか・処理時間・ステム名を確認 |
| ② | `sounddevice` でリアルタイムミックス・シーク・A/B ループ・速度変更が実現できるか確認 |
| ③ | embeddable Python + pip で `vendor/demucs-env/` を構築できるか確認 |

3つ通ってから実装に着手する。

## 未決定事項

- 対応するタブレット OS
- 新しい音源を読み込むとき、現在のキューを置き換えるか追加するか
- 音源分離モデルと実行環境

## 受け入れ条件

- 速度を `0.50x` にしても音程が不自然に下がらない。
- A/Bループが速度変更中も指定区間を外れない。
- 大きな操作要素をタッチしても隣の操作が誤作動しない。
- 分析処理中も再生と画面操作が止まらない。
- プレイリストを再起動後も復元できる。
