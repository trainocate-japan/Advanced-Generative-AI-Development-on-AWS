"""
モジュール 4: 思考連鎖推論（Chain-of-Thought）デモ
- 線形 CoT: ステップバイステップ推論
- 分岐 CoT: 条件に応じた推論パスの分岐
- 反復 CoT: 自己検証ループによる精度向上
- 通常プロンプトとの品質比較
"""

import boto3
import json
import time

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "amazon.nova-pro-v1:0"


# ============================================================
# 思考連鎖推論テンプレート
# ============================================================

COT_TEMPLATES = {
    "linear": """以下の問題を段階的に分析してください。各ステップで思考過程を明示してください。

問題: {problem}

回答形式:
ステップ1 [データ整理]: 与えられた数値や条件を整理する
ステップ2 [計算・分析]: 各要素を個別に分析する
ステップ3 [比較・評価]: 選択肢を比較評価する
ステップ4 [結論]: 根拠を示して最終判断を述べる""",

    "branching": """以下の問題を条件分岐を含めて分析してください。
各条件によって異なる結論に至る可能性を検討してください。

問題: {problem}

回答形式:
[初期分析]: 問題の構造を把握する

シナリオA - {condition_a}の場合:
  → 前提: ...
  → 分析: ...
  → 結論A: ...

シナリオB - {condition_b}の場合:
  → 前提: ...
  → 分析: ...
  → 結論B: ...

[統合判断]: 最も蓋然性の高いシナリオと推奨アクション""",

    "iterative": """以下の問題を自己検証ループで分析してください。
最初の推論を行い、それを批判的に検証し、必要に応じて修正してください。

問題: {problem}

回答形式:
[第1回推論]: 最初の分析と仮説
[検証]: 上記推論の論理的矛盾、見落とし、バイアスを検証
[修正]: 検証結果に基づく修正（必要な場合）
[最終結論]: 検証済みの結論
[信頼度]: X/10（根拠を添えて）"""
}


def invoke_normal(problem):
    """通常プロンプト（CoTなし）でモデルを呼び出す"""
    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{
            "role": "user",
            "content": [{"text": f"以下の質問に簡潔に回答してください:\n\n{problem}"}]
        }],
        inferenceConfig={"temperature": 0.2, "maxTokens": 600}
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


# ============================================================
# デモ 1: 通常プロンプト vs 線形 CoT の比較
# ============================================================

def demo_linear_cot():
    """線形 CoT による段階的推論のデモ"""
    print("=" * 70)
    print("  デモ 1: 通常プロンプト vs 線形 CoT（ステップバイステップ推論）")
    print("=" * 70)

    problem = (
        "ある企業がAIチャットボットを導入検討中です。"
        "月間10万件のサポート問い合わせがあり、現在の平均対応時間は15分、"
        "人件費は1件あたり500円です。AIチャットボットの導入コストは月額200万円で、"
        "問い合わせの60%を自動化できると見込まれています。"
        "導入すべきでしょうか？"
    )

    print(f"\n  問題: {problem}")

    # 通常プロンプト
    print(f"\n{'─' * 70}")
    print("  【通常プロンプト（CoTなし）】")
    print(f"{'─' * 70}")
    try:
        normal = invoke_normal(problem)
        print(f"\n{normal}")
    except Exception as e:
        print(f"  エラー: {e}")

    time.sleep(1)

    # 線形 CoT
    print(f"\n{'─' * 70}")
    print("  【線形 CoT（段階的推論）】")
    print(f"{'─' * 70}")
    try:
        cot = invoke_with_cot("linear", problem)
        print(f"\n{cot}")
    except Exception as e:
        print(f"  エラー: {e}")

    print(f"\n{'─' * 70}")
    print("  📊 比較ポイント:")
    print("  • CoT は各ステップの計算過程が明示され、検証可能")
    print("  • 通常プロンプトは結論に飛びがちで、根拠が不明確な場合がある")
    print("  • CoT は計算ミスの発見が容易")
    print(f"{'─' * 70}")


# ============================================================
# デモ 2: 分岐 CoT（条件付き推論）
# ============================================================

