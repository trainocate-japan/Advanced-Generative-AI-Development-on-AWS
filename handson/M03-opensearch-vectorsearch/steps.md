# モジュール 3 補足: Amazon OpenSearch Service によるベクトル検索 - ハンズオン手順

## パート 1: OpenSearch Serverless コレクションの構築（15分）

### ステップ 1.1: 環境準備

```bash
cd ~/handson/M03-opensearch-vectorsearch

# 必要なパッケージのインストール
pip install opensearch-py requests-aws4auth boto3
```

### ステップ 1.2: OpenSearch Serverless コレクションの作成

```bash
python3.12 setup_opensearch.py
```

スクリプトは以下を実行します：
1. 暗号化ポリシーの作成
2. ネットワークポリシーの作成（パブリックアクセス）
3. データアクセスポリシーの作成（現在の IAM ユーザー/ロールに権限付与）
4. ベクトル検索コレクションの作成
5. コレクションが ACTIVE になるまで待機

**ポイント（試験対応）:**
- OpenSearch Serverless は**コレクション**単位でリソースを管理（従来のドメインとは異なる）
- ベクトル検索には `type: VECTORSEARCH` のコレクションが必要
- 3 つのポリシー（暗号化・ネットワーク・データアクセス）が必須

### ステップ 1.3: コレクションの確認

```bash
# コレクション情報の確認
aws opensearchserverless list-collections
```

コンソールでも確認できます：
- AWS コンソール → OpenSearch → Serverless → Collections

---

## パート 2: ベクトル検索（k-NN）の実装（15分）

### ステップ 2.1: インデックスの作成とドキュメント投入

```bash
python3.12 vector_search.py --setup
```

このステップでは以下を実行します：

1. **インデックス作成（マッピング定義）**:
   - `title`: keyword 型（完全一致検索用）
   - `content`: text 型（全文検索用）
   - `category`: keyword 型（フィルタリング用）
   - `content_vector`: knn_vector 型（1024次元、cosinesimil）

2. **k-NN アルゴリズムの設定**:
   - `engine: nmslib`（HNSW アルゴリズム）
   - `space_type: cosinesimil`（コサイン類似度）
   - `ef_construction: 512`（インデックス構築時の精度パラメータ）
   - `m: 16`（各ノードの接続数）

3. **ドキュメントの埋め込み生成と投入**:
   - Titan Embeddings V2 でテキストをベクトル化
   - OpenSearch にドキュメント + ベクトルをインデックス

**ポイント（試験対応）:**
- HNSW（Hierarchical Navigable Small World）: 高速な近似 k-NN。メモリ使用量は多いが検索速度に優れる
- IVF（Inverted File Index）: メモリ効率が良いが精度は HNSW に劣る
- `ef_construction` を大きくすると精度↑、インデックス構築時間↑
- `m` を大きくすると精度↑、メモリ使用量↑

### ステップ 2.2: k-NN ベクトル検索の実行

```bash
python3.12 vector_search.py --search "クラウドサービスの障害対応手順"
```

以下のクエリで動作を確認します：
- 「クラウドサービスの障害対応手順」→ インシデント対応ドキュメントがヒット
- 「マイクロサービスのベストプラクティス」→ アーキテクチャガイドがヒット
- 「新入社員のオンボーディング」→ 人事関連ドキュメントがヒット

**観察ポイント:**
- コサイン類似度スコア（0〜1）の分布
- 完全一致しなくても意味的に関連する文書が検索される
- `k` パラメータ（返却件数）による結果の変化

### ステップ 2.3: k-NN アルゴリズムの比較

```bash
python3.12 vector_search.py --compare-algorithms
```

| パラメータ | HNSW (nmslib) | HNSW (faiss) | IVF (faiss) |
|-----------|---------------|--------------|-------------|
| 検索速度 | 高速 | 高速 | 中程度 |
| メモリ効率 | 低い | 低い | 高い |
| 精度 | 高い | 高い | 中程度 |
| 適するケース | リアルタイム検索 | リアルタイム検索 | 大規模データ |

---

## パート 3: ハイブリッド検索の実装（15分）

### ステップ 3.1: ハイブリッド検索の実行

```bash
python3.12 hybrid_search.py --query "Lambda 関数のタイムアウトエラー解決方法"
```

3 つの検索タイプを同時に実行し、結果を比較します：

| 検索タイプ | 方式 | 強み |
|-----------|------|------|
| キーワード検索（BM25） | テキストの完全/部分一致 | 特定エラーコード・固有名詞 |
| セマンティック検索（k-NN） | ベクトル類似度 | 概念的・探索的クエリ |
| ハイブリッド検索 | BM25 + k-NN のスコア統合 | 両方の強みを組み合わせ |

### ステップ 3.2: スコア正規化と重み付け

```bash
python3.12 hybrid_search.py --query "セキュリティのベストプラクティス" --semantic-weight 0.7
```

ハイブリッド検索のスコア統合方法：

```
final_score = (semantic_weight × normalized_knn_score) + ((1 - semantic_weight) × normalized_bm25_score)
```

**パラメータ実験:**
- `--semantic-weight 0.9`: 概念的クエリ向け（セマンティック重視）
- `--semantic-weight 0.5`: バランス型
- `--semantic-weight 0.2`: 特定用語クエリ向け（キーワード重視）

### ステップ 3.3: クエリタイプ別の最適な検索戦略

```bash
python3.12 hybrid_search.py --demo
```

以下のクエリタイプで結果を比較：

