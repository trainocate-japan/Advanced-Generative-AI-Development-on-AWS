"""
モジュール 4: プロンプトフローとオーケストレーション デモ
- マルチステップワークフローの構築
- 条件付きルーティング（意図分類→専門ペルソナへ転送）
- 動的プロンプト選択（言語検出、複雑度判定）
- A/B テストフレームワーク
"""

import boto3
import json
import time

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "amazon.nova-pro-v1:0"


# ============================================================
# プロンプトフロー: ノード定義
# ============================================================

FLOW_NODES = {
    "classify": {
        "name": "意図分類ノード",
        "prompt": """以下のカスタマーサポート問い合わせを分類してください。

カテゴリ（1つ選択）:
- billing: 請求・支払い関連
- technical: 技術的な問題
- account: アカウント管理
- general: 一般的な質問

緊急度:
- high: 即時対応が必要（金銭被害、サービス停止）
- medium: 早めの対応が望ましい
- low: 通常対応で可

問い合わせ: {query}

以下のJSON形式のみで回答してください:
{{"category": "...", "urgency": "...", "summary": "..."}}"""
    },
    "billing": {
        "name": "請求サポート ペルソナ",
        "system_prompt": """あなたは請求・会計サポートの専門家です。

対応方針:
- 金銭に関わる問題は最優先で対応
- 具体的な調査手順と解決までの目安を提示
- 返金が必要な場合はプロセスを明確に説明
- 常に共感を示し、不安を軽減する

応答形式:
1. 状況の確認と共感
2. 調査・対応手順の説明
3. 解決までの目安
4. 追加サポートの案内"""
    },
    "technical": {
        "name": "テクニカルサポート ペルソナ",
        "system_prompt": """あなたは上級テクニカルサポートエンジニアです。

対応方針:
- 技術的な問題を体系的にトラブルシュート
- ステップバイステップの解決手順を提示
- 必要に応じてエスカレーション基準を説明
- 回避策がある場合は先に提示

応答形式:
1. 問題の切り分け
2. 推定原因
3. 解決手順（番号付き）
4. 改善しない場合の次のステップ"""
    },
    "account": {
        "name": "アカウント管理 ペルソナ",
        "system_prompt": """あなたはアカウント管理の専門スタッフです。

対応方針:
- セキュリティを最優先に考慮
- 本人確認の手順を明確に案内
- アカウント変更は慎重に、確認ステップを設ける
- プライバシーに配慮した説明

応答形式:
1. セキュリティ確認事項
2. 対応可能な操作の説明
3. 必要な手続きの案内
4. 注意事項"""
    },
    "general": {
        "name": "一般サポート ペルソナ",
        "system_prompt": """あなたは親切で知識豊富なカスタマーサポート担当です。

対応方針:
- わかりやすく丁寧に説明
- 関連情報やリソースへのリンクを案内
- FAQ に該当する場合は簡潔に回答
- 専門チームへの転送が必要な場合は案内

応答形式:
1. 質問への直接的な回答
2. 補足情報
3. 関連するヘルプリソース"""
    },
    "validate": {
        "name": "出力検証ノード",
        "prompt": """以下のカスタマーサポート応答の品質を検証してください。

元の問い合わせ: {query}
生成された応答: {response}

検証項目:
1. 共感・礼儀: 適切な共感表現が含まれているか
2. 正確性: 問い合わせに対して的確に回答しているか
3. 完全性: 必要な情報が網羅されているか
4. 次のアクション: 明確な次のステップが示されているか
5. 不適切表現: 不適切な表現や約束がないか

以下のJSON形式のみで回答:
{{"empathy": true/false, "accuracy": true/false, "completeness": true/false, "next_action": true/false, "appropriate": true/false, "overall_score": 1-10, "feedback": "..."}}"""
    }
}


def invoke_model(prompt, system_prompt=None, temperature=0.2, max_tokens=600):
    """モデル呼び出しのユーティリティ"""
    kwargs = {
        "modelId": MODEL_ID,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens}
    }
    if system_prompt:
        kwargs["system"] = [{"text": system_prompt}]

    response = bedrock.converse(**kwargs)
    return response['output']['message']['content'][0]['text']


# ============================================================
# デモ 1: マルチステップ プロンプトフロー
# ============================================================

