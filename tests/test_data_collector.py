#!/usr/bin/env python3
"""
DataCollector 테스트 코드
실행 방법: python test_data_collector.py
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.api.binance_client import BinanceClient
from src.api.supabase_client import SupabaseClient
from src.core.data_collector import DataCollector
from src.utils.logger import get_logger

logger = get_logger(__name__)

def setup_test_environment():
    """테스트 환경 설정"""
    print("🔧 테스트 환경 설정 중...")
    
    # .env 파일 로드
    env_path = project_root / 'config' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ 환경변수 로드: {env_path}")
    else:
        print(f"❌ .env 파일을 찾을 수 없음: {env_path}")
        return None, None
    
    try:
        # 클라이언트 초기화
        binance_client = BinanceClient(
            os.getenv('BINANCE_API_KEY'),
            os.getenv('BINANCE_SECRET_KEY'),
            testnet=True
        )
        
        supabase_client = SupabaseClient()
        
        print("✅ 클라이언트 초기화 완료")
        return binance_client, supabase_client
        
    except Exception as e:
        print(f"❌ 클라이언트 초기화 실패: {e}")
        return None, None

def test_data_collector_init():
    """DataCollector 초기화 테스트"""
    print("\n1️⃣ DataCollector 초기화 테스트")
    
    binance_client, supabase_client = setup_test_environment()
    
    if not binance_client or not supabase_client:
        print("❌ 클라이언트 초기화 실패로 테스트 중단")
        return None
    
    try:
        # DataCollector 생성
        collector = DataCollector(
            binance_client=binance_client,
            supabase_client=supabase_client,
            symbols=['BTCUSDT']
        )
        
        print("✅ DataCollector 초기화 성공")
        return collector, binance_client, supabase_client
        
    except Exception as e:
        print(f"❌ DataCollector 초기화 실패: {e}")
        return None

def test_missing_data_check(collector):
    """누락 데이터 확인 테스트"""
    print("\n2️⃣ 누락 데이터 확인 테스트")
    
    try:
        symbol = 'BTCUSDT'
        
        # 누락 구간 확인
        missing_ranges = collector.db_client.get_missing_time_ranges(symbol, 200)
        
        print(f"📊 {symbol} 누락 구간: {len(missing_ranges)}개")
        
        if missing_ranges:
            print("   누락된 시간 구간들:")
            for i, (start, end) in enumerate(missing_ranges[:5]):  # 최대 5개만 표시
                duration = int((end - start).total_seconds() / 60) + 1
                print(f"   {i+1}. {start} ~ {end} ({duration}분)")
            
            if len(missing_ranges) > 5:
                print(f"   ... 외 {len(missing_ranges) - 5}개 구간")
        else:
            print("   ✅ 누락된 데이터 없음")
        
        return missing_ranges
        
    except Exception as e:
        print(f"❌ 누락 데이터 확인 실패: {e}")
        return []

def test_single_data_collection(collector):
    """단일 데이터 수집 테스트"""
    print("\n3️⃣ 단일 데이터 수집 테스트")
    
    try:
        symbol = 'BTCUSDT'
        
        print(f"📈 {symbol} 최신 데이터 1개 수집 중...")
        start_time = time.time()
        
        success = collector.collect_latest_data(symbol)
        
        elapsed = time.time() - start_time
        
        if success:
            print(f"✅ 데이터 수집 성공 ({elapsed:.1f}초)")
        else:
            print(f"❌ 데이터 수집 실패 ({elapsed:.1f}초)")
        
        return success
        
    except Exception as e:
        print(f"❌ 단일 데이터 수집 중 에러: {e}")
        return False

def test_concurrent_collection(collector):
    """동시 데이터 수집 테스트"""
    print("\n4️⃣ 동시 데이터 수집 테스트")
    
    try:
        # 여러 심볼로 테스트 (실제로는 BTCUSDT만 있을 수 있음)
        test_symbols = ['BTCUSDT']
        collector.symbols = test_symbols
        
        print(f"📊 심볼 {len(test_symbols)}개 동시 수집 중...")
        start_time = time.time()
        
        results = collector.collect_all_symbols_concurrent()
        
        elapsed = time.time() - start_time
        success_count = sum(results.values())
        
        print(f"📈 수집 결과: {success_count}/{len(test_symbols)}개 성공 ({elapsed:.1f}초)")
        
        for symbol, success in results.items():
            status = "✅" if success else "❌"
            print(f"   {status} {symbol}")
        
        if elapsed > 10:
            print("⚠️  10초 제한 초과 - 성능 최적화 필요")
        
        return results
        
    except Exception as e:
        print(f"❌ 동시 수집 중 에러: {e}")
        return {}

def test_historical_data_fill(collector, limit_ranges=2):
    """과거 데이터 보완 테스트 (제한적)"""
    print(f"\n5️⃣ 과거 데이터 보완 테스트 (최대 {limit_ranges}개 구간)")
    
    try:
        symbol = 'BTCUSDT'
        
        # 누락 구간 확인
        missing_ranges = collector.db_client.get_missing_time_ranges(symbol, 200)
        
        if not missing_ranges:
            print("✅ 보완할 데이터 없음")
            return True
        
        # 테스트용으로 최대 2개 구간만 처리
        test_ranges = missing_ranges[:limit_ranges]
        
        print(f"📊 {len(test_ranges)}개 구간 보완 시작...")
        
        success_count = 0
        for i, (start_time, end_time) in enumerate(test_ranges, 1):
            duration = int((end_time - start_time).total_seconds() / 60) + 1
            print(f"   구간 {i}: {start_time} ~ {end_time} ({duration}분)")
            
            collected = collector._collect_candles_by_range(symbol, start_time, end_time)
            
            if collected > 0:
                print(f"      ✅ {collected}개 수집 완료")
                success_count += 1
            else:
                print(f"      ❌ 수집 실패")
        
        print(f"📈 보완 결과: {success_count}/{len(test_ranges)}개 구간 성공")
        
        if len(missing_ranges) > limit_ranges:
            remaining = len(missing_ranges) - limit_ranges
            print(f"ℹ️  남은 {remaining}개 구간은 실제 운영시 처리됩니다")
        
        return success_count > 0
        
    except Exception as e:
        print(f"❌ 과거 데이터 보완 중 에러: {e}")
        return False

def test_database_status(supabase_client):
    """데이터베이스 상태 확인"""
    print("\n6️⃣ 데이터베이스 상태 확인")
    
    try:
        db_info = supabase_client.get_database_info()
        
        print("📊 데이터베이스 현황:")
        print(f"   연결 상태: {'✅ 정상' if db_info['connection'] else '❌ 실패'}")
        print(f"   총 레코드: {db_info['total_records']:,}개")
        
        print("\n📋 테이블별 상세:")
        for table, info in db_info['tables'].items():
            status = "✅" if info['exists'] else "❌"
            print(f"   {status} {table}: {info['records']:,}개")
        
        return db_info['connection']
        
    except Exception as e:
        print(f"❌ 데이터베이스 상태 확인 실패: {e}")
        return False

def main():
    """메인 테스트 함수"""
    print("🧪 DataCollector 통합 테스트 시작")
    print("=" * 60)
    
    # 초기화 테스트
    result = test_data_collector_init()
    if not result:
        print("\n💥 초기화 실패로 테스트 중단")
        return
    
    collector, binance_client, supabase_client = result
    
    # 데이터베이스 상태 확인
    db_ok = test_database_status(supabase_client)
    if not db_ok:
        print("\n⚠️  데이터베이스 연결 문제 있지만 계속 진행")
    
    # 누락 데이터 확인
    missing_ranges = test_missing_data_check(collector)
    
    # 단일 데이터 수집 테스트
    single_success = test_single_data_collection(collector)
    
    # 동시 데이터 수집 테스트
    concurrent_results = test_concurrent_collection(collector)
    
    # 과거 데이터 보완 테스트 (제한적)
    if missing_ranges:
        historical_success = test_historical_data_fill(collector, limit_ranges=1)
    else:
        print("\n5️⃣ 과거 데이터 보완 테스트 건너뜀 (누락 데이터 없음)")
        historical_success = True
    
    # 최종 결과
    print("\n" + "=" * 60)
    print("🎯 테스트 결과 요약")
    
    tests = [
        ("DataCollector 초기화", True),
        ("데이터베이스 연결", db_ok),
        ("단일 데이터 수집", single_success),
        ("동시 데이터 수집", len(concurrent_results) > 0 and any(concurrent_results.values())),
        ("과거 데이터 보완", historical_success)
    ]
    
    for test_name, success in tests:
        status = "✅ 통과" if success else "❌ 실패"
        print(f"   {status} {test_name}")
    
    success_count = sum(success for _, success in tests)
    print(f"\n📊 전체 결과: {success_count}/{len(tests)}개 테스트 통과")
    
    if success_count == len(tests):
        print("🎉 모든 테스트 통과! DataCollector 준비 완료")
        print("\n📋 다음 단계:")
        print("   1. Strategy 클래스 개발")
        print("   2. Trader 클래스 개발")
        print("   3. 스케줄러 연동")
    else:
        print("⚠️  일부 테스트 실패 - 문제 해결 후 재테스트")

if __name__ == "__main__":
    main()