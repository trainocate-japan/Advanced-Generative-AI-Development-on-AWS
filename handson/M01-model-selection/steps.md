# モジュール 1: 基盤モデルの選択と設定 - ハンズオン手順

## パート 1: モデル評価とベンチマーク（10分）

### ステップ 1.1: プロジェクトの準備

```bash
sudo su - ec2-user
cd ~/handson/M01-model-selection
```

### ステップ 1.2: モデルベンチマーク比較の実行

```bash
python3.12 benchmark.py
```

このスクリプトは以下を測定します：
- **レイテンシー**: 合計応答時間
- **トークン使用量**: 入力/出力トークン数
- **コスト**: モデルごとの推定コスト
- **応答長**: 生成されたテキストの文字数

### ステップ 1.3: 結果の確認

出力される比較テーブルを確認し、以下を議論します：
- どのモデルがどのユースケースに最適か
- コストとパフォーマンスのトレードオフ
- レイテンシー要件に基づくモデル選定基準

---

## パート 2: 動的モデル選択 API のデプロイ（15分）

### ステップ 2.1: SAM テンプレートの確認

`template.yaml` で以下のリソースが定義されています：
- API Gateway REST API
- Lambda ルーティング関数（サーキットブレーカー内蔵）
- IAM ロール（Bedrock アクセス権限付き）
- CloudWatch ダッシュボード

### ステップ 2.2: ルーティングロジックの確認

`lambda/router.py` に実装されているルーティング戦略：

1. **リクエスト分類**: クエリの文字数・キーワードに基づいて複雑度を判定
2. **モデル選択**: 複雑度に応じてモデルを割り当て
   - `simple` → Amazon Nova Lite（安価・高速）
   - `medium` → Amazon Nova Pro（バランス）
   - `complex` → Claude Sonnet 4.5（高品質）
3. **サーキットブレーカー**: 障害発生時に自動フォールバック
4. **コスト管理**: 予算超過時に低コストモデルへ自動切り替え

### ステップ 2.3: デプロイ

```bash
sam build
sam deploy --stack-name m01 --resolve-s3 --capabilities CAPABILITY_IAM --no-confirm-changeset
```

デプロイ完了後、出力される API Gateway のエンドポイント URL をメモします：

```bash
aws cloudformation describe-stacks --stack-name m01 \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
```

### ステップ 2.4: 負荷テスト

100件のクエリ（simple=40, medium=30, complex=30）を一括送信して動的ルーティングの動作を確認します：

```bash
python3.12 load_test.py <API_URL>
```

出力される結果：
- 各クエリのルーティング先モデルとレイテンシー
- 複雑度別の成功率・平均レイテンシー・主なルーティング先
- モデル別の呼び出し回数と平均レイテンシー
- フォールバック発生回数

---

## パート 3: サーキットブレーカーと障害シミュレーション（15分）

### ステップ 3.1: ヘルスチェックの確認

```bash
API_URL=<デプロイ時に取得したURL>
curl -s $API_URL/health | python3.12 -m json.tool
```

レスポンス例：
```json
{
    "status": "healthy",
    "circuit_breakers": {},
    "timestamp": "2026-08-11T10:00:00"
}
```

### ステップ 3.2: 通常動作の確認

```bash
# simple → Nova Lite にルーティングされることを確認
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "S3とは？", "complexity": "simple"}' | python3.12 -m json.tool

# complex → Claude Sonnet にルーティングされることを確認
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "マルチリージョンDR設計をRTO5分RPO1分で提案してください", "complexity": "complex"}' | python3.12 -m json.tool
```

### ステップ 3.3: 障害シミュレーション（プロバイダー障害を発生させる）

```bash
# Anthropic (Claude) に timeout 障害をシミュレート
curl -s -X POST $API_URL/admin/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"provider": "us", "failure_type": "timeout"}' | python3.12 -m json.tool
```

### ステップ 3.4: フォールバック動作の確認

障害シミュレーション中に complex クエリを送信：

```bash
# 通常なら Claude に行くクエリだが、Nova Pro にフォールバックする
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "金融規制コンプライアンスのリスク評価を行ってください", "complexity": "complex"}' | python3.12 -m json.tool
```

レスポンスで以下を確認：
- `"fallback_used": true` になっている
- `"fallback_reason"` にサーキットブレーカーの情報
- `"model_used"` がフォールバック先モデルになっている

### ステップ 3.5: サーキットブレーカー状態の確認

```bash
curl -s $API_URL/health | python3.12 -m json.tool
```

`circuit_breakers` フィールドに `"OPEN"` 状態が表示されることを確認。

### ステップ 3.6: 障害の解除と回復確認

```bash
# 障害を解除
curl -s -X POST $API_URL/admin/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"provider": "us", "failure_type": "none"}' | python3.12 -m json.tool

# 30秒後（CB タイムアウト後）に complex クエリを送信 → Claude に復帰
sleep 35
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "マイクロサービスのCI/CD設計を提案してください", "complexity": "complex"}' | python3.12 -m json.tool
```

`"fallback_used": false` で元のモデルに復帰したことを確認。

---

## パート 4: CloudWatch ダッシュボードでの可視化（5分）

### ステップ 4.1: ダッシュボード URL の取得

```bash
aws cloudformation describe-stacks --stack-name m01 \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" --output text
```

### ステップ 4.2: ダッシュボードの確認

AWS コンソールで CloudWatch ダッシュボード（`GenAI-Model-Selection`）を開き確認：
- モデルごとの呼び出し回数
- レイテンシーの推移
- サーキットブレーカー状態
- 推定コスト

---

## デモでの見せ方

### デモ 1: 動的ルーティングの動作（7分）

1. `python3.12 load_test.py <API_URL>` を実行
2. リアルタイムで各クエリのルーティング先が表示される
3. 完了後のサマリーで以下を説明：
   - simple は Nova Lite、complex は Claude にルーティングされた
   - コスト差（Nova Lite: $0.00003 vs Claude: $0.005）
   - レイテンシー差（Nova Lite: ~1秒 vs Claude: ~3秒）
4. 「ユースケースに応じて最適なモデルを自動選択 → コスト削減 + 品質確保」

### デモ 2: 障害時のレジリエンス（7分）

1. `curl $API_URL/health` で全プロバイダー正常を確認
2. complex クエリを送信 → Claude で応答されることを確認
3. `curl -X POST $API_URL/admin/simulate-failure -d '{"provider":"us","failure_type":"timeout"}'` で障害発生
4. 同じ complex クエリを送信 → Nova Pro にフォールバック（`fallback_used: true`）
5. `curl $API_URL/health` でサーキットブレーカー OPEN を確認
6. 障害解除 → 30秒後に再送信 → Claude に復帰
7. CloudWatch ダッシュボードでメトリクスの変化を確認

### デモ 3: コスト比較（3分）

1. `python3.12 benchmark.py` の月間コスト試算を表示
2. 全リクエストを Claude で処理した場合 vs 動的ルーティングのコスト比較
3. 「70%のリクエストは簡単な質問 → Nova Lite で十分 → コスト90%削減」

---

## クリーンアップ

```bash
sam delete --stack-name m01
```

---

## 発展課題

1. **Canary デプロイ**: 新しいモデルバージョンを5%のトラフィックでテストするロジックを追加
2. **マルチリージョン**: us-east-1 と us-west-2 でのフェイルオーバー構成を設計
3. **カスタムメトリクス**: ドメイン固有の品質スコアに基づくルーティングを実装
