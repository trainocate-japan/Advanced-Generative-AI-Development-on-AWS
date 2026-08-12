"""
モジュール 9 - パート 6: 古典的メトリクス（BLEU / ROUGE）による評価
参照ベースの n-gram メトリクスで、LLM-as-Judge との比較・使い分けを学ぶ
"""

import json
import math
from collections import Counter

import boto3

# Bedrock クライアント
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# ==============================================================================
# ステップ 6.1: BLEU スコアの実装
# ==============================================================================


def tokenize_ja(text: str) -> list[str]:
    """
    日本語テキストを文字単位でトークン化（簡易版）。
    本番環境では MeCab や SudachiPy などの形態素解析器を推奨。
    ここでは句読点・スペースで分割した後、各チャンクを文字単位に分解する。
    """
    # 句読点・記号を除去し、スペースで分割
    import re

    text = re.sub(r"[、。，．！？!?\s]+", " ", text).strip()
    # スペースで分割し、さらに短い単位（2-3文字）に分割
    chunks = text.split()
    tokens = []
    for chunk in chunks:
        # 英数字はそのまま1トークン
        if chunk.isascii():
            tokens.append(chunk.lower())
        else:
            # 日本語は2文字ずつのバイグラム的トークン化
            for i in range(0, len(chunk), 2):
                tokens.append(chunk[i : i + 2])
    return tokens


def get_ngrams(tokens: list[str], n: int) -> Counter:
    """トークンリストから n-gram のカウンターを生成"""
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def compute_bleu(
    reference: str, candidate: str, max_n: int = 4, brevity_penalty: bool = True
) -> dict:
    """
    BLEU スコアを計算する。

    BLEU (Bilingual Evaluation Understudy):
    - 機械翻訳の品質評価のために開発されたメトリクス
    - 生成文と参照文の n-gram 一致率を測定
    - 1-gram〜4-gram の精度の幾何平均 + 短文ペナルティ

    Args:
        reference: 参照テキスト（正解）
        candidate: 生成テキスト（評価対象）
        max_n: 最大 n-gram（通常 4）
        brevity_penalty: 短文ペナルティを適用するか

    Returns:
        各 n-gram の精度と BLEU スコア
    """
    ref_tokens = tokenize_ja(reference)
    cand_tokens = tokenize_ja(candidate)

    if not cand_tokens or not ref_tokens:
        return {"bleu": 0.0, "precisions": [], "brevity_penalty": 0.0}

    precisions = []

    for n in range(1, max_n + 1):
        ref_ngrams = get_ngrams(ref_tokens, n)
        cand_ngrams = get_ngrams(cand_tokens, n)

        if not cand_ngrams:
            precisions.append(0.0)
            continue

        # クリッピング: 各 n-gram のカウントを参照の出現数で上限
        clipped_count = 0
        for ngram, count in cand_ngrams.items():
            clipped_count += min(count, ref_ngrams.get(ngram, 0))

        total_count = sum(cand_ngrams.values())
        precision = clipped_count / total_count if total_count > 0 else 0.0
        precisions.append(precision)

    # 幾何平均（0を含む場合はスムージング）
    log_avg = 0.0
    for p in precisions:
        if p == 0:
            log_avg = float("-inf")
            break
        log_avg += math.log(p)
    log_avg /= max_n

    # Brevity Penalty（短文ペナルティ）
    bp = 1.0
    if brevity_penalty and len(cand_tokens) < len(ref_tokens):
        bp = math.exp(1 - len(ref_tokens) / len(cand_tokens))

    bleu_score = bp * math.exp(log_avg) if log_avg != float("-inf") else 0.0

    return {
        "bleu": round(bleu_score, 4),
        "precisions": [round(p, 4) for p in precisions],
        "brevity_penalty": round(bp, 4),
        "ref_length": len(ref_tokens),
        "cand_length": len(cand_tokens),
    }


# ==============================================================================
# ステップ 6.2: ROUGE スコアの実装
# ==============================================================================


def compute_rouge_n(reference: str, candidate: str, n: int = 1) -> dict:
    """
    ROUGE-N スコアを計算する。

    ROUGE (Recall-Oriented Understudy for Gisting Evaluation):
    - 要約タスクの品質評価のために開発されたメトリクス
    - 参照文の n-gram のうち、生成文に含まれる割合（再現率ベース）
    - BLEU が精度ベースなのに対し、ROUGE は再現率ベース

    Args:
        reference: 参照テキスト
        candidate: 生成テキスト
        n: n-gram サイズ（1 = unigram, 2 = bigram）

    Returns:
        precision, recall, f1
    """
    ref_tokens = tokenize_ja(reference)
    cand_tokens = tokenize_ja(candidate)

    if not ref_tokens or not cand_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    ref_ngrams = get_ngrams(ref_tokens, n)
    cand_ngrams = get_ngrams(cand_tokens, n)

    # 一致する n-gram 数
    overlap = 0
    for ngram, count in ref_ngrams.items():
        overlap += min(count, cand_ngrams.get(ngram, 0))

    ref_total = sum(ref_ngrams.values())
    cand_total = sum(cand_ngrams.values())

    precision = overlap / cand_total if cand_total > 0 else 0.0
    recall = overlap / ref_total if ref_total > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def lcs_length(seq1: list, seq2: list) -> int:
    """最長共通部分列（LCS）の長さを計算"""
    m, n = len(seq1), len(seq2)
    # メモリ効率のため2行のみ保持
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, [0] * (n + 1)

    return prev[n]


