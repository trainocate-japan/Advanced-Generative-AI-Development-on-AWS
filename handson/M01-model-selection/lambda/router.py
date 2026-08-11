"""
モジュール 1: 動的モデル選択 Lambda ルーター
- AWS AppConfig による動的設定管理
- リクエスト分類に基づくインテリジェントルーティング
- サーキットブレーカーパターンによるレジリエンス
- コストベースの自動モデル切り替え
"""

import boto3
import json
import os
import time
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS クライアント
bedrock = boto3.client('bedrock-runtime')
cloudwatch = boto3.client('cloudwatch')
ssm = boto3.client('ssm')
appconfig_data = boto3.client('appconfigdata')
appconfig = boto3.client('appconfig')

# 環境変数（AppConfig 参照用）
APPCONFIG_APP = os.environ.get('APPCONFIG_APP', '')
APPCONFIG_ENV = os.environ.get('APPCONFIG_ENV', '')
APPCONFIG_PROFILE = os.environ.get('APPCONFIG_PROFILE', '')

# 障害シミュレーション用 SSM パラメータのプレフィックス
FAILURE_SIM_PREFIX = os.environ.get('FAILURE_SIM_PREFIX', '/genai/model-selection/simulate-failure/')

# サーキットブレーカー状態（Lambda のインメモリ - 本番では DynamoDB 推奨）
circuit_breakers = {}

# ========================================
# AppConfig 設定取得
# ========================================

# AppConfig セッショントークン（Lambda コンテナ再利用時にキャッシュ）
_appconfig_token = None
_cached_config = None
_config_last_fetched = 0
CONFIG_CACHE_TTL = 30  # 秒


def get_routing_config():
    """
    AppConfig から最新のルーティング設定を取得する。
    キャッシュを利用して AppConfig への呼び出し頻度を抑える。
    """
    global _appconfig_token, _cached_config, _config_last_fetched

    now = time.time()

    # キャッシュが有効ならそのまま返す
    if _cached_config and (now - _config_last_fetched) < CONFIG_CACHE_TTL:
        return _cached_config

    try:
        # セッションがなければ開始
        if _appconfig_token is None:
            session_response = appconfig_data.start_configuration_session(
                ApplicationIdentifier=APPCONFIG_APP,
                EnvironmentIdentifier=APPCONFIG_ENV,
                ConfigurationProfileIdentifier=APPCONFIG_PROFILE,
                RequiredMinimumPollIntervalInSeconds=15
            )
            _appconfig_token = session_response['InitialConfigurationToken']

        # 最新設定を取得
        response = appconfig_data.get_latest_configuration(
            ConfigurationToken=_appconfig_token
        )

        # 次回用トークンを更新
        _appconfig_token = response['NextPollConfigurationToken']

        # Configuration が空の場合は前回設定が最新（変更なし）
        content = response['Configuration'].read()
        if content:
            _cached_config = json.loads(content)
            logger.info("AppConfig: new configuration loaded")
        elif _cached_config is None:
            # 初回取得で空が返った場合はデフォルト設定を使用
            _cached_config = _get_default_config()

        _config_last_fetched = now
        return _cached_config

    except Exception as e:
        logger.error(f"AppConfig fetch failed: {str(e)}, using cached/default config")
        # セッションをリセット（次回再接続させる）
        _appconfig_token = None
        if _cached_config:
            return _cached_config
        return _get_default_config()


def _get_default_config():
    """AppConfig 取得失敗時のデフォルト設定"""
    return {
        "routing_rules": {
            "simple": {
                "primary": "amazon.nova-lite-v1:0",
                "fallback": "amazon.nova-lite-v1:0"
            },
            "medium": {
                "primary": "amazon.nova-pro-v1:0",
                "fallback": "amazon.nova-lite-v1:0"
            },
            "complex": {
                "primary": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                "fallback": "amazon.nova-pro-v1:0"
            }
        },
        "circuit_breaker": {
            "failure_threshold": 5,
            "timeout_seconds": 30
        },
        "cost_budget": {
            "daily_limit_usd": 50,
            "budget_exceeded_model": "amazon.nova-lite-v1:0"
        },
        "classification_keywords": {
            "complex": ["分析", "評価", "設計", "比較", "アーキテクチャ",
                        "リスク", "コンプライアンス", "最適化", "戦略"],
            "simple": ["とは", "何ですか", "教えて", "リスト", "一覧"]
        }
    }


# ========================================
# AppConfig 設定更新（管理用）
# ========================================

