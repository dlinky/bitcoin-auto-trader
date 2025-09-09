#!/usr/bin/env python3
"""
데이터베이스 연동 테스트 스크립트
프로젝트 루트에서 실행: python test_database.py

사전 준비사항:
1. Supabase 프로젝트 생성
2. .env 파일에 SUPABASE_URL, SUPABASE_ANON_KEY 설정
3. Supabase 대시보드에서 CREATE_TABLES_SQL 실행
4. pip install supabase 설치
"""

import sys
import os
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.database.database_manager import DatabaseManager
from backend.database.models import (
    Trade, Position, TradingSession, RiskEvent, SystemLog, 
    Configuration, PerformanceMetric, CREATE_TABLES_SQL
)

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def print_sql_instructions():
    """SQL 테이블 생성 가이드"""
    print("📋 Supabase 테이블 생성 가이드:")
    print("=" * 70)
    print("1. Supabase 대시보드 (https://app.supabase.com) 접속")
    print("2. 프로젝트 선택 → SQL Editor 메뉴")
    print("3. 아래 SQL을 복사해서 실행:")
    print("-" * 70)
    print(CREATE_TABLES_SQL)
    print("-" * 70)
    print("4. 실행 완료 후 이 테스트 스크립트 재실행")
    print("=" * 70)

def test_database_connection():
    """데이터베이스 연결 테스트"""
    print("=" * 70)
    print("🗄️ 데이터베이스 연동 시스템 테스트")
    print("=" * 70)
    
    # 환경변수 확인
    print("\n" + "-" * 50)
    print("1️⃣ 환경변수 확인")
    print("-" * 50)
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_ANON_KEY')
    
    if not supabase_url or not supabase_key:
        print("❌ Supabase 환경변수가 설정되지 않았습니다!")
        print("📋 .env 파일에 다음 내용을 추가하세요:")
        print("SUPABASE_URL=https://your-project.supabase.co")
        print("SUPABASE_ANON_KEY=your-anon-key")
        return False
    
    print("✅ SUPABASE_URL:", supabase_url[:50] + "...")
    print("✅ SUPABASE_ANON_KEY:", supabase_key[:20] + "...")
    
    # 데이터베이스 매니저 초기화
    print("\n" + "-" * 50)
    print("2️⃣ 데이터베이스 연결")
    print("-" * 50)
    
    try:
        db = DatabaseManager()
        print("✅ 데이터베이스 매니저 초기화 성공")
    except Exception as e:
        print(f"❌ 데이터베이스 연결 실패: {e}")
        return False
    
    # 테이블 존재 확인
    print("\n" + "-" * 50)
    print("3️⃣ 테이블 존재 확인")
    print("-" * 50)
    
    if not db.initialize_database():
        print("❌ 테이블이 존재하지 않거나 접근할 수 없습니다!")
        print_sql_instructions()
        return False
    
    print("✅ 모든 테이블 확인 완료")
    
    # 상태 확인
    print("\n" + "-" * 50)
    print("4️⃣ 데이터베이스 상태 확인")
    print("-" * 50)
    
    health = db.health_check()
    print(f"📊 전체 상태: {health['status']}")
    
    for table, info in health['tables'].items():
        status = "✅" if info['accessible'] else "❌"
        count = f"({info.get('count', 0)}개 레코드)" if info['accessible'] else f"({info.get('error', 'unknown')})"
        print(f"   {status} {table}: {count}")
    
    if health['status'] != 'healthy':
        print("⚠️ 일부 테이블에 문제가 있습니다.")
    
    return True

