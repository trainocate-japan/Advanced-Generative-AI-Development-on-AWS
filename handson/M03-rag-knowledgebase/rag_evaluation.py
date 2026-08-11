"""
モジュール 3: RAGAS（RAG Assessment）フレームワークによる RAG 評価
- Faithfulness（忠実性）: 回答がソースに忠実か
- Answer Relevancy（回答関連性）: 回答が質問に対して適切か
- Context Precision（コンテキスト精度）: 検索結果が関連しているか
- Context Recall（コンテキスト再現率）: 必要な情報が検索されているか
- LLM-as-a-Judge パターンによる自動評価
"""

import boto3
import json
import time
import os
from dataclasses import dataclass, field

# AWS クライアント
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# 設定読み込み
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "kb_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

config = load_config()
KNOWLEDGE_BASE_ID = config.get("knowledge_base_id", "YOUR_KB_ID")
MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"
EVAL_MODEL_ID = "amazon.nova-lite-v1:0"


# ═══════════════════════════════════════════════════════════════════════
#  評価データセット（Ground Truth）
# ═══════════════════════════════════════════════════════════════════════

EVALUATION_DATASET = [
    {
        "question": "契約書の解除条件について教えてください",
        "ground_truth": "契約の解除は、相手方が契約に違反し催告後30日以内に是正されない場合、"
                        "破産手続開始の決定を受けた場合、または信用不安が生じた場合に認められる。",
        "expected_sources": ["contract_template.txt"],
        "category": "contract"
    },
    {
        "question": "解雇予告は何日前に必要ですか",
        "ground_truth": "使用者は労働者を解雇しようとする場合、少なくとも30日前に予告しなければならない。"
                        "30日前に予告しない場合は30日分以上の平均賃金（解雇予告手当）を支払う必要がある。",
        "expected_sources": ["employment_law.txt"],
        "category": "employment_law"
    },
    {
        "question": "個人情報の第三者提供に関する規制を説明してください",
        "ground_truth": "個人情報取扱事業者は、あらかじめ本人の同意を得ないで個人データを第三者に提供してはならない。"
                        "ただし、法令に基づく場合、人の生命・身体・財産の保護に必要な場合等は例外とされる。",
        "expected_sources": ["privacy_regulation.txt"],
        "category": "privacy"
    },
    {
        "question": "秘密保持義務の期間はどのくらいですか",
        "ground_truth": "秘密保持義務の期間は契約終了後も一定期間継続し、"
                        "一般的に2年から5年が設定される。営業秘密に該当する場合は無期限の場合もある。",
        "expected_sources": ["contract_template.txt"],
        "category": "contract"
    },
    {
        "question": "従業員の残業時間の上限規制について教えてください",
        "ground_truth": "時間外労働の上限は原則月45時間・年360時間。36協定の特別条項でも"
                        "年720時間、単月100時間未満、2-6ヶ月平均80時間以内。"
                        "違反には6ヶ月以下の懲役または30万円以下の罰金。",
        "expected_sources": ["employment_law.txt"],
        "category": "employment_law"
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  評価結果データクラス
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class EvaluationResult:
    """単一の質問に対する評価結果"""
    question: str
    answer: str = ""
    contexts: list = field(default_factory=list)
    ground_truth: str = ""
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0

    @property
    def overall_score(self):
        """総合スコア（4指標の平均）"""
        return (self.faithfulness + self.answer_relevancy +
                self.context_precision + self.context_recall) / 4


# ═══════════════════════════════════════════════════════════════════════
#  LLM-as-a-Judge 評価関数
# ═══════════════════════════════════════════════════════════════════════

def invoke_llm(prompt, temperature=0.1, max_tokens=500):
    """評価用 LLM 呼び出し"""
    try:
        response = bedrock_runtime.invoke_model(
            modelId=EVAL_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens}
            })
        )
        body = json.loads(response['body'].read())
        return body['output']['message']['content'][0]['text']
    except Exception as e:
        return f"ERROR: {e}"


def parse_json_response(text):
    """LLM応答からJSONを抽出してパースする"""
    import re

    # まず直接パースを試みる
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # ```json ... ``` ブロックから抽出
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # { から } までを抽出
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    # "score" の数値だけ抽出
    score_match = re.search(r'"score"\s*:\s*([\d.]+)', text)
    if score_match:
        return {"score": float(score_match.group(1)), "reasoning": "部分パース"}

    return None