def compute_rouge_l(reference: str, candidate: str) -> dict:
    """
    ROUGE-L スコアを計算する。

    ROUGE-L:
    - 最長共通部分列（LCS）ベースの評価
    - 語順を考慮した柔軟なマッチング
    - n-gram のサイズを固定しないため、文の構造的な類似性を捉える

    Args:
        reference: 参照テキスト
        candidate: 生成テキスト

    Returns:
        precision, recall, f1
    """
    ref_tokens = tokenize_ja(reference)
    cand_tokens = tokenize_ja(candidate)

    if not ref_tokens or not cand_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    lcs_len = lcs_length(ref_tokens, cand_tokens)

    precision = lcs_len / len(cand_tokens) if len(cand_tokens) > 0 else 0.0
    recall = lcs_len / len(ref_tokens) if len(ref_tokens) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "lcs_length": lcs_len,
    }


# ==============================================================================
# ステップ 6.3: Bedrock モデル出力を BLEU/ROUGE で評価
# ==============================================================================

EVALUATION_CASES = [
    {
        "question": "Amazon S3とは何ですか？簡潔に説明してください。",
        "reference": "Amazon S3（Simple Storage Service）は、AWSが提供するオブジェクトストレージサービスです。高い耐久性とスケーラビリティを持ち、任意の量のデータをインターネット経由で保存・取得できます。",
    },
    {
        "question": "Lambda関数のコールドスタートとは何ですか？",
        "reference": "コールドスタートとは、Lambda関数が初めて呼び出された際や、一定時間アイドル状態だった後に呼び出された際に、実行環境の初期化が必要となり、応答時間が通常より長くなる現象です。",
    },
    {
        "question": "IAMの最小権限の原則を説明してください。",
        "reference": "最小権限の原則とは、ユーザーやロールに対して、業務に必要な最小限のアクセス権限のみを付与するセキュリティ原則です。不要な権限を排除することで、セキュリティリスクを低減します。",
    },
    {
        "question": "RAGのメリットを2つ挙げてください。",
        "reference": "モデルの知識を最新の情報で補完でき、ハルシネーションを減らせる。ファインチューニングなしで専門領域の知識を活用できる。",
    },
    {
        "question": "思考連鎖推論とは何ですか？",
        "reference": "思考連鎖推論は、モデルに対して最終回答に至るまでの中間的な推論ステップを明示的に出力させるプロンプト技法です。複雑な問題を段階的に解き、推論の正確性と透明性を向上させます。",
    },
]


def generate_answer(question: str) -> str:
    """Bedrock モデルから回答を生成"""
    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": question}]}],
                "inferenceConfig": {"temperature": 0.3, "maxTokens": 300},
            }
        ),
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


