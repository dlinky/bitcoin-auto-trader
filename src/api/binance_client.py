import time
import logging
from typing import Dict, List, Optional, Tuple
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
import pandas as pd
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)

class BinanceClient:
    """바이낸스 선물 거래를 위한 클라이언트"""
    
    def __init__(self, api_key: str, secret_key: str, testnet: bool = True):
        """
        바이낸스 클라이언트 초기화
        
        Args:
            api_key: API 키
            secret_key: 시크릿 키  
            testnet: 테스트넷 사용 여부
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet
        
        # 바이낸스 클라이언트 초기화
        self.client = Client(
            api_key=api_key,
            api_secret=secret_key,
            testnet=testnet
        )
        
        # 타임아웃 설정 (5초)
        self.client.session.timeout = 5
        
        logger.info(f"BinanceClient 초기화 완료 (testnet: {testnet})")
    
    def _retry_request(self, func, *args, **kwargs):
        """
        API 요청 재시도 로직 (1회 재시도)
        
        Args:
            func: 실행할 함수
            *args, **kwargs: 함수 파라미터
            
        Returns:
            API 응답 결과
            
        Raises:
            Exception: 재시도 후에도 실패시
        """
        for attempt in range(2):  # 최대 2번 시도 (원본 + 재시도 1회)
            try:
                result = func(*args, **kwargs)
                if attempt > 0:  # 재시도로 성공한 경우
                    logger.info(f"API 요청 재시도 성공: {func.__name__}")
                return result
                
            except (BinanceAPIException, BinanceRequestException, Exception) as e:
                if attempt == 0:  # 첫번째 시도 실패
                    logger.warning(f"API 요청 실패, 재시도 중: {func.__name__} - {str(e)}")
                    time.sleep(1)  # 1초 대기 후 재시도
                else:  # 재시도도 실패
                    logger.error(f"API 요청 최종 실패: {func.__name__} - {str(e)}")
                    raise e
    
    def get_klines(self, symbol: str, interval: str = '1m', limit: int = 100) -> pd.DataFrame:
        """
        캔들스틱 데이터 조회
        
        Args:
            symbol: 거래 심볼 (예: 'BTCUSDT')
            interval: 시간 간격 (예: '1m', '5m', '1h')
            limit: 조회할 캔들 개수
            
        Returns:
            OHLCV 데이터가 포함된 DataFrame
        """
        logger.debug(f"캔들 데이터 조회 시작: {symbol} {interval} {limit}개")
        
        def _get_klines():
            return self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
        
        klines = self._retry_request(_get_klines)
        
        # DataFrame으로 변환
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # 필요한 컬럼만 선택하고 타입 변환
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        
        logger.debug(f"캔들 데이터 조회 완료: {symbol} {len(df)}개")
        return df
    
    def get_position_info(self, symbol: str) -> Dict:
        """
        포지션 정보 조회
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            포지션 정보 딕셔너리
        """
        logger.debug(f"포지션 정보 조회: {symbol}")
        
        def _get_position():
            positions = self.client.futures_position_information(symbol=symbol)
            return positions[0] if positions else {}
        
        position = self._retry_request(_get_position)
        
        # 포지션 정보 정리
        result = {
            'symbol': position.get('symbol', ''),
            'size': float(position.get('positionAmt', 0)),
            'entry_price': float(position.get('entryPrice', 0)),
            'unrealized_pnl': float(position.get('unRealizedProfit', 0)),
            'side': 'LONG' if float(position.get('positionAmt', 0)) > 0 else 'SHORT' if float(position.get('positionAmt', 0)) < 0 else 'NONE'
        }
        
        logger.debug(f"포지션 정보: {symbol} - {result['side']} {result['size']}")
        return result
    
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict:
        """
        시장가 주문 실행
        
        Args:
            symbol: 거래 심볼
            side: 주문 방향 ('BUY' 또는 'SELL')
            quantity: 주문 수량
            
        Returns:
            주문 결과 딕셔너리
        """
        logger.info(f"시장가 주문 실행: {symbol} {side} {quantity}")
        
        def _place_order():
            return self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
        
        order_result = self._retry_request(_place_order)
        
        # 주문 결과 정리
        result = {
            'order_id': order_result.get('orderId'),
            'symbol': order_result.get('symbol'),
            'side': order_result.get('side'),
            'quantity': float(order_result.get('origQty', 0)),
            'price': float(order_result.get('avgPrice', 0)) if order_result.get('avgPrice') else 0,
            'status': order_result.get('status'),
            'time': pd.to_datetime(order_result.get('updateTime'), unit='ms')
        }
        
        logger.info(f"주문 완료: {symbol} {side} {result['quantity']} @ {result['price']}")
        return result
    
    def get_account_balance(self) -> Dict:
        """
        계좌 잔고 조회
        
        Returns:
            USDT 잔고 정보
        """
        logger.debug("계좌 잔고 조회")
        
        def _get_balance():
            return self.client.futures_account_balance()
        
        balances = self._retry_request(_get_balance)
        
        # USDT 잔고 찾기
        usdt_balance = next((b for b in balances if b['asset'] == 'USDT'), {})
        
        result = {
            'balance': float(usdt_balance.get('balance', 0)),
            'available': float(usdt_balance.get('availableBalance', 0))
        }
        
        logger.debug(f"USDT 잔고: {result['available']}")
        return result
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """
        심볼 정보 조회 (최소 주문 단위 등)
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            심볼 정보 딕셔너리
        """
        logger.debug(f"심볼 정보 조회: {symbol}")
        
        exchange_info = self.client.futures_exchange_info()
        symbols = exchange_info.get('symbols', [])
        symbol_info = next((s for s in symbols if s['symbol'] == symbol), {})
        
        # 최소 주문 단위 찾기
        filters = symbol_info.get('filters', [])
        lot_size_filter = next((f for f in filters if f['filterType'] == 'LOT_SIZE'), {})
        
        result = {
            'symbol': symbol_info.get('symbol', ''),
            'min_qty': float(lot_size_filter.get('minQty', 0)),
            'step_size': float(lot_size_filter.get('stepSize', 0)),
            'status': symbol_info.get('status', '')
        }
        
        logger.debug(f"심볼 정보: {symbol} - 최소수량: {result['min_qty']}")
        return result
    
    def calculate_quantity(self, symbol: str, usdt_amount: float, price: float) -> float:
        """
        USDT 금액을 기준으로 주문 수량 계산
        
        Args:
            symbol: 거래 심볼
            usdt_amount: 투자할 USDT 금액
            price: 현재 가격
            
        Returns:
            계산된 주문 수량
        """
        symbol_info = self.get_symbol_info(symbol)
        step_size = symbol_info['step_size']
        min_qty = symbol_info['min_qty']
        
        # 수량 계산
        quantity = usdt_amount / price
        
        # step_size에 맞춰 반올림 (소수점 자리수 계산)
        if step_size < 1:
            precision = len(str(step_size).split('.')[1]) if '.' in str(step_size) else 0
            quantity = float(Decimal(str(quantity)).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN))
        else:
            quantity = int(quantity // step_size) * step_size
        
        # 최소 주문 수량 확인
        if quantity < min_qty:
            raise ValueError(f"계산된 수량 {quantity}이 최소 주문 수량 {min_qty}보다 작습니다")
        
        logger.debug(f"주문 수량 계산: {usdt_amount} USDT @ {price} = {quantity}")
        return quantity