def evaluate_faithfulness(answer, contexts):
    """
    Faithfulness（忠実性）評価

    回答の各主張がコンテキスト（検索結果）に基づいているかを評価。
    ハルシネーション（ソースにない情報の捏造）を検出する。

    スコア: 0.0（完全に捏造）〜 1.0（完全にソースに忠実）
    """
    context_text = "\n---\n".join(contexts[:3])

    prompt = f"""あなたは RAG システムの品質評価者です。
以下の回答が、提供されたコンテキスト（検索結果）に忠実かどうかを評価してください。

## 評価基準
- 回答の各主張がコンテキストに明示的に含まれているか
- コンテキストにない情報を回答が含んでいないか（ハルシネーション）
- 数値や固有名詞が正確にコンテキストと一致しているか

## コンテキスト（検索結果）:
{context_text}

## 回答:
{answer}

## 評価
以下のJSON形式で回答してください:
{{"score": <0.0-1.0の数値>, "reasoning": "<評価理由>", "unsupported_claims": ["<コンテキストに根拠がない主張のリスト>"]}}
"""
    result = invoke_llm(prompt)
    try:
        parsed = parse_json_response(result)
        if parsed:
            return parsed.get("score", 0.0), parsed.get("reasoning", "")
        return 0.5, f"パース失敗: {result[:100]}"
    except Exception:
        return 0.5, "パース失敗"


def evaluate_answer_relevancy(question, answer):
    """
    Answer Relevancy（回答関連性）評価

    回答が質問に対して適切に回答しているかを評価。
    質問の意図に沿った回答であるかを判定する。

    スコア: 0.0（完全に無関係）〜 1.0（完全に適切）
    """
    prompt = f"""あなたは RAG システムの品質評価者です。
以下の回答が質問に対して適切に回答しているかを評価してください。

## 評価基準
- 質問の意図を正しく理解して回答しているか
- 質問に対して直接的な回答を提供しているか
- 不要な情報で回答が冗長になっていないか
- 回答が具体的で実用的か

## 質問:
{question}

## 回答:
{answer}

## 評価
以下のJSON形式で回答してください:
{{"score": <0.0-1.0の数値>, "reasoning": "<評価理由>"}}
"""
    result = invoke_llm(prompt)
    try:
        parsed = parse_json_response(result)
        if parsed:
            return parsed.get("score", 0.0), parsed.get("reasoning", "")
        return 0.5, f"パース失敗: {result[:100]}"
    except Exception:
        return 0.5, "パース失敗"


def evaluate_context_precision(question, contexts, ground_truth):
    """
    Context Precision（コンテキスト精度）評価

    検索結果が質問の回答に必要な情報を含んでいるかを評価。
    上位に関連度の高いチャンクが来ているかの順序も考慮。

    スコア: 0.0（検索結果が全て無関係）〜 1.0（全て高関連度）
    """
    contexts_formatted = ""
    for i, ctx in enumerate(contexts[:5], 1):
        contexts_formatted += f"\n[チャンク {i}]: {ctx[:200]}...\n"

    prompt = f"""あなたは RAG システムの品質評価者です。
検索結果（コンテキスト）が質問の回答に必要な情報を含んでいるかを評価してください。

## 評価基準
- 各チャンクが質問の回答に直接関連しているか
- 上位のチャンクほど関連度が高いか（順序の適切さ）
- 不要なチャンクが含まれていないか

## 質問:
{question}

## 正解（参考）:
{ground_truth}

## 検索結果:
{contexts_formatted}

## 評価
以下のJSON形式で回答してください:
{{"score": <0.0-1.0の数値>, "reasoning": "<評価理由>", "relevant_chunks": [<関連チャンクの番号リスト>]}}
"""
    result = invoke_llm(prompt)
    try:
        parsed = parse_json_response(result)
        if parsed:
            return parsed.get("score", 0.0), parsed.get("reasoning", "")
        return 0.5, f"パース失敗: {result[:100]}"
    except Exception:
        return 0.5, "パース失敗"


