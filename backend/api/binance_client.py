import os
import asyncio
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from dotenv import load_dotenv
import logging

# 환경 변수 로드
load_dotenv()

class BinanceClient:
    def __init__(self, testnet=True):
        """
        바이낸스 클라이언트 초기화
        
        Args:
            testnet (bool): True면 테스트넷, False면 메인넷
        """
        self.testnet = testnet
        
        if testnet:
            self.api_key = os.getenv('TESTNET_API_KEY')
            self.api_secret = os.getenv('TESTNET_API_SECRET')
        else:
            self.api_key = os.getenv('BINANCE_API_KEY')
            self.api_secret = os.getenv('BINANCE_API_SECRET')
            
        if not self.api_key or not self.api_secret:
            raise ValueError("API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        
        # 바이낸스 클라이언트 초기화
        self.client = Client(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=testnet
        )
        
        # 로깅 설정
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def test_connection(self):
        """
        API 연결 테스트
        
        Returns:
            bool: 연결 성공 여부
        """
        try:
            # 서버 시간 확인
            server_time = self.client.get_server_time()
            self.logger.info(f"서버 연결 성공! 서버 시간: {server_time}")
            return True
            
        except BinanceAPIException as e:
            self.logger.error(f"바이낸스 API 에러: {e}")
            return False
        except BinanceRequestException as e:
            self.logger.error(f"바이낸스 요청 에러: {e}")
            return False
        except Exception as e:
            self.logger.error(f"예상치 못한 에러: {e}")
            return False
    
    def get_account_info(self):
        """
        선물 계정 정보 조회
        
        Returns:
            dict: 계정 정보 또는 None
        """
        try:
            # 선물 계정 정보 조회
            account_info = self.client.futures_account()
            
            # 주요 정보 추출
            total_balance = float(account_info['totalWalletBalance'])
            available_balance = float(account_info['availableBalance'])
            
            self.logger.info(f"총 잔고: {total_balance} USDT")
            self.logger.info(f"사용 가능한 잔고: {available_balance} USDT")
            
            return {
                'total_balance': total_balance,
                'available_balance': available_balance,
                'positions': account_info.get('positions', [])
            }
            
        except BinanceAPIException as e:
            self.logger.error(f"계정 정보 조회 실패: {e}")
            return None
        except Exception as e:
            self.logger.error(f"예상치 못한 에러: {e}")
            return None
    
    def get_symbol_price(self, symbol="BTCUSDT"):
        """
        특정 심볼의 현재가 조회
        
        Args:
            symbol (str): 조회할 심볼 (기본값: BTCUSDT)
            
        Returns:
            float: 현재가 또는 None
        """
        try:
            # 현재가 조회
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            current_price = float(ticker['price'])
            
            self.logger.info(f"{symbol} 현재가: {current_price}")
            return current_price
            
        except BinanceAPIException as e:
            self.logger.error(f"가격 조회 실패: {e}")
            return None
        except Exception as e:
            self.logger.error(f"예상치 못한 에러: {e}")
            return None
    
    def get_exchange_info(self):
        """
        거래소 정보 조회 (거래 가능한 심볼 확인)
        
        Returns:
            dict: 거래소 정보 또는 None
        """
        try:
            exchange_info = self.client.futures_exchange_info()
            
            # 활성 심볼만 필터링
            active_symbols = []
            for symbol_info in exchange_info['symbols']:
                if symbol_info['status'] == 'TRADING':
                    active_symbols.append(symbol_info['symbol'])
            
            self.logger.info(f"거래 가능한 심볼 수: {len(active_symbols)}")
            self.logger.info(f"주요 심볼 예시: {active_symbols[:10]}")
            
            return {
                'timezone': exchange_info['timezone'],
                'server_time': exchange_info['serverTime'],
                'active_symbols': active_symbols
            }
            
        except BinanceAPIException as e:
            self.logger.error(f"거래소 정보 조회 실패: {e}")
            return None
        except Exception as e:
            self.logger.error(f"예상치 못한 에러: {e}")
            return None

    def test_small_order(self, symbol="BTCUSDT", quantity=0.001):
        """
        소량 테스트 주문 (실제 주문이 아닌 주문 검증만)
        
        Args:
            symbol (str): 거래할 심볼
            quantity (float): 수량
            
        Returns:
            bool: 주문 검증 성공 여부
        """
        try:
            # 테스트 주문 (실제로 주문되지 않음)
            test_order = self.client.futures_create_test_order(
                symbol=symbol,
                side='BUY',
                type='MARKET',
                quantity=quantity
            )
            
            self.logger.info(f"테스트 주문 성공: {symbol} {quantity} 매수")
            return True
            
        except BinanceAPIException as e:
            self.logger.error(f"테스트 주문 실패: {e}")
            return False
        except Exception as e:
            self.logger.error(f"예상치 못한 에러: {e}")
            return False