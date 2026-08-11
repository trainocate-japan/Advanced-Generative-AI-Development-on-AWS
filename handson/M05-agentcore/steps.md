# モジュール 5: Amazon Bedrock AgentCore - ハンズオン手順

## 環境セットアップ

```bash
cd ~/handson/M05-agentcore

# 基本パッケージ
pip install boto3 strands-agents strands-agents-tools

# AgentCore Runtime デプロイ用
pip install bedrock-agentcore bedrock-agentcore-starter-toolkit

# フレームワーク比較用（パート3）
pip install langgraph langchain-aws langchain-core
pip install crewai crewai-tools
```

---

## パート 1: エージェントの基本設計（15分）

### ステップ 1.1: Strands Agents によるエージェント構築

```bash
python3.12 travel_agent.py
```

エージェントの基本コンポーネント：
- **モデル**: 推論エンジン（Nova Pro）
- **ツール**: 外部API/サービスとのインターフェース（TOOLS_SCHEMA で定義）
- **エージェントループ**: モデルが toolUse を返す限りツール実行を繰り返す
- **プロンプト**: エージェントの行動指針

### ステップ 1.2: ツールの定義

旅行プランニングエージェントのツール：
1. `search_flights`: フライト検索（出発地、目的地、日付）
2. `search_hotels`: ホテル検索（都市、チェックイン/アウト、予算）
3. `get_weather`: 天気予報取得（都市、日付）
4. `calculate_budget`: 旅行予算の計算

### ステップ 1.3: エージェントの実行

Converse API の `toolUse` による自律的ツール選択：
```
ユーザー: 来月東京から沖縄に2泊3日で旅行したいです。予算は10万円以内で。

エージェントループ:
  stopReason == "tool_use" → ツール実行 → 結果をモデルに返す → 再推論
  stopReason == "end_turn" → 最終回答を出力

モデルが自律的に判断:
  1. search_flights を呼ぶべき → 呼び出し → 結果取得
  2. search_hotels を呼ぶべき → 呼び出し → 結果取得
  3. get_weather を呼ぶべき → 呼び出し → 結果取得
  4. calculate_budget を呼ぶべき → 呼び出し → 結果取得
  5. 全情報が揃った → 最終プランを生成 (end_turn)
```

---

## パート 2: AgentCore の各コンポーネント（25分）

### ステップ 2.1: AgentCore Gateway - ツール管理とルーティング

```bash
python3.12 agentcore_gateway_demo.py
```

実行内容：
1. Gateway を作成（MCP プロトコル、NONE 認可）
2. Lambda ツールを Gateway Target として登録
3. 登録情報を確認

Gateway の機能：
- API / Lambda / MCP サーバーを MCP 互換ツールに変換
- セマンティック検索によるツール自動選択
- 認証・認可の一元管理

クリーンアップ：
```bash
python3.12 agentcore_gateway_demo.py --cleanup
```

### ステップ 2.2: AgentCore Memory - コンテキスト保持

```bash
python3.12 agentcore_memory_demo.py
```

実行内容：
1. Memory リソースを作成（要約 + ユーザー嗜好戦略）
2. 会話イベントを登録（短期記憶）
3. 短期記憶を取得（イベント一覧）
4. 長期記憶をセマンティック検索

Memory の戦略：
- **summaryMemoryStrategy**: 会話を要約して保存
- **userPreferenceMemoryStrategy**: ユーザー嗜好を自動抽出

```python
# メモリの活用例
# ユーザー: 「前回と同じホテルでお願いします」
# → retrieve_memory_records で過去の嗜好を検索
# → 「ANAが好き」「リゾートホテル希望」を取得
```

クリーンアップ：
```bash
python3.12 agentcore_memory_demo.py --cleanup
```

### ステップ 2.3: AgentCore Identity - セキュアなアクセス

```bash
python3.12 agentcore_identity_demo.py
```

実行内容：
1. Workload Identity を作成（エージェントに固有 ID を付与）
2. 登録済み Identity の一覧を確認