def evaluate_context_recall(contexts, ground_truth):
    """
    Context Recall（コンテキスト再現率）評価

    正解に含まれる情報が検索結果に含まれているかを評価。
    必要な情報の取りこぼしがないかを検出する。

    スコア: 0.0（正解の情報が全く検索されていない）〜 1.0（全て含まれている）
    """
    context_text = "\n---\n".join(contexts[:5])

    prompt = f"""あなたは RAG システムの品質評価者です。
正解（Ground Truth）に含まれる情報が、検索結果に含まれているかを評価してください。

## 評価基準
- 正解の各ポイントが検索結果のいずれかに含まれているか
- 重要な情報の取りこぼしがないか
- 正解を再構成するのに十分な情報が検索されているか

## 正解（Ground Truth）:
{ground_truth}

## 検索結果:
{context_text}

## 評価
以下のJSON形式で回答してください:
{{"score": <0.0-1.0の数値>, "reasoning": "<評価理由>", "missing_info": ["<検索結果に含まれていない情報>"]}}
"""
    result = invoke_llm(prompt)
    try:
        parsed = parse_json_response(result)
        if parsed:
            return parsed.get("score", 0.0), parsed.get("reasoning", "")
        return 0.5, f"パース失敗: {result[:100]}"
    except Exception:
        return 0.5, "パース失敗"


# ═══════════════════════════════════════════════════════════════════════
#  RAG パイプライン実行 + 評価
# ═══════════════════════════════════════════════════════════════════════

def run_rag_pipeline(question, kb_id=None, num_results=5):
    """RAG パイプラインを実行して回答と検索結果を取得"""
    kb_id = kb_id or KNOWLEDGE_BASE_ID

    # Retrieve API で検索結果を取得
    try:
        retrieve_response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": question},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": num_results,
                    "overrideSearchType": "SEMANTIC"
                }
            }
        )
        contexts = [
            item.get('content', {}).get('text', '')
            for item in retrieve_response.get('retrievalResults', [])
        ]
    except Exception as e:
        contexts = []

    # RetrieveAndGenerate API で回答を取得
    try:
        rag_response = bedrock_agent_runtime.retrieve_and_generate(
            input={"text": question},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {"numberOfResults": num_results}
                    }
                }
            }
        )
        answer = rag_response['output']['text']
    except Exception as e:
        answer = f"エラー: {e}"

    return answer, contexts


def evaluate_single(question, ground_truth, kb_id=None, num_results=5):
    """単一の質問を評価"""
    print(f"    質問: {question[:50]}...")

    # RAG 実行
    answer, contexts = run_rag_pipeline(question, kb_id, num_results)

    # 4指標を評価
    faith_score, faith_reason = evaluate_faithfulness(answer, contexts)
    relevancy_score, relevancy_reason = evaluate_answer_relevancy(question, answer)
    precision_score, precision_reason = evaluate_context_precision(question, contexts, ground_truth)
    recall_score, recall_reason = evaluate_context_recall(contexts, ground_truth)

    result = EvaluationResult(
        question=question,
        answer=answer,
        contexts=contexts,
        ground_truth=ground_truth,
        faithfulness=faith_score,
        answer_relevancy=relevancy_score,
        context_precision=precision_score,
        context_recall=recall_score
    )

    return result


def evaluate_dataset(dataset=None, kb_id=None):
    """データセット全体を評価"""
    dataset = dataset or EVALUATION_DATASET
    results = []

    for item in dataset:
        result = evaluate_single(
            question=item["question"],
            ground_truth=item["ground_truth"],
            kb_id=kb_id
        )
        results.append(result)
        time.sleep(1)  # レート制限対策

    return results


# ═══════════════════════════════════════════════════════════════════════
#  結果表示
# ═══════════════════════════════════════════════════════════════════════