def demo_branching_cot():
    """分岐 CoT による条件付き推論のデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: 分岐 CoT（条件に応じた推論パスの分岐）")
    print("=" * 70)

    problem = (
        "スタートアップ企業が生成AIプロダクトを構築する際、"
        "自社でモデルをファインチューニングすべきか、"
        "既存のAPIサービス（Bedrock等）を利用すべきか判断してください。"
        "チームは5名のエンジニアで、月間予算は500万円です。"
    )

    print(f"\n  問題: {problem}")
    print(f"\n{'─' * 70}")
    print("  【分岐 CoT】")
    print(f"{'─' * 70}")

    try:
        response = invoke_with_cot(
            "branching",
            problem,
            condition_a="差別化が競争優位の核心である",
            condition_b="市場投入速度が最優先である"
        )
        print(f"\n{response}")
    except Exception as e:
        print(f"  エラー: {e}")

    print(f"\n{'─' * 70}")
    print("  📊 分岐 CoT の利点:")
    print("  • 単一の「正解」に固執せず、条件に応じた複数の結論を提示")
    print("  • 意思決定者が自社の状況に合わせて判断できる")
    print("  • 見落としがちな代替シナリオを強制的に検討")
    print(f"{'─' * 70}")


# ============================================================
# デモ 3: 反復 CoT（自己検証ループ）
# ============================================================

def demo_iterative_cot():
    """反復 CoT による自己検証のデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: 反復 CoT（自己検証ループ）")
    print("=" * 70)

    problem = (
        "金融機関のリスク評価シナリオ: "
        "ある中堅企業（年商50億円、従業員200名）が1億円の融資を申請しています。"
        "直近3年の営業利益率は5%→3%→1%と低下傾向、"
        "負債比率は40%→55%→65%と上昇中、"
        "ただし新規事業（AI関連）の受注が前年比200%増で成長しています。"
        "融資の可否と条件を判断してください。"
    )

    print(f"\n  問題: {problem}")
    print(f"\n{'─' * 70}")
    print("  【反復 CoT（推論→検証→修正→確定）】")
    print(f"{'─' * 70}")

    try:
        response = invoke_with_cot("iterative", problem)
        print(f"\n{response}")
    except Exception as e:
        print(f"  エラー: {e}")

    print(f"\n{'─' * 70}")
    print("  📊 反復 CoT の利点:")
    print("  • 最初の推論のバイアスや見落としを自己検出")
    print("  • 信頼度スコアにより、判断の確実性を定量化")
    print("  • 人間のレビュアーが検証ポイントを把握しやすい")
    print(f"{'─' * 70}")


# ============================================================
# デモ 4: エラー検出パターン
# ============================================================

def demo_error_detection():
    """推論連鎖におけるエラー検出パターン"""
    print("\n\n" + "=" * 70)
    print("  デモ 4: 推論エラー検出パターン")
    print("=" * 70)

    error_detection_prompt = """あなたは論理検証の専門家です。以下の推論に論理的な問題がないか検証してください。

推論:
「AIの導入により、カスタマーサポートの対応件数が50%増加した。
 顧客満足度も80%から85%に上昇した。
 したがって、AI導入は完全に成功であり、人間のオペレーターは不要になった。」

検証タスク:
1. 論理的飛躍や非論理的な結論はないか？
2. 見落とされている変数や条件はないか？
3. データの解釈に誤りはないか？
4. 結論の妥当性を 1-10 で評価してください。

形式:
[問題点1]: ...
[問題点2]: ...
[見落とし]: ...
[修正された結論]: ...
[妥当性スコア]: X/10"""

    print(f"\n{'─' * 70}")
    print("  【論理検証プロンプト】")
    print(f"{'─' * 70}")

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": error_detection_prompt}]}],
            inferenceConfig={"temperature": 0.1, "maxTokens": 800}
        )
        print(f"\n{response['output']['message']['content'][0]['text']}")
    except Exception as e:
        print(f"  エラー: {e}")

    print(f"\n{'─' * 70}")
    print("  📊 エラー検出の活用場面:")
    print("  • 自動生成されたレポートの品質チェック")
    print("  • 意思決定支援における論理的整合性の担保")
    print("  • ハルシネーション検出の一手法として")
    print(f"{'─' * 70}")


# ============================================================
# まとめ
# ============================================================

def print_summary():
    """CoT パターンのまとめ"""
    print("\n\n" + "=" * 70)
    print("  まとめ: 思考連鎖推論のパターン選択ガイド")
    print("=" * 70)
    print("""
  ┌──────────────┬─────────────────────────┬──────────────────────────┐
  │ パターン     │ 適用場面                │ 特徴                     │
  ├──────────────┼─────────────────────────┼──────────────────────────┤
  │ 線形 CoT     │ 計算、段階的分析        │ 各ステップが検証可能     │
  │ 分岐 CoT     │ 意思決定、シナリオ分析  │ 複数の結論を並行検討     │
  │ 反復 CoT     │ リスク評価、高精度要求  │ 自己検証で精度向上       │
  │ エラー検出   │ 品質チェック、監査      │ 論理的矛盾を自動検出     │
  └──────────────┴─────────────────────────┴──────────────────────────┘

  実装のベストプラクティス:
  • タスクの複雑度に応じてパターンを選択する
  • 信頼度スコアを付与し、閾値以下は人間レビューに回す
  • 推論過程をログに残し、改善サイクルに活用する
  • 本番環境では反復 CoT のループ回数に上限を設ける
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    demo_linear_cot()
    time.sleep(1)
    demo_branching_cot()
    time.sleep(1)
    demo_iterative_cot()
    time.sleep(1)
    demo_error_detection()
    print_summary()
