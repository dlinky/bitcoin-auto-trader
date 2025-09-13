#!/usr/bin/env python3
"""
간단한 Slack 명령어 테스트
파일 위치: test_commands.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from unittest.mock import Mock

# 프로젝트 루트 설정
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.core.slack_command_handler import SlackCommandHandler

def create_mock_supabase():
    """Mock Supabase 클라이언트"""
    mock = Mock()
    
    # 활성 트레이더 목록
    mock.get_active_traders.return_value = [
        {'id': 1, 'name': 'BTC_Trader', 'symbol': 'BTCUSDT', 'total_pnl': 100.50, 'is_active': True},
        {'id': 2, 'name': 'ETH_Trader', 'symbol': 'ETHUSDT', 'total_pnl': -50.25, 'is_active': True}
    ]
    
    # client.table() 체인 Mock 설정
    mock_table = Mock()
    mock_select = Mock()
    mock_query = Mock()
    
    # 쿼리 체인: client.table().select().gte().execute()
    mock_table.select.return_value = mock_select
    mock_select.gte.return_value = mock_query
    mock_select.eq.return_value = mock_query  
    mock_select.order.return_value = mock_query
    mock_select.limit.return_value = mock_query
    mock_select.single.return_value = mock_query
    mock_select.update.return_value = mock_query
    
    # traders 테이블 조회 결과
    def mock_execute():
        result = Mock()
        result.data = [
            {'id': 1, 'name': 'BTC_Trader', 'symbol': 'BTCUSDT', 'total_pnl': 100.50, 'is_active': True},
            {'id': 2, 'name': 'ETH_Trader', 'symbol': 'ETHUSDT', 'total_pnl': -50.25, 'is_active': True}
        ]
        return result
    
    # trades 테이블 조회 결과  
    def mock_execute_trades():
        result = Mock()
        result.data = [
            {'trader_id': 1, 'traders': {'name': 'BTC_Trader'}, 'realized_pnl': 25.0, 'trade_type': 'EXIT'},
            {'trader_id': 2, 'traders': {'name': 'ETH_Trader'}, 'realized_pnl': -10.0, 'trade_type': 'EXIT'}
        ]
        return result
    
    # 기본적으로 traders 테이블 결과 반환
    mock_query.execute.return_value = mock_execute()
    
    # client.table 반환
    mock.client.table.return_value = mock_table
    
    return mock

def test_commands():
    """명령어 테스트"""
    print("Slack 명령어 테스트 시작")
    print("-" * 50)
    
    # Mock 클라이언트 생성
    mock_supabase = create_mock_supabase()
    handler = SlackCommandHandler(mock_supabase)
    
    # 테스트할 명령어들
    commands = [
        "status",
        "/status", 
        "help",
        "traders",
        "position BTCUSDT",
        "pnl today",
        "stop 1",
        "invalid_command"
    ]
    
    for cmd in commands:
        print(f"\n테스트: '{cmd}'")
        result = handler.process_command(cmd)
        
        if result.success:
            print(f"  성공: {result.message[:100]}...")
        else:
            print(f"  실패: {result.error}")
    
    print("\n" + "="*50)
    print("테스트 완료!")

if __name__ == "__main__":
    # 환경변수 로드
    env_file = Path("config/.env")
    if env_file.exists():
        load_dotenv(env_file)
    
    test_commands()