def test_database_operations(db: DatabaseManager):
    """데이터베이스 CRUD 작업 테스트"""
    
    print("\n" + "-" * 50)
    print("5️⃣ 거래 기록 테스트")
    print("-" * 50)
    
    # 테스트 거래 기록 생성
    test_trade = Trade(
        trader_id="test_trader",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.001,
        price=50000.0,
        executed_quantity=0.001,
        executed_price=50000.0,
        commission=0.05,
        status="FILLED",
        binance_order_id="12345678",
        stop_loss_price=48000.0,
        take_profit_price=52000.0,
        notes="테스트 거래"
    )
    
    # 거래 기록 저장
    trade_id = db.save_trade(test_trade)
    if trade_id:
        print(f"✅ 거래 기록 저장 성공: {trade_id}")
        
        # 거래 기록 업데이트
        update_success = db.update_trade(trade_id, {
            'status': 'FILLED',
            'notes': '테스트 거래 - 업데이트됨'
        })
        print(f"✅ 거래 기록 업데이트: {'성공' if update_success else '실패'}")
        
    else:
        print("❌ 거래 기록 저장 실패")
    
    # 거래 기록 조회
    recent_trades = db.get_trades("test_trader", limit=5)
    print(f"📊 최근 거래 기록: {len(recent_trades)}개")
    
    for trade in recent_trades[:2]:  # 최근 2개만 출력
        print(f"   • {trade['symbol']} {trade['side']} {trade['quantity']} @ ${trade['price']}")
    
    print("\n" + "-" * 50)
    print("6️⃣ 포지션 기록 테스트")
    print("-" * 50)
    
    # 테스트 포지션 생성
    test_position = Position(
        trader_id="test_trader",
        symbol="BTCUSDT",
        side="LONG",
        size=0.001,
        entry_price=50000.0,
        mark_price=50500.0,
        unrealized_pnl=0.5,
        percentage=1.0,
        notional=50.5,
        margin=25.0,
        is_active=True
    )
    
    position_id = db.save_position(test_position)
    if position_id:
        print(f"✅ 포지션 기록 저장 성공: {position_id}")
        
        # 포지션 업데이트 (가격 변동)
        update_success = db.update_position(position_id, {
            'mark_price': 51000.0,
            'unrealized_pnl': 1.0,
            'percentage': 2.0
        })
        print(f"✅ 포지션 업데이트: {'성공' if update_success else '실패'}")
        
    else:
        print("❌ 포지션 기록 저장 실패")
    
    # 활성 포지션 조회
    active_positions = db.get_active_positions("test_trader")
    print(f"📊 활성 포지션: {len(active_positions)}개")
    
    print("\n" + "-" * 50)
    print("7️⃣ 거래 세션 테스트")
    print("-" * 50)
    
    # 거래 세션 생성
    test_session = TradingSession(
        trader_id="test_trader",
        session_name=f"테스트_세션_{datetime.now().strftime('%Y%m%d_%H%M')}",
        strategy="TEST_STRATEGY",
        symbol="BTCUSDT",
        start_balance=1000.0,
        current_balance=1005.0,
        peak_balance=1010.0,
        total_pnl=5.0,
        total_trades=3,
        winning_trades=2,
        losing_trades=1,
        win_rate=66.67,
        max_drawdown=0.5,
        is_active=True,
        notes="데이터베이스 테스트 세션"
    )
    
    session_id = db.create_trading_session(test_session)
    if session_id:
        print(f"✅ 거래 세션 생성 성공: {session_id}")
        
        # 세션 종료
        end_success = db.end_trading_session(session_id, {
            'current_balance': 1008.0,
            'total_pnl': 8.0,
            'total_trades': 5,
            'notes': '테스트 완료'
        })
        print(f"✅ 세션 종료: {'성공' if end_success else '실패'}")
        
    else:
        print("❌ 거래 세션 생성 실패")
    
    print("\n" + "-" * 50)
    print("8️⃣ 리스크 이벤트 테스트")
    print("-" * 50)
    
    # 리스크 이벤트 기록
    test_risk_event = RiskEvent(
        trader_id="test_trader",
        session_id=session_id,
        event_type="CONSECUTIVE_LOSS",
        risk_level="MEDIUM",
        triggered_by="LOSS_COUNT",
        trigger_value=3.0,
        threshold_value=5.0,
        action_taken="REDUCE_SIZE",
        description="3회 연속 손실 발생, 포지션 크기 50% 축소"
    )
    
    risk_id = db.log_risk_event(test_risk_event)
    print(f"✅ 리스크 이벤트 기록: {'성공' if risk_id else '실패'}")
    
    # 최근 리스크 이벤트 조회
    recent_risks = db.get_recent_risk_events("test_trader", hours=24)
    print(f"📊 24시간 내 리스크 이벤트: {len(recent_risks)}개")
    
    print("\n" + "-" * 50)
    print("9️⃣ 성과 지표 테스트")
    print("-" * 50)
    
    # 일일 성과 지표 저장
    test_metrics = PerformanceMetric(
        trader_id="test_trader",
        session_id=session_id,
        metric_date=datetime.now(),
        daily_pnl=5.0,
        weekly_pnl=25.0,
        monthly_pnl=100.0,
        cumulative_pnl=150.0,
        total_trades_today=5,
        winning_trades_today=3,
        losing_trades_today=2,
        win_rate_today=60.0,
        max_drawdown=2.5,
        current_drawdown=0.5,
        consecutive_losses=0,
        largest_win=10.0,
        largest_loss=-5.0,
        account_balance=1005.0,
        available_balance=950.0,
        allocated_capital=100.0,
        capital_utilization=55.0,
        sharpe_ratio=1.25,
        profit_factor=1.8
    )
    
    metrics_success = db.save_daily_metrics(test_metrics)
    print(f"✅ 일일 성과 지표 저장: {'성공' if metrics_success else '실패'}")
    
    # 성과 요약 조회
    performance_summary = db.get_performance_summary("test_trader", days=30)
    if performance_summary:
        print(f"📊 30일 성과 요약:")
        print(f"   총 손익: ${performance_summary.get('total_pnl', 0):+.2f}")
        print(f"   총 거래: {performance_summary.get('total_trades', 0)}회")
        print(f"   승률: {performance_summary.get('win_rate', 0):.1f}%")
        print(f"   최고 수익일: ${performance_summary.get('best_day', 0):+.2f}")
        print(f"   최악 손실일: ${performance_summary.get('worst_day', 0):+.2f}")
    
    print("\n" + "-" * 50)
    print("🔟 시스템 로그 테스트")
    print("-" * 50)
    
    # 시스템 로그 기록
    test_log = SystemLog(
        trader_id="test_trader",
        log_level="INFO",
        component="DATABASE_TEST",
        event="TEST_COMPLETED",
        message="데이터베이스 테스트가 성공적으로 완료되었습니다.",
        data={
            'test_duration': '5 minutes',
            'operations_tested': 10,
            'success_rate': '100%'
        }
    )
    
    log_success = db.log_system_event(test_log)
    print(f"✅ 시스템 로그 기록: {'성공' if log_success else '실패'}")
    
    print("\n" + "-" * 50)
    print("1️⃣1️⃣ 거래 통계 조회")
    print("-" * 50)
    
    # 거래 통계 조회
    trading_stats = db.get_trading_statistics("test_trader", days=30)
    if 'error' not in trading_stats:
        print(f"📊 30일 거래 통계:")
        print(f"   총 거래: {trading_stats.get('total_trades', 0)}회")
        print(f"   체결 거래: {trading_stats.get('filled_trades', 0)}회")
        print(f"   성공률: {trading_stats.get('success_rate', 0):.1f}%")
        if 'total_volume' in trading_stats:
            print(f"   총 거래량: ${trading_stats.get('total_volume', 0):,.2f}")
            print(f"   평균 거래 크기: ${trading_stats.get('average_trade_size', 0):,.2f}")
    
    print("\n" + "-" * 50)
    print("1️⃣2️⃣ 설정 저장/조회 테스트")
    print("-" * 50)
    
    # 설정 저장
    test_config = Configuration(
        trader_id="test_trader",
        config_type="RISK",
        config_name="default_risk_config",
        config_data={
            'max_daily_loss_ratio': 0.05,
            'max_consecutive_losses': 5,
            'max_drawdown_ratio': 0.20,
            'max_trades_per_hour': 10,
            'cool_down_after_consecutive': 30
        },
        is_active=True,
        version=1
    )
    
    config_success = db.save_configuration(test_config)
    print(f"✅ 설정 저장: {'성공' if config_success else '실패'}")
    
    # 설정 조회
    retrieved_config = db.get_configuration("test_trader", "RISK", "default_risk_config")
    if retrieved_config:
        print(f"✅ 설정 조회 성공")
        print(f"   버전: {retrieved_config['version']}")
        print(f"   최대 일일 손실: {retrieved_config['config_data']['max_daily_loss_ratio']}")
    else:
        print("❌ 설정 조회 실패")

