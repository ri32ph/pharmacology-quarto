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

## 教材マスター → 開閉式マインドマップ

`看護薬理学｜教材マスター`の`マインドマップ表示`がONの項目を取得し、`親項目`Relationと`表示順`から開閉式HTMLを生成します。

```bash
export NOTION_TOKEN='secret_...'
node scripts/sync-notion-interactive-mindmap.mjs
quarto render
```

生成先は`lectures/11-neurology/interactive-mindmap.html`です。Vercelではデプロイ時に自動生成し、Notion APIエラー時はGitに保存されたHTMLを使用します。

## 学生用教材DB → 15回の講義ポータル

`学習資材`からRelationされた学生用教材のうち、`公開状態`が`公開可`または`配布可`の教材を全15回分取得します。`03-01`などの小単元ごとに、`基礎理解`、`臨床判断`、`統合・定着`、`全体版`を個別生成します。

```bash
export NOTION_TOKEN='secret_...'
python3 scripts/sync-notion-all-lectures.py
quarto render
```

公開入口は`lectures/notion/index.html`です。Vercelでは`--activate-index`を付け、通常のトップページもNotion生成版へ差し替えます。Notion取得に失敗した場合は、Gitに保存された手動トップページを使用します。Notion側で非公開の教材は掲載されません。

薬効群DBの`Status=Published`、`Slug`、`学習領域`Relationも読み取り、小単元の右端にYakuriLab辞書へのリンクを表示します。薬効群DBを取得できない場合も講義資料の生成は継続します。

### 小単元のマインドマップ

小単元名の横に、公開済みマップがある場合だけ「マインドマップ」を表示します。対応は`data/unit-mindmaps.json`の`units`に、小単元コードをキーとして最大1件登録します。`href`はサイトルートからの相対パスで、既存のHTMLを指定します。新しいHTMLは`_quarto.yml`の`project.resources`にも追加してください。

```json
{"units": {"03-01": {"name": "血圧と降圧薬", "href": "lectures/mindmaps/blood-pressure-antihypertensives.html"}}, "unassigned": []}
```

この例のHTMLは未作成です。ファイル生成と公開準備を終えてから登録してください。`マインドマップSlug`だけでは生成済みか判断できないため、自動的にリンクを組み立てません。

学習資材または学生用教材に`学習領域`Relationがある場合は、コードが一致する学習領域の`マインドマップ公開`を確認します。明示的にOFFならリンクを出しません。`マインドマップ名`があれば表示情報に使用します。プロパティが未整備の場合は、この登録表が公開設定になります。Relation取得に失敗した小単元もリンクを出しません。

既存のパーキンソン病マップは正式な小単元コードを確認できていないため、`unassigned`に置き、下部の関連教材から開ける状態を維持しています。コード確定後に`units`へ移してください。名前の部分一致や講義番号だけで別の小単元に接続することはありません。手動フォールバックの`index.qmd`に該当小単元がある場合は、同じ`.unit-heading`内に`.unit-mindmap`リンクを追加します。生成時の`manifest.json`には小単元ごとの公開マップを`mindmaps`に記録します。
