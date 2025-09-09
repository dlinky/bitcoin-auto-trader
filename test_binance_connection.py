#!/usr/bin/env python3
"""
바이낸스 API 연결 테스트 스크립트
프로젝트 루트 디렉토리에서 실행: python test_binance_connection.py
"""

import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.api.binance_client import BinanceClient

def main():
    """
    바이낸스 API 연결 테스트 실행
    """
    print("=" * 60)
    print("🚀 바이낸스 테스트넷 API 연결 테스트 시작")
    print("=" * 60)
    
    # 바이낸스 클라이언트 초기화 (테스트넷)
    try:
        binance_client = BinanceClient(testnet=True)
        print("✅ 바이낸스 클라이언트 초기화 성공")
    except Exception as e:
        print(f"❌ 클라이언트 초기화 실패: {e}")
        return
    
    print("\n" + "-" * 40)
    print("1️⃣ API 연결 테스트")
    print("-" * 40)
    
    # 연결 테스트
    if binance_client.test_connection():
        print("✅ API 연결 성공!")
    else:
        print("❌ API 연결 실패!")
        return
    
    print("\n" + "-" * 40)
    print("2️⃣ 계정 정보 조회")
    print("-" * 40)
    
    # 계정 정보 조회
    account_info = binance_client.get_account_info()
    if account_info:
        print("✅ 계정 정보 조회 성공!")
        print(f"   💰 총 잔고: {account_info['total_balance']} USDT")
        print(f"   💳 사용 가능: {account_info['available_balance']} USDT")
    else:
        print("❌ 계정 정보 조회 실패!")
    
    print("\n" + "-" * 40)
    print("3️⃣ 현재가 조회 테스트")
    print("-" * 40)
    
    # 주요 암호화폐 현재가 조회
    symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
    for symbol in symbols:
        price = binance_client.get_symbol_price(symbol)
        if price:
            print(f"✅ {symbol}: ${price:,.2f}")
        else:
            print(f"❌ {symbol}: 조회 실패")
    
    print("\n" + "-" * 40)
    print("4️⃣ 거래소 정보 조회")
    print("-" * 40)
    
    # 거래소 정보 조회
    exchange_info = binance_client.get_exchange_info()
    if exchange_info:
        print("✅ 거래소 정보 조회 성공!")
        print(f"   🌍 시간대: {exchange_info['timezone']}")
        print(f"   📊 거래 가능 심볼: {len(exchange_info['active_symbols'])}개")
    else:
        print("❌ 거래소 정보 조회 실패!")
    
    print("\n" + "-" * 40)
    print("5️⃣ 테스트 주문 검증")
    print("-" * 40)
    
    # 테스트 주문 (실제 주문되지 않음)
    if binance_client.test_small_order("BTCUSDT", 0.001):
        print("✅ 테스트 주문 검증 성공!")
        print("   (실제 주문이 실행되지는 않습니다)")
    else:
        print("❌ 테스트 주문 검증 실패!")
    
    print("\n" + "=" * 60)
    print("🎉 바이낸스 API 연결 테스트 완료!")
    print("=" * 60)
    
    # 다음 단계 안내
    print("\n📋 다음 단계:")
    print("1. 모든 테스트가 성공했다면 트레이더 핵심 로직 개발 시작")
    print("2. 실패한 항목이 있다면 API 키 설정을 다시 확인해주세요")
    print("3. 테스트넷 USDT가 부족하다면 테스트넷 파우셋에서 추가 충전")

if __name__ == "__main__":
    main()