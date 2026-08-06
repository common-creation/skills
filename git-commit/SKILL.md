---
name: git-commit
description: Conventional Commits形式のコミットメッセージを生成し、gitコミットを実行するスキル。ユーザーが「コミットして」「変更をコミット」「/git-commit」などと言った時、またはコード変更後にコミットが必要な場面で使用する。feat, fix, chore, docs, style, refactor, perf, test, build, ciの種別をサポートし、スコープを自動推定する。変更が多い場合はコミットを適切に分割する。
---

# Git Commit

Conventional Commits形式でコミットメッセージを生成し、gitコミットを実行する。

## ワークフロー

1. 変更内容を分析する
2. コミットを計画する（必要に応じて分割）
3. Planモードでユーザーに提示・承認を得る
4. コミットを実行する

## Step 1: 変更内容の分析

以下のコマンドを並列実行して変更内容を把握する:

- `git status` — 変更・未追跡ファイルの一覧
- `git diff` — 未ステージの変更内容
- `git diff --cached` — ステージ済みの変更内容
- `git log --oneline -10` — 直近のコミットスタイル確認

## Step 2: コミット計画

### 種別の判定

変更内容から適切な種別を選択する:

| 種別 | 用途 |
|------|------|
| `feat` | 新機能の追加 |
| `fix` | バグ修正 |
| `chore` | ビルド、依存関係、設定などの雑務 |
| `docs` | ドキュメントのみの変更 |
| `style` | コードの意味に影響しない変更（空白、フォーマット、セミコロンなど） |
| `refactor` | バグ修正でも機能追加でもないコード変更 |
| `perf` | パフォーマンス改善 |
| `test` | テストの追加・修正 |
| `build` | ビルドシステムや外部依存関係の変更 |
| `ci` | CI設定ファイル・スクリプトの変更 |

### スコープの自動推定

変更ファイルのパスからスコープを推定する:

- 変更が単一ディレクトリ配下に集中 → そのディレクトリ名をスコープにする
  - 例: `src/auth/login.ts`, `src/auth/token.ts` → `auth`
- モノレポのパッケージ → パッケージ名をスコープにする
  - 例: `packages/api/src/handler.ts` → `api`
- 変更が広範囲に及ぶ場合 → スコープを省略する
- 設定ファイルのみ → `config` をスコープにする

### コミット分割の判断

以下の場合はコミットを分割する:

- 異なる種別の変更が混在（例: 新機能追加とバグ修正が同時）
- 論理的に無関係な変更が含まれる
- 異なるモジュール/機能に対する独立した変更

分割時のルール:
- 関連する変更をグループ化する
- 各コミットが単独で意味を持つようにする
- 依存関係がある場合は正しい順序でコミットする

### メッセージ形式

```
type(scope): summary

Optional body with more details.
```

- summaryは英語、命令形、小文字開始、末尾にピリオドなし、50文字以内
- bodyは必要な場合のみ。変更の理由や背景を英語で記述

**良い例:**

```
feat(auth): add JWT token refresh endpoint

Add automatic token refresh when access token expires.
Refresh tokens are stored in HTTP-only cookies.
```

```
fix(api): handle null response from payment gateway
```

```
chore: update dependencies to latest versions
```

## Step 3: Planモードでの提示

**EnterPlanModeを使用**して、コミット計画をユーザーに提示する。  
EnterPlanModeツールが存在しない場合は、コミット計画をユーザーに **メッセージ** で提示する。

Planには以下を含める:

### 単一コミットの場合

```markdown
## コミット計画

### コミット
- **タイトル:** `feat(auth): add JWT token refresh endpoint`
- **説明:** Add automatic token refresh when access token expires.
- **対象ファイル:**
  - `src/auth/refresh.ts` (新規)
  - `src/auth/middleware.ts` (変更)
  - `src/auth/types.ts` (変更)
```

### 複数コミットに分割する場合

```markdown
## コミット計画（N件のコミット）

### コミット 1/N
- **タイトル:** `fix(api): handle null response from payment gateway`
- **説明:** Add null check before accessing response body.
- **対象ファイル:**
  - `src/api/payment.ts` (変更)

### コミット 2/N
- **タイトル:** `feat(api): add retry logic for failed payments`
- **説明:** Retry up to 3 times with exponential backoff.
- **対象ファイル:**
  - `src/api/payment.ts` (変更)
  - `src/api/retry.ts` (新規)
```

ユーザーの承認を待つ。修正要望があれば反映する。

## Step 4: コミットの実行

承認後、各コミットを順番に実行する:

1. 対象ファイルをステージング: `git add <files>`
2. コミット実行（HEREDOCを使用）:
   ```bash
   git commit -m "$(cat <<'EOF'
   type(scope): summary

   Optional body.
   EOF
   )"
   ```
3. 複数コミットの場合は1-2を繰り返す
4. 最後に `git status` で結果を確認する

## 注意事項

- `.env`、credentials、秘密鍵などの機密ファイルをコミットしない
- `git add -A` や `git add .` ではなく、ファイルを個別に指定する
- `--amend` は使用しない（ユーザーが明示的に要求した場合を除く）
- `--no-verify` は使用しない（ユーザーが明示的に要求した場合を除く）
- pre-commitフックが失敗した場合は、問題を修正して新しいコミットを作成する
- コミット前の調査でLintやTestを行わない。pre-commitフックが失敗した場合のみ追加調査を行う
