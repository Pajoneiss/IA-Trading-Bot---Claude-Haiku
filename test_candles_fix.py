"""
Test - Normalização de Candles
Valida que technical_analysis aceita formato Hyperliquid
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.phase2 import TechnicalAnalysis


def test_normalize_candles():
    """Testa normalização de diferentes formatos"""
    print("\n" + "="*60)
    print("TESTE 1: Normalização de Candles")
    print("="*60)
    
    ta = TechnicalAnalysis()
    
    # Formato Hyperliquid (o, h, l, c, v)
    hyperliquid_candles = [
        {'t': 1234567890, 'o': 100.5, 'h': 102.0, 'l': 99.0, 'c': 101.0, 'v': 1000},
        {'t': 1234567891, 'o': 101.0, 'h': 103.0, 'l': 100.0, 'c': 102.5, 'v': 1500}
    ]
    
    normalized = ta.normalize_candles(hyperliquid_candles)
    
    print(f"\n  INPUT (Hyperliquid):")
    print(f"    Keys: {list(hyperliquid_candles[0].keys())}")
    print(f"    First: {hyperliquid_candles[0]}")
    
    print(f"\n  OUTPUT (Normalized):")
    print(f"    Keys: {list(normalized[0].keys())}")
    print(f"    First: {normalized[0]}")
    
    # Valida
    expected_keys = {'open', 'high', 'low', 'close', 'volume'}
    actual_keys = set(normalized[0].keys())
    
    if expected_keys == actual_keys:
        print(f"\n  ✅ Normalização CORRETA")
        print(f"    'o' → 'open': {normalized[0]['open']}")
        print(f"    'h' → 'high': {normalized[0]['high']}")
        print(f"    'c' → 'close': {normalized[0]['close']}")
    else:
        print(f"\n  ❌ ERRO: Keys esperadas {expected_keys}, recebidas {actual_keys}")
    
    # Formato padrão (open, high, low, close, volume)
    print("\n" + "-"*60)
    
    standard_candles = [
        {'open': 100.5, 'high': 102.0, 'low': 99.0, 'close': 101.0, 'volume': 1000},
        {'open': 101.0, 'high': 103.0, 'low': 100.0, 'close': 102.5, 'volume': 1500}
    ]
    
    normalized2 = ta.normalize_candles(standard_candles)
    
    print(f"\n  INPUT (Padrão):")
    print(f"    Keys: {list(standard_candles[0].keys())}")
    
    print(f"\n  OUTPUT (Normalizado):")
    print(f"    Keys: {list(normalized2[0].keys())}")
    
    if normalized2[0]['open'] == 100.5 and normalized2[0]['close'] == 101.0:
        print(f"\n  ✅ Formato padrão preservado corretamente")
    else:
        print(f"\n  ❌ ERRO ao processar formato padrão")


def test_analyze_with_hyperliquid_format():
    """Testa análise completa com formato Hyperliquid"""
    print("\n" + "="*60)
    print("TESTE 2: Análise com Formato Hyperliquid")
    print("="*60)
    
    ta = TechnicalAnalysis()
    
    # 50 candles no formato Hyperliquid
    candles = []
    for i in range(50):
        candles.append({
            't': 1234567890 + i * 3600,
            'o': 100 + i * 0.5,
            'h': 102 + i * 0.5,
            'l': 99 + i * 0.5,
            'c': 101 + i * 0.5,
            'v': 1000 + i * 10
        })
    
    try:
        # Estrutura
        structure = ta.analyze_structure(candles, "1h")
        print(f"\n  Estrutura:")
        print(f"    Trend: {structure['trend']}")
        print(f"    Structure: {structure['structure']}")
        print(f"    ✅ analyze_structure funcionou")
        
        # Padrões
        patterns = ta.detect_patterns(candles)
        print(f"\n  Padrões: {patterns if patterns else 'Nenhum'}")
        print(f"    ✅ detect_patterns funcionou")
        
        # EMA
        ema = ta.check_ema_confluence(candles)
        print(f"\n  EMA:")
        print(f"    Alignment: {ema['alignment']}")
        print(f"    Strength: {ema['strength']:.2f}")
        print(f"    ✅ check_ema_confluence funcionou")
        
        # Liquidez
        liquidity = ta.identify_liquidity_zones(candles)
        print(f"\n  Liquidez:")
        print(f"    Buy-side: {len(liquidity['buy_side'])} zonas")
        print(f"    Sell-side: {len(liquidity['sell_side'])} zonas")
        print(f"    ✅ identify_liquidity_zones funcionou")
        
        print(f"\n  ✅ TODOS OS MÉTODOS FUNCIONARAM SEM ERRO!")
        
    except Exception as e:
        print(f"\n  ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()


def test_empty_and_malformed():
    """Testa proteção contra dados vazios/malformados"""
    print("\n" + "="*60)
    print("TESTE 3: Proteção contra Dados Inválidos")
    print("="*60)
    
    ta = TechnicalAnalysis()
    
    # Lista vazia
    result = ta.normalize_candles([])
    print(f"\n  Lista vazia:")
    print(f"    Result: {result}")
    print(f"    ✅ Retornou lista vazia" if result == [] else "    ❌ ERRO")
    
    # Candle malformado (sem keys necessárias)
    malformed = [{'foo': 'bar', 'baz': 123}]
    result = ta.normalize_candles(malformed)
    print(f"\n  Candle malformado:")
    print(f"    Input keys: {list(malformed[0].keys())}")
    print(f"    Result: {result}")
    print(f"    ✅ Ignorou candle inválido" if result == [] else "    ❌ ERRO")
    
    # Estrutura com poucos candles
    few_candles = [
        {'o': 100, 'h': 101, 'l': 99, 'c': 100.5, 'v': 1000}
    ]
    structure = ta.analyze_structure(few_candles)
    print(f"\n  Poucos candles (1):")
    print(f"    Trend: {structure['trend']}")
    print(f"    ✅ Retornou estrutura vazia" if structure['trend'] == 'ranging' else "    ❌ ERRO")


if __name__ == "__main__":
    print("\n🧪 TESTANDO NORMALIZAÇÃO DE CANDLES\n")
    
    test_normalize_candles()
    test_analyze_with_hyperliquid_format()
    test_empty_and_malformed()
    
    print("\n" + "="*60)
    print("✅ TODOS OS TESTES CONCLUÍDOS")
    print("="*60 + "\n")
