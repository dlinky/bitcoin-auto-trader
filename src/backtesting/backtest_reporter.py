#!/usr/bin/env python3
"""
백테스트 리포터 - 결과를 Slack으로 전송
파일 위치: src/backtesting/backtest_reporter.py
"""

import os
import tempfile
import base64
from datetime import datetime
from typing import Dict, List, Optional

from src.utils.logger import get_logger
from src.api.slack_client import SlackClient
from src.backtesting.backtester import BacktestResult
from src.backtesting.performance_analyzer import PerformanceAnalyzer

logger = get_logger(__name__)

class BacktestReporter:
    """백테스트 결과 리포터"""
    
    def __init__(self, slack_client: Optional[SlackClient] = None):
        """
        리포터 초기화
        
        Args:
            slack_client: SlackClient 인스턴스 (None이면 자동 생성)
        """
        self.slack_client = slack_client
        self.analyzer = PerformanceAnalyzer()
        
        # Slack 클라이언트가 없으면 생성
        if not self.slack_client:
            try:
                self.slack_client = SlackClient()
            except Exception as e:
                logger.warning(f"Slack 클라이언트 초기화 실패: {e}")
                self.slack_client = None
        
        logger.info("BacktestReporter 초기화 완료")
    
    def send_backtest_report(self, result: BacktestResult, 
                           include_charts: bool = True, 
                           channel: Optional[str] = None) -> bool:
        """
        백테스트 결과를 Slack으로 전송
        
        Args:
            result: BacktestResult 객체
            include_charts: 차트 포함 여부
            channel: 전송할 채널 (None이면 기본 채널)
            
        Returns:
            전송 성공 여부
        """
        try:
            if not self.slack_client:
                logger.error("Slack 클라이언트가 없어서 리포트 전송 불가")
                return False
            
            logger.info(f"백테스트 리포트 전송 시작 - {result.strategy_name}")
            
            # 성과 분석 수행
            analysis = self.analyzer.analyze_performance(result)
            
            # 메인 리포트 메시지 생성
            message_blocks = self._create_main_report_blocks(result, analysis)
            
            # 메인 리포트 전송
            success = self.slack_client.send_message(
                text=f"📊 백테스트 결과: {result.strategy_name}",
                blocks=message_blocks,
                channel=channel
            )
            
            if not success:
                logger.error("메인 리포트 전송 실패")
                return False
            
            # 차트 전송 (옵션)
            if include_charts:
                self._send_charts(analysis.get('charts', {}), result, channel)
            
            logger.info("백테스트 리포트 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"백테스트 리포트 전송 실패: {e}")
            return False
    
    def _create_main_report_blocks(self, result: BacktestResult, analysis: Dict) -> List[Dict]:
        """메인 리포트 블록 생성"""
        try:
            basic = analysis.get('basic_metrics', {})
            risk = analysis.get('risk_metrics', {})
            trade = analysis.get('trade_analysis', {})
            monthly = analysis.get('monthly_returns', {})
            
            # 수익률에 따른 이모지
            return_pct = basic.get('total_return_pct', 0)
            emoji = "📈" if return_pct > 0 else "📉" if return_pct < 0 else "➖"
            
            blocks = [
                # 헤더
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} 백테스트 결과 리포트"
                    }
                },
                
                # 기본 정보
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*전략:* {result.strategy_name}"
                        },
                        {
                            "type": "mrkdwn", 
                            "text": f"*심볼:* {result.symbol}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*기간:* {basic.get('duration_days', 0)}일"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*초기자본:* ${result.initial_capital:,.0f}"
                        }
                    ]
                },
                
                {"type": "divider"},
                
                # 수익성 섹션
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📈 수익성*\n"
                               f"• 총 수익률: *{return_pct:.2f}%*\n"
                               f"• 연환산 수익률: {basic.get('annual_return', 0):.2f}%\n"
                               f"• 최종 자본: ${basic.get('final_capital', 0):,.2f}\n"
                               f"• 총 수익: ${basic.get('total_return', 0):,.2f}"
                    }
                },
                
                # 거래 통계 섹션
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*⚡ 거래 통계*\n"
                               f"• 총 거래: {trade.get('total_trades', 0)}회\n"
                               f"• 승률: {trade.get('win_rate', 0):.1f}% ({trade.get('winning_trades', 0)}승 {trade.get('losing_trades', 0)}패)\n"
                               f"• 평균 수익: ${trade.get('avg_win', 0):.2f}\n"
                               f"• 평균 손실: ${trade.get('avg_loss', 0):.2f}\n"
                               f"• Profit Factor: {trade.get('profit_factor', 'N/A')}"
                    }
                },
                
                # 리스크 섹션
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*⚠️ 리스크 지표*\n"
                               f"• 최대 낙폭: {risk.get('max_drawdown_pct', 0):.2f}%\n"
                               f"• 변동성: {risk.get('volatility', 0):.2f}%\n"
                               f"• 샤프 비율: {risk.get('sharpe_ratio', 0):.3f}\n"
                               f"• 칼마 비율: {risk.get('calmar_ratio', 0):.3f}\n"
                               f"• 소르티노 비율: {risk.get('sortino_ratio', 0):.3f}"
                    }
                }
            ]
            
            # 월별 성과가 있으면 추가
            if monthly:
                monthly_text = ""
                for month, ret in list(monthly.get('monthly_returns', {}).items())[-6:]:  # 최근 6개월만
                    emoji_month = "📈" if ret > 0 else "📉" if ret < 0 else "➖"
                    monthly_text += f"• {month}: {emoji_month} {ret:.1f}%\n"
                
                if monthly_text:
                    blocks.extend([
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*📅 최근 월별 성과*\n{monthly_text.rstrip()}"
                            }
                        }
                    ])
            
            # 추가 정보
            blocks.extend([
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"백테스트 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                                   f"데이터 기간: {result.start_date.strftime('%Y-%m-%d')} ~ {result.end_date.strftime('%Y-%m-%d')}"
                        }
                    ]
                }
            ])
            
            return blocks
            
        except Exception as e:
            logger.error(f"리포트 블록 생성 실패: {e}")
            return []
    
    def _send_charts(self, charts: Dict, result: BacktestResult, channel: Optional[str]):
        """차트 이미지들을 Slack으로 전송"""
        try:
            if not charts:
                logger.info("전송할 차트가 없습니다")
                return
            
            # 차트 순서 정의
            chart_order = [
                ('equity_curve', '📈 자본 곡선'),
                ('drawdown', '📉 낙폭 분석'),
                ('trade_analysis', '📊 거래 분석'),
                ('monthly_heatmap', '🗓️ 월별 수익률')
            ]
            
            for chart_key, chart_title in chart_order:
                chart_data = charts.get(chart_key)
                if chart_data:
                    self._send_single_chart(chart_data, chart_title, result, channel)
            
        except Exception as e:
            logger.error(f"차트 전송 실패: {e}")
    
    def _send_single_chart(self, chart_base64: str, title: str, 
                          result: BacktestResult, channel: Optional[str]):
        """개별 차트 전송"""
        try:
            if not chart_base64:
                return
            
            # Base64를 이미지 파일로 변환
            image_data = base64.b64decode(chart_base64)
            
            # 임시 파일 생성
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name
            
            try:
                # Slack 파일 업로드 (현재는 메시지로 대체)
                # 실제 구현에서는 Slack Files API를 사용해야 함
                
                # 차트 정보를 텍스트 메시지로 전송 (임시)
                self.slack_client.send_message(
                    text=f"{title} - {result.strategy_name}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{title}*\n차트가 생성되었습니다 (이미지 파일: {len(image_data)} bytes)"
                            }
                        }
                    ],
                    channel=channel
                )
                
                logger.info(f"차트 정보 전송 완료: {title}")
                
            finally:
                # 임시 파일 삭제
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            
        except Exception as e:
            logger.error(f"개별 차트 전송 실패 ({title}): {e}")
    
    def send_comparison_report(self, results: List[BacktestResult], 
                             channel: Optional[str] = None) -> bool:
        """
        여러 전략 비교 리포트 전송
        
        Args:
            results: BacktestResult 리스트
            channel: 전송할 채널
            
        Returns:
            전송 성공 여부
        """
        try:
            if not self.slack_client:
                logger.error("Slack 클라이언트가 없어서 비교 리포트 전송 불가")
                return False
            
            if len(results) < 2:
                logger.error("비교할 결과가 부족합니다 (최소 2개 필요)")
                return False
            
            logger.info(f"전략 비교 리포트 전송 시작 ({len(results)}개 전략)")
            
            # 비교 테이블 생성
            comparison_blocks = self._create_comparison_blocks(results)
            
            # 비교 리포트 전송
            success = self.slack_client.send_message(
                text=f"⚖️ 전략 비교 리포트 ({len(results)}개 전략)",
                blocks=comparison_blocks,
                channel=channel
            )
            
            if success:
                logger.info("전략 비교 리포트 전송 완료")
            else:
                logger.error("전략 비교 리포트 전송 실패")
            
            return success
            
        except Exception as e:
            logger.error(f"전략 비교 리포트 전송 실패: {e}")
            return False
    
    def _create_comparison_blocks(self, results: List[BacktestResult]) -> List[Dict]:
        """전략 비교 블록 생성"""
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"⚖️ 전략 비교 리포트 ({len(results)}개)"
                    }
                }
            ]
            
            # 각 전략별 분석
            analyses = []
            for result in results:
                analysis = self.analyzer.analyze_performance(result)
                analyses.append((result, analysis))
            
            # 비교 테이블 생성
            comparison_data = []
            for result, analysis in analyses:
                basic = analysis.get('basic_metrics', {})
                risk = analysis.get('risk_metrics', {})
                trade = analysis.get('trade_analysis', {})
                
                comparison_data.append({
                    'strategy': result.strategy_name,
                    'return_pct': basic.get('total_return_pct', 0),
                    'annual_return': basic.get('annual_return', 0),
                    'max_dd': risk.get('max_drawdown_pct', 0),
                    'sharpe': risk.get('sharpe_ratio', 0),
                    'win_rate': trade.get('win_rate', 0),
                    'total_trades': trade.get('total_trades', 0),
                    'profit_factor': trade.get('profit_factor', 0)
                })
            
            # 성과 순으로 정렬
            comparison_data.sort(key=lambda x: x['return_pct'], reverse=True)
            
            # 헤더 추가
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*📊 핵심 지표 비교*\n수익률 기준 내림차순 정렬"
                }
            })
            
            # 각 전략 정보 추가
            for i, data in enumerate(comparison_data):
                rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}️⃣"
                return_emoji = "📈" if data['return_pct'] > 0 else "📉" if data['return_pct'] < 0 else "➖"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{rank_emoji} *{data['strategy']}*\n"
                               f"{return_emoji} 총 수익률: *{data['return_pct']:.2f}%*\n"
                               f"• 연환산: {data['annual_return']:.2f}%\n"
                               f"• 최대낙폭: {data['max_dd']:.2f}%\n"
                               f"• 샤프비율: {data['sharpe']:.3f}\n"
                               f"• 승률: {data['win_rate']:.1f}% ({data['total_trades']}회)"
                    }
                })
                
                if i < len(comparison_data) - 1:  # 마지막이 아니면 구분선 추가
                    blocks.append({"type": "divider"})
            
            # 요약 통계 추가
            avg_return = sum(d['return_pct'] for d in comparison_data) / len(comparison_data)
            best_strategy = comparison_data[0]
            worst_strategy = comparison_data[-1]
            
            blocks.extend([
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📈 요약 통계*\n"
                               f"• 평균 수익률: {avg_return:.2f}%\n"
                               f"• 최고 전략: {best_strategy['strategy']} ({best_strategy['return_pct']:.2f}%)\n"
                               f"• 최저 전략: {worst_strategy['strategy']} ({worst_strategy['return_pct']:.2f}%)\n"
                               f"• 수익률 격차: {best_strategy['return_pct'] - worst_strategy['return_pct']:.2f}%p"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"비교 리포트 생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ])
            
            return blocks
            
        except Exception as e:
            logger.error(f"비교 블록 생성 실패: {e}")
            return []
    
    def send_quick_summary(self, result: BacktestResult, 
                          channel: Optional[str] = None) -> bool:
        """
        간단한 요약 메시지 전송
        
        Args:
            result: BacktestResult 객체
            channel: 전송할 채널
            
        Returns:
            전송 성공 여부
        """
        try:
            if not self.slack_client:
                logger.error("Slack 클라이언트가 없어서 요약 전송 불가")
                return False
            
            # 간단한 요약 텍스트 생성
            emoji = "📈" if result.total_return_pct > 0 else "📉" if result.total_return_pct < 0 else "➖"
            
            summary_text = (
                f"{emoji} *{result.strategy_name}* 백테스트 완료\n"
                f"• 수익률: *{result.total_return_pct:.2f}%*\n"
                f"• 총 거래: {result.total_trades}회\n"
                f"• 승률: {result.win_rate:.1f}%\n"
                f"• 최대낙폭: {result.max_drawdown_pct:.2f}%"
            )
            
            success = self.slack_client.send_message(
                text=summary_text,
                channel=channel
            )
            
            if success:
                logger.info(f"백테스트 요약 전송 완료: {result.strategy_name}")
            else:
                logger.error(f"백테스트 요약 전송 실패: {result.strategy_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"백테스트 요약 전송 실패: {e}")
            return False
    
    def save_detailed_report(self, result: BacktestResult, 
                           analysis: Dict, filepath: str) -> bool:
        """
        상세 리포트를 파일로 저장
        
        Args:
            result: BacktestResult 객체
            analysis: 분석 결과
            filepath: 저장할 파일 경로
            
        Returns:
            저장 성공 여부
        """
        try:
            # 상세 리포트 텍스트 생성
            report_text = self.analyzer.generate_summary_report(result, analysis)
            
            # 추가 상세 정보
            detailed_sections = []
            
            # 거래 내역
            if result.trades:
                detailed_sections.append("\n\n📋 **거래 내역**")
                detailed_sections.append("=" * 50)
                
                for i, trade in enumerate(result.trades, 1):
                    detailed_sections.append(
                        f"{i}. {trade.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                        f"{trade.action} {trade.position_side} | "
                        f"${trade.price:.2f} | {trade.quantity:.6f} | "
                        f"{trade.trade_type}"
                    )
            
            # 자본 곡선 데이터
            if not result.equity_curve.empty:
                detailed_sections.append("\n\n📊 **자본 곡선 (마지막 10개)**")
                detailed_sections.append("=" * 50)
                
                last_10 = result.equity_curve.tail(10)
                for _, row in last_10.iterrows():
                    detailed_sections.append(
                        f"{row['timestamp']} | ${row['total_value']:.2f} | "
                        f"포지션: {row.get('position', 'None')}"
                    )
            
            # 전체 리포트 조합
            full_report = report_text + "\n".join(detailed_sections)
            
            # 파일 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_report)
            
            logger.info(f"상세 리포트 저장 완료: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"상세 리포트 저장 실패: {e}")
            return False