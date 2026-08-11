"""
モジュール 4: インタラクティブ カスタマーサポート ワークフロー デモ

スライドの「インタラクティブデモンストレーション」に対応:
1. 受信リクエストを分析する（意図分類・感情分析）
2. 適切な専門家にルーティングする（条件付きロジック）
3. CRM データと統合する（顧客情報参照）
4. 構造化された応答を提供する（テンプレート応答生成）
5. 品質保証のためにインタラクションをログに記録する（品質スコア・ログ）

連続チェーン、条件付きロジック、外部データ統合、A/Bテストを含む
エンタープライズグレードのカスタマーサポート AI ワークフローを構築します。
"""

import boto3
import json
import time
from datetime import datetime

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "amazon.nova-pro-v1:0"


# ============================================================
# シミュレート CRM データベース（外部データ統合のデモ）
# ============================================================

CRM_DATABASE = {
    "C-1001": {
        "name": "田中 太郎",
        "tier": "Premium",
        "account_since": "2021-03-15",
        "monthly_spend": 15000,
        "open_tickets": 1,
        "last_interaction": "2026-07-28",
        "products": ["エンタープライズプラン", "API アドオン", "優先サポート"],
        "satisfaction_score": 4.2
    },
    "C-1002": {
        "name": "佐藤 花子",
        "tier": "Standard",
        "account_since": "2023-08-01",
        "monthly_spend": 5000,
        "open_tickets": 0,
        "last_interaction": "2026-08-05",
        "products": ["スタンダードプラン"],
        "satisfaction_score": 3.8
    },
    "C-1003": {
        "name": "鈴木 一郎",
        "tier": "Enterprise",
        "account_since": "2020-01-10",
        "monthly_spend": 80000,
        "open_tickets": 3,
        "last_interaction": "2026-08-10",
        "products": ["エンタープライズプラン", "専用インスタンス", "SLA 99.99%", "専任AM"],
        "satisfaction_score": 3.5
    }
}


# ============================================================
# 品質ログ（インタラクション記録）
# ============================================================

interaction_log = []


def log_interaction(step, data):
    """品質保証用のインタラクションログを記録"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "step": step,
        "data": data
    }
    interaction_log.append(entry)
    return entry


# ============================================================
# ステップ 1: 受信リクエストの分析
# ============================================================

def analyze_request(query, customer_id):
    """受信リクエストの意図分類と感情分析を実行"""

    analysis_prompt = f"""以下のカスタマーサポートの問い合わせを分析してください。

問い合わせ: {query}

以下のJSON形式のみで回答してください（説明不要）:
{{
  "category": "billing/technical/account/product/escalation",
  "urgency": "critical/high/medium/low",
  "sentiment": "positive/neutral/frustrated/angry",
  "complexity": "simple/moderate/complex",
  "key_entities": ["関連するキーワードを最大3つ"],
  "summary": "問い合わせの要約（1文）"
}}"""

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": analysis_prompt}]}],
        inferenceConfig={"temperature": 0, "maxTokens": 300}
    )

    raw_text = response['output']['message']['content'][0]['text']

    # JSONパース
    try:
        import re
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            analysis = json.loads(raw_text)
    except json.JSONDecodeError:
        analysis = {
            "category": "general",
            "urgency": "medium",
            "sentiment": "neutral",
            "complexity": "moderate",
            "key_entities": [],
            "summary": query[:50]
        }

    # ログ記録
    log_interaction("request_analysis", {
        "customer_id": customer_id,
        "query": query,
        "analysis": analysis
    })

    return analysis


# ============================================================
# ステップ 2: 適切な専門家にルーティング
# ============================================================

EXPERT_ROUTING = {
    "billing": {
        "team": "請求・会計チーム",
        "sla_minutes": 30,
        "system_prompt": """あなたは請求・会計サポートの上級スペシャリストです。

対応ガイドライン:
- 金銭に関わる問題は正確性を最優先
- 具体的な金額や日付を含めて回答
- 返金・調整が必要な場合はプロセスと期間を明示
- 共感を示しつつ、事実に基づいた説明を行う

応答構造:
1. 状況の確認と共感
2. 原因の説明（わかる場合）
3. 解決策と手順
4. 対応完了までの目安"""
    },
    "technical": {
        "team": "テクニカルサポートチーム",
        "sla_minutes": 60,
        "system_prompt": """あなたは上級テクニカルサポートエンジニアです。

対応ガイドライン:
- 問題を体系的にトラブルシュート
- ステップバイステップの解決手順を提示
- 回避策がある場合は先に提示してから根本対策を説明
- 技術的な詳細は顧客のレベルに合わせて調整

応答構造:
1. 問題の切り分け
2. 推定原因
3. 解決手順（番号付き）
4. 改善しない場合の次のステップ"""
    },
    "account": {
        "team": "アカウント管理チーム",
        "sla_minutes": 45,
        "system_prompt": """あなたはアカウント管理の専門スタッフです。

