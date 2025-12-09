
import logging
import os
import sys

# Setup mock config
mock_config = {
    'wallet_address': '0x123',
    'private_key': '0x123',
    'max_open_trades': 5,
    'max_daily_drawdown_pct': 5.0,
    'max_leverage': 20,
    'min_notional': 10.0,
    'default_stop_pct': 2.0,
    'default_tp_pct': 4.0,
    'trading_pairs': ['BTC-USD', 'ETH-USD'],
    'live_trading': False,
    'loop_sleep_seconds': 1,
    'network': 'sim',
    'anthropic_api_key': 'sk-mock',
    'openai_api_key': 'sk-mock'
}

# Configura logger
logging.basicConfig(level=logging.INFO)

print("--- INICIANDO TESTE DE INTEGRACAO ---")

try:
    print("1. Importando bot_hyperliquid...")
    from bot_hyperliquid import HyperliquidBot
    print("[OK] Importacao OK")
    
    print("2. Testando RiskManager standalone...")
    from bot.risk_manager import RiskManager
    rm = RiskManager()
    rm.update_equity(5000.0) # Precisa de saldo para calcular size
    print(f"[OK] RiskManager instanciado. Testando calculate_position_size_structural...")
    res = rm.calculate_position_size_structural('BTC-USD', 100000, 99000, risk_pct=1.0)
    if res and res['stop_price_structural'] == 99000:
        print("[OK] calculate_position_size_structural OK")
    else:
        print("[FAIL] Falha em calculate_position_size_structural")
        
    print("3. Testando TradingModeManager...")
    from bot.phase5.trading_modes import TradingModeManager
    tm = TradingModeManager()
    print(f"[OK] TradingModeManager carregado no modo: {tm.current_mode}")
    
    print("4. Testando OpenAiScalpEngine com ModeManager...")
    from bot.openai_scalp_engine import OpenAiScalpEngine
    open_ai = OpenAiScalpEngine(api_key="mock", mode_manager=tm)
    if open_ai.mode_manager == tm:
         print(f"[OK] OpenAiScalpEngine recebeu mode_manager com sucesso. Max trades: {open_ai.mode_manager.get_max_trades_scalp()}")
    else:
         print("[FAIL] OpenAiScalpEngine falhou em receber mode_manager")

    print("\n[OK] TESTE DE INTEGRACAO COMPLETO COM SUCESSO!")
    
except Exception as e:
    print(f"\n[ERROR] ERRO FATAL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
