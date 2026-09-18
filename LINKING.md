# Quartoと辞書・Simulatorのリンク方針

Quartoには公開URLを直接書かず、教材の種類とSlugを記述する。URLの変更は `data/links.yml` だけで行う。

## 通常の用語リンク

```markdown
[心拍出量]{.ph-link data-kind="keyword" data-slug="cardiac-output"}
[Ca拮抗薬]{.ph-link data-kind="drug-class" data-slug="calcium-channel-blockers"}
[アムロジピン]{.ph-link data-kind="drug" data-slug="amlodipine"}
```

## Simulatorボタン

```markdown
[動かして理解する]{.ph-link .ph-simulator data-kind="simulator" data-slug="blood-pressure"}
```

## 運用ルール

- SlugはNotion・Web・Quartoで共通にする。
- NotionのURLや内部IDを `.qmd` に書かない。
- 未公開ページは `status: planned` とし、壊れたリンクを出さない。
- 公開後は `data/links.yml` のURLを確定し、`status: active` へ変更する。
- Simulatorはまず別タブで開く。iframe埋め込みは必要な教材だけ個別に検討する。
- 未登録SlugはRender時に `ph-links: unresolved slug` という警告を出す。

## 種類

| `data-kind` | 用途 | URLの想定 |
|---|---|---|
| `keyword` | 薬理・生理・病態用語 | `/dictionary/keywords/<slug>/` |
| `drug-class` | 薬効群 | `/dictionary/drug-classes/<slug>/` |
| `drug` | 個別薬剤 | `/dictionary/drugs/<slug>/` |
| `simulator` | インタラクティブ教材 | `/simulations/<slug>/` または現行公開URL |
