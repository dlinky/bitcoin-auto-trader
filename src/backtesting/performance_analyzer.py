#!/usr/bin/env python3
"""
성과 분석기
파일 위치: src/backtesting/performance_analyzer.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import io
import base64

from src.utils.logger import get_logger
from src.backtesting.backtester import BacktestResult

logger = get_logger(__name__)

class PerformanceAnalyzer:
    """백테스트 성과 분석기"""
    
    def __init__(self):
        """성과 분석기 초기화"""
        # matplotlib 한글 폰트 설정 (선택사항)
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        
        logger.info("PerformanceAnalyzer 초기화 완료")
    
    def analyze_performance(self, result: BacktestResult) -> Dict:
        """
        성과 분석 수행
        
        Args:
            result: BacktestResult 객체
            
        Returns:
            분석 결과 딕셔너리
        """
        try:
            logger.info(f"성과 분석 시작 - {result.strategy_name} ({result.symbol})")
            
            analysis = {
                'basic_metrics': self._calculate_basic_metrics(result),
                'risk_metrics': self._calculate_risk_metrics(result),
                'trade_analysis': self._analyze_trades(result),
                'time_analysis': self._analyze_time_performance(result),
                'monthly_returns': self._calculate_monthly_returns(result),
                'charts': self._generate_charts(result)
            }
            
            logger.info("성과 분석 완료")
            return analysis
            
        except Exception as e:
            logger.error(f"성과 분석 실패: {e}")
            raise
    
    def _calculate_basic_metrics(self, result: BacktestResult) -> Dict:
        """기본 성과 지표 계산"""
        try:
            # 기간 계산
            duration = result.end_date - result.start_date
            duration_days = duration.days
            duration_years = duration_days / 365.25
            
            # 연환산 수익률
            annual_return = 0.0
            if duration_years > 0:
                annual_return = ((result.final_capital / result.initial_capital) ** (1/duration_years) - 1) * 100
            
            # 총 수익률
            total_return_pct = result.total_return_pct
            
            # 거래당 평균 수익
            avg_trade_return = 0.0
            if result.total_trades > 0:
                exit_trades = [t for t in result.trades if t.trade_type == 'EXIT']
                total_trade_pnl = sum(t.signal_data.get('pnl', 0) for t in exit_trades)
                avg_trade_return = total_trade_pnl / result.total_trades
            
            return {
                'duration_days': duration_days,
                'duration_years': round(duration_years, 2),
                'total_return': round(result.total_return, 2),
                'total_return_pct': round(total_return_pct, 2),
                'annual_return': round(annual_return, 2),
                'final_capital': round(result.final_capital, 2),
                'total_trades': result.total_trades,
                'avg_trade_return': round(avg_trade_return, 2)
            }
            
        except Exception as e:
            logger.error(f"기본 지표 계산 실패: {e}")
            return {}
    
    def _calculate_risk_metrics(self, result: BacktestResult) -> Dict:
        """리스크 지표 계산"""
        try:
            if result.equity_curve.empty:
                return {}
            
            # 일일 수익률 계산
            equity_curve = result.equity_curve.copy()
            equity_curve['daily_return'] = equity_curve['total_value'].pct_change()
            daily_returns = equity_curve['daily_return'].dropna()
            
            # 변동성 (연환산)
            volatility = 0.0
            if len(daily_returns) > 1:
                volatility = daily_returns.std() * np.sqrt(365 * 24 * 60) * 100  # 분단위 -> 연환산
            
            # 최대 낙폭 상세 계산
            peak = equity_curve['total_value'].expanding().max()
            drawdown = (equity_curve['total_value'] - peak) / peak * 100
            max_dd_pct = abs(drawdown.min())
            
            # 최대 낙폭 기간
            in_drawdown = drawdown < -0.01  # 0.01% 이상 낙폭
            if in_drawdown.any():
                dd_periods = []
                start_idx = None
                
                for i, is_dd in enumerate(in_drawdown):
                    if is_dd and start_idx is None:
                        start_idx = i
                    elif not is_dd and start_idx is not None:
                        dd_periods.append(i - start_idx)
                        start_idx = None
                
                # 마지막 낙폭이 끝나지 않은 경우
                if start_idx is not None:
                    dd_periods.append(len(in_drawdown) - start_idx)
                
                max_dd_duration = max(dd_periods) if dd_periods else 0
            else:
                max_dd_duration = 0
            
            # 칼마 비율 (연환산 수익률 / 최대 낙폭)
            calmar_ratio = 0.0
            basic_metrics = self._calculate_basic_metrics(result)
            if max_dd_pct > 0:
                calmar_ratio = basic_metrics.get('annual_return', 0) / max_dd_pct
            
            # 소르티노 비율 (하방 리스크 고려)
            sortino_ratio = 0.0
            if len(daily_returns) > 1:
                negative_returns = daily_returns[daily_returns < 0]
                if len(negative_returns) > 0:
                    downside_deviation = negative_returns.std() * np.sqrt(365 * 24 * 60)
                    if downside_deviation > 0:
                        avg_return = daily_returns.mean() * 365 * 24 * 60
                        sortino_ratio = avg_return / downside_deviation
            
            return {
                'volatility': round(volatility, 2),
                'max_drawdown': round(result.max_drawdown, 2),
                'max_drawdown_pct': round(max_dd_pct, 2),
                'max_drawdown_duration': max_dd_duration,
                'sharpe_ratio': round(result.sharpe_ratio, 3),
                'calmar_ratio': round(calmar_ratio, 3),
                'sortino_ratio': round(sortino_ratio, 3)
            }
            
        except Exception as e:
            logger.error(f"리스크 지표 계산 실패: {e}")
            return {}
    
    def _analyze_trades(self, result: BacktestResult) -> Dict:
        """거래 분석"""
        try:
            exit_trades = [t for t in result.trades if t.trade_type == 'EXIT']
            
            if not exit_trades:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0.0
                }
            
            # PnL 리스트
            pnls = [t.signal_data.get('pnl', 0) for t in exit_trades]
            wins = [pnl for pnl in pnls if pnl > 0]
            losses = [pnl for pnl in pnls if pnl < 0]
            
            # 승률 및 평균
            win_rate = (len(wins) / len(exit_trades)) * 100
            avg_win = np.mean(wins) if wins else 0.0
            avg_loss = np.mean(losses) if losses else 0.0
            
            # 최대 수익/손실
            max_win = max(wins) if wins else 0.0
            max_loss = min(losses) if losses else 0.0
            
            # Profit Factor (총 수익 / 총 손실)
            total_wins = sum(wins) if wins else 0.0
            total_losses = abs(sum(losses)) if losses else 0.0
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
            
            # 연속 승/패
            consecutive_wins = 0
            consecutive_losses = 0
            max_consecutive_wins = 0
            max_consecutive_losses = 0
            
            for pnl in pnls:
                if pnl > 0:
                    consecutive_wins += 1
                    consecutive_losses = 0
                    max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
                else:
                    consecutive_losses += 1
                    consecutive_wins = 0
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            
            # 거래 기간 분석
            entry_trades = [t for t in result.trades if t.trade_type == 'ENTRY']
            hold_times = []
            
            for i in range(min(len(entry_trades), len(exit_trades))):
                hold_time = exit_trades[i].timestamp - entry_trades[i].timestamp
                hold_times.append(hold_time.total_seconds() / 60)  # 분 단위
            
            avg_hold_time = np.mean(hold_times) if hold_times else 0.0
            
            return {
                'total_trades': len(exit_trades),
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate': round(win_rate, 1),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'max_win': round(max_win, 2),
                'max_loss': round(max_loss, 2),
                'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'Inf',
                'max_consecutive_wins': max_consecutive_wins,
                'max_consecutive_losses': max_consecutive_losses,
                'avg_hold_time_minutes': round(avg_hold_time, 1),
                'total_wins': round(total_wins, 2),
                'total_losses': round(total_losses, 2)
            }
            
        except Exception as e:
            logger.error(f"거래 분석 실패: {e}")
            return {}
    
    def _analyze_time_performance(self, result: BacktestResult) -> Dict:
        """시간대별 성과 분석"""
        try:
            if result.equity_curve.empty:
                return {}
            
            equity_curve = result.equity_curve.copy()
            equity_curve['hour'] = pd.to_datetime(equity_curve['timestamp']).dt.hour
            equity_curve['weekday'] = pd.to_datetime(equity_curve['timestamp']).dt.dayofweek
            equity_curve['daily_return'] = equity_curve['total_value'].pct_change()
            
            # 시간대별 평균 수익률
            hourly_returns = equity_curve.groupby('hour')['daily_return'].mean()
            best_hour = hourly_returns.idxmax() if not hourly_returns.empty else None
            worst_hour = hourly_returns.idxmin() if not hourly_returns.empty else None
            
            # 요일별 평균 수익률 (0=월요일, 6=일요일)
            weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            daily_returns = equity_curve.groupby('weekday')['daily_return'].mean()
            
            weekday_performance = {}
            for day_num, avg_return in daily_returns.items():
                if day_num < len(weekday_names):
                    weekday_performance[weekday_names[day_num]] = round(avg_return * 100, 3)
            
            return {
                'best_hour': int(best_hour) if best_hour is not None else None,
                'worst_hour': int(worst_hour) if worst_hour is not None else None,
                'best_hour_return': round(hourly_returns.max() * 100, 3) if not hourly_returns.empty else 0,
                'worst_hour_return': round(hourly_returns.min() * 100, 3) if not hourly_returns.empty else 0,
                'weekday_performance': weekday_performance
            }
            
        except Exception as e:
            logger.error(f"시간대별 분석 실패: {e}")
            return {}
    
    def _calculate_monthly_returns(self, result: BacktestResult) -> Dict:
        """월별 수익률 계산"""
        try:
            if result.equity_curve.empty:
                return {}
            
            equity_curve = result.equity_curve.copy()
            equity_curve['timestamp'] = pd.to_datetime(equity_curve['timestamp'])
            equity_curve = equity_curve.set_index('timestamp')
            
            # 월말 값으로 리샘플링
            monthly_values = equity_curve['total_value'].resample('M').last()
            monthly_returns = monthly_values.pct_change().dropna() * 100
            
            monthly_data = {}
            for date, return_pct in monthly_returns.items():
                month_key = date.strftime('%Y-%m')
                monthly_data[month_key] = round(return_pct, 2)
            
            # 최고/최악 월 성과
            best_month = monthly_returns.idxmax() if not monthly_returns.empty else None
            worst_month = monthly_returns.idxmin() if not monthly_returns.empty else None
            
            return {
                'monthly_returns': monthly_data,
                'best_month': best_month.strftime('%Y-%m') if best_month is not None else None,
                'best_month_return': round(monthly_returns.max(), 2) if not monthly_returns.empty else 0,
                'worst_month': worst_month.strftime('%Y-%m') if worst_month is not None else None,
                'worst_month_return': round(monthly_returns.min(), 2) if not monthly_returns.empty else 0,
                'positive_months': int((monthly_returns > 0).sum()),
                'negative_months': int((monthly_returns < 0).sum()),
                'avg_monthly_return': round(monthly_returns.mean(), 2) if not monthly_returns.empty else 0
            }
            
        except Exception as e:
            logger.error(f"월별 수익률 계산 실패: {e}")
            return {}
    
    def _generate_charts(self, result: BacktestResult) -> Dict:
        """차트 생성"""
        try:
            charts = {}
            
            if not result.equity_curve.empty:
                # 1. 자본 곡선 차트
                charts['equity_curve'] = self._create_equity_curve_chart(result)
                
                # 2. 낙폭 차트
                charts['drawdown'] = self._create_drawdown_chart(result)
                
                # 3. 월별 수익률 히트맵
                charts['monthly_heatmap'] = self._create_monthly_heatmap(result)
            
            if result.trades:
                # 4. 거래 분석 차트
                charts['trade_analysis'] = self._create_trade_analysis_chart(result)
            
            return charts
            
        except Exception as e:
            logger.error(f"차트 생성 실패: {e}")
            return {}
    
    def _create_equity_curve_chart(self, result: BacktestResult) -> str:
        """자본 곡선 차트 생성"""
        try:
            fig, ax = plt.subplots(figsize=(12, 6))
            
            equity_curve = result.equity_curve.copy()
            equity_curve['timestamp'] = pd.to_datetime(equity_curve['timestamp'])
            
            # 자본 곡선 플롯
            ax.plot(equity_curve['timestamp'], equity_curve['total_value'], 
                   linewidth=2, color='#2E86AB', label='Portfolio Value')
            
            # 초기 자본 기준선
            ax.axhline(y=result.initial_capital, color='gray', linestyle='--', 
                      alpha=0.7, label=f'Initial Capital (${result.initial_capital:,.0f})')
            
            # 거래 포인트 표시
            entry_trades = [t for t in result.trades if t.trade_type == 'ENTRY']
            exit_trades = [t for t in result.trades if t.trade_type == 'EXIT']
            
            for trade in entry_trades:
                # 해당 시점의 포트폴리오 가치 찾기
                trade_time = pd.to_datetime(trade.timestamp)
                closest_idx = equity_curve['timestamp'].sub(trade_time).abs().idxmin()
                portfolio_value = equity_curve.loc[closest_idx, 'total_value']
                
                color = 'green' if trade.position_side == 'LONG' else 'red'
                ax.scatter(trade_time, portfolio_value, color=color, s=50, 
                          marker='^', alpha=0.7, zorder=5)
            
            for trade in exit_trades:
                trade_time = pd.to_datetime(trade.timestamp)
                closest_idx = equity_curve['timestamp'].sub(trade_time).abs().idxmin()
                portfolio_value = equity_curve.loc[closest_idx, 'total_value']
                
                ax.scatter(trade_time, portfolio_value, color='orange', s=50, 
                          marker='v', alpha=0.7, zorder=5)
            
            # 차트 설정
            ax.set_title(f'{result.strategy_name} - Portfolio Value Over Time\n'
                        f'Total Return: {result.total_return_pct:.2f}% | '
                        f'Max Drawdown: {result.max_drawdown_pct:.2f}%', 
                        fontsize=14, fontweight='bold')
            ax.set_xlabel('Date', fontsize=12)
            ax.set_ylabel('Portfolio Value ($)', fontsize=12)
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 날짜 포맷팅
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(equity_curve)//10)))
            plt.xticks(rotation=45)
            
            plt.tight_layout()
            
            # 이미지를 base64로 인코딩
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logger.error(f"자본 곡선 차트 생성 실패: {e}")
            plt.close()
            return ""
    
    def _create_drawdown_chart(self, result: BacktestResult) -> str:
        """낙폭 차트 생성"""
        try:
            fig, ax = plt.subplots(figsize=(12, 4))
            
            equity_curve = result.equity_curve.copy()
            equity_curve['timestamp'] = pd.to_datetime(equity_curve['timestamp'])
            
            # 낙폭 계산
            peak = equity_curve['total_value'].expanding().max()
            drawdown = (equity_curve['total_value'] - peak) / peak * 100
            
            # 낙폭 영역 플롯
            ax.fill_between(equity_curve['timestamp'], drawdown, 0, 
                           color='red', alpha=0.3, label='Drawdown')
            ax.plot(equity_curve['timestamp'], drawdown, color='red', linewidth=1)
            
            # 차트 설정
            ax.set_title(f'Drawdown Analysis - Max: {abs(drawdown.min()):.2f}%', 
                        fontsize=14, fontweight='bold')
            ax.set_xlabel('Date', fontsize=12)
            ax.set_ylabel('Drawdown (%)', fontsize=12)
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 날짜 포맷팅
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(equity_curve)//10)))
            plt.xticks(rotation=45)
            
            plt.tight_layout()
            
            # 이미지를 base64로 인코딩
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logger.error(f"낙폭 차트 생성 실패: {e}")
            plt.close()
            return ""
    
    def _create_monthly_heatmap(self, result: BacktestResult) -> str:
        """월별 수익률 히트맵 생성"""
        try:
            if result.equity_curve.empty:
                return ""
            
            equity_curve = result.equity_curve.copy()
            equity_curve['timestamp'] = pd.to_datetime(equity_curve['timestamp'])
            equity_curve = equity_curve.set_index('timestamp')
            
            # 월별 수익률 계산
            monthly_values = equity_curve['total_value'].resample('M').last()
            monthly_returns = monthly_values.pct_change().dropna() * 100
            
            if monthly_returns.empty:
                return ""
            
            # 연도와 월 분리
            monthly_data = pd.DataFrame({
                'year': monthly_returns.index.year,
                'month': monthly_returns.index.month,
                'return': monthly_returns.values
            })
            
            # 피벗 테이블 생성
            heatmap_data = monthly_data.pivot(index='year', columns='month', values='return')
            
            # 월 이름으로 컬럼 변경
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            heatmap_data.columns = [month_names[i-1] for i in heatmap_data.columns]
            
            # 히트맵 생성
            fig, ax = plt.subplots(figsize=(12, 6))
            
            # 컬러맵 설정 (빨강-흰색-초록)
            import matplotlib.colors as mcolors
            colors = ['red', 'white', 'green']
            n_bins = 100
            cmap = mcolors.LinearSegmentedColormap.from_list('returns', colors, N=n_bins)
            
            # 히트맵 플롯
            im = ax.imshow(heatmap_data.values, cmap=cmap, aspect='auto',
                          vmin=-abs(heatmap_data.values).max(), 
                          vmax=abs(heatmap_data.values).max())
            
            # 텍스트 추가
            for i in range(len(heatmap_data.index)):
                for j in range(len(heatmap_data.columns)):
                    value = heatmap_data.iloc[i, j]
                    if not pd.isna(value):
                        text_color = 'white' if abs(value) > abs(heatmap_data.values).max() * 0.7 else 'black'
                        ax.text(j, i, f'{value:.1f}%', ha='center', va='center',
                               color=text_color, fontweight='bold')
            
            # 축 설정
            ax.set_xticks(range(len(heatmap_data.columns)))
            ax.set_xticklabels(heatmap_data.columns)
            ax.set_yticks(range(len(heatmap_data.index)))
            ax.set_yticklabels(heatmap_data.index)
            
            ax.set_title('Monthly Returns Heatmap (%)', fontsize=14, fontweight='bold')
            
            # 컬러바 추가
            cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Return (%)', rotation=270, labelpad=15)
            
            plt.tight_layout()
            
            # 이미지를 base64로 인코딩
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logger.error(f"월별 히트맵 생성 실패: {e}")
            plt.close()
            return ""
    
    def _create_trade_analysis_chart(self, result: BacktestResult) -> str:
        """거래 분석 차트 생성"""
        try:
            exit_trades = [t for t in result.trades if t.trade_type == 'EXIT']
            if not exit_trades:
                return ""
            
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
            
            # PnL 리스트
            pnls = [t.signal_data.get('pnl', 0) for t in exit_trades]
            
            # 1. PnL 히스토그램
            ax1.hist(pnls, bins=20, alpha=0.7, color='steelblue', edgecolor='black')
            ax1.axvline(x=0, color='red', linestyle='--', alpha=0.7)
            ax1.set_title('Trade PnL Distribution', fontweight='bold')
            ax1.set_xlabel('PnL ($)')
            ax1.set_ylabel('Frequency')
            ax1.grid(True, alpha=0.3)
            
            # 2. 누적 PnL
            cumulative_pnl = np.cumsum(pnls)
            ax2.plot(range(1, len(cumulative_pnl) + 1), cumulative_pnl, 
                    linewidth=2, color='green')
            ax2.set_title('Cumulative PnL by Trade', fontweight='bold')
            ax2.set_xlabel('Trade Number')
            ax2.set_ylabel('Cumulative PnL ($)')
            ax2.grid(True, alpha=0.3)
            
            # 3. 승패 패턴
            win_loss = ['Win' if pnl > 0 else 'Loss' for pnl in pnls]
            colors = ['green' if w == 'Win' else 'red' for w in win_loss]
            ax3.bar(range(1, len(win_loss) + 1), [1 if w == 'Win' else -1 for w in win_loss],
                   color=colors, alpha=0.7)
            ax3.set_title('Win/Loss Pattern', fontweight='bold')
            ax3.set_xlabel('Trade Number')
            ax3.set_ylabel('Win(+1) / Loss(-1)')
            ax3.set_ylim(-1.5, 1.5)
            ax3.grid(True, alpha=0.3)
            
            # 4. 수익률 vs 거래 크기
            trade_sizes = [abs(t.signal_data.get('pnl', 0)) for t in exit_trades]
            colors_scatter = ['green' if pnl > 0 else 'red' for pnl in pnls]
            ax4.scatter(trade_sizes, pnls, c=colors_scatter, alpha=0.6)
            ax4.axhline(y=0, color='black', linestyle='-', alpha=0.3)
            ax4.set_title('PnL vs Trade Size', fontweight='bold')
            ax4.set_xlabel('Absolute PnL ($)')
            ax4.set_ylabel('PnL ($)')
            ax4.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            # 이미지를 base64로 인코딩
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logger.error(f"거래 분석 차트 생성 실패: {e}")
            plt.close()
            return ""
    
    def generate_summary_report(self, result: BacktestResult, analysis: Dict) -> str:
        """요약 리포트 생성"""
        try:
            basic = analysis.get('basic_metrics', {})
            risk = analysis.get('risk_metrics', {})
            trade = analysis.get('trade_analysis', {})
            
            report = f"""
