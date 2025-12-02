import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Adiciona diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_hyperliquid import HyperliquidBot
from bot.market_context import MarketContext

class TestHyperliquidBotLogic(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_client = MagicMock()
        self.mock_client.sz_decimals_cache = {'BTC': 4}
        
        self.mock_telegram = MagicMock()
        self.mock_position_manager = MagicMock()
        self.mock_risk_manager = MagicMock()
        
        # Mock risk_manager.calculate_position_size to return proper dict
        self.mock_risk_manager.calculate_position_size.return_value = {
            'size': 0.002,
            'leverage': 10
        }
        
        # Initialize bot with mocks
        with patch('bot_hyperliquid.HyperliquidBotClient', return_value=self.mock_client), \
             patch('bot_hyperliquid.TelegramNotifier', return_value=self.mock_telegram), \
             patch('bot_hyperliquid.PositionManager', return_value=self.mock_position_manager), \
             patch('bot_hyperliquid.RiskManager', return_value=self.mock_risk_manager):
            
            # Config fake
            config = {
                'wallet_address': '0x123',
                'private_key': '0xabc',
                'network': 'testnet',
                'max_open_trades': 5,
                'risk_per_trade_pct': 1,
                'max_daily_drawdown_pct': 5,
                'max_leverage': 20,
                'min_notional': 10,
                'default_stop_pct': 2.0,
                'default_tp_pct': 4.0,
                'trading_pairs': ['BTC', 'ETH'],
                'live_trading': False,
                'loop_sleep_seconds': 60
            }
            self.bot = HyperliquidBot(config)
            self.bot.client = self.mock_client
            self.bot.telegram = self.mock_telegram
            self.bot.position_manager = self.mock_position_manager
            self.bot.risk_manager = self.mock_risk_manager
            self.bot.live_trading = True

    def test_execute_open_isolated_margin(self):
        """Testa se abre posição com margem ISOLADA"""
        decision = {
            'symbol': 'BTC',
            'side': 'long',
            'size_usd': 100,
            'leverage': 10,
            'stop_loss_pct': 2.0,
            'confidence': 0.8
        }
        prices = {'BTC': 50000.0}
        
        # Mock position checks
        self.mock_position_manager.has_position.return_value = False
        self.mock_position_manager.get_position.return_value = None
        self.mock_position_manager.get_positions_count.return_value = 0
        
        # Mock place_order success
        self.mock_client.place_order.return_value = {'status': 'ok'}
        
        self.bot._execute_open(decision, prices)
        
        # Verifica se chamou adjust_leverage com is_cross=False
        self.mock_client.adjust_leverage.assert_called_with('BTC', 10, is_cross=False)

    def test_execute_open_quality_gate(self):
        """Testa se rejeita trade com confiança baixa"""
        decision = {
            'symbol': 'BTC',
            'side': 'long',
            'size_usd': 100,
            'leverage': 10,
            'stop_loss_pct': 2.0,
            'confidence': 0.5  # Baixa confiança (< 0.6)
        }
        prices = {'BTC': 50000.0}
        
        result = self.bot._execute_open(decision, prices)
        
        self.assertFalse(result)
        self.mock_client.place_order.assert_not_called()

    def test_execute_open_stop_loss_calculation(self):
        """Testa cálculo de stop_loss_pct quando vem stop_loss_price"""
        decision = {
            'symbol': 'BTC',
            'side': 'long',
            'size_usd': 100,
            'leverage': 10,
            'stop_loss_price': 49000.0, # 2% abaixo de 50k
            'confidence': 0.8
        }
        prices = {'BTC': 50000.0}
        
        # Mock position checks
        self.mock_position_manager.has_position.return_value = False
        self.mock_position_manager.get_position.return_value = None
        self.mock_position_manager.get_positions_count.return_value = 0
        
        self.mock_client.place_order.return_value = {'status': 'ok'}
        
        self.bot._execute_open(decision, prices)
        
        # Verifica se calculou pct corretamente (aprox 2.0)
        # O argumento stop_loss_pct é passado para add_position
        if self.mock_position_manager.add_position.call_args:
            args, kwargs = self.mock_position_manager.add_position.call_args
            self.assertAlmostEqual(kwargs['stop_loss_pct'], 2.0, places=1)

    def test_execute_manage_partial_close(self):
        """Testa fechamento parcial via AI manage"""
        decision = {
            'symbol': 'BTC',
            'manage_decision': {
                'reason': 'Take profit partial',
                'close_pct': 0.5
            }
        }
        prices = {'BTC': 50000.0}
        
        # Mock position
        mock_pos = MagicMock()
        mock_pos.size = 0.1
        mock_pos.side = 'long'
        mock_pos.entry_price = 48000
        self.mock_position_manager.has_position.return_value = True
        self.mock_position_manager.get_position.return_value = mock_pos
        
        self.mock_client.place_order.return_value = {'status': 'ok'}
        
        self.bot._execute_manage(decision, prices)
        
        # Verifica se enviou ordem de venda de 50% (0.05)
        self.mock_client.place_order.assert_called()
        call_args = self.mock_client.place_order.call_args[1]
        self.assertAlmostEqual(call_args['size'], 0.05)
        self.assertTrue(call_args['reduce_only'])

    def test_market_context_anti_chasing(self):
        """Testa métricas anti-chasing no MarketContext"""
        ctx = MarketContext()
        
        # Mock candles (apenas closes importam para EMA)
        # Vamos criar uma lista de candles onde o preço atual (último) explodiu
        candles = [{'c': 100, 'h':100, 'l':100, 'v':100} for _ in range(30)]
        # EMA21 vai estar perto de 100
        
        # Preço atual explode para 110 (10% acima)
        current_price = 110.0
        
        context = ctx.build_context_for_pair('BTC', current_price, candles)
        
        # Verifica se detectou esticado
        self.assertTrue(context['trend']['is_extended'])
        self.assertGreater(context['indicators']['distance_from_ema21_pct'], 5.0)

if __name__ == '__main__':
    unittest.main()
