#!/usr/bin/env python3
"""
SlackClient 테스트
파일 위치: tests/test_slack_client.py
"""

import os
import sys
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from dotenv import load_dotenv

# 루트 디렉토리를 Python 경로에 추가
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.api.slack_client import SlackClient

class TestSlackClient:
    """SlackClient 테스트 클래스"""
    
    @pytest.fixture
    def mock_env_vars(self, monkeypatch):
        """환경변수 모킹"""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token-12345")
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C1234567890")
    
    @pytest.fixture
    def mock_successful_response(self):
        """성공적인 API 응답 모킹"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "user": "test-bot"}
        return mock_response
    
    @pytest.fixture
    def mock_failed_response(self):
        """실패한 API 응답 모킹"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": False, "error": "invalid_token"}
        return mock_response
    
    @patch('api.slack_client.requests.post')
    def test_slack_client_initialization_success(self, mock_post, mock_env_vars, mock_successful_response):
        """SlackClient 성공적 초기화 테스트"""
        mock_post.return_value = mock_successful_response
        
        client = SlackClient()
        
        assert client.bot_token == "xoxb-test-token-12345"
        assert client.channel_id == "C1234567890"
        assert mock_post.called
    
    @patch('api.slack_client.requests.post')
    def test_slack_client_initialization_failure(self, mock_post, mock_env_vars, mock_failed_response):
        """SlackClient 초기화 실패 테스트"""
        mock_post.return_value = mock_failed_response
        
        with pytest.raises(Exception, match="Slack API 연결 테스트 실패"):
            SlackClient()
    
    def test_slack_client_no_token_error(self, monkeypatch):
        """토큰 없을 때 에러 테스트"""
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        
        with pytest.raises(ValueError, match="SLACK_BOT_TOKEN이 필요합니다"):
            SlackClient()
    
    @patch('api.slack_client.requests.post')
    def test_send_message_success(self, mock_post, mock_env_vars):
        """메시지 전송 성공 테스트"""
        # 초기화용 모킹
        init_response = Mock()
        init_response.status_code = 200
        init_response.json.return_value = {"ok": True, "user": "test-bot"}
        
        # 메시지 전송용 모킹
        send_response = Mock()
        send_response.status_code = 200
        send_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        
        mock_post.side_effect = [init_response, send_response]
        
        client = SlackClient()
        result = client.send_message("테스트 메시지")
        
        assert result is True
        assert mock_post.call_count == 2
        
        # 두 번째 호출 (메시지 전송) 확인
        args, kwargs = mock_post.call_args_list[1]
        assert "chat.postMessage" in args[0]
        assert kwargs['json']['text'] == "테스트 메시지"
        assert kwargs['json']['channel'] == "C1234567890"
    
    @patch('api.slack_client.requests.post')
    def test_send_message_failure(self, mock_post, mock_env_vars):
        """메시지 전송 실패 테스트"""
        init_response = Mock()
        init_response.status_code = 200
        init_response.json.return_value = {"ok": True, "user": "test-bot"}
        
        send_response = Mock()
        send_response.status_code = 200
        send_response.json.return_value = {"ok": False, "error": "channel_not_found"}
        
        mock_post.side_effect = [init_response, send_response]
        
        client = SlackClient()
        result = client.send_message("테스트 메시지")
        
        assert result is False
    
    @patch('api.slack_client.requests.post')
    def test_send_error_alert(self, mock_post, mock_env_vars):
        """에러 알림 전송 테스트"""
        init_response = Mock()
        init_response.status_code = 200
        init_response.json.return_value = {"ok": True, "user": "test-bot"}
        
        send_response = Mock()
        send_response.status_code = 200
        send_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        
        mock_post.side_effect = [init_response, send_response]
        
        client = SlackClient()
        result = client.send_error_alert(
            error_message="테스트 에러 메시지",
            module_name="test_module",
            level="ERROR",
            additional_info={"key": "value"}
        )
        
        assert result is True
        
        # 메시지 전송 호출 확인
        args, kwargs = mock_post.call_args_list[1]
        assert "chat.postMessage" in args[0]
        assert "blocks" in kwargs['json']
        assert "❌" in kwargs['json']['text']  # ERROR 이모지 확인
    
    @patch('api.slack_client.requests.post')
    def test_send_daily_report(self, mock_post, mock_env_vars):
        """일일 리포트 전송 테스트"""
        init_response = Mock()
        init_response.status_code = 200
        init_response.json.return_value = {"ok": True, "user": "test-bot"}
        
        send_response = Mock()
        send_response.status_code = 200
        send_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        
        mock_post.side_effect = [init_response, send_response]
        
        client = SlackClient()
        
        report_data = {
            'date': '2025-01-15',
            'traders': [
                {
                    'name': 'BTC_MACD_Trader_1',
                    'symbol': 'BTCUSDT',
                    'total_pnl': 123.45,
                    'trades_count': 5,
                    'success_rate': 60.0
                }
            ],
            'total_pnl': 123.45,
            'total_trades': 5
        }
        
        result = client.send_daily_report(report_data)
        
        assert result is True
        
        # 메시지 전송 호출 확인
        args, kwargs = mock_post.call_args_list[1]
        assert "chat.postMessage" in args[0]
        assert "blocks" in kwargs['json']
        assert "📈" in kwargs['json']['text']  # 수익 이모지 확인
    
    @patch('api.slack_client.requests.post')
    def test_send_system_status(self, mock_post, mock_env_vars):
        """시스템 상태 전송 테스트"""
        init_response = Mock()
        init_response.status_code = 200
        init_response.json.return_value = {"ok": True, "user": "test-bot"}
        
        send_response = Mock()
        send_response.status_code = 200
        send_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        
        mock_post.side_effect = [init_response, send_response]
        
        client = SlackClient()
        
        status_data = {
            'system_status': 'running',
            'uptime': '2 days 3 hours',
            'active_traders': 1,
            'last_trade': '2025-01-15 14:30:00',
            'errors_today': 2
        }
        
        result = client.send_system_status(status_data)
        
        assert result is True
        
        # 메시지 전송 호출 확인
        args, kwargs = mock_post.call_args_list[1]
        assert "chat.postMessage" in args[0]
        assert "blocks" in kwargs['json']
        assert "✅" in kwargs['json']['text']  # running 상태 이모지 확인