📊 **백테스트 결과 요약**

**전략**: {result.strategy_name}
**심볼**: {result.symbol}
**기간**: {result.start_date.strftime('%Y-%m-%d')} ~ {result.end_date.strftime('%Y-%m-%d')} ({basic.get('duration_days', 0)}일)

**📈 수익성**
• 총 수익률: {basic.get('total_return_pct', 0):.2f}%
• 연환산 수익률: {basic.get('annual_return', 0):.2f}%
• 최종 자본: ${basic.get('final_capital', 0):,.2f}

**⚡ 거래 통계**
• 총 거래: {trade.get('total_trades', 0)}회
• 승률: {trade.get('win_rate', 0):.1f}%
• 평균 수익: ${trade.get('avg_win', 0):.2f}
• 평균 손실: ${trade.get('avg_loss', 0):.2f}
• Profit Factor: {trade.get('profit_factor', 0)}

**⚠️ 리스크**
• 최대 낙폭: {risk.get('max_drawdown_pct', 0):.2f}%
• 변동성: {risk.get('volatility', 0):.2f}%
• 샤프 비율: {risk.get('sharpe_ratio', 0):.3f}
• 칼마 비율: {risk.get('calmar_ratio', 0):.3f}
"""
            
            return report.strip()
            
        except Exception as e:
            logger.error(f"요약 리포트 생성 실패: {e}")
            return "리포트 생성 실패"