def demo_prompt_flow():
    """カスタマーサポート プロンプトフローのデモ"""
    print("=" * 70)
    print("  デモ 1: プロンプトフロー - マルチステップオーケストレーション")
    print("=" * 70)

    queries = [
        "先月の請求書が二重に引き落とされているようです。確認と返金をお願いします。",
        "ログインしようとするとエラーコード503が表示されて利用できません。",
        "契約プランのアップグレード方法を教えてください。"
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n{'━' * 70}")
        print(f"  テストケース {i}: {query}")
        print(f"{'━' * 70}")

        # ステップ 1: 意図分類
        print("\n  ┌─ [ノード1: 意図分類]")
        try:
            classify_prompt = FLOW_NODES["classify"]["prompt"].format(query=query)
            classification_raw = invoke_model(classify_prompt, temperature=0)
            print(f"  │  結果: {classification_raw.strip()}")

            # JSONパース試行
            try:
                classification = json.loads(classification_raw.strip())
            except json.JSONDecodeError:
                # JSON抽出を試みる
                import re
                json_match = re.search(r'\{.*\}', classification_raw, re.DOTALL)
                if json_match:
                    classification = json.loads(json_match.group())
                else:
                    classification = {"category": "general", "urgency": "medium", "summary": query[:30]}
        except Exception as e:
            print(f"  │  エラー: {e}")
            classification = {"category": "general", "urgency": "medium", "summary": query[:30]}

        category = classification.get("category", "general")
        urgency = classification.get("urgency", "medium")

        # ステップ 2: ルーティング
        print(f"  │")
        print(f"  ├─ [ノード2: ルーティング]")
        print(f"  │  → カテゴリ: {category}")
        print(f"  │  → 緊急度: {urgency}")
        if urgency == "high":
            print(f"  │  → ⚠️  優先対応フラグ設定")

        # ステップ 3: 専門ペルソナによる応答生成
        print(f"  │")
        print(f"  ├─ [ノード3: 応答生成 ({FLOW_NODES[category]['name']})]")
        try:
            system = FLOW_NODES[category]["system_prompt"]
            response_text = invoke_model(query, system_prompt=system, temperature=0.3)
            # 表示を整形
            for line in response_text.split('\n')[:8]:
                print(f"  │  {line}")
            if len(response_text.split('\n')) > 8:
                print(f"  │  ...")
        except Exception as e:
            response_text = f"申し訳ございません。現在対応準備中です。"
            print(f"  │  エラー: {e}")

        # ステップ 4: 出力検証
        print(f"  │")
        print(f"  ├─ [ノード4: 出力検証]")
        try:
            validate_prompt = FLOW_NODES["validate"]["prompt"].format(
                query=query, response=response_text[:500]
            )
            validation_raw = invoke_model(validate_prompt, temperature=0, max_tokens=300)
            try:
                validation = json.loads(validation_raw.strip())
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'\{.*\}', validation_raw, re.DOTALL)
                if json_match:
                    validation = json.loads(json_match.group())
                else:
                    validation = {"overall_score": 7, "feedback": "検証完了"}

            score = validation.get("overall_score", "N/A")
            print(f"  │  品質スコア: {score}/10")
            print(f"  │  共感表現: {'✅' if validation.get('empathy') else '❌'}")
            print(f"  │  正確性:   {'✅' if validation.get('accuracy') else '❌'}")
            print(f"  │  完全性:   {'✅' if validation.get('completeness') else '❌'}")
            print(f"  │  次の行動: {'✅' if validation.get('next_action') else '❌'}")
        except Exception as e:
            print(f"  │  検証エラー: {e}")

        print(f"  │")
        print(f"  └─ フロー完了 ✅")

        if i < len(queries):
            time.sleep(1)


# ============================================================
# デモ 2: 動的プロンプト選択（条件付きロジック）
# ============================================================

def demo_conditional_routing():
    """条件付きルーティングのデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: 動的プロンプト選択（条件付きロジック）")
    print("=" * 70)

    # 言語検出 → 適切な言語で応答
    test_queries = [
        ("日本語", "製品の返品ポリシーを教えてください。"),
        ("English", "What is your return policy?"),
        ("混合", "AWSのLambdaについて教えてください。Cold startの対策は？"),
    ]

    print(f"\n{'─' * 70}")
    print("  条件 1: 言語検出による応答言語の自動切り替え")
    print(f"{'─' * 70}")

    language_detect_prompt = """以下のテキストの主要言語を判定してください。