# 실제 Slack과의 통합 테스트 (수동 실행용)
class TestSlackClientIntegration:
    """실제 Slack API와의 통합 테스트"""
    
    def setup_method(self):
        """테스트 셋업"""
        # 실제 환경변수가 설정되어 있는지 확인
        if not os.getenv('SLACK_BOT_TOKEN') or not os.getenv('SLACK_CHANNEL_ID'):
            pytest.skip("실제 Slack 환경변수가 설정되지 않음")
    
    def test_real_connection(self):
        """실제 Slack 연결 테스트"""
        try:
            client = SlackClient()
            assert client is not None
            print("✅ Slack 연결 성공")
        except Exception as e:
            pytest.fail(f"Slack 연결 실패: {e}")
    
    def test_real_simple_message(self):
        """실제 간단한 메시지 전송 테스트"""
        try:
            client = SlackClient()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"🧪 SlackClient 테스트 메시지 - {timestamp}"
            
            result = client.send_simple_message(message, use_emoji=False)
            assert result is True
            print("✅ 테스트 메시지 전송 성공")
        except Exception as e:
            pytest.fail(f"테스트 메시지 전송 실패: {e}")
    
    def test_real_error_alert(self):
        """실제 에러 알림 전송 테스트"""
        try:
            client = SlackClient()
            
            result = client.send_error_alert(
                error_message="이것은 테스트 에러 메시지입니다.",
                module_name="test_slack_client",
                level="WARNING",
                additional_info={
                    "test_parameter": "test_value",
                    "timestamp": datetime.now().isoformat()
                }
            )
            assert result is True
            print("✅ 에러 알림 전송 성공")
        except Exception as e:
            pytest.fail(f"에러 알림 전송 실패: {e}")
    
    def test_real_daily_report(self):
        """실제 일일 리포트 전송 테스트"""
        try:
            client = SlackClient()
            
            test_report = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'traders': [
                    {
                        'name': 'TEST_BTC_Trader',
                        'symbol': 'BTCUSDT',
                        'total_pnl': 50.25,
                        'trades_count': 3,
                        'success_rate': 66.7
                    },
                    {
                        'name': 'TEST_ETH_Trader',
                        'symbol': 'ETHUSDT',
                        'total_pnl': -15.75,
                        'trades_count': 2,
                        'success_rate': 50.0
                    }
                ],
                'total_pnl': 34.50,
                'total_trades': 5
            }
            
            result = client.send_daily_report(test_report)
            assert result is True
            print("✅ 일일 리포트 전송 성공")
        except Exception as e:
            pytest.fail(f"일일 리포트 전송 실패: {e}")
    
    def test_real_system_status(self):
        """실제 시스템 상태 전송 테스트"""
        try:
            client = SlackClient()
            
            test_status = {
                'system_status': 'running',
                'uptime': '1 hour 30 minutes',
                'active_traders': 2,
                'last_trade': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'errors_today': 1
            }
            
            result = client.send_system_status(test_status)
            assert result is True
            print("✅ 시스템 상태 전송 성공")
        except Exception as e:
            pytest.fail(f"시스템 상태 전송 실패: {e}")


