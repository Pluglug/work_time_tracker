## Work Time Tracker: Textベース（.blend内Text）管理レポート

### 目的
- main版の `core/old_time_data.py`（Textブロック永続化方式）を読み取り、方式のメリット、重要メソッド、処理フロー、考慮点を整理。

### データ保存方式（概要）
- `.blend` 内の `Text` データブロックに JSON を保存。
  - 名前: `.work_time_tracker.json`（存在しなければ作成／`use_fake_user=True` で永続）
  - キー: `version, total_time, last_save_time, sessions[], file_creation_time, file_id`
- ファイル単位の真のソース（.blendと状態が常に一体）。

### 主要コンポーネント
- 定数
  - `TEXT_NAME = ".work_time_tracker"`
  - `DATA_VERSION = 1`
- ヘルパー
  - `blend_time_data()`
    - Textブロックの取得／作成。初期 JSON を生成して書き込み。Fake User 設定。

### 重要クラスとメソッド
- `class TimeData`
  - 状態: `total_time, last_save_time, sessions[], file_creation_time, file_id, current_session_start`
  - `reset()`
    - 状態をゼロクリア。新規ファイル・異常時の初期化用。
  - `ensure_loaded()`
    - 初回だけ `load_data()` 実行。二重ロード防止。
  - `start_session()`
    - 既存のアクティブを終了してから新規セッションを開始。`sessions[]` に `{id,start,end=None,...}` 追加。
  - `switch_session()`
    - アクティブを閉じる→新規開始→保存。
  - `reset_current_session()`
    - 現在セッションの `start` を `now` に更新し `duration` を0、`total_time` から古い分を減算。
  - `end_active_sessions()`
    - `end=None` のセッションを `end=now` で確定、`duration=end-start` を確定。最後に `total_time` を `sessions[].duration` の合算で更新。
  - `get_current_session()` / `get_current_session_time()`
  - `load_data()`
    - Textから JSON を読み込み、`file_id` 一致時のみ反映。
    - 「未終了セッションがある場合、開く .blend のファイル最終更新時刻（mtime）で `end` を補完」→ `duration` を確定し、`total_time` を合算（未保存終了やクラッシュ時の頑健化）。
  - `update_session()`
    - 現在セッションの経過時間を加味して `total_time` を導出更新（`end` 済みは `duration`、アクティブは `now - start`）。
  - `save_data()`
    - `update_session()`→ JSON を構築→ Textへ書き込み。

- ハンドラ／タイマー
  - `@persistent load_handler`
    - `load_data()`→`start_session()`→ログ。
  - `@persistent save_handler`
    - `file_id` を現在のファイル名で更新→`save_data()`。
  - `update_time_callback()`（1秒周期）
    - `update_session()`で合計を導出更新。
    - Save As などで `filepath` が変わったら、旧セッションを閉じて新セッションを開始→保存。
  - `delayed_start()` / `start_timer()` / `stop_timer()`

### この方式のメリット（今回の課題に照らして）
- **境界イベントに強い**
  - 未終了セッションを「ファイルの最終更新時刻」で確定でき、未保存終了／クラッシュでも時間がゼロになりにくい。
- **.blendと状態が一体**
  - 外部状態や起動順・ハンドラの在/不在に影響されづらい。ファイルを開けば、そのファイル自身の Text が真のソースに。
- **実装がシンプル**
  - 導出計算は `start/end` ベースのみ。休憩（idle）などの複雑なランタイム状態に依存しないため、誤検出の影響を受けにくい。

### 既知の制約 / 補足
- 標準の main 実装には「休憩」概念がない。
  - 砂時計モデル（休憩は積算しない）を実現するには、休憩セッションや idle 検出・補正の設計を追加する必要がある。
- 未保存の新規 .blend では、保存前に Text が外部へ残らない。
  - Fake User は保存後の永続性には有効。
- Save As で Text は物理的に複製される可能性あり。
  - `file_id` 不一致で読み込み回避は可能（main実装が対応）。

