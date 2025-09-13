#!/usr/bin/env python3
"""
Slack 명령어 처리기
파일 위치: src/core/slack_command_handler.py
"""

import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class CommandResult:
    """명령어 실행 결과"""
    success: bool
    message: str
    data: Optional[Dict] = None
    error: Optional[str] = None

class SlackCommandHandler:
    """Slack 대화형 명령어 처리기"""
    
    def __init__(self, supabase_client, notification_manager=None):
        """
        SlackCommandHandler 초기화
        
        Args:
            supabase_client: SupabaseClient 인스턴스
            notification_manager: NotificationManager 인스턴스 (선택사항)
        """
        self.db_client = supabase_client
        self.notification_manager = notification_manager
        
        # 명령어 매핑
        self.commands = {
            'status': self._handle_status_command,
            'position': self._handle_position_command,
            'pnl': self._handle_pnl_command,
            'stop': self._handle_stop_command,
            'start': self._handle_start_command,
            'help': self._handle_help_command,
            'traders': self._handle_traders_command,
            'report': self._handle_report_command
        }
        
        logger.info("SlackCommandHandler 초기화 완료")
    
    def process_command(self, message_text: str, user_id: str = None) -> CommandResult:
        """
        Slack 메시지에서 명령어 처리
        
        Args:
            message_text: 사용자 메시지
            user_id: 사용자 ID (권한 확인용)
            
        Returns:
            CommandResult 객체
        """
        try:
            # 메시지 정제 (앞뒤 공백 제거, 소문자 변환)
            clean_message = message_text.strip()
            
            # 명령어 파싱
            command, args = self._parse_command(clean_message)
            
            if not command:
                return CommandResult(
                    success=False,
                    message="명령어를 인식할 수 없습니다. `/help`를 입력하여 도움말을 확인하세요.",
                    error="invalid_command"
                )
            
            # 명령어 실행
            if command in self.commands:
                logger.info(f"명령어 실행: {command} (args: {args})")
                return self.commands[command](args, user_id)
            else:
                return CommandResult(
                    success=False,
                    message=f"지원하지 않는 명령어입니다: `{command}`\n`/help`를 입력하여 사용 가능한 명령어를 확인하세요.",
                    error="unsupported_command"
                )
                
        except Exception as e:
            logger.error(f"명령어 처리 중 오류: {e}")
            return CommandResult(
                success=False,
                message="명령어 처리 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _parse_command(self, message: str) -> Tuple[str, List[str]]:
        """
        메시지에서 명령어와 인자 파싱
        
        Args:
            message: 사용자 메시지
            
        Returns:
            (명령어, 인자 리스트) 튜플
        """
        # /command 형식 또는 command 형식 지원
        if message.startswith('/'):
            parts = message[1:].split()
        else:
            parts = message.split()
        
        if not parts:
            return "", []
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return command, args
    
    def _handle_status_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """전체 시스템 상태 조회"""
        try:
            logger.info("시스템 상태 명령어 처리")
            
            # 활성 트레이더 조회
            active_traders = self.db_client.get_active_traders()
            
            # 시스템 상태 정보 수집
            status_info = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'active_traders': len(active_traders),
                'notification_manager_status': 'N/A',
                'database_status': 'Connected'
            }
            
            # NotificationManager 상태 확인
            if self.notification_manager:
                nm_status = self.notification_manager.get_notification_status()
                status_info['notification_manager_status'] = 'Running' if nm_status['is_running'] else 'Stopped'
                status_info['queue_size'] = nm_status['queue_size']
                status_info['last_report'] = nm_status['last_report_date']
            
            # 최근 거래 정보
            recent_trades = self._get_recent_trades_summary()
            status_info.update(recent_trades)
            
            # 응답 메시지 구성
            message = f"""🤖 **시스템 상태 리포트**

⏰ **조회 시간**: {status_info['timestamp']}

📊 **트레이더 현황**
• 활성 트레이더: {status_info['active_traders']}개

🔔 **알림 시스템**
• 상태: {status_info['notification_manager_status']}
• 대기열: {status_info.get('queue_size', 0)}개"""

            if status_info.get('last_report'):
                message += f"\n• 마지막 리포트: {status_info['last_report']}"

            message += f"""

💰 **최근 거래** (24시간)
• 총 거래: {status_info.get('recent_trades_count', 0)}회
• 총 손익: ${status_info.get('recent_total_pnl', 0):.2f}

🔗 **연결 상태**
• 데이터베이스: {status_info['database_status']}"""
            
            return CommandResult(
                success=True,
                message=message,
                data=status_info
            )
            
        except Exception as e:
            logger.error(f"상태 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="시스템 상태를 조회하는 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _handle_position_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """포지션 조회 명령어"""
        try:
            # 심볼 인자 확인
            if not args:
                return CommandResult(
                    success=False,
                    message="사용법: `/position <심볼>`\n예: `/position BTCUSDT`",
                    error="missing_symbol"
                )
            
            symbol = args[0].upper()
            logger.info(f"포지션 조회: {symbol}")
            
            # 해당 심볼의 트레이더 및 포지션 조회
            positions = self._get_positions_by_symbol(symbol)
            
            if not positions:
                return CommandResult(
                    success=True,
                    message=f"📊 **{symbol} 포지션 현황**\n\n현재 {symbol}에 대한 활성 포지션이 없습니다.",
                    data={'symbol': symbol, 'positions': []}
                )
            
            # 응답 메시지 구성
            message = f"📊 **{symbol} 포지션 현황**\n\n"
            total_pnl = 0.0
            
            for pos in positions:
                pnl = pos.get('unrealized_pnl', 0) or 0
                total_pnl += pnl
                
                pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
                
                message += f"{pnl_emoji} **{pos['trader_name']}**\n"
                message += f"• 방향: {pos['side']}\n"
                message += f"• 크기: {pos['size']}\n"
                message += f"• 진입가: ${pos['entry_price']:.4f}\n"
                message += f"• 미실현 PnL: ${pnl:.2f}\n\n"
            
            message += f"💰 **총 미실현 PnL**: ${total_pnl:.2f}"
            
            return CommandResult(
                success=True,
                message=message,
                data={'symbol': symbol, 'positions': positions, 'total_pnl': total_pnl}
            )
            
        except Exception as e:
            logger.error(f"포지션 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="포지션 정보를 조회하는 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _handle_pnl_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """수익률 조회 명령어"""
        try:
            # 기간 파라미터 처리
            period = args[0] if args else 'today'
            period = period.lower()
            
            logger.info(f"수익률 조회: {period}")
            
            # 기간별 데이터 조회
            if period in ['today', '오늘']:
                start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = "오늘"
            elif period in ['week', '주간', '1w']:
                start_date = datetime.now() - timedelta(days=7)
                period_name = "최근 7일"
            elif period in ['month', '월간', '1m']:
                start_date = datetime.now() - timedelta(days=30)
                period_name = "최근 30일"
            else:
                return CommandResult(
                    success=False,
                    message="사용법: `/pnl [기간]`\n지원 기간: today, week, month\n예: `/pnl today`",
                    error="invalid_period"
                )
            
            # PnL 데이터 조회
            pnl_data = self._get_pnl_by_period(start_date)
            
            # 응답 메시지 구성
            total_pnl = pnl_data.get('total_pnl', 0)
            total_trades = pnl_data.get('total_trades', 0)
            traders_pnl = pnl_data.get('traders', [])
            
            pnl_emoji = "📈" if total_pnl > 0 else "📉" if total_pnl < 0 else "➖"
            
            message = f"{pnl_emoji} **{period_name} 수익률 현황**\n\n"
            message += f"💰 **총 손익**: ${total_pnl:.2f}\n"
            message += f"📊 **총 거래**: {total_trades}회\n\n"
            
            if traders_pnl:
                message += "**트레이더별 상세:**\n"
                for trader in traders_pnl:
                    t_pnl = trader.get('pnl', 0)
                    t_emoji = "🟢" if t_pnl > 0 else "🔴" if t_pnl < 0 else "⚪"
                    message += f"{t_emoji} {trader['name']}: ${t_pnl:.2f} ({trader['trades']}회)\n"
            else:
                message += "_해당 기간에 거래 내역이 없습니다._"
            
            return CommandResult(
                success=True,
                message=message,
                data=pnl_data
            )
            
        except Exception as e:
            logger.error(f"PnL 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="수익률 정보를 조회하는 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _handle_stop_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """트레이더 정지 명령어"""
        try:
            if not args:
                return CommandResult(
                    success=False,
                    message="사용법: `/stop <트레이더ID 또는 이름>`\n예: `/stop 1` 또는 `/stop BTC_Trader`",
                    error="missing_trader"
                )
            
            trader_identifier = args[0]
            logger.info(f"트레이더 정지 요청: {trader_identifier}")
            
            # 트레이더 조회
            trader = self._find_trader(trader_identifier)
            if not trader:
                return CommandResult(
                    success=False,
                    message=f"트레이더를 찾을 수 없습니다: {trader_identifier}\n`/traders` 명령어로 활성 트레이더를 확인하세요.",
                    error="trader_not_found"
                )
            
            # 트레이더 비활성화
            success = self._deactivate_trader(trader['id'])
            
            if success:
                message = f"✅ **트레이더 정지 완료**\n\n"
                message += f"• 트레이더: {trader['name']}\n"
                message += f"• 심볼: {trader['symbol']}\n"
                message += f"• 정지 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                message += "_현재 포지션은 유지되며, 새로운 거래만 중단됩니다._"
                
                return CommandResult(
                    success=True,
                    message=message,
                    data={'trader': trader, 'action': 'stopped'}
                )
            else:
                return CommandResult(
                    success=False,
                    message="트레이더 정지 중 오류가 발생했습니다.",
                    error="stop_failed"
                )
                
        except Exception as e:
            logger.error(f"정지 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="트레이더 정지 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _handle_start_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """트레이더 시작 명령어"""
        try:
            if not args:
                return CommandResult(
                    success=False,
                    message="사용법: `/start <트레이더ID 또는 이름>`\n예: `/start 1` 또는 `/start BTC_Trader`",
                    error="missing_trader"
                )
            
            trader_identifier = args[0]
            logger.info(f"트레이더 시작 요청: {trader_identifier}")
            
            # 트레이더 조회 (비활성 트레이더도 포함)
            trader = self._find_trader(trader_identifier, include_inactive=True)
            if not trader:
                return CommandResult(
                    success=False,
                    message=f"트레이더를 찾을 수 없습니다: {trader_identifier}",
                    error="trader_not_found"
                )
            
            # 이미 활성화된 경우
            if trader.get('is_active', False):
                return CommandResult(
                    success=True,
                    message=f"ℹ️ **{trader['name']}**는 이미 활성화되어 있습니다.",
                    data={'trader': trader, 'action': 'already_active'}
                )
            
            # 트레이더 활성화
            success = self._activate_trader(trader['id'])
            
            if success:
                message = f"✅ **트레이더 시작 완료**\n\n"
                message += f"• 트레이더: {trader['name']}\n"
                message += f"• 심볼: {trader['symbol']}\n"
                message += f"• 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                message += "_다음 스케줄부터 자동 거래를 시작합니다._"
                
                return CommandResult(
                    success=True,
                    message=message,
                    data={'trader': trader, 'action': 'started'}
                )
            else:
                return CommandResult(
                    success=False,
                    message="트레이더 시작 중 오류가 발생했습니다.",
                    error="start_failed"
                )
                
        except Exception as e:
            logger.error(f"시작 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="트레이더 시작 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _handle_traders_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """트레이더 목록 조회 명령어"""
        try:
            logger.info("트레이더 목록 조회")
            
            # 모든 트레이더 조회 (활성/비활성 모두)
            all_traders = self._get_all_traders()
            
            if not all_traders:
                return CommandResult(
                    success=True,
                    message="📋 **트레이더 목록**\n\n등록된 트레이더가 없습니다.",
                    data={'traders': []}
                )
            
            # 활성/비활성으로 분류
            active_traders = [t for t in all_traders if t.get('is_active', False)]
            inactive_traders = [t for t in all_traders if not t.get('is_active', False)]
            
            message = "📋 **트레이더 목록**\n\n"
            
            # 활성 트레이더
            if active_traders:
                message += "✅ **활성 트레이더**\n"
                for trader in active_traders:
                    pnl = trader.get('total_pnl', 0) or 0
                    pnl_str = f"${pnl:.2f}" if pnl != 0 else "$0.00"
                    message += f"• #{trader['id']} {trader['name']} ({trader['symbol']}) - PnL: {pnl_str}\n"
                message += "\n"
            
            # 비활성 트레이더
            if inactive_traders:
                message += "⏸️ **비활성 트레이더**\n"
                for trader in inactive_traders:
                    pnl = trader.get('total_pnl', 0) or 0
                    pnl_str = f"${pnl:.2f}" if pnl != 0 else "$0.00"
                    message += f"• #{trader['id']} {trader['name']} ({trader['symbol']}) - PnL: {pnl_str}\n"
            
            message += f"\n**총합**: {len(all_traders)}개 (활성: {len(active_traders)}, 비활성: {len(inactive_traders)})"
            
            return CommandResult(
                success=True,
                message=message,
                data={'traders': all_traders, 'active_count': len(active_traders), 'inactive_count': len(inactive_traders)}
            )
            
        except Exception as e:
            logger.error(f"트레이더 목록 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="트레이더 목록을 조회하는 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _handle_report_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """리포트 강제 전송 명령어"""
        try:
            logger.info("리포트 강제 전송 요청")
            
            if not self.notification_manager:
                return CommandResult(
                    success=False,
                    message="알림 관리자가 설정되지 않아 리포트를 전송할 수 없습니다.",
                    error="notification_manager_not_available"
                )
            
            # 리포트 전송
            success = self.notification_manager.send_daily_report(force=True)
            
            if success:
                return CommandResult(
                    success=True,
                    message="📊 일일 리포트를 전송했습니다.\n잠시 후 채널에서 확인하세요.",
                    data={'action': 'report_sent'}
                )
            else:
                return CommandResult(
                    success=False,
                    message="리포트 전송 중 오류가 발생했습니다.",
                    error="report_send_failed"
                )
                
        except Exception as e:
            logger.error(f"리포트 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="리포트 전송 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    def _handle_help_command(self, args: List[str], user_id: str = None) -> CommandResult:
        """도움말 명령어"""
        try:
            message = """🤖 **암호화폐 자동매매 봇 명령어**

**📊 조회 명령어**
• `/status` - 전체 시스템 상태 확인
• `/traders` - 모든 트레이더 목록 조회
• `/position <심볼>` - 특정 심볼 포지션 조회
• `/pnl [기간]` - 수익률 조회 (today/week/month)

**⚡ 제어 명령어**
• `/stop <트레이더ID>` - 트레이더 정지
• `/start <트레이더ID>` - 트레이더 시작
• `/report` - 일일 리포트 강제 전송

**💡 사용 예시**
```
/status
/position BTCUSDT
/pnl today
/stop 1
/traders
```

**ℹ️ 참고사항**
• 트레이더ID는 `/traders` 명령어로 확인 가능
• 기간은 today, week, month 지원
• 모든 명령어는 `/` 없이도 사용 가능"""
            
            return CommandResult(
                success=True,
                message=message,
                data={'commands': list(self.commands.keys())}
            )
            
        except Exception as e:
            logger.error(f"도움말 명령어 처리 실패: {e}")
            return CommandResult(
                success=False,
                message="도움말을 불러오는 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    # ===== 유틸리티 메서드들 =====
    
    def _get_recent_trades_summary(self) -> Dict:
        """최근 24시간 거래 요약"""
        try:
            since = datetime.now() - timedelta(hours=24)
            
            response = self.db_client.client.table('trades').select('*').gte(
                'executed_at', since.isoformat()
            ).execute()
            
            trades = response.data or []
            
            # 실현 손익만 계산 (EXIT 거래)
            exit_trades = [t for t in trades if t.get('trade_type') == 'EXIT']
            total_pnl = sum(float(t.get('realized_pnl', 0) or 0) for t in exit_trades)
            
            return {
                'recent_trades_count': len(trades),
                'recent_total_pnl': total_pnl
            }
            
        except Exception as e:
            logger.error(f"최근 거래 요약 조회 실패: {e}")
            return {'recent_trades_count': 0, 'recent_total_pnl': 0}
    
    def _get_positions_by_symbol(self, symbol: str) -> List[Dict]:
        """심볼별 포지션 조회"""
        try:
            # 활성 포지션 조회
            response = self.db_client.client.table('positions').select(
                'traders.name, *'
            ).eq('symbol', symbol).eq('is_open', True).execute()
            
            positions = []
            for pos in response.data or []:
                positions.append({
                    'trader_name': pos.get('traders', {}).get('name', 'Unknown'),
                    'side': pos.get('side'),
                    'size': pos.get('size'),
                    'entry_price': pos.get('entry_price'),
                    'unrealized_pnl': pos.get('unrealized_pnl', 0)
                })
            
            return positions
            
        except Exception as e:
            logger.error(f"포지션 조회 실패 ({symbol}): {e}")
            return []
    
    def _get_pnl_by_period(self, start_date: datetime) -> Dict:
        """기간별 PnL 조회"""
        try:
            # 해당 기간의 거래 내역 조회
            response = self.db_client.client.table('trades').select(
                'trader_id, traders.name, realized_pnl, trade_type'
            ).gte('executed_at', start_date.isoformat()).execute()
            
            trades = response.data or []
            exit_trades = [t for t in trades if t.get('trade_type') == 'EXIT']
            
            # 트레이더별 PnL 계산
            trader_pnl = {}
            total_pnl = 0
            
            for trade in exit_trades:
                trader_id = trade.get('trader_id')
                trader_name = trade.get('traders', {}).get('name', f'Trader_{trader_id}')
                pnl = float(trade.get('realized_pnl', 0) or 0)
                
                if trader_id not in trader_pnl:
                    trader_pnl[trader_id] = {
                        'name': trader_name,
                        'pnl': 0,
                        'trades': 0
                    }
                
                trader_pnl[trader_id]['pnl'] += pnl
                trader_pnl[trader_id]['trades'] += 1
                total_pnl += pnl
            
            return {
                'total_pnl': total_pnl,
                'total_trades': len(trades),
                'traders': list(trader_pnl.values())
            }
            
        except Exception as e:
            logger.error(f"기간별 PnL 조회 실패: {e}")
            return {'total_pnl': 0, 'total_trades': 0, 'traders': []}
    
    def _find_trader(self, identifier: str, include_inactive: bool = False) -> Optional[Dict]:
        """트레이더 검색 (ID 또는 이름)"""
        try:
            # ID로 검색 시도
            if identifier.isdigit():
                response = self.db_client.client.table('traders').select('*').eq(
                    'id', int(identifier)
                ).single().execute()
                
                if response.data:
                    trader = response.data
                    if include_inactive or trader.get('is_active', False):
                        return trader
            
            # 이름으로 검색
            response = self.db_client.client.table('traders').select('*').eq(
                'name', identifier
            ).single().execute()
            
            if response.data:
                trader = response.data
                if include_inactive or trader.get('is_active', False):
                    return trader
            
            return None
            
        except Exception as e:
            logger.error(f"트레이더 검색 실패 ({identifier}): {e}")
            return None
    
    def _get_all_traders(self) -> List[Dict]:
        """모든 트레이더 조회"""
        try:
            response = self.db_client.client.table('traders').select('*').order(
                'id', desc=False
            ).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"트레이더 목록 조회 실패: {e}")
            return []
    
    def _deactivate_trader(self, trader_id: int) -> bool:
        """트레이더 비활성화"""
        try:
            response = self.db_client.client.table('traders').update({
                'is_active': False,
                'updated_at': datetime.now().isoformat()
            }).eq('id', trader_id).execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            logger.error(f"트레이더 비활성화 실패 (ID: {trader_id}): {e}")
            return False
    
    def _activate_trader(self, trader_id: int) -> bool:
        """트레이더 활성화"""
        try:
            response = self.db_client.client.table('traders').update({
                'is_active': True,
                'updated_at': datetime.now().isoformat()
            }).eq('id', trader_id).execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            logger.error(f"트레이더 활성화 실패 (ID: {trader_id}): {e}")
            return False