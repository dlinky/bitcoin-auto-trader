#!/usr/bin/env python3
"""
NotificationManager 테스트
파일 위치: tests/test_notification_manager.py
"""

import os
import sys
import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from queue import Queue
from dotenv import load_dotenv

# 루트 디렉토리를 Python 경로에 추가
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.core.notification_manager import NotificationManager

class TestNotificationManager:
    """NotificationManager 단위 테스트"""
    
    @pytest.fixture
    def mock_supabase_client(self):
        """Supabase 클라이언트 모킹"""
        mock_client = Mock()
        
        # get_active_traders 모킹
        mock_client.get_active_traders.return_value = [
            {
                'id': 1,
                'name': 'TEST_BTC_Trader',
                'symbol': 'BTCUSDT',
                'total_pnl': 123.45
            }
        ]
        
        # DB 테이블 접근 모킹
        mock_table = Mock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.lt.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = Mock(data=[], count=0)
        
        mock_client.client.table.return_value = mock_table
        
        return mock_client
    
    @pytest.fixture
    def mock_slack_client(self):
        """Slack 클라이언트 모킹"""
        with patch('src.core.notification_manager.SlackClient') as mock_class:
            mock_instance = Mock()
            mock_instance.send_error_alert.return_value = True
            mock_instance.send_daily_report.return_value = True
            mock_instance.send_system_status.return_value = True
            mock_class.return_value = mock_instance
            yield mock_instance
    
    def test_notification_manager_init(self, mock_supabase_client):
        """NotificationManager 초기화 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        assert nm.db_client == mock_supabase_client
        assert nm.slack_client is None
        assert not nm.is_running
        assert nm.daily_report_time == "07:00"
        assert nm.last_report_date is None
        assert isinstance(nm.notification_queue, Queue)
        assert isinstance(nm.error_throttle, dict)
    
    def test_initialize_slack_success(self, mock_supabase_client, mock_slack_client):
        """Slack 클라이언트 초기화 성공 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        result = nm.initialize_slack()
        
        assert result is True
        assert nm.slack_client is not None
    
    @patch('src.core.notification_manager.SlackClient')
    def test_initialize_slack_failure(self, mock_slack_class, mock_supabase_client):
        """Slack 클라이언트 초기화 실패 테스트"""
        # SlackClient 초기화 시 예외 발생
        mock_slack_class.side_effect = Exception("Slack 연결 실패")
        
        nm = NotificationManager(mock_supabase_client)
        result = nm.initialize_slack()
        
        assert result is False
        assert nm.slack_client is None
    
    def test_start_and_stop(self, mock_supabase_client, mock_slack_client):
        """NotificationManager 시작/정지 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        # 시작 테스트
        result = nm.start()
        assert result is True
        assert nm.is_running is True
        assert nm.notification_thread is not None
        assert nm.notification_thread.is_alive()
        
        # 중복 시작 테스트
        result2 = nm.start()
        assert result2 is True  # 이미 실행 중이지만 성공 반환
        
        # 정지 테스트
        nm.stop()
        assert nm.is_running is False
    
    def test_send_error_alert(self, mock_supabase_client):
        """에러 알림 전송 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        result = nm.send_error_alert(
            error_message="테스트 에러",
            module_name="test_module",
            level="ERROR",
            additional_info={"key": "value"}
        )
        
        assert result is True
        assert nm.notification_queue.qsize() == 1
        
        # 큐에서 알림 확인
        notification = nm.notification_queue.get()
        assert notification['type'] == 'error'
        assert notification['error_message'] == "테스트 에러"
        assert notification['module_name'] == "test_module"
        assert notification['level'] == "ERROR"
        assert notification['additional_info'] == {"key": "value"}
    
    def test_error_throttling(self, mock_supabase_client):
        """에러 알림 스팸 방지 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        # 첫 번째 에러 알림
        result1 = nm.send_error_alert("동일한 에러", "test_module", "ERROR")
        assert result1 is True
        assert nm.notification_queue.qsize() == 1
        
        # 동일한 에러 알림 (5분 내 - 차단되어야 함)
        result2 = nm.send_error_alert("동일한 에러", "test_module", "ERROR")
        assert result2 is False
        assert nm.notification_queue.qsize() == 1  # 큐 크기 변화 없음
        
        # throttle=False로 강제 전송
        result3 = nm.send_error_alert("동일한 에러", "test_module", "ERROR", throttle=False)
        assert result3 is True
        assert nm.notification_queue.qsize() == 2
    
    def test_send_daily_report(self, mock_supabase_client):
        """일일 리포트 전송 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        result = nm.send_daily_report(force=True)
        
        assert result is True
        assert nm.notification_queue.qsize() == 1
        
        # 큐에서 알림 확인
        notification = nm.notification_queue.get()
        assert notification['type'] == 'daily_report'
        assert notification['force'] is True
    
    def test_send_system_status(self, mock_supabase_client):
        """시스템 상태 전송 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        status_data = {
            'system_status': 'running',
            'active_traders': 2
        }
        
        result = nm.send_system_status(status_data)
        
        assert result is True
        assert nm.notification_queue.qsize() == 1
        
        # 큐에서 알림 확인
        notification = nm.notification_queue.get()
        assert notification['type'] == 'system_status'
        assert notification['status_data'] == status_data
    
    def test_generate_daily_report_data(self, mock_supabase_client):
        """일일 리포트 데이터 생성 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        # _get_trader_trades_by_date 모킹
        nm._get_trader_trades_by_date = Mock(return_value=[
            {'realized_pnl': 50.0},
            {'realized_pnl': -20.0},
            {'realized_pnl': 30.0}
        ])
        
        report_data = nm._generate_daily_report_data()
        
        assert 'date' in report_data
        assert 'traders' in report_data
        assert 'total_pnl' in report_data
        assert 'total_trades' in report_data
        
        assert len(report_data['traders']) == 1
        assert report_data['traders'][0]['name'] == 'TEST_BTC_Trader'
        assert report_data['traders'][0]['trades_count'] == 3
        assert report_data['traders'][0]['success_rate'] == 66.7  # 2/3 * 100
    
    def test_generate_system_status_data(self, mock_supabase_client):
        """시스템 상태 데이터 생성 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        # 메서드 모킹
        nm._get_last_trade_time = Mock(return_value='2025-01-15 14:30:00')
        nm._get_today_error_count = Mock(return_value=2)
        
        status_data = nm._generate_system_status_data()
        
        assert status_data['system_status'] == 'running'
        assert status_data['active_traders'] == 1
        assert status_data['last_trade'] == '2025-01-15 14:30:00'
        assert status_data['errors_today'] == 2
    
    def test_set_daily_report_time(self, mock_supabase_client):
        """일일 리포트 시간 설정 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        # 올바른 시간 형식
        result = nm.set_daily_report_time("09:30")
        assert result is True
        assert nm.daily_report_time == "09:30"
        
        # 잘못된 시간 형식
        result = nm.set_daily_report_time("25:00")
        assert result is False
        
        result = nm.set_daily_report_time("invalid")
        assert result is False
    
    def test_get_notification_status(self, mock_supabase_client):
        """알림 시스템 상태 조회 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        status = nm.get_notification_status()
        
        assert 'is_running' in status
        assert 'slack_connected' in status
        assert 'queue_size' in status
        assert 'last_report_date' in status
        assert 'daily_report_time' in status
        assert 'error_throttle_count' in status
        
        assert status['is_running'] is False
        assert status['slack_connected'] is False
        assert status['queue_size'] == 0
        assert status['daily_report_time'] == "07:00"


class TestNotificationManagerIntegration:
    """NotificationManager 통합 테스트"""
    
    def setup_method(self):
        """테스트 셋업"""
        # .env 파일 로드
        env_path = project_root / 'config' / '.env'
        if env_path.exists():
            load_dotenv(env_path)
        
        # 실제 환경변수가 설정되어 있는지 확인
        if not os.getenv('SLACK_BOT_TOKEN') or not os.getenv('SLACK_CHANNEL_ID'):
            pytest.skip("실제 Slack 환경변수가 설정되지 않음")
    
    @pytest.fixture
    def mock_supabase_client(self):
        """실제 연동을 위한 Supabase 클라이언트 모킹"""
        mock_client = Mock()
        
        mock_client.get_active_traders.return_value = [
            {
                'id': 1,
                'name': 'TEST_Integration_Trader',
                'symbol': 'BTCUSDT',
                'total_pnl': 87.65
            },
            {
                'id': 2,
                'name': 'TEST_ETH_Trader',
                'symbol': 'ETHUSDT',
                'total_pnl': -23.40
            }
        ]
        
        # DB 조회 모킹 (빈 결과)
        mock_table = Mock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.lt.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = Mock(data=[], count=0)
        
        mock_client.client.table.return_value = mock_table
        
        return mock_client
    
    def test_real_slack_integration(self, mock_supabase_client):
        """실제 Slack과의 통합 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        try:
            # 시작 테스트
            start_result = nm.start()
            assert start_result is True
            assert nm.slack_client is not None
            
            # 에러 알림 테스트
            nm.send_error_alert(
                "통합 테스트 에러 알림",
                "test_notification_manager",
                "WARNING",
                {"test_type": "integration", "timestamp": datetime.now().isoformat()}
            )
            
            # 시스템 상태 테스트
            nm.send_system_status({
                'system_status': 'testing',
                'uptime': '테스트 모드',
                'active_traders': 2,
                'last_trade': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'errors_today': 0
            })
            
            # 일일 리포트 테스트 (강제)
            nm.send_daily_report(force=True)
            
            # 큐 처리를 위해 잠시 대기
            time.sleep(3)
            
            print("✅ 실제 Slack 통합 테스트 성공")
            
        finally:
            # 정리
            nm.stop()
    
    def test_notification_worker_thread(self, mock_supabase_client):
        """알림 처리 스레드 테스트"""
        nm = NotificationManager(mock_supabase_client)
        
        try:
            # 시작
            nm.start()
            
            initial_queue_size = nm.notification_queue.qsize()
            
            # 여러 알림 추가
            nm.send_error_alert("스레드 테스트 에러 1", "test", "ERROR")
            nm.send_error_alert("스레드 테스트 에러 2", "test", "WARNING")
            nm.send_system_status()
            
            # 큐에 알림이 추가되었는지 확인
            assert nm.notification_queue.qsize() > initial_queue_size
            
            # 스레드가 처리할 시간 대기
            time.sleep(5)
            
            # 큐가 처리되었는지 확인 (비어있거나 줄어들었음)
            final_queue_size = nm.notification_queue.qsize()
            assert final_queue_size <= initial_queue_size
            
            print("✅ 알림 처리 스레드 테스트 성공")
            
        finally:
            nm.stop()
    
    @patch('src.core.notification_manager.datetime')
    def test_daily_report_schedule(self, mock_datetime, mock_supabase_client):
        """일일 리포트 스케줄 테스트"""
        # 07:00 시간으로 모킹
        mock_now = datetime(2025, 1, 15, 7, 0, 30)  # 07:00:30
        mock_datetime.now.return_value = mock_now
        mock_datetime.strftime = datetime.strftime  # strftime은 실제 사용
        
        nm = NotificationManager(mock_supabase_client)
        
        try:
            nm.start()
            
            initial_queue_size = nm.notification_queue.qsize()
            
            # _check_daily_report_schedule 직접 호출
            nm._check_daily_report_schedule()
            
            # 일일 리포트가 큐에 추가되었는지 확인
            assert nm.notification_queue.qsize() > initial_queue_size
            assert nm.last_report_date == "2025-01-15"
            
            print("✅ 일일 리포트 스케줄 테스트 성공")
            
        finally:
            nm.stop()


