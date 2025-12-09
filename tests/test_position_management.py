import unittest
import logging
import sys
import os

# Adiciona diretório raiz ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.position_manager import PositionManager
from bot.position_state import TradeState, ManagementProfile

# Configura logging
logging.basicConfig(level=logging.INFO)

class TestPositionManager(unittest.TestCase):
    def setUp(self):
        self.pm = PositionManager()
        self.symbol = "BTC"
        self.entry = 100000.0
        self.stop = 99000.0 # Risco = 1000
        # Cria posicao simulada
        self.pm.add_position(
            symbol=self.symbol,
            side="long",
            entry_price=self.entry,
            size=1.0,
            leverage=10,
            stop_loss_pct=1.0,
            initial_stop_price=self.stop,
            management_profile="SCALP_CAN_PROMOTE"
        )
        
    def test_r_calculation(self):
        pos = self.pm.get_position(self.symbol)
        # Price = 101000 -> 1R
        self.assertAlmostEqual(pos.calculate_current_r(101000), 1.0)
        # Price = 100500 -> 0.5R
        self.assertAlmostEqual(pos.calculate_current_r(100500), 0.5)
        # Price = 99000 -> -1R
        self.assertAlmostEqual(pos.calculate_current_r(99000), -1.0)
        
    def test_phase1_partial_be(self):
        """Testa se move para Phase 2 após atingir trigger"""
        # Config padrão BALANCEADO: first_trim_rr=1.8 (aprox, ver json)
        # Vamos assumir que config carregada é a do json. Se nao tiver json, usa defaults do codigo.
        # Codigo defaults: trim=1.5, pct=0.3
        
        market_ctx = {'trend': {'strength': 10}}
        
        # Simula preço a 1.9R (101900) para superar o threshold de 1.8R do Balanceado
        actions = self.pm.manage_position(
            self.symbol,
            current_price=101900, 
            current_mode="BALANCEADO",
            market_context=market_ctx
        )
        
        # Espera partial e update_stop
        has_partial = any(a['action'] == 'partial_close' for a in actions)
        has_stop_up = any(a['action'] == 'update_stop' for a in actions)
        
        self.assertTrue(has_partial, "Deve gerar partial close")
        self.assertTrue(has_stop_up, "Deve mover stop para BE")
        
        pos = self.pm.get_position(self.symbol)
        self.assertEqual(pos.trade_state, TradeState.SCALP_ACTIVE)
        
    def test_phase2_promotion(self):
        """Testa promoção para Swing"""
        # Avança estado
        pos = self.pm.get_position(self.symbol)
        pos.trade_state = TradeState.SCALP_ACTIVE
        
        # Config promotion_rr=2.2 (BALANCEADO)
        # Simula preço a 2.5R (102500)
        # Contexto forte
        market_ctx = {
            'trend': {
                'direction': 'bullish',
                'strength': 25
            }
        }
        
        actions = self.pm.manage_position(
            self.symbol,
            current_price=102500,
            current_mode="BALANCEADO",
            market_context=market_ctx
        )
        
        has_promo = any(a['action'] == 'promote_to_swing' for a in actions)
        self.assertTrue(has_promo, "Deve promover para swing com contexto forte")
        
        self.assertEqual(pos.trade_state, TradeState.PROMOTED_TO_SWING)
        
    def test_phase3_trailing(self):
        """Testa trailing stop"""
        pos = self.pm.get_position(self.symbol)
        pos.trade_state = TradeState.PROMOTED_TO_SWING
        pos.stop_loss_price = 100100 # BE
        
        current_price = 105000 # 5R
        
        # Simula trailing via estrutura (fallback percentual 1.5% = 1500)
        # Stop deve ir para 105000 - 1500 = 103500
        
        actions = self.pm.manage_position(
            self.symbol,
            current_price=current_price,
            current_mode="BALANCEADO",
            market_context={}
        )
        
        has_update = any(a['action'] == 'update_stop' for a in actions)
        self.assertTrue(has_update, "Deve atualizar trailing stop")
        
        new_stop = actions[0]['price']
        self.assertTrue(new_stop > 100100, "Stop deve subir")

if __name__ == '__main__':
    unittest.main()