def display_results(results):
    """評価結果を表形式で表示"""
    print(f"\n{'═' * 70}")
    print("  RAGAS 評価結果サマリー")
    print(f"{'═' * 70}")

    # ヘッダー
    print(f"\n  {'質問':<30} {'忠実性':<8} {'関連性':<8} {'精度':<8} {'再現率':<8} {'総合':<8}")
    print(f"  {'─' * 70}")

    for r in results:
        q = r.question[:28] + "..." if len(r.question) > 28 else r.question
        print(f"  {q:<30} {r.faithfulness:<8.2f} {r.answer_relevancy:<8.2f} "
              f"{r.context_precision:<8.2f} {r.context_recall:<8.2f} {r.overall_score:<8.2f}")

    # 集計
    avg_faith = sum(r.faithfulness for r in results) / len(results)
    avg_relevancy = sum(r.answer_relevancy for r in results) / len(results)
    avg_precision = sum(r.context_precision for r in results) / len(results)
    avg_recall = sum(r.context_recall for r in results) / len(results)
    avg_overall = sum(r.overall_score for r in results) / len(results)

    print(f"  {'─' * 70}")
    print(f"  {'平均':<30} {avg_faith:<8.2f} {avg_relevancy:<8.2f} "
          f"{avg_precision:<8.2f} {avg_recall:<8.2f} {avg_overall:<8.2f}")

    # 品質判定
    print(f"\n  品質判定:")
    if avg_overall >= 0.8:
        print(f"  ✅ 優秀（{avg_overall:.2f}）: RAG システムは高品質です")
    elif avg_overall >= 0.6:
        print(f"  ⚠️  良好（{avg_overall:.2f}）: 改善の余地あり（チャンキングや検索パラメータの調整を検討）")
    else:
        print(f"  ❌ 要改善（{avg_overall:.2f}）: チャンキング戦略、検索タイプ、プロンプトの見直しが必要")

    # 改善提案
    print(f"\n  改善提案:")
    if avg_faith < 0.7:
        print(f"  • 忠実性が低い → temperature を下げる、検索結果数を減らす")
    if avg_relevancy < 0.7:
        print(f"  • 関連性が低い → プロンプト改善、クエリ拡張の検討")
    if avg_precision < 0.7:
        print(f"  • 検索精度が低い → チャンキング戦略の変更、ハイブリッド検索の活用")
    if avg_recall < 0.7:
        print(f"  • 再現率が低い → numberOfResults を増やす、チャンクサイズを調整")

    return {
        "faithfulness": avg_faith,
        "answer_relevancy": avg_relevancy,
        "context_precision": avg_precision,
        "context_recall": avg_recall,
        "overall": avg_overall
    }


# ═══════════════════════════════════════════════════════════════════════
#  デモ関数
# ═══════════════════════════════════════════════════════════════════════

def demo_full_evaluation():
    """完全な RAGAS 評価のデモ"""
    print("=" * 70)
    print("  RAGAS 評価デモ: RAG システムの品質測定")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_evaluation()
        return

    print(f"\n  ナレッジベース: {KNOWLEDGE_BASE_ID}")
    print(f"  評価モデル: {EVAL_MODEL_ID}")
    print(f"  評価データセット: {len(EVALUATION_DATASET)} 件")
    print(f"\n  評価実行中...")

    results = evaluate_dataset()
    scores = display_results(results)

    # 結果をファイルに保存
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "knowledge_base_id": KNOWLEDGE_BASE_ID,
        "eval_model": EVAL_MODEL_ID,
        "aggregate_scores": scores,
        "individual_results": [
            {
                "question": r.question,
                "faithfulness": r.faithfulness,
                "answer_relevancy": r.answer_relevancy,
                "context_precision": r.context_precision,
                "context_recall": r.context_recall,
                "overall": r.overall_score
            }
            for r in results
        ]
    }

    output_path = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  結果を {output_path} に保存しました。")


def demo_single_evaluation():
    """単一質問の詳細評価デモ"""
    print("\n\n" + "=" * 70)
    print("  RAGAS 詳細評価: 単一質問の深掘り分析")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_single()
        return

    item = EVALUATION_DATASET[0]
    print(f"\n  質問: {item['question']}")
    print(f"  正解: {item['ground_truth'][:80]}...")

    result = evaluate_single(item["question"], item["ground_truth"])

    print(f"\n  ── 評価結果 ──")
    print(f"  忠実性:     {result.faithfulness:.2f}")
    print(f"  回答関連性: {result.answer_relevancy:.2f}")
    print(f"  検索精度:   {result.context_precision:.2f}")
    print(f"  検索再現率: {result.context_recall:.2f}")
    print(f"  総合:       {result.overall_score:.2f}")
    print(f"\n  回答: {result.answer[:200]}...")
    print(f"  検索チャンク数: {len(result.contexts)}")


# ═══════════════════════════════════════════════════════════════════════
#  シミュレーションモード
# ═══════════════════════════════════════════════════════════════════════

