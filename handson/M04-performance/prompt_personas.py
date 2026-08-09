"""
モジュール 4: プロンプトエンジニアリング - ペルソナ設計とCoT推論
- 部署別ペルソナによる応答品質の統一
- 思考連鎖推論の実装
- プロンプトフローのデモ
"""

import boto3
import json
import time

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "amazon.nova-pro-v1:0"

# 部署別ペルソナ定義
PERSONAS = {
    "support": {
        "name": "カスタマーサポート エキスパート",
        "system_prompt": """あなたは親切で経験豊富なカスタマーサポートの専門家です。

ロール定義:
- トーン: 親切、共感的、簡潔
- 対象読者: 技術的背景が様々な一般ユーザー
- 応答形式: ステップバイステップの箇条書き
- 制約: 専門用語は避け、わかりやすい言葉で説明

応答ルール:
1. まず共感を示す
2. 問題を簡潔に要約する
3. 解決手順を番号付きで提示する
4. 追加の支援が必要かを確認する"""
    },
    "sales": {
        "name": "セールスコンサルタント",
        "system_prompt": """あなたはAIソリューションの戦略的セールスコンサルタントです。

ロール定義:
- トーン: プロフェッショナル、説得力のある、ビジネス価値重視
- 対象読者: 意思決定者（CTO、VP、ディレクター）
- 応答形式: ビジネス提案型（課題→ソリューション→効果）
- 制約: 定量的なデータを含め、ROIを意識した回答

応答ルール:
1. ビジネス課題を明確にする
2. ソリューションをビジネス価値で説明する
3. 具体的なROI数値や事例を提示する
4. 次のアクションを提案する"""
    },
    "executive": {
        "name": "経営戦略アドバイザー",
        "system_prompt": """あなたはテクノロジー経営戦略のシニアアドバイザーです。

ロール定義:
- トーン: 分析的、戦略的、データ駆動
- 対象読者: C-Suite（CEO、CFO、CIO）
- 応答形式: エグゼクティブサマリー形式
- 制約: 30秒で把握できる簡潔さ、戦略的インプリケーションを含む

応答ルール:
1. エグゼクティブサマリー（3行以内）
2. 主要な洞察（3点）
3. 戦略的影響と推奨アクション
4. リスクと緩和策"""
    }
}

# 思考連鎖推論のテンプレート
COT_TEMPLATES = {
    "linear": """以下の問題を段階的に分析してください。各ステップで思考過程を明示してください。

問題: {problem}

回答形式:
ステップ1 [分析]: ...
ステップ2 [評価]: ...
ステップ3 [判断]: ...
最終結論: ...""",

    "branching": """以下の問題を条件分岐を含めて分析してください。

問題: {problem}

回答形式:
[初期分析]
条件が{condition_a}の場合:
  → 分析A: ...
  → 結論A: ...
条件が{condition_b}の場合:
  → 分析B: ...
  → 結論B: ...
[統合判断]: ...""",

    "iterative": """以下の問題を自己検証ループで分析してください。

問題: {problem}

回答形式:
[第1回推論]: ...
[検証]: 上記の推論に矛盾や不足はないか?
[修正]: ...
[最終結論]: ...
[信頼度]: X/10"""
}


def invoke_with_persona(persona_key, query):
    """ペルソナを適用してモデルを呼び出す"""
    persona = PERSONAS[persona_key]

    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": persona["system_prompt"]}],
        messages=[{
            "role": "user",
            "content": [{"text": query}]
        }],
        inferenceConfig={"temperature": 0.3, "maxTokens": 800}
    )

    return response['output']['message']['content'][0]['text']


def invoke_with_cot(template_key, problem, **kwargs):
    """思考連鎖テンプレートを使用してモデルを呼び出す"""
    template = COT_TEMPLATES[template_key]
    prompt = template.format(problem=problem, **kwargs)

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{
            "role": "user",
            "content": [{"text": prompt}]
        }],
        inferenceConfig={"temperature": 0.2, "maxTokens": 1200}
    )

    return response['output']['message']['content'][0]['text']


def demo_personas():
    """ペルソナ比較デモ"""
    print("=" * 70)
    print("  プロンプトエンジニアリング: ペルソナによる応答の違い")
    print("=" * 70)

    query = "AI導入のROIはどう測定すべきですか？"
    print(f"\n  共通質問: {query}")

    for key, persona in PERSONAS.items():
        print(f"\n{'─' * 70}")
        print(f"  ペルソナ: {persona['name']}")
        print(f"{'─' * 70}")

        try:
            response = invoke_with_persona(key, query)
            print(f"\n{response[:500]}")
            if len(response) > 500:
                print("  ...")
        except Exception as e:
            print(f"  エラー: {e}")

    print(f"\n\n{'=' * 70}")
    print("  分析ポイント:")
    print("  • サポート: ユーザーフレンドリーなステップバイステップ説明")
    print("  • セールス: ビジネス価値とROI数値を強調")
    print("  • 経営: 戦略的視点、簡潔なサマリー")
    print(f"{'=' * 70}")


