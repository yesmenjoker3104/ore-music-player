# ore-music-player

個人利用を想定した、音楽練習用プレイヤーです。

## 目標

- プレイリスト管理
- A/B区間ループ
- ピッチを維持した再生速度変更
- タブレットで操作しやすい大きな UI
- 将来の音源分離、パート別音量変更、コード進行分析

## 現在の状態

旧 wxPython 実装は再利用せず、画面とアーキテクチャを刷新しています。現在はPySide6とlibmpvによる音声再生、プレイリスト、A/Bループ、再生方法切り替えまで実装済みです。

### 実装済み

- `Track`、`LoopRegion`、`PlaybackSettings` のドメインモデル
- 再生状態の管理（再生、一時停止、停止、シーク）
- A/B区間とループ状態の管理
- `0.50x`〜`1.50x`、`0.05x`刻みの再生速度検証
- `PlaybackBackend` プロトコル
- `PlaybackService` によるドメイン状態とバックエンド操作の同期
- プレイリストのSQLite保存・復元と曲順変更
- 全曲ループ、ランダム再生、1曲ループの切り替え
- 音量設定、最近再生、最後の再生セッション（キュー、曲、位置、速度、A/Bループ、再生モード、ステム個別音量）の保存・復元
- ファイルツリーの検索・フィルタ
- スペースキー、左右矢印、Ctrl+左右矢印によるキーボード操作
- PySide6の画面とlibmpvによる実際の音声再生

### 未実装

- イコライザ / トーンコントロール
- スリープタイマー
- 音源分離、パート別音量変更、コード進行分析

Windowsで音声再生するには、下記の手順でmpv共有DLLを `vendor/mpv/` に配置してください。旧実装の復元や個人環境のパス追加は行いません。

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

## Windows向けExeのビルド

PyInstallerの`onedir`形式で、mpvランタイムを含むZIPを作成できます。先に、開発用mpvアーカイブから共有DLLと依存DLLを`vendor/mpv/`へ配置してください。`libmpv-2.dll`、`mpv-2.dll`、または`mpv-1.dll`のいずれかが必要です。

```powershell
.\.venv\Scripts\Activate.ps1
.\build.ps1
```

成功すると`dist\ore-music-player-windows-x64.zip`が作成されます。ZIPを展開した後は、フォルダー内の`ore-music-player.exe`を起動してください。`onedir`形式では、EXE単体ではなくフォルダー全体を配布します。

GitHub Actionsは`v`で始まるタグをpushすると起動し、テスト、Exe化、GitHub ReleaseへのZIP添付まで行います。

```powershell
git tag v0.1.0
git push origin v0.1.0
```

Exe版では、ファイルメニューの「更新を確認」からGitHub Releaseの最新版を確認できます。新しいバージョンがある場合は、ZIPをダウンロードしてアプリを再起動し、プレイリストなどの`data`を引き継いで更新します。更新処理の詳細ログは`%LOCALAPPDATA%\OreMusicPlayer\update.log`にJSONL形式で記録されます。開発版を`python -m ore_music_player`で起動している場合、更新確認は利用できません。

設定はアプリフォルダー内の`data\settings.ini`に保存されます。プレイリストやライブラリ情報は`data\ore_music_player.sqlite3`に保存されます。初回起動時だけ旧バージョンのWindows設定を読み込み、以後はWindowsレジストリを使用しません。アプリフォルダーを削除すれば、新しい設定とデータもまとめて削除できます。旧バージョンが残したレジストリ設定は自動削除しないため、不要であれば手動で削除してください。

次のReleaseを作るときは、`src/ore_music_player/version.py`と`pyproject.toml`のバージョンを同じ値へ変更してから、同じ値の`v`タグをpushしてください。

```powershell
git tag v0.2.3
git push origin v0.2.3
```

mpvランタイムはライセンスとサイズの都合でこのリポジトリには含めていません。GitHub Actionsでビルドする場合は、CIが参照できる方法で`vendor/mpv/`を用意してください。個人用リポジトリなら管理対象に追加する方法もありますが、mpvの配布条件を確認してから行ってください。

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