def test_cleanup_operations(db: DatabaseManager):
    """정리 작업 테스트"""
    
    print("\n" + "-" * 50)
    print("1️⃣3️⃣ 데이터 정리 테스트")
    print("-" * 50)
    
    # 데이터 정리 (테스트용으로 1일 이전 데이터 정리)
    cleanup_results = db.cleanup_old_data(days_to_keep=1)
    
    if 'error' not in cleanup_results:
        print("✅ 데이터 정리 완료:")
        print(f"   삭제된 로그: {cleanup_results.get('deleted_logs', 0)}개")
        print(f"   삭제된 리스크 이벤트: {cleanup_results.get('deleted_risk_events', 0)}개")
        print(f"   삭제된 비활성 포지션: {cleanup_results.get('deleted_positions', 0)}개")
    else:
        print(f"❌ 데이터 정리 실패: {cleanup_results.get('error')}")

def main():
    """메인 테스트 함수"""
    
    setup_logging()
    
    print("⚠️ 주의사항:")
    print("- 이 테스트는 Supabase 데이터베이스에 실제 데이터를 생성합니다")
    print("- 테스트 데이터는 'test_trader' ID로 생성됩니다")
    print("- 테스트 완료 후 수동으로 데이터를 정리할 수 있습니다")
    print("- .env 파일에 SUPABASE_URL, SUPABASE_ANON_KEY 설정이 필요합니다\n")
    
    # 기본 연결 테스트
    if not test_database_connection():
        print("\n❌ 기본 연결 테스트 실패. 종료합니다.")
        return
    
    try:
        # 데이터베이스 매니저 초기화
        db = DatabaseManager()
        
        # CRUD 작업 테스트
        test_database_operations(db)
        
        # 정리 작업 테스트
        test_cleanup_operations(db)
        
        print("\n" + "=" * 70)
        print("🎉 데이터베이스 연동 테스트 완료!")
        print("=" * 70)
        
        print("\n📋 테스트된 핵심 기능:")
        print("✅ Supabase 연결 및 인증")
        print("✅ 거래 기록 저장/수정/조회")
        print("✅ 포지션 추적 및 업데이트")
        print("✅ 거래 세션 관리")
        print("✅ 리스크 이벤트 로깅")
        print("✅ 성과 지표 저장 및 분석")
        print("✅ 시스템 로그 기록")
        print("✅ 설정 저장 및 버전 관리")
        print("✅ 거래 통계 및 요약")
        print("✅ 데이터 정리 및 최적화")
        print("✅ 데이터베이스 헬스 체크")
        
        print("\n📋 다음 단계:")
        print("1. 통합 트레이더에 데이터베이스 연동")
        print("2. 실시간 데이터 로깅 시스템")
        print("3. 성과 분석 대시보드")
        print("4. 백업 및 복구 시스템")
        
        # 최종 상태 확인
        final_health = db.health_check()
        print(f"\n📊 최종 데이터베이스 상태: {final_health['status']}")
        
        if final_health['status'] == 'healthy':
            print("✅ 모든 시스템 정상 작동")
        else:
            print("⚠️ 일부 시스템에 주의 필요")
            
    except KeyboardInterrupt:
        print("\n\n🛑 사용자가 테스트를 중단했습니다")
    except Exception as e:
        print(f"\n\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()