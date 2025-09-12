#!/usr/bin/env python3
"""
Strategy 테스트 코드
실행 방법: python test_strategy.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.api.supabase_client import SupabaseClient
from src.strategies.macd_atr import MACDATRStrategy
from src.utils.logger import get_logger

logger = get_logger(__name__)

def setup_test_environment():
    """테스트 환경 설정"""
    print("🔧 Strategy 테스트 환경 설정 중...")
    
    # .env 파일 로드
    env_path = project_root / 'config' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ 환경변수 로드: {env_path}")
    else:
        print(f"❌ .env 파일을 찾을 수 없음: {env_path}")
        return None
    
    try:
        # Supabase 클라이언트 생성
        supabase_client = SupabaseClient()
        print("✅ Supabase 클라이언트 초기화 완료")
        
        return supabase_client
        
    except Exception as e:
        print(f"❌ 클라이언트 초기화 실패: {e}")
        return None

def test_strategy_initialization():
    """Strategy 초기화 테스트"""
    print("\n1️⃣ Strategy 초기화 테스트")
    
    supabase_client = setup_test_environment()
    if not supabase_client:
        print("❌ 환경 설정 실패로 테스트 중단")
        return None
    
    try:
        # MACDATRStrategy 생성
        strategy = MACDATRStrategy(
            supabase_client=supabase_client,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            atr_period=14,
            atr_multiplier=2.0
        )
        
        # 전략 정보 확인
        strategy_info = strategy.get_strategy_info()
        
        print("✅ Strategy 초기화 성공")
        print(f"   전략명: {strategy_info['name']}")
        print(f"   설명: {strategy_info['description']}")
        print(f"   파라미터: {strategy_info['parameters']}")
        
        return strategy, supabase_client
        
    except Exception as e:
        print(f"❌ Strategy 초기화 실패: {e}")
        return None

def test_market_data_availability(supabase_client):
    """시장 데이터 가용성 확인"""
    print("\n2️⃣ 시장 데이터 가용성 확인")
    
    try:
        symbol = 'BTCUSDT'
        
        # 최근 데이터 조회
        response = supabase_client.client.table('market_data').select(
            'timestamp, close, macd_12_26_9_line, macd_12_26_9_signal, macd_12_26_9_histogram, atr_14_value'
        ).eq('symbol', symbol).order(
            'timestamp', desc=True
        ).limit(5).execute()
        
        if not response.data:
            print(f"❌ {symbol} 시장 데이터 없음")
            return False
        
        print(f"📊 {symbol} 시장 데이터 현황:")
        print(f"   조회된 레코드 수: {len(response.data)}개")
        
        # 최신 데이터 상세 정보
        latest = response.data[0]
        print(f"   최신 데이터 시간: {latest['timestamp']}")
        print(f"   종가: ${float(latest['close']):,.2f}")
        
        # 지표 데이터 확인
        indicators_ok = True
        if latest['macd_12_26_9_line'] is None:
            print("   ⚠️ MACD Line 데이터 없음")
            indicators_ok = False
        else:
            print(f"   MACD Line: {float(latest['macd_12_26_9_line']):.6f}")
        
        if latest['macd_12_26_9_signal'] is None:
            print("   ⚠️ MACD Signal 데이터 없음")
            indicators_ok = False
        else:
            print(f"   MACD Signal: {float(latest['macd_12_26_9_signal']):.6f}")
        
        if latest['atr_14_value'] is None:
            print("   ⚠️ ATR 데이터 없음")
            indicators_ok = False
        else:
            print(f"   ATR(14): {float(latest['atr_14_value']):.4f}")
        
        if indicators_ok:
            print("   ✅ 모든 지표 데이터 정상")
        else:
            print("   ❌ 일부 지표 데이터 누락")
        
        return indicators_ok
        
    except Exception as e:
        print(f"❌ 시장 데이터 확인 실패: {e}")
        return False

def test_signal_generation(strategy):
    """시그널 생성 테스트"""
    print("\n3️⃣ 시그널 생성 테스트")
    
    symbol = 'BTCUSDT'
    test_cases = [
        {'position': None, 'description': '포지션 없음'},
        {'position': 'LONG', 'description': '롱 포지션 보유'},
        {'position': 'SHORT', 'description': '숏 포지션 보유'},
        {'position': 'NONE', 'description': '포지션 없음 (명시)'}
    ]
    
    results = []
    
    for i, case in enumerate(test_cases, 1):
        try:
            print(f"\n   테스트 케이스 {i}: {case['description']}")
            
            # 시그널 생성
            signal = strategy.generate_signal(symbol, case['position'])
            
            # 결과 출력
            print(f"   📈 시그널: {signal['signal']}")
            print(f"   🎯 신뢰도: {signal['confidence']:.2f}")
            print(f"   📝 사유: {signal['reason']}")
            
            if signal['data']:
                print(f"   📊 추가 정보:")
                for key, value in signal['data'].items():
                    if key == 'timestamp':
                        print(f"      {key}: {value}")
                    elif isinstance(value, (int, float)):
                        print(f"      {key}: {value:.6f}")
                    else:
                        print(f"      {key}: {value}")
            
            results.append({
                'case': case['description'],
                'signal': signal['signal'],
                'confidence': signal['confidence'],
                'success': True
            })
            
            print(f"   ✅ 테스트 케이스 {i} 성공")
            
        except Exception as e:
            print(f"   ❌ 테스트 케이스 {i} 실패: {e}")
            results.append({
                'case': case['description'],
                'signal': 'ERROR',
                'confidence': 0.0,
                'success': False
            })
    
    return results

def test_crossover_detection(strategy):
    """크로스오버 감지 테스트"""
    print("\n4️⃣ MACD 크로스오버 감지 테스트")
    
    try:
        symbol = 'BTCUSDT'
        
        # 최근 3개 데이터 조회 (크로스오버 확인을 위해)
        indicators = strategy._get_latest_indicators(symbol, limit=3)
        
        if len(indicators) < 2:
            print("❌ 크로스오버 테스트를 위한 데이터 부족")
            return False
        
        print(f"📊 최근 {len(indicators)}개 데이터로 크로스오버 분석:")
        
        for i in range(len(indicators)):
            data = indicators[i]
            macd_line = float(data['macd_12_26_9_line'])
            macd_signal = float(data['macd_12_26_9_signal'])
            position = "위" if macd_line > macd_signal else "아래"
            
            print(f"   {i+1}. {data['timestamp']}")
            print(f"      MACD Line: {macd_line:.6f}")
            print(f"      MACD Signal: {macd_signal:.6f}")
            print(f"      상대위치: MACD가 Signal {position}")
        
        # 크로스오버 확인 (최신 2개 데이터)
        if len(indicators) >= 2:
            current = indicators[-1]
            previous = indicators[-2]
            crossover_type = strategy._check_macd_crossover(current, previous)
            
            print(f"\n🔍 크로스오버 분석 결과: {crossover_type}")
            
            if crossover_type == 'GOLDEN':
                print("   🟢 골든크로스 발생 - 상승 시그널")
            elif crossover_type == 'DEAD':
                print("   🔴 데드크로스 발생 - 하락 시그널")
            else:
                print("   ⚪ 크로스오버 없음 - 대기")
        
        return True
        
    except Exception as e:
        print(f"❌ 크로스오버 감지 테스트 실패: {e}")
        return False

def test_atr_filter(strategy):
    """ATR 필터 테스트"""
    print("\n5️⃣ ATR 노이즈 필터 테스트")
    
    try:
        symbol = 'BTCUSDT'
        
        # 최신 데이터 조회
        indicators = strategy._get_latest_indicators(symbol, limit=1)
        
        if not indicators:
            print("❌ ATR 테스트를 위한 데이터 없음")
            return False
        
        current = indicators[0]
        atr_value = float(current['atr_14_value'])
        close_price = float(current['close'])
        
        print("📊 ATR 필터 분석:")
        print(f"   현재 종가: ${close_price:,.2f}")
        print(f"   ATR(14) 값: {atr_value:.4f}")
        print(f"   ATR 비율: {(atr_value/close_price)*100:.3f}%")
        
        # ATR 필터 테스트
        filter_passed = strategy._check_atr_filter(current)
        
        if filter_passed:
            print("   ✅ ATR 필터 통과 - 유의미한 움직임")
        else:
            print("   ❌ ATR 필터 차단 - 노이즈로 판단")
        
        return True
        
    except Exception as e:
        print(f"❌ ATR 필터 테스트 실패: {e}")
        return False

def main():
    """메인 테스트 함수"""
    print("🧪 MACDATRStrategy 통합 테스트 시작")
    print("=" * 60)
    
    # 1. Strategy 초기화
    result = test_strategy_initialization()
    if not result:
        print("\n💥 Strategy 초기화 실패로 테스트 중단")
        return
    
    strategy, supabase_client = result
    
    # 2. 시장 데이터 확인
    data_ok = test_market_data_availability(supabase_client)
    if not data_ok:
        print("\n⚠️ 시장 데이터 문제 있지만 계속 진행")
    
    # 3. 시그널 생성 테스트
    signal_results = test_signal_generation(strategy)
    
    # 4. 크로스오버 감지 테스트
    crossover_ok = test_crossover_detection(strategy)
    
    # 5. ATR 필터 테스트
    atr_ok = test_atr_filter(strategy)
    
    # 최종 결과
    print("\n" + "=" * 60)
    print("🎯 테스트 결과 요약")
    
    success_count = 0
    total_count = 5
    
    tests = [
        ("Strategy 초기화", True),
        ("시장 데이터 가용성", data_ok),
        ("시그널 생성", len([r for r in signal_results if r['success']]) == len(signal_results)),
        ("크로스오버 감지", crossover_ok),
        ("ATR 필터", atr_ok)
    ]
    
    for test_name, success in tests:
        status = "✅ 통과" if success else "❌ 실패"
        print(f"   {status} {test_name}")
        if success:
            success_count += 1
    
    print(f"\n📊 전체 결과: {success_count}/{total_count}개 테스트 통과")
    
    # 시그널 결과 상세
    print("\n📈 시그널 생성 결과:")
    for result in signal_results:
        status = "✅" if result['success'] else "❌"
        print(f"   {status} {result['case']}: {result['signal']} (신뢰도: {result['confidence']:.2f})")
    
    if success_count == total_count:
        print("\n🎉 모든 테스트 통과! MACDATRStrategy 준비 완료")
        print("\n📋 다음 단계:")
        print("   1. Trader 클래스 개발")
        print("   2. Strategy-Trader 통합 테스트")
        print("   3. 실제 매매 시뮬레이션")
    else:
        print(f"\n⚠️ {total_count - success_count}개 테스트 실패 - 문제 해결 후 재테스트")

if __name__ == "__main__":
    main()