# コードレビュー & 機能提案

> 対象: `master` ブランチ現在の作業ツリー  
> 日付: 2026-09-25

---

## 1. コードレビュー

### 1.1 バグ・潜在的問題

#### `load()` が即座に再生を開始する (`infrastructure/audio/playback_backend.py`)

`LibMpvPlaybackBackend.load()` 内で `self._player.play(str(path))` を呼ぶと、libmpv はその時点で音声再生を開始する。
しかし `PlaybackService.load()` はバックエンドの `load()` を呼んだ後、ドメイン状態を `STOPPED` にリセットする設計になっている。
結果として「バックエンドは音を出し始めているが、ドメイン状態は STOPPED」という矛盾が一瞬発生する。
`MainWindow._load_current_track()` が `autoplay=False` の場合でも音が出てしまう可能性がある。

```python
# playback_backend.py:20-27
def load(self, track: Track) -> None:
    ...
    self._player.stop()
    self._player.play(str(path))  # ← ここで即座に再生開始
    self._is_stopped = False
```

**修正案**: `load` 時は `self._player.pause = True` を設定して一時停止状態にしておく。

---

#### `enable_loop` と `_sync_loop` の非対称な実装 (`application/playback_service.py`)

`enable_loop` はバックエンドへの `set_loop` 呼び出しを直接行うが、`disable_loop` は `_sync_loop` を経由する。
処理結果は同じだが、一貫性がなく `_sync_loop` の目的が不明瞭になっている。

```python
def enable_loop(self) -> PlaybackState:
    self.state = self.state.set_loop_enabled(True)
    region = self.state.loop_region
    if region is not None:
        self.backend.set_loop(region.start_seconds, region.end_seconds)  # 直接呼ぶ
    return self.state

def disable_loop(self) -> PlaybackState:
    self.state = self.state.set_loop_enabled(False)
    self._sync_loop()  # _sync_loop 経由
    return self.state
```

**修正案**: `enable_loop` も `_sync_loop()` を呼ぶよう統一する。

---

#### `_format_duration` 関数の重複 (`ui/main_window.py` / `ui/playlist_view.py`)

まったく同じ実装がどちらのファイルにも定義されている。
変更が片方だけに適用されるとフォーマットが食い違うリスクがある。

```python
# 両ファイルに同じ関数が存在
def _format_duration(seconds: float | None) -> str: ...
```

**修正案**: `ui/` 直下の共通ユーティリティモジュール（例: `ui/utils.py`）に移動する。

---

### 1.2 設計上の改善点

#### `SQLitePlaylistRepository.list_all()` の N+1 クエリ

`list_all()` は全プレイリストの ID を一括取得した後、それぞれに対して `get()` を1回ずつ呼ぶ。
プレイリスト数が増えると DB へのラウンドトリップが線形に増加する。

```python
def list_all(self) -> tuple[Playlist, ...]:
    rows = self._connection.execute(
        "SELECT playlist_id FROM playlists ORDER BY rowid"
    ).fetchall()
    return tuple(
        playlist
        for row in rows
        if (playlist := self.get(row["playlist_id"])) is not None  # ← N+1
    )
```

**修正案**: `playlists` / `tracks` / `playlist_tracks` を JOIN する1クエリで取得してメモリ上で組み立てる。

---

#### `MainWindow` の過大な責務

`MainWindow.__init__` が約700行に達している。ファイルツリー管理・プレイヤーコントロール・キュー管理・設定の保存・復元がすべて同クラスに集中している。
新機能を追加するたびに変更箇所が増え、テストも困難になる。

**修正案（方向性）**:
- ファイルツリー関連を `FilePane` ウィジェットに分離
- プレイヤーコントロール部分を `PlayerControlWidget` に分離
- キュー管理ロジックを `PlayQueue` クラスに分離

---

#### `FakePlaylistRepository` の重複定義

`tests/unit/test_main_window.py` と `tests/unit/test_playlist_view.py` に同じ `FakePlaylistRepository` が定義されている。

**修正案**: `tests/conftest.py` に移動して共有する。

---

#### `loop_seek_target` メソッドが未使用 (`domain/playback_state.py:196`)

`PlaybackState.loop_seek_target()` は定義されているが、アプリケーションのどこからも呼ばれていない。
libmpv のネイティブ A/B ループ機能に委任しているため、このメソッドは現状では冗長。

