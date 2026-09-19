# ore-music-player

個人利用を想定した、音楽練習用プレイヤーです。

## 目標

- プレイリスト管理
- A/B区間ループ
- ピッチを維持した再生速度変更
- タブレットで操作しやすい大きな UI
- 将来の音源分離、パート別音量変更、コード進行分析

## 現在の状態

現在は設計とスキャフォールド作成のフェーズです。旧 wxPython 実装は再利用せず、画面とアーキテクチャを刷新します。

`src/ore_music_player/` と `tests/` のフォルダおよび空の Python ファイルは作成済みですが、入口の `__main__.py` を含めてまだ実装されていません。そのため、現時点ではアプリを起動できません。

設計の詳細は [DESIGN.md](DESIGN.md) を参照してください。

## 開発環境

Python 3.13 を使用します。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

再生バックエンドはピッチ維持タイムストレッチを検証してから依存関係へ追加します。現段階では、依存関係のインストールコマンドやアプリの起動コマンドは確定していません。

実装後の起動方法は次の形にします。

```powershell
python -m pip install -e ".[dev]"
python -m ore_music_player
```

`python -m ore_music_player` は `src/ore_music_player/__main__.py` を入口にします。入口の実装が完了するまでは、このコマンドは使用できません。

## 開発方針

- UI、再生制御、音声処理、分析処理、保存を分離する。
- 音声分析や音源分離で UI スレッドをブロックしない。
- 個人環境の音楽フォルダをコードへハードコードしない。
- 仕様変更は [DESIGN.md](DESIGN.md) に反映する。
- 実装後は `pyproject.toml` に定義したテスト・品質チェックを実行する。