テキスト: {text}

以下のJSON形式のみで回答:
{{"language": "ja" or "en", "confidence": 0.0-1.0}}"""

    for label, query in test_queries:
        print(f"\n  入力 ({label}): {query}")
        try:
            detect_prompt = language_detect_prompt.format(text=query)
            result = invoke_model(detect_prompt, temperature=0, max_tokens=100)
            print(f"  検出結果: {result.strip()}")
        except Exception as e:
            print(f"  エラー: {e}")

    # 複雑度判定 → 簡易回答 or 詳細分析
    print(f"\n{'─' * 70}")
    print("  条件 2: クエリ複雑度による応答深度の自動調整")
    print(f"{'─' * 70}")

    complexity_queries = [
        ("簡単", "営業時間は何時までですか？"),
        ("中程度", "プランAとプランBの違いを比較して、どちらが中小企業に向いているか教えてください。"),
        ("複雑", "マイクロサービスアーキテクチャへの移行を検討中です。現在のモノリシック構成からの段階的移行計画、リスク評価、必要なチーム体制、推定コストを含む提案をお願いします。"),
    ]

    complexity_prompt = """以下の問い合わせの複雑度を判定してください。

問い合わせ: {query}

判定基準:
- simple: 単一の事実確認、FAQ的な質問
- moderate: 比較や選択を含む質問
- complex: 多面的な分析や専門知識が必要な質問

以下のJSON形式のみで回答:
{{"complexity": "simple/moderate/complex", "reasoning": "...", "recommended_depth": "1-2文/3-5段落/詳細レポート"}}"""

    for label, query in complexity_queries:
        print(f"\n  入力 ({label}): {query[:50]}...")
        try:
            prompt = complexity_prompt.format(query=query)
            result = invoke_model(prompt, temperature=0, max_tokens=200)
            print(f"  判定: {result.strip()}")
        except Exception as e:
            print(f"  エラー: {e}")


# ============================================================
# デモ 3: A/B テストフレームワーク
# ============================================================

def demo_ab_testing():
    """プロンプト A/B テストのデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: A/B テストフレームワーク")
    print("=" * 70)

    # バリアント定義
    variants = {
        "A（現行）": {
            "system": "あなたはカスタマーサポート担当です。お客様の質問に回答してください。",
            "description": "シンプルなシステムプロンプト"
        },
        "B（改善版）": {
            "system": """あなたは経験豊富なカスタマーサポートの専門家です。

応答ガイドライン:
1. まず共感を示す（お客様の状況を理解していることを伝える）
2. 問題を簡潔に要約する
3. 解決策をステップバイステップで提示する
4. 追加の質問がないか確認する

トーン: 温かく、プロフェッショナルで、簡潔に
制約: 200文字以内で回答する""",
            "description": "構造化されたガイドライン付きプロンプト"
        }
    }

    test_query = "注文した商品が届かないのですが、どうすればいいですか？"
    print(f"\n  テストクエリ: {test_query}")
    print(f"\n  バリアント比較:")

    results = {}
    for variant_name, config in variants.items():
        print(f"\n{'─' * 70}")
        print(f"  バリアント {variant_name}: {config['description']}")
        print(f"{'─' * 70}")

        try:
            start_time = time.time()
            response = invoke_model(
                test_query,
                system_prompt=config["system"],
                temperature=0.3,
                max_tokens=400
            )
            elapsed = time.time() - start_time

            print(f"\n  応答:\n  {response[:300]}")
            print(f"\n  メトリクス:")
            print(f"    レイテンシー: {elapsed:.2f}秒")
            print(f"    トークン数（概算）: 約{len(response) // 2}トークン")

            results[variant_name] = {
                "response": response,
                "latency": elapsed,
                "tokens": len(response) // 2
            }
        except Exception as e:
            print(f"  エラー: {e}")

        time.sleep(1)

    # A/B テスト結果サマリー
    if len(results) == 2:
        print(f"\n{'─' * 70}")
        print("  A/B テスト結果サマリー")
        print(f"{'─' * 70}")
        print("""
  ┌────────────────┬──────────────────┬──────────────────┐
  │ メトリクス     │ バリアント A     │ バリアント B     │
  ├────────────────┼──────────────────┼──────────────────┤""")
        a = results.get("A（現行）", {})
        b = results.get("B（改善版）", {})
        print(f"  │ レイテンシー   │ {a.get('latency', 0):.2f}秒{' ' * (12 - len(f'{a.get(chr(108) + chr(97) + chr(116) + chr(101) + chr(110) + chr(99) + chr(121), 0):.2f}秒'))}│ {b.get('latency', 0):.2f}秒{' ' * (12 - len(f'{b.get(chr(108) + chr(97) + chr(116) + chr(101) + chr(110) + chr(99) + chr(121), 0):.2f}秒'))}│")
        print(f"  │ トークン数     │ ~{a.get('tokens', 0)}{' ' * (14 - len(str(a.get('tokens', 0))))}│ ~{b.get('tokens', 0)}{' ' * (14 - len(str(b.get('tokens', 0))))}│")
        print("  └────────────────┴──────────────────┴──────────────────┘")

        print("""
  A/B テスト運用のポイント:
  • 統計的有意性を確保するため、十分なサンプル数で実施
  • 品質スコアはLLM-as-Judge または人間評価で測定
  • レイテンシーとトークン効率もコスト指標として追跡
  • 勝者バリアントを段階的にロールアウト（カナリアデプロイ）
""")


