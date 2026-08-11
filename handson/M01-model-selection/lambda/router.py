"""
モジュール 1: 動的モデル選択 Lambda ルーター
- リクエスト分類に基づくインテリジェントルーティング
- サーキットブレーカーパターンによるレジリエンス
- コストベースの自動モデル切り替え
"""

import boto3
import json
import os
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS クライアント
bedrock = boto3.client('bedrock-runtime')
cloudwatch = boto3.client('cloudwatch')
ssm = boto3.client('ssm')

# 環境変数
PRIMARY_MODEL = os.environ.get('PRIMARY_MODEL', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')
FALLBACK_MODEL = os.environ.get('FALLBACK_MODEL', 'amazon.nova-pro-v1:0')
BUDGET_MODEL = os.environ.get('BUDGET_MODEL', 'amazon.nova-lite-v1:0')
CB_THRESHOLD = int(os.environ.get('CIRCUIT_BREAKER_THRESHOLD', '5'))
CB_TIMEOUT = int(os.environ.get('CIRCUIT_BREAKER_TIMEOUT', '30'))

# サーキットブレーカー状態（Lambda のインメモリ - 本番では DynamoDB 推奨）
circuit_breakers = {}

# 障害シミュレーション用 SSM パラメータのプレフィックス
FAILURE_SIM_PREFIX = os.environ.get('FAILURE_SIM_PREFIX', '/genai/model-selection/simulate-failure/')


def get_simulated_failure(provider):
    """SSM Parameter Store から障害シミュレーション設定を取得する"""
    try:
        response = ssm.get_parameter(
            Name=f"{FAILURE_SIM_PREFIX}{provider}"
        )
        value = response['Parameter']['Value']
        if value == "none":
            return None
        return value
    except ssm.exceptions.ParameterNotFound:
        return None
    except Exception as e:
        logger.warning(f"Failed to read failure simulation from SSM: {str(e)}")
        return None


def set_simulated_failure(provider, failure_type):
    """SSM Parameter Store に障害シミュレーション設定を書き込む"""
    try:
        ssm.put_parameter(
            Name=f"{FAILURE_SIM_PREFIX}{provider}",
            Value=failure_type,
            Type='String',
            Overwrite=True
        )
    except Exception as e:
        logger.error(f"Failed to write failure simulation to SSM: {str(e)}")
        raise


def remove_simulated_failure(provider):
    """SSM Parameter Store から障害シミュレーション設定を削除する"""
    try:
        ssm.delete_parameter(
            Name=f"{FAILURE_SIM_PREFIX}{provider}"
        )
    except ssm.exceptions.ParameterNotFound:
        pass  # 存在しなければ何もしない
    except Exception as e:
        logger.error(f"Failed to delete failure simulation from SSM: {str(e)}")
        raise


def get_all_simulated_failures():
    """SSM Parameter Store から全ての障害シミュレーション設定を取得する"""
    try:
        response = ssm.get_parameters_by_path(
            Path=FAILURE_SIM_PREFIX,
            Recursive=False
        )
        return {
            p['Name'].replace(FAILURE_SIM_PREFIX, ''): p['Value']
            for p in response.get('Parameters', [])
        }
    except Exception as e:
        logger.warning(f"Failed to list failure simulations from SSM: {str(e)}")
        return {}


class CircuitBreaker:
    """サーキットブレーカーパターンの実装"""

    def __init__(self, provider, threshold=5, timeout=30):
        self.provider = provider
        self.threshold = threshold
        self.timeout = timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_failure_time = None

    def record_failure(self):
        """障害を記録する"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPENED for {self.provider}")

    def record_success(self):
        """成功を記録する"""
        self.failure_count = 0
        self.state = "CLOSED"

    def can_execute(self):
        """リクエストを実行可能か判定する"""
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                logger.info(f"Circuit breaker HALF_OPEN for {self.provider}")
                return True
            return False
        # HALF_OPEN: テストリクエストを1つ許可
        return True


def get_circuit_breaker(provider):
    """プロバイダーのサーキットブレーカーを取得する"""
    if provider not in circuit_breakers:
        circuit_breakers[provider] = CircuitBreaker(
            provider, CB_THRESHOLD, CB_TIMEOUT
        )
    return circuit_breakers[provider]


def classify_request(query, complexity=None):
    """
    リクエストを分類してルーティング先を決定する
    戦略:
    - simple: 短い質問、FAQ → Budget モデル (Nova Lite)
    - medium: 一般的なタスク → Fallback モデル (Nova Pro)
    - complex: 分析、推論、専門的タスク → Primary モデル (Claude Sonnet)
    """
    if complexity:
        return complexity

    # クエリの特性に基づく自動分類
    query_length = len(query)

    # 複雑さのヒューリスティック
    complex_keywords = ['分析', '評価', '設計', '比較', 'アーキテクチャ',
                        'リスク', 'コンプライアンス', '最適化', '戦略']
    simple_keywords = ['とは', '何ですか', '教えて', 'リスト', '一覧']

    complex_score = sum(1 for kw in complex_keywords if kw in query)
    simple_score = sum(1 for kw in simple_keywords if kw in query)

    if complex_score >= 2 or query_length > 500:
        return "complex"
    elif simple_score >= 1 and query_length < 100:
        return "simple"
    else:
        return "medium"


def select_model(complexity, budget_exceeded=False):
    """
    複雑度とコスト条件に基づいてモデルを選択する
    """
    if budget_exceeded:
        logger.info("Budget exceeded - routing to budget model")
        return BUDGET_MODEL, "budget_override"

    model_map = {
        "complex": (PRIMARY_MODEL, "complexity_based"),
        "medium": (FALLBACK_MODEL, "complexity_based"),
        "simple": (BUDGET_MODEL, "complexity_based"),
    }

    return model_map.get(complexity, (FALLBACK_MODEL, "default"))


def invoke_model_with_fallback(model_id, query):
    """
    モデルを呼び出し、失敗時はフォールバックする
    """
    provider = model_id.split('.')[0]  # anthropic, amazon, meta

    # 障害シミュレーションのチェック（SSM Parameter Store から取得）
    failure_type = get_simulated_failure(provider)
    if failure_type:
        if failure_type == "timeout":
            time.sleep(10)
            raise TimeoutError(f"Simulated timeout for {provider}")
        elif failure_type == "error":
            raise Exception(f"Simulated error for {provider}")

    # サーキットブレーカーのチェック
    cb = get_circuit_breaker(provider)
    if not cb.can_execute():
        logger.warning(f"Circuit breaker OPEN for {provider}, using fallback")
        return invoke_fallback(query, f"circuit_breaker_{provider}")

    try:
        start_time = time.time()
        response = bedrock.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": query}]
                }
            ],
            inferenceConfig={
                "temperature": 0.3,
                "maxTokens": 1024
            }
        )
        latency = time.time() - start_time

        # 成功を記録
        cb.record_success()

        output_text = response['output']['message']['content'][0]['text']
        usage = response['usage']

        # メトリクスを送信
        publish_metrics(provider, model_id, latency, usage, success=True)

        return {
            "response": output_text,
            "model_used": model_id,
            "provider": provider,
            "latency": latency,
            "input_tokens": usage['inputTokens'],
            "output_tokens": usage['outputTokens'],
            "fallback_used": False
        }

    except Exception as e:
        logger.error(f"Error invoking {model_id}: {str(e)}")
        cb.record_failure()
        publish_metrics(provider, model_id, 0, None, success=False)
        return invoke_fallback(query, f"error_{provider}")


def invoke_fallback(query, reason):
    """フォールバックモデルを呼び出す"""
    fallback_models = [FALLBACK_MODEL, BUDGET_MODEL]

    for fallback in fallback_models:
        provider = fallback.split('.')[0]
        fb_cb = get_circuit_breaker(provider)

        if not fb_cb.can_execute():
            continue

        try:
            start_time = time.time()
            response = bedrock.converse(
                modelId=fallback,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": query}]
                    }
                ],
                inferenceConfig={
                    "temperature": 0.3,
                    "maxTokens": 1024
                }
            )
            latency = time.time() - start_time
            fb_cb.record_success()

            output_text = response['output']['message']['content'][0]['text']
            usage = response['usage']

            publish_metrics(provider, fallback, latency, usage, success=True)

            return {
                "response": output_text,
                "model_used": fallback,
                "provider": provider,
                "latency": latency,
                "input_tokens": usage['inputTokens'],
                "output_tokens": usage['outputTokens'],
                "fallback_used": True,
                "fallback_reason": reason
            }

        except Exception as e:
            logger.error(f"Fallback {fallback} also failed: {str(e)}")
            fb_cb.record_failure()
            continue

    # すべてのモデルが失敗
    return {
        "response": "申し訳ございません。現在すべてのAIモデルが利用できない状態です。しばらくしてからお試しください。",
        "model_used": "none",
        "fallback_used": True,
        "fallback_reason": "all_models_failed",
        "error": True
    }


def get_model_short_name(model_id):
    """モデルIDからダッシュボード表示用の短縮名を返す"""
    if 'claude-sonnet' in model_id:
        return 'claude-sonnet'
    elif 'nova-pro' in model_id:
        return 'nova-pro'
    elif 'nova-lite' in model_id:
        return 'nova-lite'
    elif 'nova-micro' in model_id:
        return 'nova-micro'
    # フォールバック: ドットで分割して最後の部分から推測
    return model_id.split('.')[-1].split('-v')[0]


# モデルごとの料金テーブル (USD per 1000 tokens)
MODEL_PRICING = {
    'claude-sonnet': {'input': 0.003, 'output': 0.015},
    'nova-pro': {'input': 0.0008, 'output': 0.0032},
    'nova-lite': {'input': 0.00006, 'output': 0.00024},
}


def estimate_cost(model_short, input_tokens, output_tokens):
    """トークン使用量に基づいてコストを推定する"""
    pricing = MODEL_PRICING.get(model_short, {'input': 0.001, 'output': 0.005})
    cost = (input_tokens / 1000) * pricing['input'] + (output_tokens / 1000) * pricing['output']
    return cost


def publish_metrics(provider, model_id, latency, usage, success):
    """CloudWatch にカスタムメトリクスを送信する"""
    try:
        metrics = [
            {
                'MetricName': 'Invocations',
                'Dimensions': [{'Name': 'Provider', 'Value': provider}],
                'Value': 1,
                'Unit': 'Count'
            }
        ]

        if success and usage:
            model_short = get_model_short_name(model_id)
            metrics.extend([
                {
                    'MetricName': 'Latency',
                    'Dimensions': [{'Name': 'Model', 'Value': model_short}],
                    'Value': latency,
                    'Unit': 'Seconds'
                },
                {
                    'MetricName': 'InputTokens',
                    'Dimensions': [{'Name': 'Provider', 'Value': provider}],
                    'Value': usage['inputTokens'],
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'OutputTokens',
                    'Dimensions': [{'Name': 'Provider', 'Value': provider}],
                    'Value': usage['outputTokens'],
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'EstimatedCost',
                    'Dimensions': [{'Name': 'Provider', 'Value': provider}],
                    'Value': estimate_cost(model_short, usage['inputTokens'], usage['outputTokens']),
                    'Unit': 'None'
                }
            ])

        if not success:
            metrics.append({
                'MetricName': 'Errors',
                'Dimensions': [{'Name': 'Provider', 'Value': provider}],
                'Value': 1,
                'Unit': 'Count'
            })

        # サーキットブレーカー状態
        cb = get_circuit_breaker(provider)
        metrics.append({
            'MetricName': 'CircuitBreakerOpen',
            'Dimensions': [{'Name': 'Provider', 'Value': provider}],
            'Value': 1 if cb.state == "OPEN" else 0,
            'Unit': 'None'
        })

        cloudwatch.put_metric_data(
            Namespace='GenAI/ModelSelection',
            MetricData=metrics
        )
    except Exception as e:
        logger.warning(f"Failed to publish metrics: {str(e)}")


def lambda_handler(event, context):
    """Lambda ハンドラー"""
    path = event.get('path', '')
    method = event.get('httpMethod', 'GET')

    # ヘルスチェック
    if path == '/health':
        cb_states = {
            provider: cb.state
            for provider, cb in circuit_breakers.items()
        }
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'status': 'healthy',
                'circuit_breakers': cb_states,
                'timestamp': datetime.now().isoformat()
            })
        }

    # 障害シミュレーション（管理者用）
    if path == '/admin/simulate-failure' and method == 'POST':
        body = json.loads(event.get('body', '{}'))
        provider = body.get('provider', '')
        failure_type = body.get('failure_type', 'none')

        if failure_type == 'none':
            set_simulated_failure(provider, 'none')
            msg = f"Failure simulation removed for {provider}"
        else:
            set_simulated_failure(provider, failure_type)
            msg = f"Simulating {failure_type} for {provider}"

        logger.info(msg)
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'message': msg, 'simulated_failures': get_all_simulated_failures()})
        }

    # メインのクエリ処理
    if path == '/query' and method == 'POST':
        body = json.loads(event.get('body', '{}'))
        query = body.get('query', '')
        requested_complexity = body.get('complexity')

        if not query:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'query is required'})
            }

        # リクエスト分類
        complexity = classify_request(query, requested_complexity)

        # モデル選択
        model_id, selection_reason = select_model(complexity)

        logger.info(f"Query classified as '{complexity}', routing to {model_id} ({selection_reason})")

        # モデル呼び出し（フォールバック付き）
        result = invoke_model_with_fallback(model_id, query)

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'query': query,
                'complexity': complexity,
                'selection_reason': selection_reason,
                **result
            }, ensure_ascii=False)
        }

    return {
        'statusCode': 404,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({'error': 'Not found'})
    }