| クエリ | 最適な検索タイプ | 理由 |
|--------|----------------|------|
| `ERROR-5023` | キーワード検索 | 正確なコード一致が必要 |
| 「パフォーマンス改善のヒント」 | セマンティック検索 | 概念的・探索的 |
| 「Lambda timeout 解決方法」 | ハイブリッド検索 | 固有名詞 + 概念の混合 |

**ポイント（試験対応）:**
- ハイブリッド検索は「既存のキーワード検索がうまく動いている部分を壊さず、セマンティック検索で弱点を補う」パターン
- Amazon OpenSearch Service と Bedrock Knowledge Bases の両方でハイブリッド検索をサポート

---

## パート 4: カスタムスコアリングの実装（10分）

### ステップ 4.1: script_score によるカスタムスコアリング

```bash
python3.12 custom_scoring.py --query "障害対応" --boost-recent
```

カスタムスコアリングのユースケース：

1. **時間減衰（Time Decay）**: 新しいドキュメントを優先
2. **カテゴリブースト**: 特定カテゴリのスコアを増幅
3. **人気度ブースト**: 閲覧回数や評価に基づく加点

### ステップ 4.2: スコアリング関数の比較

```bash
python3.12 custom_scoring.py --compare
```

実装するスコアリング関数：

```
# 1. 基本 k-NN スコア（ベースライン）
score = cosineSimilarity(query_vector, doc_vector)

# 2. 時間減衰付き
score = cosineSimilarity(...) * exp(-decay_rate * days_since_published)

# 3. カテゴリブースト付き
score = cosineSimilarity(...) * (1 + category_boost_factor)

# 4. 複合スコアリング
score = (knn_score * 0.6) + (bm25_score * 0.2) + (recency_score * 0.1) + (popularity_score * 0.1)
```

### ステップ 4.3: フィルタリングとの組み合わせ

```bash
python3.12 custom_scoring.py --query "API設計" --filter-category "architecture"
```

メタデータフィルタリング + カスタムスコアリングの組み合わせ：
- カテゴリフィルタ: 検索対象を絞り込み
- 日付範囲フィルタ: 直近 N 日のドキュメントのみ
- カスタムスコアで最終ランキングを最適化

**ポイント（試験対応）:**
- OpenSearch Service はカスタムスコアリング関数に最大限の制御を提供
- OpenSearch Serverless ではカスタムスコアリングの一部制約あり → フル機能が必要な場合は OpenSearch Service（マネージドドメイン）を使用
- Bedrock Knowledge Bases では Retrieve API の結果を後処理してリランキングする方法もある

---

## パート 5: まとめと比較（5分）

### OpenSearch Serverless vs OpenSearch Service（マネージドドメイン）

| 観点 | OpenSearch Serverless | OpenSearch Service（ドメイン） |
|------|----------------------|------------------------------|
| 運用負荷 | 低い（自動スケーリング） | 中程度（シャード・ノード管理） |
| カスタムスコアリング | 制限あり | フル機能 |
| k-NN アルゴリズム | HNSW (faiss/nmslib) | HNSW + IVF |
| コスト | 使用量課金 | インスタンス時間課金 |
| 適するケース | 開発・小〜中規模 | 大規模・カスタム要件 |

### OpenSearch vs S3 Vectors vs Aurora pgvector

| 観点 | OpenSearch | S3 Vectors | Aurora pgvector |
|------|-----------|------------|-----------------|
| ハイブリッド検索 | ネイティブサポート | 非対応 | 非対応 |
| カスタムスコアリング | 柔軟 | 限定的 | SQL関数 |
| フルテキスト検索 | BM25 ネイティブ | 非対応 | 基本的 |
| 運用コスト | 中〜高 | 低 | 中 |
| Bedrock KB 統合 | ○ | ○ | ○ |

---

## デモ手順

### デモ 1: k-NN ベクトル検索（5分）
1. `python3.12 vector_search.py --search "システムの可用性を高める方法"` を実行
2. コサイン類似度スコアと検索結果を確認
3. 完全一致しない表現でも意味的に関連するドキュメントが返ることを説明
4. `--k 3` と `--k 10` で返却件数を変えて精度の変化を見る

### デモ 2: ハイブリッド検索の威力（5分）
1. キーワード検索のみ: `--mode keyword` → 特定用語には強いが概念検索に弱い
2. セマンティック検索のみ: `--mode semantic` → 概念は拾うが正確なコード番号に弱い
3. ハイブリッド検索: `--mode hybrid` → 両方をカバー
4. 「ERROR-5023」と「パフォーマンス改善」で違いを実演

### デモ 3: カスタムスコアリング（5分）
1. 基本スコアと時間減衰付きスコアの違いを表示
2. 古いドキュメントが下位にランキングされることを確認
3. カテゴリブースト適用で特定ドメインの文書が上位に来ることを確認
4. 「OpenSearch = 検索ランキングへの最大限の制御」を強調

---

## クリーンアップ

```bash
python3.12 cleanup.py
```

以下のリソースを削除します：
- OpenSearch Serverless コレクション
- 暗号化ポリシー
- ネットワークポリシー
- データアクセスポリシー

---

## 発展課題

1. **正確な k-NN との比較**: 近似 k-NN（ANN）と正確な k-NN（ブルートフォース）の精度・速度トレードオフを検証
2. **マルチテナント検索**: テナント ID をメタデータに含め、フィルタリングでテナント分離を実現
3. **Search Pipeline**: OpenSearch の Search Pipeline 機能でリランキングを自動化
4. **Bedrock KB 統合**: OpenSearch Serverless を Bedrock ナレッジベースのベクトルストアとして使用し、RetrieveAndGenerate API と連携