def run_bleu_rouge_evaluation():
    """BLEU/ROUGE 評価を実行"""
    print("=" * 60)
    print("古典的メトリクス評価: BLEU / ROUGE")
    print("=" * 60)

    print("\n  BLEU: 生成文のn-gramが参照文にどれだけ含まれるか（精度ベース）")
    print("  ROUGE: 参照文のn-gramが生成文にどれだけ含まれるか（再現率ベース）")

    all_bleu = []
    all_rouge1 = []
    all_rouge2 = []
    all_rougeL = []

    for i, case in enumerate(EVALUATION_CASES):
        question = case["question"]
        reference = case["reference"]

        print(f"\n{'─' * 55}")
        print(f"[{i+1}/{len(EVALUATION_CASES)}] {question}")

        # モデルから回答を生成
        candidate = generate_answer(question)
        print(f"  参照: {reference[:60]}...")
        print(f"  生成: {candidate[:60]}...")

        # BLEU
        bleu_result = compute_bleu(reference, candidate)
        all_bleu.append(bleu_result["bleu"])

        # ROUGE-1 (unigram)
        rouge1_result = compute_rouge_n(reference, candidate, n=1)
        all_rouge1.append(rouge1_result["f1"])

        # ROUGE-2 (bigram)
        rouge2_result = compute_rouge_n(reference, candidate, n=2)
        all_rouge2.append(rouge2_result["f1"])

        # ROUGE-L (LCS)
        rougeL_result = compute_rouge_l(reference, candidate)
        all_rougeL.append(rougeL_result["f1"])

        print(f"\n  スコア:")
        print(f"    BLEU:    {bleu_result['bleu']:.4f}  "
              f"(1-gram={bleu_result['precisions'][0]:.3f}, "
              f"2-gram={bleu_result['precisions'][1]:.3f}, "
              f"BP={bleu_result['brevity_penalty']:.3f})")
        print(f"    ROUGE-1: P={rouge1_result['precision']:.3f}  "
              f"R={rouge1_result['recall']:.3f}  F1={rouge1_result['f1']:.4f}")
        print(f"    ROUGE-2: P={rouge2_result['precision']:.3f}  "
              f"R={rouge2_result['recall']:.3f}  F1={rouge2_result['f1']:.4f}")
        print(f"    ROUGE-L: P={rougeL_result['precision']:.3f}  "
              f"R={rougeL_result['recall']:.3f}  F1={rougeL_result['f1']:.4f}")

    # ==============================================================================
    # サマリー
    # ==============================================================================
    print("\n" + "=" * 60)
    print("評価サマリー")
    print("=" * 60)

    n = len(EVALUATION_CASES)
    avg_bleu = sum(all_bleu) / n
    avg_rouge1 = sum(all_rouge1) / n
    avg_rouge2 = sum(all_rouge2) / n
    avg_rougeL = sum(all_rougeL) / n

    print(f"\n  {'メトリクス':<12} {'平均スコア':>10} {'説明'}")
    print(f"  {'─' * 55}")
    print(f"  {'BLEU':<12} {avg_bleu:>10.4f}  n-gram精度の幾何平均")
    print(f"  {'ROUGE-1':<12} {avg_rouge1:>10.4f}  unigram F1（単語レベル）")
    print(f"  {'ROUGE-2':<12} {avg_rouge2:>10.4f}  bigram F1（フレーズレベル）")
    print(f"  {'ROUGE-L':<12} {avg_rougeL:>10.4f}  LCS F1（文構造レベル）")

    # ==============================================================================
    # ステップ 6.4: LLM-as-Judge との比較・使い分け
    # ==============================================================================
    print("\n" + "=" * 60)
    print("BLEU/ROUGE vs LLM-as-Judge: 使い分けガイド")
    print("=" * 60)

    comparison = [
        {
            "aspect": "評価の性質",
            "bleu_rouge": "表層的（n-gram一致）",
            "llm_judge": "意味的（内容理解）",
        },
        {
            "aspect": "計算コスト",
            "bleu_rouge": "低い（ルールベース）",
            "llm_judge": "高い（API呼出し）",
        },
        {
            "aspect": "再現性",
            "bleu_rouge": "完全に再現可能",
            "llm_judge": "温度=0でもブレあり",
        },
        {
            "aspect": "言い換え対応",
            "bleu_rouge": "弱い（同じ意味でも低スコア）",
            "llm_judge": "強い（意味を理解）",
        },
        {
            "aspect": "適したタスク",
            "bleu_rouge": "翻訳、要約、定型応答",
            "llm_judge": "QA、対話、創造的生成",
        },
        {
            "aspect": "参照データ",
            "bleu_rouge": "必須（正解が必要）",
            "llm_judge": "なくても評価可能",
        },
    ]

    print(f"\n  {'観点':<14} {'BLEU/ROUGE':<24} {'LLM-as-Judge'}")
    print(f"  {'─' * 60}")
    for row in comparison:
        print(f"  {row['aspect']:<14} {row['bleu_rouge']:<24} {row['llm_judge']}")

    print("\n  推奨アプローチ:")
    print("    1. CI/CD パイプラインの高速チェック → BLEU/ROUGE（コスト低、即時）")
    print("    2. リリース前の品質ゲート         → LLM-as-Judge（精度高）")
    print("    3. 両者を併用し、乖離があれば人間がレビュー")

    # スコア目安
    print("\n  スコアの目安:")
    print("    BLEU  > 0.30: 良好（参照に忠実な生成）")
    print("    BLEU  > 0.15: 許容範囲（要点は含む）")
    print("    ROUGE-L F1 > 0.40: 良好")
    print("    ROUGE-L F1 > 0.25: 許容範囲")
    print()
    print("    ※ LLM は言い換えを多用するため、BLEU/ROUGE が低くても")
    print("      必ずしも品質が低いとは限らない。LLM-as-Judge と併用すること。")

    return {
        "avg_bleu": avg_bleu,
        "avg_rouge1": avg_rouge1,
        "avg_rouge2": avg_rouge2,
        "avg_rougeL": avg_rougeL,
    }


# ==============================================================================
# メイン実行
# ==============================================================================

if __name__ == "__main__":
    results = run_bleu_rouge_evaluation()
    print("\n完了しました。")