対応ガイドライン:
- セキュリティを最優先に考慮
- アカウント変更は確認ステップを設ける
- プラン変更は現在の利用状況と比較して提案
- アップグレード機会は押し付けず情報提供として

応答構造:
1. 本人確認の案内（必要な場合）
2. リクエスト内容の確認
3. 対応手順の説明
4. 変更による影響の説明"""
    },
    "product": {
        "team": "プロダクトスペシャリストチーム",
        "sla_minutes": 120,
        "system_prompt": """あなたはプロダクトの専門アドバイザーです。

対応ガイドライン:
- 製品の機能と制限を正確に説明
- ユースケースに基づいた具体的な提案
- ドキュメントやリソースへの参照を含める
- 機能リクエストは記録して開発チームへ転送

応答構造:
1. 質問内容の理解確認
2. 回答（具体例付き）
3. 関連する機能やベストプラクティス
4. 追加リソースの案内"""
    },
    "escalation": {
        "team": "エスカレーションマネージャー",
        "sla_minutes": 15,
        "system_prompt": """あなたはエスカレーション対応の上級マネージャーです。

対応ガイドライン:
- 即座に状況を把握し、最優先で対応
- 顧客の感情に十分配慮
- 具体的な補償や改善策を提示する権限あり
- 必要に応じて上位の意思決定者への連携を約束

応答構造:
1. 即時の謝罪と状況理解の表明
2. これまでの経緯の確認
3. 即座に取れるアクション
4. 再発防止策と今後のフォロー"""
    }
}


def route_to_expert(analysis, customer_data):
    """分析結果と顧客情報に基づいて適切な専門家チームにルーティング"""

    category = analysis.get("category", "product")
    urgency = analysis.get("urgency", "medium")
    sentiment = analysis.get("sentiment", "neutral")
    tier = customer_data.get("tier", "Standard")

    # エスカレーション判定ロジック
    should_escalate = False
    escalation_reason = ""

    if urgency == "critical":
        should_escalate = True
        escalation_reason = "緊急度: critical"
    elif sentiment in ("angry", "frustrated") and tier == "Enterprise":
        should_escalate = True
        escalation_reason = f"Enterprise顧客の不満 (sentiment: {sentiment})"
    elif customer_data.get("open_tickets", 0) >= 3:
        should_escalate = True
        escalation_reason = f"未解決チケット多数 ({customer_data['open_tickets']}件)"

    if should_escalate:
        routing = EXPERT_ROUTING["escalation"]
        final_category = "escalation"
    else:
        # カテゴリが定義にない場合はproductにフォールバック
        if category not in EXPERT_ROUTING:
            category = "product"
        routing = EXPERT_ROUTING[category]
        final_category = category

    # SLA 調整（Premium/Enterprise は短縮）
    sla = routing["sla_minutes"]
    if tier == "Premium":
        sla = int(sla * 0.7)
    elif tier == "Enterprise":
        sla = int(sla * 0.5)

    routing_result = {
        "team": routing["team"],
        "category": final_category,
        "sla_minutes": sla,
        "escalated": should_escalate,
        "escalation_reason": escalation_reason if should_escalate else None,
        "priority_boost": tier in ("Premium", "Enterprise")
    }

    # ログ記録
    log_interaction("routing", routing_result)

    return routing_result, routing["system_prompt"]


# ============================================================
# ステップ 3: CRM データと統合
# ============================================================

def lookup_crm(customer_id):
    """CRM からの顧客データ取得（シミュレーション）"""
    customer = CRM_DATABASE.get(customer_id, {
        "name": "不明な顧客",
        "tier": "Standard",
        "account_since": "N/A",
        "monthly_spend": 0,
        "open_tickets": 0,
        "products": [],
        "satisfaction_score": 0
    })

    # ログ記録
    log_interaction("crm_lookup", {
        "customer_id": customer_id,
        "tier": customer.get("tier"),
        "products": customer.get("products", [])
    })

    return customer


def build_context_with_crm(query, customer_data, analysis):
    """CRM データをプロンプトコンテキストに統合"""
    context = f"""【顧客情報（CRM）】
- 顧客名: {customer_data['name']}
- 顧客ティア: {customer_data['tier']}
- 利用開始: {customer_data['account_since']}
- 月額利用額: ¥{customer_data['monthly_spend']:,}
- 契約製品: {', '.join(customer_data['products'])}
- 未解決チケット: {customer_data['open_tickets']}件
- 顧客満足度: {customer_data['satisfaction_score']}/5.0

【問い合わせ分析】
- カテゴリ: {analysis['category']}
- 緊急度: {analysis['urgency']}
- 顧客感情: {analysis['sentiment']}
- 複雑度: {analysis['complexity']}