def demo_simulated_evaluation():
    """シミュレーション: RAGAS 評価結果"""
    print(f"\n  📋 シミュレーションモード: RAGAS 評価の解説")
    print(f"{'─' * 70}")

    print(f"""
  RAGAS (Retrieval Augmented Generation Assessment) の4指標:

  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                   │
  │  1. Faithfulness（忠実性）                                       │
  │     「回答はソースドキュメントに忠実か？」                       │
  │     - 回答の各主張がコンテキストに含まれているかを検証           │
  │     - ハルシネーション（捏造情報）を検出                         │
  │     - 低スコアの原因: temperature が高い、検索結果が不十分       │
  │                                                                   │
  │  2. Answer Relevancy（回答関連性）                               │
  │     「回答は質問の意図に沿っているか？」                         │
  │     - 質問に対して直接的な回答を提供しているか                   │
  │     - 不必要に冗長でないか                                       │
  │     - 低スコアの原因: プロンプト設計の問題、無関係チャンクの混入 │
  │                                                                   │
  │  3. Context Precision（コンテキスト精度）                        │
  │     「検索結果は質問に関連しているか？」                         │
  │     - 上位チャンクが質問に直接関連しているか                     │
  │     - 不要なチャンクが含まれていないか                           │
  │     - 低スコアの原因: チャンキングの問題、検索タイプの不適切     │
  │                                                                   │
  │  4. Context Recall（コンテキスト再現率）                         │
  │     「必要な情報は全て検索されているか？」                       │
  │     - 正解を構成する情報が検索結果に含まれているか               │
  │     - 重要な情報の取りこぼしがないか                             │
  │     - 低スコアの原因: numberOfResults が少ない、インデックス不足 │
  │                                                                   │
  └──────────────────────────────────────────────────────────────────┘
    """)

    # シミュレーション結果
    print(f"  {'質問':<30} {'忠実性':<8} {'関連性':<8} {'精度':<8} {'再現率':<8} {'総合':<8}")
    print(f"  {'─' * 70}")

    sim_results = [
        ("契約書の解除条件について...", 0.92, 0.88, 0.85, 0.90, 0.89),
        ("解雇予告は何日前に...", 0.95, 0.91, 0.88, 0.85, 0.90),
        ("個人情報の第三者提供...", 0.85, 0.82, 0.78, 0.80, 0.81),
        ("秘密保持義務の期間...", 0.88, 0.85, 0.72, 0.75, 0.80),
        ("残業時間の上限規制...", 0.90, 0.87, 0.82, 0.88, 0.87),
    ]

    for q, f, ar, cp, cr, overall in sim_results:
        print(f"  {q:<30} {f:<8.2f} {ar:<8.2f} {cp:<8.2f} {cr:<8.2f} {overall:<8.2f}")

    avg_overall = sum(r[5] for r in sim_results) / len(sim_results)
    print(f"  {'─' * 70}")
    print(f"  {'平均':<30} {0.90:<8.2f} {0.87:<8.2f} {0.81:<8.2f} {0.84:<8.2f} {avg_overall:<8.2f}")

    print(f"""
  品質判定:
  ✅ 優秀（{avg_overall:.2f}）: RAG システムは高品質です

  改善提案:
  • 検索精度（0.81）がやや低い → セマンティックチャンキングの検討
  • 秘密保持義務の再現率（0.75）が低い → 関連チャンクが分散している可能性
    """)


def demo_simulated_single():
    """シミュレーション: 単一質問の詳細評価"""
    print(f"\n  📋 シミュレーション: 単一質問の詳細分析")
    print(f"{'─' * 70}")

    print(f"""
  質問: 「契約書の解除条件について教えてください」
  正解: 「契約の解除は、相手方が契約に違反し催告後30日以内に是正されない場合...」

  ── 検索結果（Retrieve API）──
  [1] スコア 0.92: 「第7条（契約の解除）甲又は乙は、相手方が本契約に違反し、
                      催告後30日以内に是正されない場合、直ちに本契約を解除する
                      ことができる。」
  [2] スコア 0.85: 「第8条（損害賠償）本契約に違反した当事者は、相手方に生じた
                      損害を賠償する責任を負う。」
  [3] スコア 0.71: 「第9条（不可抗力）天災、戦争、ストライキ等の不可抗力により
                      本契約の履行が不可能となった場合...」

  ── RAG 回答 ──
  「契約書の解除条件は主に以下の場合に認められます：
   1. 相手方の重大な契約違反（催告後30日以内に是正されない場合）
   2. 相手方の破産手続開始の決定
   3. 不可抗力による履行不能
   解除は将来に向かってのみ効力を生じます。」

  ── 評価詳細 ──

  1. Faithfulness = 0.92
     ✅ 「催告後30日以内に是正されない場合」→ チャンク[1]に根拠あり
     ✅ 「不可抗力による履行不能」→ チャンク[3]に根拠あり
     ⚠️ 「破産手続開始の決定」→ 検索結果に明示的な根拠なし（-0.08）

  2. Answer Relevancy = 0.88
     ✅ 質問「解除条件」に対して条件を列挙 → 直接的な回答
     ✅ 具体的かつ実用的な情報
     ⚠️ 「損害賠償」には触れていない（質問の範囲外なので減点なし）

  3. Context Precision = 0.85
     ✅ チャンク[1] → 解除条件に直接関連（最も重要）
     ⚠️ チャンク[2] → 損害賠償は副次的（やや関連度低）
     ⚠️ チャンク[3] → 不可抗力は補足情報

  4. Context Recall = 0.90
     ✅ 「催告後30日以内に是正されない場合」→ 検索済み
     ⚠️ 「破産手続開始の決定」→ 検索されていない（-0.10）
     ✅ 「信用不安が生じた場合」→ チャンク[1]に含意

  総合スコア: 0.89 ✅ 優秀
    """)


