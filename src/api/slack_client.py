#!/usr/bin/env python3
"""
Slack 클라이언트 모듈
파일 위치: src/api/slack_client.py
"""

import os
import json
import requests
import time
from typing import Dict, Optional, List
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)

class SlackClient:
    """Slack API 연동 클라이언트"""
    
    def __init__(self, bot_token: Optional[str] = None, channel_id: Optional[str] = None):
        """
        Slack 클라이언트 초기화
        
        Args:
            bot_token: Slack Bot Token (xoxb-...)
            channel_id: 기본 채널 ID
        """
        self.bot_token = bot_token or os.getenv('SLACK_BOT_TOKEN')
        self.channel_id = channel_id or os.getenv('SLACK_CHANNEL_ID')
        
        if not self.bot_token:
            raise ValueError("SLACK_BOT_TOKEN이 필요합니다")
        
        self.base_url = "https://slack.com/api"
        self.headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        # 연결 테스트
        if not self._test_connection():
            raise Exception("Slack API 연결 테스트 실패")
        
        logger.info("Slack 클라이언트 초기화 완료")
    
    def _test_connection(self) -> bool:
        """Slack API 연결 테스트"""
        try:
            response = requests.post(
                f"{self.base_url}/auth.test",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    logger.info(f"Slack 연결 성공 - Bot: {data.get('user', 'Unknown')}")
                    return True
                else:
                    logger.error(f"Slack 인증 실패: {data.get('error', 'Unknown error')}")
                    return False
            else:
                logger.error(f"Slack API 호출 실패: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Slack 연결 테스트 중 에러: {e}")
            return False
    
    def send_message(self, text: str, channel: Optional[str] = None, 
                    blocks: Optional[List[Dict]] = None, thread_ts: Optional[str] = None) -> bool:
        """
        Slack 메시지 전송
        
        Args:
            text: 메시지 텍스트
            channel: 채널 ID (미지정시 기본 채널 사용)
            blocks: Slack Block Kit 포맷 (옵션)
            thread_ts: 스레드 타임스탬프 (답글용)
            
        Returns:
            전송 성공 여부
        """
        try:
            target_channel = channel or self.channel_id
            if not target_channel:
                logger.error("채널 ID가 지정되지 않았습니다")
                return False
            
            payload = {
                "channel": target_channel,
                "text": text
            }
            
            if blocks:
                payload["blocks"] = blocks
            
            if thread_ts:
                payload["thread_ts"] = thread_ts
            
            response = requests.post(
                f"{self.base_url}/chat.postMessage",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    logger.debug(f"Slack 메시지 전송 완료: {text[:50]}...")
                    return True
                else:
                    logger.error(f"Slack 메시지 전송 실패: {data.get('error', 'Unknown error')}")
                    return False
            else:
                logger.error(f"Slack API 호출 실패: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Slack 메시지 전송 중 에러: {e}")
            return False
    
    def send_error_alert(self, error_message: str, module_name: str = "Unknown", 
                        level: str = "ERROR", additional_info: Optional[Dict] = None) -> bool:
        """
        에러 알림 전송 (포맷된 메시지)
        
        Args:
            error_message: 에러 메시지
            module_name: 발생 모듈명
            level: 에러 레벨 (ERROR, CRITICAL, WARNING)
            additional_info: 추가 정보
            
        Returns:
            전송 성공 여부
        """
        try:
            # 에러 레벨에 따른 이모지
            level_emojis = {
                "CRITICAL": "🚨",
                "ERROR": "❌", 
                "WARNING": "⚠️"
            }
            
            emoji = level_emojis.get(level.upper(), "⚠️")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 기본 메시지 구성
            message_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{level} 알림*\n*시간:* {timestamp}\n*모듈:* {module_name}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*메시지:*\n```{error_message}```"
                    }
                }
            ]
            
            # 추가 정보가 있는 경우
            if additional_info:
                info_text = json.dumps(additional_info, indent=2, ensure_ascii=False)
                message_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*추가 정보:*\n```{info_text}```"
                    }
                })
            
            # 구분선 추가
            message_blocks.append({"type": "divider"})
            
            fallback_text = f"{emoji} [{level}] {module_name}: {error_message}"
            
            return self.send_message(
                text=fallback_text,
                blocks=message_blocks
            )
            
        except Exception as e:
            logger.error(f"에러 알림 전송 실패: {e}")
            return False
    
    def send_daily_report(self, report_data: Dict) -> bool:
        """
        일일 성과 리포트 전송
        
        Args:
            report_data: 리포트 데이터
            {
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
            
        Returns:
            전송 성공 여부
        """
        try:
            date = report_data.get('date', datetime.now().strftime('%Y-%m-%d'))
            total_pnl = report_data.get('total_pnl', 0.0)
            total_trades = report_data.get('total_trades', 0)
            traders = report_data.get('traders', [])
            
            # PnL에 따른 이모지
            pnl_emoji = "📈" if total_pnl > 0 else "📉" if total_pnl < 0 else "➖"
            
            # 헤더 블록
            message_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{pnl_emoji} 일일 트레이딩 리포트"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*날짜:* {date}\n*총 손익:* ${total_pnl:.2f}\n*총 거래:* {total_trades}회"
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            # 트레이더별 상세 정보
            if traders:
                for trader in traders:
                    trader_pnl = trader.get('total_pnl', 0.0)
                    trader_emoji = "✅" if trader_pnl > 0 else "❌" if trader_pnl < 0 else "➖"
                    
                    success_rate = trader.get('success_rate', 0.0)
                    trades_count = trader.get('trades_count', 0)
                    
                    message_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{trader_emoji} *{trader.get('name', 'Unknown')}*\n"
                                   f"심볼: {trader.get('symbol', 'N/A')}\n"
                                   f"손익: ${trader_pnl:.2f}\n"
                                   f"거래: {trades_count}회 (성공률: {success_rate:.1f}%)"
                        }
                    })
            else:
                message_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "_활성화된 트레이더가 없습니다._"
                    }
                })
            
            # 푸터
            message_blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"리포트 생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            })
            
            fallback_text = f"일일 리포트 ({date}): 총 손익 ${total_pnl:.2f}, 거래 {total_trades}회"
            
            return self.send_message(
                text=fallback_text,
                blocks=message_blocks
            )
            
        except Exception as e:
            logger.error(f"일일 리포트 전송 실패: {e}")
            return False
    
    def send_system_status(self, status_data: Dict) -> bool:
        """
        시스템 상태 전송
        
        Args:
            status_data: 상태 데이터
            {
                'system_status': 'running',  # running, stopped, error
                'uptime': '2 days 3 hours',
                'active_traders': 1,
                'last_trade': '2025-01-15 14:30:00',
                'errors_today': 2
            }
            
        Returns:
            전송 성공 여부
        """
        try:
            system_status = status_data.get('system_status', 'unknown')
            uptime = status_data.get('uptime', 'N/A')
            active_traders = status_data.get('active_traders', 0)
            last_trade = status_data.get('last_trade', 'N/A')
            errors_today = status_data.get('errors_today', 0)
            
            # 상태에 따른 이모지
            status_emojis = {
                'running': '✅',
                'stopped': '⏸️',
                'error': '❌',
                'unknown': '❓'
            }
            
            emoji = status_emojis.get(system_status, '❓')
            
            message_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *시스템 상태*\n"
                               f"*상태:* {system_status.upper()}\n"
                               f"*가동시간:* {uptime}\n"
                               f"*활성 트레이더:* {active_traders}개\n"
                               f"*마지막 거래:* {last_trade}\n"
                               f"*오늘 에러:* {errors_today}건"
                    }
                }
            ]
            
            fallback_text = f"시스템 상태: {system_status.upper()} (활성 트레이더: {active_traders}개)"
            
            return self.send_message(
                text=fallback_text,
                blocks=message_blocks
            )
            
        except Exception as e:
            logger.error(f"시스템 상태 전송 실패: {e}")
            return False
    
    def send_simple_message(self, message: str, use_emoji: bool = True) -> bool:
        """
        간단한 메시지 전송 (명령어 응답용)
        
        Args:
            message: 전송할 메시지
            use_emoji: 이모지 사용 여부
            
        Returns:
            전송 성공 여부
        """
        try:
            if use_emoji:
                message = f"🤖 {message}"
            
            return self.send_message(text=message)
            
        except Exception as e:
            logger.error(f"간단 메시지 전송 실패: {e}")
            return False
    
    def get_channel_info(self, channel_id: Optional[str] = None) -> Optional[Dict]:
        """
        채널 정보 조회 (디버깅용)
        
        Args:
            channel_id: 조회할 채널 ID
            
        Returns:
            채널 정보 딕셔너리
        """
        try:
            target_channel = channel_id or self.channel_id
            if not target_channel:
                logger.error("채널 ID가 없습니다")
                return None
            
            response = requests.post(
                f"{self.base_url}/conversations.info",
                headers=self.headers,
                json={"channel": target_channel},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("channel")
                else:
                    logger.error(f"채널 정보 조회 실패: {data.get('error')}")
                    return None
            else:
                logger.error(f"채널 정보 조회 API 실패: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"채널 정보 조회 중 에러: {e}")
            return None