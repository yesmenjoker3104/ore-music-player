# ore-music-player

個人利用を想定した、音楽練習用プレイヤーです。

## 目標

- プレイリスト管理
- A/B区間ループ
- ピッチを維持した再生速度変更
- タブレットで操作しやすい大きな UI
- 将来の音源分離、パート別音量変更、コード進行分析

## 現在の状態

旧 wxPython 実装は再利用せず、画面とアーキテクチャを刷新しています。現在はドメイン層と再生制御の基盤まで実装済みですが、実際の音声再生やGUIはまだありません。

### 実装済み

- `Track`、`LoopRegion`、`PlaybackSettings` のドメインモデル
- 再生状態の管理（再生、一時停止、停止、シーク）
- A/B区間とループ状態の管理
- `0.50x`〜`1.50x`、`0.05x`刻みの再生速度検証
- `PlaybackBackend` プロトコル
- `PlaybackService` によるドメイン状態とバックエンド操作の同期
- ドメインおよび再生サービスの単体テスト（20件）

### 未実装

- 実際の音声再生バックエンド
- プレイリストのモデル、サービス、保存・読み込み
- SQLiteリポジトリ
- ファイル・フォルダからの音源探索
- PySide6の画面と操作
- アプリケーションの起動処理
- 音源分離、パート別音量変更、コード進行分析

そのため、現時点ではアプリを起動して音声を再生することはできません。旧実装の復元や個人環境のパス追加は行いません。

設計の詳細は [DESIGN.md](DESIGN.md) を参照してください。

## 開発環境

Python 3.13 を使用します。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

再生バックエンドは、ピッチ維持タイムストレッチ、シーク、A/B境界、対応形式を検証してから依存関係へ追加します。未検証のバックエンドは実行時必須依存にしません。

依存関係のインストールと現在の検証方法は次のとおりです。

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests
```

### Windows の mpv セットアップ

再生バックエンドは `python-mpv` を使用します。`python-mpv` は Python から
mpv を操作するためのバインディングであり、実際の再生には mpv の共有 DLL
（`libmpv-2.dll`、`mpv-2.dll`、または `mpv-1.dll`）も必要です。

`python-mpv` は `python -m pip install -e ".[dev]"` でインストールされます。
一方、mpvのWindowsランタイムDLLはサイズが大きく、Gitリポジトリへは含めていません。
`vendor/mpv/` は `.gitignore` 対象なので、各開発環境で個別に配置してください。

1. [mpv公式のWindows案内](https://mpv.io/installation/) からWindows版を取得します。
	x64 Pythonを使用する場合はx86_64版を選択してください。
2. 共有DLLが含まれる開発用アーカイブ（`mpv-dev-x86_64-*.7z` など）を取得します。
	通常版の `mpv.exe` だけでは、Pythonから使用する共有DLLが含まれない場合があります。
3. アーカイブを展開し、次のフォルダーへDLLを配置します。

```text
ore-music-player/
└── vendor/
	 └── mpv/
		  ├── libmpv-2.dll    # または mpv-2.dll / mpv-1.dll
		  └── その他の依存DLL
```

プロジェクトルートで次のコマンドを実行すると、配置先を作成して確認できます。

```powershell
New-Item -ItemType Directory -Force vendor\mpv
Get-ChildItem vendor\mpv\*.dll
python -m pip install -e ".[dev]"
python -c "import mpv; print('mpv import ok')"
python -m ore_music_player
```

アプリ起動時に `bootstrap.py` が `vendor/mpv` を検査し、必要なDLLをPATHとDLL検索対象へ
追加します。通常は実行前にPATHを手動設定する必要はありません。
Pythonとmpvのアーキテクチャ（x64 / x86）は一致させてください。

mpvランタイムが未配置の場合、起動時に `vendor/mpv` または共有DLLが見つからないという
エラーになります。その場合は上記の手順でローカルに配置してください。

## 開発方針

- UI、再生制御、音声処理、分析処理、保存を分離する。
- 音声分析や音源分離で UI スレッドをブロックしない。
- 個人環境の音楽フォルダをコードへハードコードしない。
- 仕様変更は [DESIGN.md](DESIGN.md) に反映する。
- 実装後は `pyproject.toml` に定義したテスト・品質チェックを実行する。