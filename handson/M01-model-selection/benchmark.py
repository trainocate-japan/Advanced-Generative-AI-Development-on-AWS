"""
モジュール 1: 基盤モデルベンチマーク比較スクリプト
複数のモデルを同一プロンプトで評価し、パフォーマンスとコストを比較する
"""

import boto3
import json
import time
from datetime import datetime

# Bedrock Runtime クライアント
client = boto3.client('bedrock-runtime', region_name='us-east-1')

# 評価対象モデル
MODELS = {
    "Claude Sonnet 4": {
        "model_id": "anthropic.claude-sonnet-4-20250514-v1:0",
        "input_cost_per_1k": 0.003,
        "output_cost_per_1k": 0.015,
        "category": "premium"
    },
    "Claude Haiku 4": {
        "model_id": "anthropic.claude-haiku-4-20250514-v1:0",
        "input_cost_per_1k": 0.00025,
        "output_cost_per_1k": 0.00125,
        "category": "budget"
    },
    "Amazon Nova Lite": {
        "model_id": "amazon.nova-lite-v1:0",
        "input_cost_per_1k": 0.00006,
        "output_cost_per_1k": 0.00024,
        "category": "budget"
    },
    "Amazon Nova Pro": {
        "model_id": "amazon.nova-pro-v1:0",
        "input_cost_per_1k": 0.0008,
        "output_cost_per_1k": 0.0032,
        "category": "balanced"
    },
}

# テストプロンプト（ユースケース別）
TEST_PROMPTS = [
    {
        "name": "簡単な質問応答",
        "complexity": "simple",
        "prompt": "Amazon S3のストレージクラスを3つ挙げて、それぞれの特徴を1文で説明してください。"
    },
    {
        "name": "ドキュメント要約",
        "complexity": "medium",
        "prompt": """以下の文章を要約してください：
クラウドコンピューティングは、インターネットを通じてコンピューティングリソースを
オンデマンドで利用できるサービスモデルです。IaaS、PaaS、SaaS の3つのサービスモデルが
あり、それぞれインフラ、プラットフォーム、アプリケーションレベルでサービスを提供します。
クラウドの利点には、スケーラビリティ、コスト効率、高可用性、セキュリティなどがあります。
企業はクラウドを活用することで、初期投資を抑えながら迅速にビジネスを展開できます。"""
    },
    {
        "name": "複雑な分析・推論",
        "complexity": "complex",
        "prompt": """あなたは金融リスクアナリストです。以下のシナリオを分析し、
リスク評価レポートを作成してください：

シナリオ: ある金融機関が新しいAIベースの融資審査システムを導入予定です。
- 月間処理件数: 50,000件
- 現在の承認率: 65%
- AIモデルの精度: 92%
- 規制要件: GDPR準拠、説明可能性の確保

以下の観点で分析してください：
1. 運用リスク（モデル障害、データ品質）
2. コンプライアンスリスク（規制違反の可能性）
3. レピュテーションリスク（バイアス、不公平な判定）
4. 緩和策の提案"""
    }
]


def invoke_model(model_id, prompt):
    """Converse API を使用してモデルを呼び出す"""
    start_time = time.time()
    
    try:
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            inferenceConfig={
                "temperature": 0.3,
                "maxTokens": 1024
            }
        )
        
        elapsed_time = time.time() - start_time
        
        output_text = response['output']['message']['content'][0]['text']
        input_tokens = response['usage']['inputTokens']
        output_tokens = response['usage']['outputTokens']
        
        return {
            "success": True,
            "response": output_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_seconds": elapsed_time,
            "response_length": len(output_text)
        }
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        return {
            "success": False,
            "error": str(e),
            "latency_seconds": elapsed_time
        }


def calculate_cost(model_info, input_tokens, output_tokens):
    """コストを計算する"""
    input_cost = (input_tokens / 1000) * model_info["input_cost_per_1k"]
    output_cost = (output_tokens / 1000) * model_info["output_cost_per_1k"]
    return input_cost + output_cost


def run_benchmark():
    """ベンチマークを実行する"""
    print("=" * 80)
    print("  基盤モデル ベンチマーク比較")
    print(f"  実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    results = []
    
    for prompt_info in TEST_PROMPTS:
        print(f"\n{'─' * 80}")
        print(f"  テスト: {prompt_info['name']} (複雑度: {prompt_info['complexity']})")
        print(f"{'─' * 80}")
        
        for model_name, model_info in MODELS.items():
            print(f"\n  ▶ {model_name} を呼び出し中...", end="", flush=True)
            
            result = invoke_model(model_info["model_id"], prompt_info["prompt"])
            
            if result["success"]:
                cost = calculate_cost(
                    model_info,
                    result["input_tokens"],
                    result["output_tokens"]
                )
                
                print(f" 完了 ({result['latency_seconds']:.2f}秒)")
                print(f"    入力トークン: {result['input_tokens']}")
                print(f"    出力トークン: {result['output_tokens']}")
                print(f"    レイテンシー: {result['latency_seconds']:.2f}秒")
                print(f"    推定コスト: ${cost:.6f}")
                print(f"    応答長: {result['response_length']}文字")
                
                results.append({
                    "test": prompt_info["name"],
                    "complexity": prompt_info["complexity"],
                    "model": model_name,
                    "category": model_info["category"],
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "latency": result["latency_seconds"],
                    "cost": cost,
                    "response_length": result["response_length"]
                })
            else:
                print(f" エラー: {result['error']}")
    
    # サマリーテーブルの出力
    print("\n\n" + "=" * 80)
    print("  ベンチマーク結果サマリー")
    print("=" * 80)
    
    print(f"\n{'モデル':<20} {'カテゴリ':<10} {'平均レイテンシー':<15} {'平均コスト':<15} {'推奨ユースケース'}")
    print("─" * 80)
    
    for model_name, model_info in MODELS.items():
        model_results = [r for r in results if r["model"] == model_name]
        if model_results:
            avg_latency = sum(r["latency"] for r in model_results) / len(model_results)
            avg_cost = sum(r["cost"] for r in model_results) / len(model_results)
            
            if model_info["category"] == "premium":
                use_case = "複雑な分析・推論"
            elif model_info["category"] == "balanced":
                use_case = "一般的なタスク"
            else:
                use_case = "大量処理・簡単なタスク"
            
            print(f"{model_name:<20} {model_info['category']:<10} {avg_latency:<15.2f}s ${avg_cost:<14.6f} {use_case}")
    
    # コスト比較（月間10万リクエスト想定）
    print(f"\n\n{'─' * 80}")
    print("  月間コスト試算（100,000リクエスト / 平均 500入力 + 300出力トークン）")
    print(f"{'─' * 80}")
    
    for model_name, model_info in MODELS.items():
        monthly_cost = 100000 * (
            (500 / 1000) * model_info["input_cost_per_1k"] +
            (300 / 1000) * model_info["output_cost_per_1k"]
        )
        print(f"  {model_name:<20}: ${monthly_cost:>10.2f}/月")
    
    print("\n" + "=" * 80)
    print("  推奨アーキテクチャ:")
    print("  • プライマリ (複雑な分析): Claude Sonnet 4")
    print("  • セカンダリ (一般タスク): Amazon Nova Pro")
    print("  • バジェット (大量処理): Amazon Nova Lite")
    print("  • フォールバック: Claude Haiku 4")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