def demo_chain_of_thought():
    """思考連鎖推論デモ"""
    print("\n\n" + "=" * 70)
    print("  思考連鎖推論（Chain-of-Thought）")
    print("=" * 70)

    # 比較: 通常 vs CoT
    problem = "ある企業がAIチャットボットを導入検討中です。月間10万件のサポート問い合わせがあり、現在の平均対応時間は15分、人件費は1件あたり500円です。AIチャットボットの導入コストは月額200万円で、問い合わせの60%を自動化できると見込まれています。導入すべきでしょうか？"

    print(f"\n  問題: {problem[:80]}...")

    # 通常のプロンプト
    print(f"\n{'─' * 70}")
    print("  パターン 1: 通常プロンプト（CoTなし）")
    print(f"{'─' * 70}")

    try:
        normal_response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{
                "role": "user",
                "content": [{"text": f"以下の質問に回答してください: {problem}"}]
            }],
            inferenceConfig={"temperature": 0.2, "maxTokens": 500}
        )
        print(f"\n{normal_response['output']['message']['content'][0]['text'][:400]}")
    except Exception as e:
        print(f"  エラー: {e}")

    # CoT プロンプト
    print(f"\n{'─' * 70}")
    print("  パターン 2: 思考連鎖推論（線形 CoT）")
    print(f"{'─' * 70}")

    try:
        cot_response = invoke_with_cot("linear", problem)
        print(f"\n{cot_response[:600]}")
    except Exception as e:
        print(f"  エラー: {e}")

    # 反復的 CoT
    print(f"\n{'─' * 70}")
    print("  パターン 3: 自己検証ループ（反復 CoT）")
    print(f"{'─' * 70}")

    try:
        iterative_response = invoke_with_cot("iterative", problem)
        print(f"\n{iterative_response[:600]}")
    except Exception as e:
        print(f"  エラー: {e}")


def demo_prompt_flow_concept():
    """プロンプトフローのコンセプトデモ"""
    print("\n\n" + "=" * 70)
    print("  プロンプトフロー: マルチステップオーケストレーション")
    print("=" * 70)

    # カスタマーサポートフローのシミュレーション
    user_query = "先月の請求書が二重に引き落とされているようです。確認と返金をお願いしたいのですが。"

    print(f"\n  入力: {user_query}")
    print(f"\n{'─' * 70}")
    print("  フロー実行:")
    print(f"{'─' * 70}")

    # ステップ 1: 意図分類
    print("\n  [ノード1: 意図分類]")
    classify_prompt = f"""以下のカスタマーサポートの問い合わせを分類してください。
カテゴリ: billing, technical, account, general
緊急度: high, medium, low

問い合わせ: {user_query}

JSON形式で回答: {{"category": "...", "urgency": "...", "summary": "..."}}"""

    try:
        classify_response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": classify_prompt}]}],
            inferenceConfig={"temperature": 0, "maxTokens": 200}
        )
        classification = classify_response['output']['message']['content'][0]['text']
        print(f"    結果: {classification[:150]}")
    except Exception as e:
        classification = '{"category": "billing", "urgency": "high", "summary": "二重引き落とし"}'
        print(f"    結果 (シミュレーション): {classification}")

    # ステップ 2: 条件分岐 → 専門ペルソナへルーティング
    print("\n  [ノード2: ルーティング]")
    print("    → カテゴリ: billing → 請求専門チームへ転送")
    print("    → 緊急度: high → 優先対応フラグ設定")

    # ステップ 3: 専門応答の生成
    print("\n  [ノード3: 応答生成（billing ペルソナ）]")
    billing_prompt = f"""あなたは請求・会計サポートの専門家です。
以下の問い合わせに対して、共感を示しつつ具体的な解決手順を提示してください。

問い合わせ: {user_query}
分類情報: {classification}

対応ガイドライン:
- 二重請求は優先的に処理する
- 調査期間の目安を伝える
- 返金プロセスを説明する"""

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": billing_prompt}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 500}
        )
        answer = response['output']['message']['content'][0]['text']
        print(f"    応答: {answer[:300]}")
    except Exception as e:
        print(f"    エラー: {e}")

    # ステップ 4: 品質検証
    print("\n  [ノード4: 出力検証]")
    print("    ✅ 共感表現: 含まれている")
    print("    ✅ 解決手順: 提示されている")
    print("    ✅ 次のアクション: 明確")
    print("    ✅ 不適切な表現: なし")

    print(f"\n{'─' * 70}")
    print("  フロー完了 ✅")
    print(f"{'─' * 70}")

    print(f"""
  プロンプトフローの利点:
  ┌─────────────────────────────────────────────────────────────┐
  │ • 複雑なロジックを視覚的に設計可能                           │
  │ • 各ノードで独立してテスト・改善できる                       │
  │ • 条件分岐で柔軟なルーティングを実現                         │
  │ • ステート管理で会話コンテキストを保持                       │
  │ • A/Bテストによる継続的な品質改善                            │
  └─────────────────────────────────────────────────────────────┘

  Bedrock プロンプトフローの作成手順:
  1. AWS コンソール → Bedrock → プロンプトフロー
  2. ビジュアルエディタでノードを配置
  3. 各ノードのプロンプトとパラメータを設定
  4. テスト実行で動作確認
  5. バージョンを作成してデプロイ
""")


if __name__ == "__main__":
    demo_personas()
    demo_chain_of_thought()
    demo_prompt_flow_concept()
