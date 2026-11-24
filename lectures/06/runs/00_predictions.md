# 第6回 演習・宿題：実行前に書いた予測（2026-11-24）

- STEP 2：`glossary_search_glossary` を 1 回、引数は「3レベル」か「宿題の3レベル」。モデル応答 2 回
- STEP 3：`fetch_fetch` を 1 回。このマシンの Node は v18 だが、`--no-readability-js` で Node を使わないので動く（改訂前は Node が原因で設定の工夫が要った）
- STEP 4：`aws_` のツールが 4〜5 個増える。説明文が英語で長いので、STEP 2 より入力トークンが数倍になる
- 基礎：エージェント側を変えずに `glossary_get_lecture_summary` が一覧に増え、「第2回では何を学びますか？」で `lecture=2` で呼ばれる
- 実装（return）：範囲外のメッセージは `[tool return]` に出て、モデルは呼び直さずに利用者へ説明する
- 実装（raise ValueError）：MCP の SDK はふつうの例外のメッセージを外に出さない（改訂前の課題で確かめた）。`[tool error]` には「Error executing tool make_quiz」だけが出て、「1〜13」は届かない
