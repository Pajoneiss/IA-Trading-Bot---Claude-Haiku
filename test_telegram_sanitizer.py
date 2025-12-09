"""
Test Telegram Markdown Sanitizer
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.utils.telegram_utils import (
    escape_markdown_v2,
    safe_markdown_bold,
    format_number,
    build_safe_line,
    sanitize_telegram_message
)


def test_escape_basic():
    """Testa escape de caracteres básicos"""
    print("\n" + "="*60)
    print("TESTE 1: Escape de Caracteres Básicos")
    print("="*60)
    
    # Teste 1: Underline
    text = "Hello_World"
    expected = "Hello\\_World"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  Expected: {expected}")
    print(f"  ✅ OK" if result == expected else f"  ❌ FALHOU")
    
    # Teste 2: Asterisco
    text = "BTC*100"
    expected = "BTC\\*100"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if result == expected else f"  ❌ FALHOU")
    
    # Teste 3: Porcentagem
    text = "Win Rate: 75%"
    expected = "Win Rate: 75\\%"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if result == expected else f"  ❌ FALHOU")
    
    # Teste 4: Dólar e ponto
    text = "PnL: $120.50"
    expected = "PnL: \\$120\\.50"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if result == expected else f"  ❌ FALHOU")


def test_escape_complex():
    """Testa escape de strings complexas"""
    print("\n" + "="*60)
    print("TESTE 2: Escape de Strings Complexas")
    print("="*60)
    
    # Teste 1: Trade info
    text = "BTC ($50.00 | +2.5%)"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    
    # Verifica se todos caracteres especiais foram escapados
    special_chars = ['$', '.', '(', ')', '|', '+', '%']
    all_escaped = all(f"\\{char}" in result for char in special_chars)
    print(f"  ✅ Todos caracteres escapados" if all_escaped else f"  ❌ Faltam escapes")
    
    # Teste 2: Strategy name
    text = "SMC_BOS-Breakout"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if "\\_" in result and "\\-" in result else f"  ❌ FALHOU")


def test_format_number():
    """Testa formatação de números"""
    print("\n" + "="*60)
    print("TESTE 3: Formatação de Números")
    print("="*60)
    
    # Teste 1: PnL
    value = 120.5
    result = format_number(value, 2, "$", "")
    print(f"\n  Input: {value}")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if "\\$" in result and "\\." in result else f"  ❌ FALHOU")
    
    # Teste 2: Win Rate
    value = 75.3
    result = format_number(value, 1, "", "%")
    print(f"\n  Input: {value}%")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if "\\%" in result and "\\." in result else f"  ❌ FALHOU")
    
    # Teste 3: None
    value = None
    result = format_number(value)
    print(f"\n  Input: None")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if result == "N/A" else f"  ❌ FALHOU")


def test_build_safe_line():
    """Testa construção de linhas seguras"""
    print("\n" + "="*60)
    print("TESTE 4: Construção de Linhas Seguras")
    print("="*60)
    
    # Teste 1: Linha simples
    result = build_safe_line("PnL: ", "$120.50")
    print(f"\n  Input: 'PnL: ' + '$120.50'")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if "\\$" in result and "\\." in result else f"  ❌ FALHOU")
    
    # Teste 2: Com emoji
    result = build_safe_line("Trades: ", "5", "📊")
    print(f"\n  Input: '📊' + 'Trades: ' + '5'")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if "📊" in result else f"  ❌ FALHOU")
    
    # Teste 3: Valor None
    result = build_safe_line("Symbol: ", None)
    print(f"\n  Input: 'Symbol: ' + None")
    print(f"  Output: {result}")
    print(f"  ✅ OK" if "N/A" in result else f"  ❌ FALHOU")


def test_problematic_cases():
    """Testa casos que causariam erro 400 no Telegram"""
    print("\n" + "="*60)
    print("TESTE 5: Casos Problemáticos do Telegram")
    print("="*60)
    
    # Caso 1: Emoji + asterisco (causava erro)
    text = "📊 **RESUMO**"
    result = sanitize_telegram_message(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  ✅ Asteriscos removidos" if "**" not in result else f"  ❌ FALHOU")
    
    # Caso 2: Underline duplo
    text = "__texto__"
    result = sanitize_telegram_message(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  ✅ Underlines removidos" if "__" not in result else f"  ❌ FALHOU")
    
    # Caso 3: Porcentagem não escapada
    text = "Win Rate: 75%"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    print(f"  ✅ % escapado" if "\\%" in result else f"  ❌ FALHOU")
    
    # Caso 4: String completa do diário
    text = "• PnL Realizado: $120.50"
    result = escape_markdown_v2(text)
    print(f"\n  Input: {text}")
    print(f"  Output: {result}")
    
    # Verifica escapes
    has_dollar = "\\$" in result
    has_dot = "\\." in result
    print(f"  ✅ Escapado corretamente" if has_dollar and has_dot else f"  ❌ FALHOU")


def test_full_message():
    """Testa mensagem completa como seria enviada"""
    print("\n" + "="*60)
    print("TESTE 6: Mensagem Completa")
    print("="*60)
    
    # Simula parte do diário
    lines = []
    lines.append(escape_markdown_v2("DIÁRIO DE TRADING"))
    lines.append(escape_markdown_v2("=" * 30))
    lines.append(build_safe_line("• Trades fechados: ", "5"))
    lines.append(build_safe_line("• Win Rate: ", "80.0%"))
    lines.append(build_safe_line("• PnL: ", "$120.50"))
    lines.append(escape_markdown_v2("✅ Win rate excelente!"))
    
    msg = "\n".join(lines)
    
    print(f"\n  Mensagem construída:")
    print(f"  {'-'*40}")
    print(f"  {msg}")
    print(f"  {'-'*40}")
    
    # Verifica se não tem caracteres sem escape
    problematic = ['_', '*', '[', ']', '(', ')', '`', '#', '+', '=', '|', '{', '}', '!']
    unescaped = []
    
    for char in problematic:
        if char in msg and f"\\{char}" not in msg:
            # Verifica se é realmente sem escape (não parte de um escape)
            if msg.count(char) > msg.count(f"\\{char}"):
                unescaped.append(char)
    
    # Verifica % especificamente
    if "%" in msg and "\\%" not in msg:
        unescaped.append('%')
    
    if unescaped:
        print(f"\n  ⚠️ Caracteres sem escape encontrados: {unescaped}")
    else:
        print(f"\n  ✅ Todos caracteres especiais escapados")
    
    print(f"\n  ✅ Pronto para envio ao Telegram")


if __name__ == "__main__":
    print("\n🧪 TESTANDO TELEGRAM SANITIZER\n")
    
    test_escape_basic()
    test_escape_complex()
    test_format_number()
    test_build_safe_line()
    test_problematic_cases()
    test_full_message()
    
    print("\n" + "="*60)
    print("✅ TODOS OS TESTES CONCLUÍDOS")
    print("="*60 + "\n")