if __name__ == "__main__":
    """
    테스트 실행 방법:
    
    1. 단위 테스트만 실행:
       python -m pytest tests/test_slack_client.py::TestSlackClient -v
    
    2. 실제 Slack과 통합 테스트 (환경변수 필요):
       python -m pytest tests/test_slack_client.py::TestSlackClientIntegration -v -s
    
    3. 모든 테스트 실행:
       python -m pytest tests/test_slack_client.py -v -s
    
    4. 특정 테스트만 실행:
       python tests/test_slack_client.py
    """
    
    # 간단한 수동 테스트
    print("=== SlackClient 수동 테스트 ===")

    # .env 파일 로드 (이 부분이 중요!)
    env_path = project_root / 'config' / '.env'
    print(f"📄 .env 파일 경로: {env_path}")
    
    if env_path.exists():
        load_dotenv(env_path)
        print("✅ .env 파일 로드 완료")
    else:
        print("⚠️  .env 파일이 없습니다")
    
    # 환경변수 확인
    bot_token = os.getenv('SLACK_BOT_TOKEN')
    channel_id = os.getenv('SLACK_CHANNEL_ID')
    print(f"🔑 SLACK_BOT_TOKEN: {'설정됨' if bot_token else '없음'}")
    print(f"📺 SLACK_CHANNEL_ID: {channel_id if channel_id else '없음'}")
    
    if not bot_token or not channel_id:
        print("❌ 환경변수가 설정되지 않았습니다.")
        print("다음 환경변수를 .env 파일에 설정해주세요:")
        print("SLACK_BOT_TOKEN=xoxb-your-token")
        print("SLACK_CHANNEL_ID=C1234567890")
        sys.exit(1)
    
    try:
        # 클라이언트 초기화 테스트
        print("1. SlackClient 초기화 테스트...")
        client = SlackClient()
        print("✅ 초기화 성공")
        
        # 채널 정보 조회 테스트
        print("2. 채널 정보 조회 테스트...")
        channel_info = client.get_channel_info()
        if channel_info:
            print(f"✅ 채널 정보: {channel_info.get('name', 'Unknown')}")
        else:
            print("⚠️  채널 정보 조회 실패")
        
        # 간단한 메시지 전송 테스트
        print("3. 테스트 메시지 전송...")
        test_message = f"🧪 SlackClient 테스트 - {datetime.now().strftime('%H:%M:%S')}"
        if client.send_simple_message(test_message):
            print("✅ 테스트 메시지 전송 성공")
        else:
            print("❌ 테스트 메시지 전송 실패")
        
        print("\n=== 모든 수동 테스트 완료 ===")
        
    except Exception as e:
        print(f"❌ 테스트 중 에러 발생: {e}")
        sys.exit(1)