### 推奨フロー（Text方式のベストプラクティス）
1. 起動/ロード: `load_data()` → 未終了セッションがあれば mtime で `end` を補完 → 新規セッション `start_session()`
2. ランタイム: 1秒タイマーで `update_session()`（合計は導出）
3. Save/Save As: `save_handler()`が `file_id` 更新→ `save_data()`、パス変更時はタイマーでも新セッション開始
4. 終了: `unregister` 時に `stop_timer()`→ `save_data()`（必要なら）

### 休憩機能と両立させるなら
- ランタイム（UI/導出）: PropertyGroup/メモリで休憩の開始/終了・控除を管理
- 永続（境界の堅牢化）: `.blend` Text へセッション履歴を保存。未終了は mtime で確定、休憩履歴も保存
- 起動直後は休憩検出に数秒のアームを入れて誤検出を抑止

### まとめ
- Textベースは「ファイル境界の堅牢性」と「シンプルさ」で優位。未終了補完（mtime）により、クラッシュや未保存終了時でも実時間を失いにくい。
- 砂時計モデル（休憩控除）まで含めるなら、Textを永続・PGをランタイムに使うハイブリッド構成が有効。


---
main版の`core/time_data.py`（Textブロック永続化方式）には、今遭遇していた問題に対して明確なメリットがありました。

メリット（Textブロック方式）
- セッションの確定が堅牢
  - 起動・ファイル再読込時に未終了セッションを「ファイル最終更新時刻（mtime）」で閉じる実装（L278-L296）。クラッシュや未保存終了でもゼロ化しにくい。
- ファイル単位の真のソース
  - `.blend`内の`Text`に保持（`use_fake_user=True`）。ファイルと状態が常に一体で、PG初期化順やハンドラ登録順に依存しない。
- Save Asへの耐性
  - Textに`file_id`を保持し、読み出し時に一致チェック（L266-L306）。他ファイルの残骸を誤読しない。
- 実装がシンプルでバグ面積が小さい
  - ランタイムはメモリ配列＋1秒タイマーの導出のみ。PGや複数ハンドラの整合に比べて壊れにくい。

デメリット／制約
- 休憩（idle）概念がない
  - mainは純粋な開始/終了の差分のみ。砂時計イメージ（休憩は積算しない）を実現するならidle追跡の追加が必要。
- 未保存新規ファイルでは保存前にテキストは外部に残らない
  - Fake Userは保存後には強いが、保存前クラッシュでは復元できない（外部JSONの補助が有効）。
- Save As時に旧ファイル由来のTextが新ファイルにも物理的にコピーされる
  - ただし`file_id`ミスマッチで読み込み回避はできている。孤児データは残り得る。

今の理解との整合
- 「合計＝経過−休憩」の導出モデルは正しい。ただし導出は境界イベント（起動/ロード/Save As/終了）で状態が崩れやすい。mainの「mtimeで未終了セッションを閉じる」はこの境界での頑健化として有効。
- devのPG＋休憩モデルで起きていた「起動/ロード直後に巨大休憩がつく」「ハンドラ未登録でidleが暴走」等は、Text方式では構造的に起きにくい。

さらに考慮すべきこと（ハイブリッド推奨）
- ランタイム＝PG（UI/高速導出）、永続＝Text（.blend内）＋外部JSON（保存前クラッシュ対策）
  - 起動/ロード: Text→PGへ同期。未終了はmtimeで閉じる→新セッション開始。
  - ランタイム: 休憩はPGで検出・集計（クランプ済み）。定期/保存時にTextへ書き戻し。
  - Save As: 新ファイルでは新Textを初期化、旧Textはfile_idミスマッチで読み捨て。
- 起動・ロード直後の休憩検出を数秒アーム（最初の操作を待つ）して誤検出を防止。
- `time.monotonic()`でidle測定、保存/永続はepochで記録に分離。
- 手動修正UI（誤休憩削除、セッション結合/分割）。

結論
- Text方式は「ファイル境界の堅牢性」「未終了セッションの扱い」で強みがあり、今回の種別の不具合を避けやすい。砂時計モデル（休憩控除）を安全に運用するなら、PGの利点（UI/導出）とTextの利点（永続/境界の堅牢化）を組み合わせるのが最善。