【お客様の問い合わせ】
{query}

上記の顧客情報と分析結果を踏まえて、このお客様に最適な回答を生成してください。
顧客ティアに応じた対応レベル（Enterprise/Premiumは特に丁寧に）で回答してください。"""

    return context


# ============================================================
# ステップ 4: 構造化された応答の生成
# ============================================================

def generate_structured_response(query, customer_data, analysis, system_prompt):
    """構造化されたテンプレート応答を生成"""

    context = build_context_with_crm(query, customer_data, analysis)

    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": context}]}],
        inferenceConfig={"temperature": 0.3, "maxTokens": 800}
    )

    response_text = response['output']['message']['content'][0]['text']

    # ログ記録
    log_interaction("response_generated", {
        "response_length": len(response_text),
        "tokens_used": response.get('usage', {})
    })

    return response_text


# ============================================================
# ステップ 5: 品質保証（品質スコアリングとログ）
# ============================================================

def quality_check(query, response_text, customer_data):
    """応答の品質を自動評価"""

    qa_prompt = f"""以下のカスタマーサポート応答の品質を評価してください。

【元の問い合わせ】
{query}

【顧客ティア】
{customer_data['tier']}

【生成された応答】
{response_text}

以下のJSON形式のみで評価してください:
{{
  "empathy_score": 1-5,
  "accuracy_score": 1-5,
  "completeness_score": 1-5,
  "tone_appropriate": true/false,
  "tier_appropriate": true/false,
  "actionable": true/false,
  "overall_score": 1-10,
  "improvement_suggestion": "改善提案（1文）"
}}"""

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": qa_prompt}]}],
            inferenceConfig={"temperature": 0, "maxTokens": 300}
        )
        raw = response['output']['message']['content'][0]['text']

        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            quality = json.loads(json_match.group())
        else:
            quality = json.loads(raw)
    except Exception:
        quality = {
            "empathy_score": 3,
            "accuracy_score": 3,
            "completeness_score": 3,
            "tone_appropriate": True,
            "tier_appropriate": True,
            "actionable": True,
            "overall_score": 6,
            "improvement_suggestion": "評価エラー"
        }

    # ログ記録
    log_interaction("quality_check", quality)

    return quality


# ============================================================
# 統合ワークフロー実行
# ============================================================

def run_workflow(customer_id, query):
    """カスタマーサポート ワークフロー全体を実行"""
    global interaction_log
    interaction_log = []

    print(f"\n{'━' * 70}")
    print(f"  📩 受信リクエスト")
    print(f"{'━' * 70}")
    print(f"  顧客ID: {customer_id}")
    print(f"  問い合わせ: {query}")

    # --- ステップ 1: リクエスト分析 ---
    print(f"\n  ┌─ [Step 1] 受信リクエストの分析")
    analysis = analyze_request(query, customer_id)
    print(f"  │  カテゴリ:  {analysis.get('category')}")
    print(f"  │  緊急度:    {analysis.get('urgency')}")
    print(f"  │  感情:      {analysis.get('sentiment')}")
    print(f"  │  複雑度:    {analysis.get('complexity')}")
    print(f"  │  要約:      {analysis.get('summary', '')}")

    # --- ステップ 2: CRM データ統合 ---
    print(f"  │")
    print(f"  ├─ [Step 2] CRM データ統合")
    customer_data = lookup_crm(customer_id)
    print(f"  │  顧客名:    {customer_data['name']}")
    print(f"  │  ティア:    {customer_data['tier']}")
    print(f"  │  月額:      ¥{customer_data['monthly_spend']:,}")
    print(f"  │  契約製品:  {', '.join(customer_data['products'][:2])}...")

    # --- ステップ 3: ルーティング ---
    print(f"  │")
    print(f"  ├─ [Step 3] 適切な専門家にルーティング")
    routing, system_prompt = route_to_expert(analysis, customer_data)
    print(f"  │  転送先:    {routing['team']}")
    print(f"  │  SLA:       {routing['sla_minutes']}分以内")
    if routing["escalated"]:
        print(f"  │  ⚠️  エスカレーション: {routing['escalation_reason']}")
    if routing["priority_boost"]:
        print(f"  │  ⭐ 優先対応（{customer_data['tier']}ティア）")

    # --- ステップ 4: 構造化応答の生成 ---
    print(f"  │")
    print(f"  ├─ [Step 4] 構造化された応答を生成")
    response_text = generate_structured_response(
        query, customer_data, analysis, system_prompt
    )
    print(f"  │")
    for line in response_text.split('\n')[:10]:
        print(f"  │  {line}")
    if len(response_text.split('\n')) > 10:
        print(f"  │  ...")

    # --- ステップ 5: 品質チェックとログ ---
    print(f"  │")
    print(f"  ├─ [Step 5] 品質保証チェック")
    quality = quality_check(query, response_text, customer_data)
    print(f"  │  品質スコア:     {quality.get('overall_score', 'N/A')}/10")
    print(f"  │  共感:           {quality.get('empathy_score', 'N/A')}/5")
    print(f"  │  正確性:         {quality.get('accuracy_score', 'N/A')}/5")
    print(f"  │  完全性:         {quality.get('completeness_score', 'N/A')}/5")
    print(f"  │  トーン適切:     {'✅' if quality.get('tone_appropriate') else '❌'}")
    print(f"  │  ティア対応:     {'✅' if quality.get('tier_appropriate') else '❌'}")
    print(f"  │  改善提案:       {quality.get('improvement_suggestion', 'なし')}")

    # --- インタラクションログ出力 ---
    print(f"  │")
    print(f"  └─ [ログ] インタラクション記録: {len(interaction_log)}エントリ")
    print(f"     ログID: {interaction_log[0]['timestamp'][:19]}")

    return {
        "analysis": analysis,
        "customer": customer_data,
        "routing": routing,
        "response": response_text,
        "quality": quality,
        "log_entries": len(interaction_log)
    }


# ============================================================
# デモ実行: 複数シナリオ
# ============================================================

def main():
    print("=" * 70)
    print("  インタラクティブ カスタマーサポート ワークフロー デモ")
    print("=" * 70)
    print("""
  このデモでは、エンタープライズグレードの AI カスタマーサポート
  ワークフローを構築します。各リクエストは以下のパイプラインを通過します:

  [受信] → [分析] → [CRM統合] → [ルーティング] → [応答生成] → [品質チェック]
     │                                                              │
     └──────────── インタラクションログ記録 ─────────────────────────┘