def update_routing_config(new_config):
    """
    AppConfig にルーティング設定を更新する。
    新しい HostedConfigurationVersion を作成し、即時デプロイする。
    """
    global _appconfig_token, _cached_config, _config_last_fetched

    try:
        # 新しい設定バージョンを作成
        version_response = appconfig.create_hosted_configuration_version(
            ApplicationId=APPCONFIG_APP,
            ConfigurationProfileId=APPCONFIG_PROFILE,
            Content=json.dumps(new_config, ensure_ascii=False).encode('utf-8'),
            ContentType='application/json'
        )
        version_number = version_response['VersionNumber']

        # 即時デプロイ（DeploymentStrategy は Immediate を使用）
        # デプロイ戦略一覧から "Immediate" を探す
        strategies = appconfig.list_deployment_strategies()
        immediate_strategy_id = None
        for s in strategies.get('Items', []):
            if s['Name'] == 'Immediate':
                immediate_strategy_id = s['Id']
                break

        if not immediate_strategy_id:
            # 見つからない場合は AppConfig.AllAtOnce を使用
            immediate_strategy_id = 'AppConfig.AllAtOnce'

        appconfig.start_deployment(
            ApplicationId=APPCONFIG_APP,
            EnvironmentId=APPCONFIG_ENV,
            DeploymentStrategyId=immediate_strategy_id,
            ConfigurationProfileId=APPCONFIG_PROFILE,
            ConfigurationVersion=str(version_number)
        )

        # キャッシュを更新しセッションをリセット
        _cached_config = new_config
        _config_last_fetched = time.time()
        _appconfig_token = None  # 次回 GetLatestConfiguration で新設定を取得

        logger.info(f"AppConfig: deployed version {version_number}")
        return {"version": version_number, "status": "deployed"}

    except Exception as e:
        logger.error(f"AppConfig update failed: {str(e)}")
        raise


# ========================================
# SSM Parameter Store（障害シミュレーション）
# ========================================

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


# ========================================
# サーキットブレーカー
# ========================================

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
    """プロバイダーのサーキットブレーカーを取得する（AppConfig の閾値を適用）"""
    config = get_routing_config()
    cb_config = config.get('circuit_breaker', {})
    threshold = cb_config.get('failure_threshold', 5)
    timeout = cb_config.get('timeout_seconds', 30)

    if provider not in circuit_breakers:
        circuit_breakers[provider] = CircuitBreaker(provider, threshold, timeout)
    else:
        # 設定が変更された場合に閾値を更新
        cb = circuit_breakers[provider]
        cb.threshold = threshold
        cb.timeout = timeout

    return circuit_breakers[provider]


# ========================================
# リクエスト分類とモデル選択
# ========================================