if __name__ == "__main__":
    """
    테스트 실행 방법:
    
    1. 단위 테스트만 실행:
       python -m pytest tests/test_notification_manager.py::TestNotificationManager -v
    
    2. 실제 Slack과 통합 테스트 (환경변수 필요):
       python -m pytest tests/test_notification_manager.py::TestNotificationManagerIntegration -v -s
    
    3. 모든 테스트 실행:
       python -m pytest tests/test_notification_manager.py -v -s
    
    4. 특정 테스트만 실행:
       python tests/test_notification_manager.py
    """
    
    # 간단한 수동 테스트
    print("=== NotificationManager 수동 테스트 ===")
    
    # .env 파일 로드
    env_path = project_root / 'config' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print("✅ .env 파일 로드 완료")
    else:
        print("⚠️  .env 파일이 없습니다")
    
    # 환경변수 확인
    bot_token = os.getenv('SLACK_BOT_TOKEN')
    channel_id = os.getenv('SLACK_CHANNEL_ID')
    
    if not bot_token or not channel_id:
        print("❌ Slack 환경변수가 설정되지 않았습니다.")
        print("단위 테스트만 실행 가능합니다:")
        print("python -m pytest tests/test_notification_manager.py::TestNotificationManager -v")
        sys.exit(1)
    
    try:
        # Mock Supabase 클라이언트 생성
        mock_supabase = Mock()
        mock_supabase.get_active_traders.return_value = [
            {
                'id': 1,
                'name': 'Manual_Test_Trader',
                'symbol': 'BTCUSDT',
                'total_pnl': 42.50
            }
        ]
        
        # 테이블 모킹
        mock_table = Mock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.lt.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = Mock(data=[], count=0)
        mock_supabase.client.table.return_value = mock_table
        
        print("1. NotificationManager 생성 및 시작...")
        nm = NotificationManager(mock_supabase)
        
        if nm.start():
            print("✅ NotificationManager 시작 성공")
        else:
            print("❌ NotificationManager 시작 실패")
            sys.exit(1)
        
        print("2. 상태 확인...")
        status = nm.get_notification_status()
        print(f"   실행 상태: {status['is_running']}")
        print(f"   Slack 연결: {status['slack_connected']}")
        print(f"   큐 크기: {status['queue_size']}")
        
        print("3. 테스트 알림 전송...")
        
        # 에러 알림
        nm.send_error_alert(
            "수동 테스트 에러 알림",
            "manual_test",
            "INFO",
            {"test_time": datetime.now().isoformat()}
        )
        print("   에러 알림 큐 추가됨")
        
        # 시스템 상태
        nm.send_system_status({
            'system_status': 'manual_testing',
            'uptime': '수동 테스트 모드',
            'active_traders': 1,
            'last_trade': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'errors_today': 0
        })
        print("   시스템 상태 큐 추가됨")
        
        # 일일 리포트 (강제)
        nm.send_daily_report(force=True)
        print("   일일 리포트 큐 추가됨")
        
        print("4. 알림 처리 대기 (5초)...")
        time.sleep(5)
        
        final_status = nm.get_notification_status()
        print(f"   처리 후 큐 크기: {final_status['queue_size']}")
        
        print("5. 정리...")
        nm.stop()
        print("✅ NotificationManager 정지 완료")
        
        print("\n=== 수동 테스트 완료 ===")
        print("Slack 채널을 확인해보세요!")
        
    except Exception as e:
        print(f"❌ 수동 테스트 중 에러: {e}")
        sys.exit(1)