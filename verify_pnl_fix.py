#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import io

# Force UTF-8 encoding for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.position_manager import Position, PositionManager

def test_pnl_calculation():
    print("="*60)
    print("TEST: Position PnL Calculation (USD)")
    print("="*60)
    
    # 1. Test LONG Position
    # Entry: $100, Size: 1.0, Current: $110 -> PnL should be +$10
    pos_long = Position(
        symbol="BTC", side="long", entry_price=100.0, size=1.0,
        leverage=1, stop_loss_pct=2.0, take_profit_pct=4.0
    )
    
    pnl_usd_long = pos_long.get_unrealized_pnl_usd(110.0)
    pnl_pct_long = pos_long.get_unrealized_pnl_pct(110.0)
    
    print(f"LONG Position (Entry $100, Size 1.0, Current $110)")
    print(f"Expected PnL: +$10.00 (+10.0%)")
    print(f"Actual PnL:   ${pnl_usd_long:.2f} ({pnl_pct_long:.1f}%)")
    
    if abs(pnl_usd_long - 10.0) < 0.01:
        print("✅ LONG PnL USD Correct")
    else:
        print("❌ LONG PnL USD Incorrect")
        
    # 2. Test SHORT Position
    # Entry: $100, Size: 1.0, Current: $90 -> PnL should be +$10
    pos_short = Position(
        symbol="ETH", side="short", entry_price=100.0, size=1.0,
        leverage=1, stop_loss_pct=2.0, take_profit_pct=4.0
    )
    
    pnl_usd_short = pos_short.get_unrealized_pnl_usd(90.0)
    pnl_pct_short = pos_short.get_unrealized_pnl_pct(90.0)
    
    print(f"\nSHORT Position (Entry $100, Size 1.0, Current $90)")
    print(f"Expected PnL: +$10.00 (+10.0%)")
    print(f"Actual PnL:   ${pnl_usd_short:.2f} ({pnl_pct_short:.1f}%)")
    
    if abs(pnl_usd_short - 10.0) < 0.01:
        print("✅ SHORT PnL USD Correct")
    else:
        print("❌ SHORT PnL USD Incorrect")

    # 3. Test PositionManager Integration
    pm = PositionManager()
    pm.positions['BTC'] = pos_long
    
    # Mock current prices
    current_prices = {'BTC': 110.0}
    
    all_positions = pm.get_all_positions(current_prices)
    pos_data = all_positions[0]
    
    print(f"\nPositionManager.get_all_positions()")
    if 'unrealized_pnl' in pos_data:
        print(f"✅ 'unrealized_pnl' key present: ${pos_data['unrealized_pnl']:.2f}")
    else:
        print("❌ 'unrealized_pnl' key MISSING")

if __name__ == "__main__":
    test_pnl_calculation()