def demo_evaluation_workflow():
    """RAGAS 評価ワークフローの解説"""
    print("\n\n" + "=" * 70)
    print("  RAGAS 評価: 実践ワークフロー")
    print("=" * 70)

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  RAGAS 評価パイプラインの構築手順                                 │
  └──────────────────────────────────────────────────────────────────┘

  Step 1: 評価データセット（Ground Truth）の作成
  ─────────────────────────────────────────────
  • 代表的な質問を 20-50 件選定
  • 各質問に対する正解（期待する回答）を人手で作成
  • カテゴリ分類（契約、労働法、プライバシー等）
  • 期待されるソースドキュメントを指定

  Step 2: RAG パイプラインの実行
  ─────────────────────────────────────────────
  • 各質問を Retrieve API → RetrieveAndGenerate API で処理
  • 検索結果（コンテキスト）と生成回答を記録
  • レスポンス時間も測定

  Step 3: LLM-as-a-Judge による自動評価
  ─────────────────────────────────────────────
  • 評価用 LLM（Nova Lite 等）で 4 指標を算出
  • 各指標のスコア + 理由を JSON で取得
  • コスト: 1質問あたり約 4 回の LLM 呼び出し

  Step 4: 結果分析と改善アクション
  ─────────────────────────────────────────────
  │ 指標が低い場合の対策:                                            │
  │                                                                   │
  │ Faithfulness↓  → temperature を 0.1-0.2 に下げる               │
  │                  → numberOfResults を 3-5 に制限                 │
  │                  → プロンプトに「ソースに基づいて回答」を追加    │
  │                                                                   │
  │ Relevancy↓    → クエリ拡張（LLM でクエリを書き換え）           │
  │                  → OpenSearch 連携でハイブリッド検索を導入        │
  │                  → 生成プロンプトの改善                          │
  │                                                                   │
  │ Precision↓    → チャンキング戦略の変更（階層型/セマンティック） │
  │                  → メタデータフィルタリングの追加                 │
  │                  → ハイブリッド検索の重み調整                    │
  │                                                                   │
  │ Recall↓       → numberOfResults を増やす（5→10）              │
  │                  → チャンクサイズを大きくする                     │
  │                  → 同義語・類義語の処理を追加                    │

  Step 5: A/B テスト
  ─────────────────────────────────────────────
  • パラメータ変更前後で同一データセットを評価
  • スコア改善を定量的に確認
  • 継続的な監視パイプラインへの組み込み

  ┌──────────────────────────────────────────────────────────────────┐
  │  コスト見積もり（評価 1 回あたり）                                │
  │                                                                   │
  │  質問数: 50 件 × LLM 呼出 4 回 = 200 回                         │
  │  入力トークン: 約 200 × 500 = 100,000 トークン                  │
  │  出力トークン: 約 200 × 200 = 40,000 トークン                   │
  │  Nova Lite 使用時: 約 $0.03 + $0.02 = $0.05 / 評価               │
  │  → 日次評価でも月額 $1.50 程度                                  │
  └──────────────────────────────────────────────────────────────────┘
    """)


# ═══════════════════════════════════════════════════════════════════════
#  メイン実行
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    demo_full_evaluation()
    demo_single_evaluation()
    demo_evaluation_workflow()
