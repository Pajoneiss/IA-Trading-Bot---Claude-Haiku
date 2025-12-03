"""
Test Phase 2 - Validação de Parser e Quality Gate
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.phase2 import DecisionParser, QualityGate


def test_parser():
    """Testa o parser com diferentes inputs"""
    print("\n" + "="*60)
    print("TESTE 1: Parse Open Decision")
    print("="*60)
    
    open_json = {
        "action": "open",
        "symbol": "BTC",
        "side": "long",
        "style": "swing",
        "confidence": 0.87,
        "reason": "Pullback em EMA21 + BOS confirmado",
        "strategy": "EMA_BOUNCE",
        "stop_loss_price": 96500,
        "take_profit_price": 102000,
        "stop_loss_pct": 2.0,
        "risk_profile": "BALANCED",
        "confluences": ["EMA21", "BOS", "Volume"],
        "risk_amount_usd": 5.0,
        "capital_alloc_usd": 50.0
    }
    
    parsed = DecisionParser.parse_ai_decision(open_json, "claude_swing")
    
    if parsed:
        print("✅ SUCESSO - Decision parseada:")
        print(f"  Symbol: {parsed['symbol']}")
        print(f"  Side: {parsed['side']}")
        print(f"  Confidence: {parsed['confidence']}")
        print(f"  Confluences: {len(parsed.get('confluences', []))}")
    else:
        print("❌ FALHA - Não conseguiu parsear")
    
    print("\n" + "="*60)
    print("TESTE 2: Parse Manage Decision")
    print("="*60)
    
    manage_json = {
        "action": "manage",
        "symbol": "ETH",
        "style": "swing",
        "manage_decision": {
            "close_pct": 0.5,
            "new_stop_price": 3450.0,
            "reason": "2R atingido, parcial + breakeven"
        }
    }
    
    parsed = DecisionParser.parse_ai_decision(manage_json, "claude_swing")
    
    if parsed:
        print("✅ SUCESSO - Manage parseada:")
        print(f"  Symbol: {parsed['symbol']}")
        print(f"  Close %: {parsed['manage_decision']['close_pct'] * 100}%")
        print(f"  New Stop: ${parsed['manage_decision']['new_stop_price']}")
    else:
        print("❌ FALHA - Não conseguiu parsear")
    
    print("\n" + "="*60)
    print("TESTE 3: Parse Skip Decision")
    print("="*60)
    
    skip_json = {
        "action": "skip",
        "symbol": "SOL",
        "style": "scalp",
        "reason": "Range sujo, sem setup claro"
    }
    
    parsed = DecisionParser.parse_ai_decision(skip_json, "openai_scalp")
    
    if parsed:
        print("✅ SUCESSO - Skip parseada:")
        print(f"  Symbol: {parsed['symbol']}")
        print(f"  Reason: {parsed['reason']}")
    else:
        print("❌ FALHA - Não conseguiu parsear")


def test_quality_gate():
    """Testa o Quality Gate"""
    print("\n" + "="*60)
    print("TESTE 4: Quality Gate - Sinal BOM")
    print("="*60)
    
    gate = QualityGate()
    
    good_decision = {
        "action": "open",
        "symbol": "BTC",
        "side": "long",
        "confidence": 0.87,
        "risk_profile": "BALANCED",
        "confluences": ["EMA", "BOS", "Volume"],
        "stop_loss_price": 96500
    }
    
    result = gate.evaluate(good_decision)
    
    print(f"  Approved: {result.approved}")
    print(f"  Final Confidence: {result.confidence_score:.2f}")
    print(f"  Reasons: {result.reasons}")
    
    print("\n" + "="*60)
    print("TESTE 5: Quality Gate - Confidence BAIXA")
    print("="*60)
    
    bad_decision = {
        "action": "open",
        "symbol": "ETH",
        "side": "long",
        "confidence": 0.65,  # Muito baixo
        "risk_profile": "BALANCED",
        "confluences": ["EMA"],
        "stop_loss_price": 3400
    }
    
    result = gate.evaluate(bad_decision)
    
    print(f"  Approved: {result.approved}")
    print(f"  Final Confidence: {result.confidence_score:.2f}")
    print(f"  Reasons: {result.reasons}")
    
    print("\n" + "="*60)
    print("TESTE 6: Quality Gate - POUCAS Confluências")
    print("="*60)
    
    few_conf_decision = {
        "action": "open",
        "symbol": "SOL",
        "side": "long",
        "confidence": 0.82,
        "risk_profile": "BALANCED",
        "confluences": ["EMA"],  # Só 1
        "stop_loss_price": 95
    }
    
    result = gate.evaluate(few_conf_decision)
    
    print(f"  Approved: {result.approved}")
    print(f"  Final Confidence: {result.confidence_score:.2f}")
    print(f"  Warnings: {result.warnings}")
    print(f"  Adjustments: {result.adjustments}")


def test_sanitize():
    """Testa sanitização de NaN"""
    print("\n" + "="*60)
    print("TESTE 7: Sanitize Decision com NaN")
    print("="*60)
    
    import math
    
    dirty = {
        "action": "open",
        "symbol": "BTC",
        "confidence": math.nan,  # NaN
        "risk_amount": math.inf,  # Inf
        "valid_field": 100.0,
        "none_field": None
    }
    
    clean = DecisionParser.sanitize_decision(dirty)
    
    print("  Antes:")
    print(f"    confidence: {dirty['confidence']}")
    print(f"    risk_amount: {dirty['risk_amount']}")
    
    print("  Depois:")
    print(f"    confidence: {clean.get('confidence', 'REMOVIDO')}")
    print(f"    risk_amount: {clean.get('risk_amount', 'REMOVIDO')}")
    print(f"    valid_field: {clean.get('valid_field')}")
    print(f"    none_field presente: {'none_field' in clean}")


if __name__ == "__main__":
    print("\n🧪 TESTANDO PHASE 2 - PARSER & QUALITY GATE\n")
    
    test_parser()
    test_quality_gate()
    test_sanitize()
    
    print("\n" + "="*60)
    print("✅ TODOS OS TESTES CONCLUÍDOS")
    print("="*60 + "\n")
