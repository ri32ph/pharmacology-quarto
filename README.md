# pharmacology-quarto

## Notion → Quarto同期

Notionを講義内容の正本として、第3回の学生用教材をQuartoへ同期する試験実装です。

- 同期元：`学習資材` → `看護薬理学（学生用教材）`
- 対象：名前が `03-` で始まる学習資材
- 区分：`基礎理解`、`臨床判断`、`統合・定着`
- 公開条件：学生用教材の`公開状態`が`公開可`または`配布可`
- Notionページの見出しをReveal.jsのスライド見出しへ変換
- Notion APIエラー時はGitに保存された手編集版をRender

### ローカル確認

```bash
export NOTION_TOKEN='secret_...'
python3 scripts/sync-notion-course.py
```

この実行は`generated/notion/03/`だけを更新します。手編集版を一時的に差し替えてRenderする場合は、作業ツリーがクリーンであることを確認してから実行します。

```bash
python3 scripts/sync-notion-course.py --activate
quarto render
```

### Vercel

Vercelの`pharmacology-quarto`プロジェクトにSecret環境変数`NOTION_TOKEN`を設定します。デプロイ時に`scripts/vercel-build.sh`が同期とRenderを行います。Notionの変更だけでは自動デプロイされないため、反映時はVercelでRedeployします。
