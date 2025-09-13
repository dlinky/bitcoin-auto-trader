#!/usr/bin/env python3
"""
Slack 명령어 처리 테스트
파일 위치: tests/test_slack_commands.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from unittest.mock import Mock

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.api.slack_client import SlackClient
from src.core.slack_command_handler import SlackCommandHandler
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
        # Mock Supabase 클라이언트 생성
        mock_supabase = create_mock_supabase()
        
        # Slack 클라이언트 초기화
        slack_client = SlackClient()
        slack_client.setup_command_handler(mock_supabase)
        
        print("✅ 클라이언트 초기화 완료")
        return slack_client, mock_supabase
        
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        return None, None

def create_mock_supabase():
    """테스트용 Mock Supabase 클라이언트"""
    mock_client = Mock()
    
    # get_active_traders 모킹
    mock_client.get_active_traders.return_value = [
        {
            'id': 1,
            'name': 'TEST_BTC_Trader',
            'symbol': 'BTCUSDT',
            'total_pnl': 123.45,
            'is_active': True
        },
        {
            'id': 2,
            'name': 'TEST_ETH_Trader',
            'symbol': 'ETHUSDT', 
            'total_pnl': -45.67,
            'is_active': True
        }
    ]
    
    # DB 테이블 모킹
    mock_table = Mock()
    
    # trades 테이블 모킹 (최근 거래)
    mock_table.select.return_value = mock_table
    mock_table.gte.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.single.return_value = mock_table
    mock_table.update.return_value = mock_table
    
    # 거래 데이터
    mock_table.execute.return_value = Mock(data=[
        {
            'trader_id': 1,
            'traders': {'name': 'TEST_BTC_Trader'},
            'realized_pnl': 50.0,
            'trade_type': 'EXIT',
            'executed_at': '2025-09-13T10:00:00'
        },
        {
            'trader_id': 2,
            'traders': {'name': 'TEST_ETH_Trader'},
            'realized_pnl': -20.0,
            'trade_type': 'EXIT',
            'executed_at': '2025-09-13T09:30:00'
        }
    ])
    
    mock_client.client.table.return_value = mock_table
    
    return mock_client

def test_command_handler():
    """명령어 처리기 단독 테스트"""
    print("\n📋 명령어 처리기 테스트")
    print("=" * 40)
    
    try:
        mock_supabase = create_mock_supabase()
        handler = SlackCommandHandler(mock_supabase)
        
        # 테스트 케이스들
        test_cases = [
            "/status",
            "status",
            "/help",
            "/traders",
            "/position BTCUSDT",
            "/pnl today",
            "/pnl week",
            "/stop 1",
            "/start 1", 
            "invalid_command",
            ""
        ]
        
        for test_input in test_cases:
            print(f"\n🧪 테스트: '{test_input}'")
            result = handler.process_command(test_input)
            
            print(f"   ✅ 성공: {result.success}")
            if result.success:
                print(f"   📝 응답: {result.message[:100]}...")
            else:
                print(f"   ❌ 에러: {result.error}")
        
        print("\n✅ 명령어 처리기 테스트 완료")
        
    except Exception as e:
        print(f"❌ 명령어 처리기 테스트 실패: {e}")

def test_slack_integration():
    """Slack 통합 테스트 (실제 메시지 전송)"""
    print("\n📡 Slack 통합 테스트")
    print("=" * 40)
    
    slack_client, mock_