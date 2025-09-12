#!/usr/bin/env python3
"""
Logger 테스트 코드
실행 방법: python test_logger.py
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.utils.logger import get_logger, setup_logger, log_function_call

def test_basic_logging():
    """기본 로깅 테스트"""
    print("1️⃣ 기본 로깅 테스트")
    
    # 테스트용 로거 생성
    logger = get_logger('test_module')
    
    print("   로그 레벨별 메시지 출력:")
    logger.debug("🔍 DEBUG 메시지 - 상세한 디버그 정보")
    logger.info("ℹ️ INFO 메시지 - 일반 정보")
    logger.warning("⚠️ WARNING 메시지 - 경고")
    logger.error("❌ ERROR 메시지 - 에러 발생")
    logger.critical("🚨 CRITICAL 메시지 - 심각한 오류")
    
    print("   ✅ 기본 로깅 테스트 완료")

def test_multiple_modules():
    """여러 모듈에서 로깅 테스트"""
    print("\n2️⃣ 다중 모듈 로깅 테스트")
    
    # 다른 모듈명으로 로거 생성
    binance_logger = get_logger('binance_client')
    trader_logger = get_logger('trader')
    collector_logger = get_logger('data_collector')
    
    print("   여러 모듈에서 로그 메시지:")
    binance_logger.info("바이낸스 API 호출 시작")
    trader_logger.info("매매 신호 분석 중")
    collector_logger.info("시장 데이터 수집 완료")
    
    print("   ✅ 다중 모듈 로깅 테스트 완료")

def test_log_levels():
    """로그 레벨별 필터링 테스트"""
    print("\n3️⃣ 로그 레벨 필터링 테스트")
    
    # 현재 설정된 로그 레벨 확인
    current_level = os.getenv('LOG_LEVEL', 'INFO')
    print(f"   현재 LOG_LEVEL: {current_level}")
    
    logger = get_logger('level_test')
    
    if current_level == 'DEBUG':
        print("   DEBUG 레벨 - 모든 로그 출력됨")
        logger.debug("이 DEBUG 메시지가 보여야 함")
    elif current_level == 'INFO':
        print("   INFO 레벨 - DEBUG 메시지는 출력 안됨")
        logger.debug("이 DEBUG 메시지는 안 보임")
        logger.info("이 INFO 메시지는 보임")
    
    print("   ✅ 로그 레벨 테스트 완료")

def test_file_logging():
    """파일 로깅 테스트"""
    print("\n4️⃣ 파일 로깅 테스트")
    
    logger = get_logger('file_test')
    
    # 로그 디렉토리 확인
    log_dir = Path('logs')
    if log_dir.exists():
        print(f"   📁 로그 디렉토리 존재: {log_dir.absolute()}")
        
        # 오늘 날짜 로그 파일 찾기
        log_files = list(log_dir.glob('trading_*.log'))
        if log_files:
            latest_log = max(log_files, key=os.path.getmtime)
            print(f"   📄 로그 파일: {latest_log.name}")
            
            # 파일 크기 확인
            file_size = latest_log.stat().st_size
            print(f"   📊 파일 크기: {file_size} bytes")
        else:
            print("   📄 로그 파일이 아직 생성되지 않음")
    else:
        print("   📁 로그 디렉토리가 생성되지 않음")
    
    # 테스트 로그 작성
    logger.info("파일 로깅 테스트 메시지")
    print("   ✅ 파일 로깅 테스트 완료")

@log_function_call(get_logger('decorator_test'), 'INFO')
def sample_function(x, y):
    """데코레이터 테스트용 함수"""
    time.sleep(0.1)  # 작업 시뮬레이션
    return x + y

def test_function_decorator():
    """함수 호출 로깅 데코레이터 테스트"""
    print("\n5️⃣ 함수 데코레이터 테스트")
    
    print("   데코레이터가 적용된 함수 호출:")
    result = sample_function(3, 7)
    print(f"   결과: {result}")
    
    print("   ✅ 데코레이터 테스트 완료")

def test_error_logging():
    """에러 로깅 테스트"""
    print("\n6️⃣ 에러 로깅 테스트")
    
    logger = get_logger('error_test')
    
    try:
        # 의도적으로 에러 발생
        result = 1 / 0
    except ZeroDivisionError as e:
        logger.error(f"계산 에러 발생: {e}")
        print("   ❌ 에러 로그 기록 완료")
    
    print("   ✅ 에러 로깅 테스트 완료")

def main():
    """메인 테스트 함수"""
    print("🧪 Logger 모듈 테스트 시작")
    print("=" * 50)
    
    # .env 파일 로드
    env_path = project_root / 'config' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"📄 환경변수 로드: {env_path}")
    else:
        print(f"⚠️ .env 파일을 찾을 수 없음: {env_path}")
    
    # 각 테스트 실행
    test_basic_logging()
    test_multiple_modules()
    test_log_levels()
    test_file_logging()
    test_function_decorator()
    test_error_logging()
    
    print("\n" + "=" * 50)
    print("🎉 모든 Logger 테스트 완료!")
    
    # 테스트 후 확인사항
    print("\n📋 확인사항:")
    print("   1. 콘솔에 로그 메시지들이 올바르게 출력되었는지 확인")
    print("   2. logs/ 디렉토리에 로그 파일이 생성되었는지 확인")
    print("   3. 로그 레벨에 따라 메시지가 필터링되는지 확인")
    print("   4. 에러 로그가 적절히 기록되었는지 확인")

if __name__ == "__main__":
    main()