# ============================================================
# デモ 4: Bedrock プロンプトフロー概要
# ============================================================

def demo_bedrock_prompt_flow_overview():
    """Bedrock プロンプトフローの概要説明"""
    print("\n\n" + "=" * 70)
    print("  デモ 4: Bedrock プロンプトフロー（コンソール操作ガイド）")
    print("=" * 70)
    print("""
  Bedrock プロンプトフローは、複数のプロンプトを視覚的に
  接続してワークフローを構築するマネージドサービスです。

  ┌────────────────────────────────────────────────────────────────┐
  │                    プロンプトフロー アーキテクチャ              │
  │                                                                │
  │  [Input] ──▶ [分類] ──▶ [条件分岐] ──▶ [処理A] ──▶ [Output]  │
  │                              │                                  │
  │                              └──▶ [処理B] ──▶ [検証] ──▶ [Out] │
  └────────────────────────────────────────────────────────────────┘

  ノードタイプ:
  ┌──────────────┬──────────────────────────────────────────────┐
  │ ノード       │ 説明                                         │
  ├──────────────┼──────────────────────────────────────────────┤
  │ Input        │ フローへの入力を受け取る                     │
  │ Prompt       │ LLM にプロンプトを送信し応答を取得           │
  │ Condition    │ 条件に基づいてフローを分岐                   │
  │ Lambda       │ カスタムロジックを Lambda で実行             │
  │ Knowledge    │ ナレッジベースから情報を検索                  │
  │ S3 Storage   │ S3 からデータを読み書き                      │
  │ Output       │ フローの最終結果を返却                       │
  └──────────────┴──────────────────────────────────────────────┘

  コンソールでの作成手順:
  1. AWS コンソール → Amazon Bedrock → プロンプトフロー
  2. 「フローを作成」をクリック
  3. ビジュアルエディタでノードをドラッグ＆ドロップ
  4. ノード間を接続線でつなぐ
  5. 各ノードのプロンプトやパラメータを設定
  6. 「テスト」ボタンでフローを実行確認
  7. バージョンを作成 → エイリアスに紐づけてデプロイ

  API からの呼び出し:
  ─────────────────────────────────────────────────────────────
  bedrock_agent = boto3.client('bedrock-agent-runtime')
  response = bedrock_agent.invoke_flow(
      flowIdentifier='FLOW_ID',
      flowAliasIdentifier='ALIAS_ID',
      inputs=[{
          'content': {'document': 'ユーザーの入力テキスト'},
          'nodeName': 'FlowInputNode',
          'nodeOutputName': 'document'
      }]
  )
  ─────────────────────────────────────────────────────────────
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    demo_prompt_flow()
    time.sleep(1)
    demo_conditional_routing()
    time.sleep(1)
    demo_ab_testing()
    demo_bedrock_prompt_flow_overview()