""")

    # テストシナリオ
    scenarios = [
        {
            "customer_id": "C-1002",
            "query": "先月の請求が通常より高いのですが、内訳を確認させてください。APIの利用量が増えた覚えはないのですが。",
            "description": "Standard顧客 - 請求問い合わせ（通常対応）"
        },
        {
            "customer_id": "C-1001",
            "query": "API のレスポンスタイムが昨日から3倍に悪化しています。本番環境に影響が出ており早急に対応が必要です。",
            "description": "Premium顧客 - 技術問題（優先対応）"
        },
        {
            "customer_id": "C-1003",
            "query": "過去2週間で3回もサービス停止が発生しています。SLA違反ではないですか？契約の見直しも含めて責任者と話がしたい。",
            "description": "Enterprise顧客 - 複数障害（エスカレーション）"
        },
    ]

    results = []

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'═' * 70}")
        print(f"  シナリオ {i}: {scenario['description']}")
        print(f"{'═' * 70}")

        result = run_workflow(scenario["customer_id"], scenario["query"])
        results.append(result)

        if i < len(scenarios):
            time.sleep(2)

    # ----------------------------------------------------------
    # サマリー
    # ----------------------------------------------------------
    print(f"\n\n{'═' * 70}")
    print("  ワークフロー実行サマリー")
    print(f"{'═' * 70}")
    print(f"\n  {'シナリオ':<8} {'カテゴリ':<12} {'ルーティング':<24} {'品質':<6} {'エスカレ'}")
    print(f"  {'─' * 65}")
    for i, (sc, r) in enumerate(zip(scenarios, results), 1):
        cat = r["analysis"].get("category", "?")
        team = r["routing"]["team"]
        score = r["quality"].get("overall_score", "?")
        esc = "⚠️ Yes" if r["routing"]["escalated"] else "No"
        print(f"  {i:<8} {cat:<12} {team:<24} {score}/10  {esc}")

    print(f"""
{'═' * 70}
  アーキテクチャまとめ
{'═' * 70}

  ┌─────────────────────────────────────────────────────────────────────┐
  │                  カスタマーサポート AI ワークフロー                  │
  │                                                                     │
  │  [受信]──▶[意図分類]──▶[CRM参照]──▶[ルーティング]──▶[応答生成]──▶[品質] │
  │    │        │             │            │               │          │  │
  │    │      感情分析       顧客情報      条件分岐       テンプレート  QAスコア │
  │    │      複雑度判定     契約情報      SLA調整        CRM統合     ログ記録 │
  │    │                    利用履歴      エスカレ判定                       │
  │    │                                                              │  │
  │    └────────────── インタラクションログ（全ステップ記録） ──────────┘  │
  └─────────────────────────────────────────────────────────────────────┘

  本番運用で追加すべき要素:
  • Amazon Bedrock Guardrails による入出力フィルタリング
  • CloudWatch Logs/Metrics による運用監視
  • DynamoDB によるセッション・チケット管理
  • Amazon Connect との統合（音声チャネル）
  • プロンプト管理 API によるバージョン管理と A/B テスト
""")


if __name__ == "__main__":
    main()
