#!/usr/bin/env python3
"""
심볼 유효성 검증 스크립트
실행: python symbol_validation.py
"""

import requests
import json

def check_symbol_validity():
    """바이낸스 현물 vs 선물 심볼 비교"""
    
    print("🔍 바이낸스 심볼 유효성 검사")
    print("=" * 50)
    
    # 1. 현물 거래소 심볼 조회
    try:
        spot_url = "https://api.binance.com/api/v3/ticker/24hr"
        spot_response = requests.get(spot_url, timeout=10)
        spot_data = spot_response.json()
        
        spot_symbols = {ticker['symbol'] for ticker in spot_data}
        print(f"📈 현물 심볼 개수: {len(spot_symbols)}개")
        
    except Exception as e:
        print(f"❌ 현물 데이터 조회 실패: {e}")
        return
    
    # 2. 선물 거래소 심볼 조회
    try:
        futures_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        futures_response = requests.get(futures_url, timeout=10)
        futures_data = futures_response.json()
        
        futures_symbols = {ticker['symbol'] for ticker in futures_data}
        print(f"🚀 선물 심볼 개수: {len(futures_symbols)}개")
        
    except Exception as e:
        print(f"❌ 선물 데이터 조회 실패: {e}")
        return
    
    # 3. MYXUSDT 검증
    test_symbols = ['MYXUSDT', 'BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'SOLUSDT']
    
    print(f"\n📊 테스트 심볼 검증:")
    print("-" * 50)
    print(f"{'심볼':<12} {'현물':<6} {'선물':<6} {'상태'}")
    print("-" * 50)
    
    for symbol in test_symbols:
        spot_exists = symbol in spot_symbols
        futures_exists = symbol in futures_symbols
        
        if spot_exists and futures_exists:
            status = "✅ 둘다"
        elif spot_exists:
            status = "⚠️ 현물만"
        elif futures_exists:
            status = "⚠️ 선물만"
        else:
            status = "❌ 없음"
        
        print(f"{symbol:<12} {'✅' if spot_exists else '❌':<6} {'✅' if futures_exists else '❌':<6} {status}")
    
    # 4. MYXUSDT 세부 정보
    print(f"\n🔍 MYXUSDT 세부 정보:")
    print("-" * 50)
    
    if 'MYXUSDT' in spot_symbols:
        # 현물에서 MYXUSDT 정보 찾기
        myxusdt_spot = next((t for t in spot_data if t['symbol'] == 'MYXUSDT'), None)
        if myxusdt_spot:
            print(f"현물: 가격 ${float(myxusdt_spot['lastPrice']):.4f}, 24h 변화 {float(myxusdt_spot['priceChangePercent']):.2f}%")
    
    if 'MYXUSDT' in futures_symbols:
        # 선물에서 MYXUSDT 정보 찾기
        myxusdt_futures = next((t for t in futures_data if t['symbol'] == 'MYXUSDT'), None)
        if myxusdt_futures:
            print(f"선물: 가격 ${float(myxusdt_futures['lastPrice']):.4f}, 24h 변화 {float(myxusdt_futures['priceChangePercent']):.2f}%")
    
    # 5. 권장 사항
    print(f"\n💡 권장 사항:")
    print("-" * 50)
    
    available_symbols = [s for s in test_symbols if s in futures_symbols]
    if available_symbols:
        print(f"✅ 선물에서 사용 가능한 심볼: {', '.join(available_symbols)}")
    
    unavailable_symbols = [s for s in test_symbols if s not in futures_symbols]
    if unavailable_symbols:
        print(f"❌ 선물에서 사용 불가능한 심볼: {', '.join(unavailable_symbols)}")

if __name__ == "__main__":
    check_symbol_validity()