def classify_request(query, complexity=None):
    """
    リクエストを分類してルーティング先を決定する。
    分類キーワードは AppConfig から取得。
    """
    if complexity:
        return complexity

    config = get_routing_config()
    keywords = config.get('classification_keywords', {})

    complex_keywords = keywords.get('complex', [])
    simple_keywords = keywords.get('simple', [])

    query_length = len(query)
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
    AppConfig のルーティングルールに基づいてモデルを選択する。
    """
    config = get_routing_config()
    routing_rules = config.get('routing_rules', {})
    cost_budget = config.get('cost_budget', {})

    if budget_exceeded:
        budget_model = cost_budget.get('budget_exceeded_model', 'amazon.nova-lite-v1:0')
        logger.info("Budget exceeded - routing to budget model")
        return budget_model, "budget_override"

    rule = routing_rules.get(complexity, routing_rules.get('medium', {}))
    model_id = rule.get('primary', 'amazon.nova-pro-v1:0')

    return model_id, "appconfig_routing"


def get_fallback_model(complexity):
    """AppConfig のルーティングルールからフォールバックモデルを取得する"""
    config = get_routing_config()
    routing_rules = config.get('routing_rules', {})
    rule = routing_rules.get(complexity, {})
    return rule.get('fallback', 'amazon.nova-lite-v1:0')


# ========================================
# モデル呼び出し
# ========================================

def extract_provider(model_id):
    """モデルIDからプロバイダー名を抽出する"""
    parts = model_id.split('.')
    if len(parts) >= 3 and parts[0] in ('us', 'eu', 'ap'):
        return parts[1]
    return parts[0]


def invoke_model_with_fallback(model_id, query, complexity="medium"):
    """モデルを呼び出し、失敗時はフォールバックする"""
    provider = extract_provider(model_id)

    # 障害シミュレーションのチェック
    failure_type = get_simulated_failure(provider)
    if failure_type:
        logger.warning(f"Simulated {failure_type} for {provider}, falling back")
        cb = get_circuit_breaker(provider)
        cb.failure_count = cb.threshold
        cb.state = "OPEN"
        cb.last_failure_time = time.time()
        publish_metrics(provider, model_id, 0, None, success=False)
        return invoke_fallback(query, f"simulated_{failure_type}_{provider}", complexity)

    # サーキットブレーカーのチェック
    cb = get_circuit_breaker(provider)
    if not cb.can_execute():
        logger.warning(f"Circuit breaker OPEN for {provider}, using fallback")
        return invoke_fallback(query, f"circuit_breaker_{provider}", complexity)

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

        cb.record_success()

        output_text = response['output']['message']['content'][0]['text']
        usage = response['usage']

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
        return invoke_fallback(query, f"error_{provider}", complexity)


def invoke_fallback(query, reason, complexity="medium"):
    """フォールバックモデルを呼び出す"""
    # AppConfig から complexity に対応するフォールバックモデルを取得
    config = get_routing_config()
    routing_rules = config.get('routing_rules', {})

    # フォールバックチェーン: complexity の fallback → medium の primary → nova-lite
    fallback_models = []
    rule = routing_rules.get(complexity, {})
    if rule.get('fallback'):
        fallback_models.append(rule['fallback'])
    medium_rule = routing_rules.get('medium', {})
    if medium_rule.get('primary') and medium_rule['primary'] not in fallback_models:
        fallback_models.append(medium_rule['primary'])
    simple_rule = routing_rules.get('simple', {})
    if simple_rule.get('primary') and simple_rule['primary'] not in fallback_models:
        fallback_models.append(simple_rule['primary'])

    if not fallback_models:
        fallback_models = ['amazon.nova-pro-v1:0', 'amazon.nova-lite-v1:0']

    for fallback in fallback_models:
        provider = extract_provider(fallback)
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

    return {
        "response": "申し訳ございません。現在すべてのAIモデルが利用できない状態です。しばらくしてからお試しください。",
        "model_used": "none",
        "fallback_used": True,
        "fallback_reason": "all_models_failed",
        "error": True
    }


# ========================================
# メトリクス
# ========================================

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
    return model_id.split('.')[-1].split('-v')[0]


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


# ========================================
# Lambda ハンドラー
# ========================================

def lambda_handler(event, context):
    """Lambda ハンドラー"""
    path = event.get('path', '')
    method = event.get('httpMethod', 'GET')

    # ヘルスチェック
    if path == '/health':
        config = get_routing_config()
        cb_states = {
            provider: cb.state
            for provider, cb in circuit_breakers.items()
        }
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'status': 'healthy',
                'config_source': 'appconfig',
                'routing_rules': config.get('routing_rules', {}),
                'circuit_breakers': cb_states,
                'timestamp': datetime.now().isoformat()
            }, ensure_ascii=False)
        }

    # 設定の取得（GET /admin/config）
    if path == '/admin/config' and method == 'GET':
        config = get_routing_config()
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'source': 'appconfig',
                'application': APPCONFIG_APP,
                'environment': APPCONFIG_ENV,
                'profile': APPCONFIG_PROFILE,
                'config': config
            }, ensure_ascii=False)
        }

    # 設定の更新（PUT /admin/config）
    if path == '/admin/config' and method == 'PUT':
        try:
            body = json.loads(event.get('body', '{}'))
            new_config = body.get('config')
            if not new_config:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'config field is required'})
                }

            # バリデーション: routing_rules が含まれているか
            if 'routing_rules' not in new_config:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'routing_rules is required in config'})
                }

            result = update_routing_config(new_config)
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'message': 'Configuration updated and deployed',
                    'version': result['version'],
                    'config': new_config
                }, ensure_ascii=False)
            }
        except Exception as e:
            logger.error(f"Config update error: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': f'Failed to update config: {str(e)}'})
            }

    # 障害シミュレーション（管理者用）
    if path == '/admin/simulate-failure' and method == 'POST':
        body = json.loads(event.get('body', '{}'))
        provider = body.get('provider', '')
        failure_type = body.get('failure_type', 'none')

        valid_providers = ['anthropic', 'amazon', 'meta']
        if provider not in valid_providers:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'error': f"Invalid provider '{provider}'. Must be one of: {valid_providers}"
                })
            }

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

        # モデル選択（AppConfig ベース）
        model_id, selection_reason = select_model(complexity)

        logger.info(f"Query classified as '{complexity}', routing to {model_id} ({selection_reason})")

        # モデル呼び出し（フォールバック付き）
        result = invoke_model_with_fallback(model_id, query, complexity)

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
