"""
AgentCore Gateway 用 Lambda 関数: travel-tools

Gateway がツール呼び出しをルーティングすると、この Lambda が呼ばれる。
event にはツールの inputSchema で定義したパラメータが入り、
context.client_context.custom['bedrockAgentCoreToolName'] でツール名を取得。
"""

import json
import random


def lambda_handler(event, context):
    """Gateway から呼び出されるメインハンドラー"""

    # ツール名を取得（"target名___tool名" 形式）
    delimiter = "___"
    original_tool_name = context.client_context.custom.get(
        "bedrockAgentCoreToolName", ""
    )
    if delimiter in original_tool_name:
        tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
    else:
        tool_name = original_tool_name

    # ツールごとに分岐
    if tool_name == "search_flights":
        return search_flights(event)
    elif tool_name == "search_hotels":
        return search_hotels(event)
    elif tool_name == "get_weather":
        return get_weather(event)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def search_flights(params):
    """フライト検索"""
    origin = params.get("origin", "東京")
    destination = params.get("destination", "沖縄")
    date = params.get("date", "2025-03-15")

    flights = [
        {"airline": "ANA", "departure": "08:00", "arrival": "10:30", "price": 35000, "class": "普通席"},
        {"airline": "JAL", "departure": "10:30", "arrival": "13:00", "price": 38000, "class": "普通席"},
        {"airline": "Peach", "departure": "06:30", "arrival": "09:15", "price": 15000, "class": "LCC"},
        {"airline": "ANA", "departure": "14:00", "arrival": "16:30", "price": 55000, "class": "プレミアムクラス"},
    ]

    return {
        "origin": origin,
        "destination": destination,
        "date": date,
        "flights": flights,
    }


def search_hotels(params):
    """ホテル検索"""
    city = params.get("city", "沖縄")
    checkin = params.get("checkin", "2025-03-15")
    checkout = params.get("checkout", "2025-03-17")

    hotels = [
        {"name": "オーシャンビューリゾート", "price_per_night": 25000, "rating": 4.5, "type": "リゾート"},
        {"name": "シティホテル那覇", "price_per_night": 12000, "rating": 4.0, "type": "ビジネス"},
        {"name": "ビーチフロント ヴィラ", "price_per_night": 45000, "rating": 4.8, "type": "高級"},
        {"name": "ゲストハウス美ら海", "price_per_night": 5000, "rating": 3.8, "type": "ゲストハウス"},
    ]

    return {
        "city": city,
        "checkin": checkin,
        "checkout": checkout,
        "hotels": hotels,
    }


def get_weather(params):
    """天気予報"""
    city = params.get("city", "沖縄")
    date = params.get("date", "2025-03-15")

    weathers = ["晴れ", "曇り", "晴れ時々曇り", "曇り時々雨"]

    return {
        "city": city,
        "date": date,
        "condition": random.choice(weathers),
        "high_temp": random.randint(25, 32),
        "low_temp": random.randint(20, 25),
        "rain_probability": random.randint(0, 40),
    }