Identity の機能：
- エージェントに固有の ID を付与（IAM ロールとは別）
- OAuth2 フローによる委任アクセス
- Gateway と連携してツール呼び出しを認可
- 監査ログで全アクションを追跡

クリーンアップ：
```bash
python3.12 agentcore_identity_demo.py --cleanup
```

### ステップ 2.4: AgentCore Runtime - サーバーレスデプロイ

```bash
python3.12 agentcore_runtime_deploy.py
```

実行内容：
1. Strands エージェントのコードを生成
2. starter-toolkit で configure → launch（ビルド＆デプロイ）
3. デプロイ済みエージェントを invoke で呼び出し

※ Docker が起動中であること

デプロイの 3 ステップ:
```python
from bedrock_agentcore_starter_toolkit import Runtime

runtime = Runtime()
runtime.configure(entrypoint="agent.py", ...)  # 設定
runtime.launch()                                # ビルド & デプロイ
runtime.invoke({"prompt": "..."})              # 呼び出し
```

呼び出しテスト：
```bash
python3.12 agentcore_runtime_deploy.py --invoke "東京から沖縄の旅行プラン"
```

クリーンアップ：
```bash
python3.12 agentcore_runtime_deploy.py --cleanup
```

---

## パート 3: フレームワーク比較（10分）

### ステップ 3.1: Strands Agents の実行

```bash
python3.12 framework_strands.py
```

特徴:
- `@tool` デコレータでツールを定義
- `Agent(model, tools)` に渡すだけでエージェント完成
- `agent("メッセージ")` で対話（ツール呼び出しは自動）
- Amazon Bedrock とネイティブ統合
- AgentCore Runtime にそのままデプロイ可能

### ステップ 3.2: LangGraph の実行

```bash
python3.12 framework_langgraph.py
```

特徴:
- `StateGraph` でノードとエッジを定義（グラフベース）
- `TypedDict` でステートを型安全に管理
- `add_conditional_edges` で条件分岐を実現
- Human-in-the-Loop をグラフに組み込み可能
- `stream()` でステップごとの実行を可視化

### ステップ 3.3: CrewAI の実行

```bash
python3.12 framework_crewai.py
```

特徴:
- `Agent` に role / goal / backstory を設定（人格を持つ）
- `Task` で各エージェントの具体的な仕事を定義
- `Crew` でチームを編成し、`Process`（順次/階層）を指定
- エージェント間で結果を受け渡し（委任も可能）
- `crew.kickoff()` で全タスクを自動実行

### ステップ 3.4: 比較まとめ

| フレームワーク | 特徴 | 最適なユースケース |
|-------------|------|----------------|
| Strands Agents | AWS ネイティブ、シンプル | AWS 環境での標準的なエージェント |
| LangGraph | 複雑なステートフロー | 条件分岐が多い対話フロー |
| CrewAI | マルチエージェント協調 | チーム型のタスク分担 |

選定基準:
- **シンプルなエージェント** → Strands Agents
- **複雑なワークフロー** → LangGraph
- **複数エージェントの協調** → CrewAI
- **本番デプロイ** → どのフレームワークでも AgentCore でデプロイ可能

---

## クリーンアップ

```bash
# 各デモの --cleanup オプションで個別削除
python3.12 agentcore_gateway_demo.py --cleanup
python3.12 agentcore_memory_demo.py --cleanup
python3.12 agentcore_identity_demo.py --cleanup
python3.12 agentcore_runtime_deploy.py --cleanup
```

---

## 発展課題

1. **マルチエージェント**: 予約エージェントと推薦エージェントを連携させる
2. **Human-in-the-Loop**: 高額予約は人間の承認を必要とするフローを追加
3. **Gateway 活用**: 実際の Lambda 関数を Gateway Target として登録し、エージェントから呼び出す
4. **Memory 活用**: 複数セッションにまたがる長期記憶を使ってパーソナライズされた提案を実現