---

#### `load_and_play` の型安全性 (`ui/main_window.py:1372`)

引数が `tuple[Track, ...]`, `Track`, `PlaylistTrackSelection` の3種類を受け取る isinstance 分岐になっている。
シグネチャが広く、呼び出し側の意図が不明瞭になりやすい。

```python
def load_and_play(
    self,
    tracks: tuple[Track, ...] | Track | PlaylistTrackSelection,
) -> None:
```

**修正案**: `PlaylistTrackSelection` を受け取るオーバーロードまたは専用メソッドに分離する。

---

#### ボリュームが `PlaybackState` に持たれていない

現状、ボリュームはバックエンドに直接送るのみで、ドメイン状態に記録されない。
アプリ再起動後にボリューム設定が失われる。将来的に再生設定の一部として保持する設計を検討する価値がある。

---

### 1.3 スタイル・細かい指摘

| 場所 | 内容 |
|------|------|
| `sqlite_repository.py:90` | `get()` と `list_all()` の間の空行が欠けている（スタイル統一） |
| `sqlite_repository.py:172` | `close()` の前の空行が欠けている |
| `playback_backend.py:62-63` | インデントが他のメソッドと統一されていない（4スペースではなく3スペース） |
| `test_volume_slider_is_small_and_updates_backend` | レイアウト座標チェックが多く、環境（DPI・フォントサイズ）依存のフラギーなテストになるリスクがある |
| `test_left_pane_settings_are_saved_and_restored` | `QSettings` のクリーンアップが `finally` ブロックに入っているが、テスト失敗時にウィンドウのクローズが先に来ないと設定が残る場合がある |

---

## 2. テストカバレッジ観察

| テスト対象 | 状況 |
|---|---|
| ドメインモデル (`Track`, `LoopRegion`, `PlaybackSettings`, `Playlist`) | 網羅的 |
| `PlaybackState` の遷移ルール | 網羅的 |
| `PlaybackService` | 網羅的 |
| `PlaylistService` | 網羅的 |
| `SQLitePlaylistRepository` | 統合テストあり |
| `MainWindow` | 主要ユースケースをカバー |
| `PlaylistView` | 主要ユースケースをカバー |
| `LibMpvPlaybackBackend` | libmpv DLL 依存のため別スイート扱い（適切） |
| `loop_seek_target` | テストなし（未使用のため） |

---

## 3. 機能提案

以下は「こんな機能があると良い」という提案です。実装の優先順位・実現方法はユーザーが判断してください。

---

### 3.1 すぐに実装できそうなもの

#### キーボードショートカット
スペースバーで再生/一時停止、左右矢印キーでシーク（5秒）、Ctrl+矢印で前後トラック移動。
楽器練習中はマウスを使わずに操作できると格段に使いやすくなる。

#### プレイリストのドラッグ&ドロップ並び替え
`Playlist.move_track()` はドメイン層・サービス層ともに実装済み。
`TrackTableWidget` に `dragDropMode = InternalMove` を追加するだけで有効化できる。

#### ボリューム設定の永続化
現状はアプリ再起動でボリュームが 100 にリセットされる。
`
` に保存しておくと毎回調整しなくて済む。

---

### 3.2 中期的な機能

#### 最後の再生位置の復元（ブックマーク）
アプリ終了時に「曲パス・再生位置・A/B点・速度」を保存し、次回起動時に復元する。
長時間の練習音源（レッスン動画・曲解説など）に特に便利。

#### ファイルツリーの検索・フィルタ
登録済みファイルの中からファイル名でインクリメンタルサーチができると、多数のファイルを管理しているときに便利。

#### 最近再生した曲のリスト
「最近再生した10曲」を素早く呼び出せるリスト。
毎回ファイルツリーをたどらなくても直前の練習曲に戻れる。

---

### 3.3 将来的な発展機能

#### イコライザ / トーンコントロール
libmpv の `af=equalizer` フィルタを使った簡易イコライザ。
楽器の音が埋もれているトラックで特定の帯域を強調できる。

#### スリープタイマー
指定した時間または曲数が経過したら自動停止する機能。
就寝前の耳コピセッションや集中練習の区切りに便利。

---
