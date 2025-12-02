#!/usr/bin/env python3
"""
Script de Verificação Pré-Deploy
Verifica se tudo está pronto para deploy no Railway
"""
import os
import sys
from pathlib import Path

def check_file(filepath, description):
    """Verifica se arquivo existe"""
    if Path(filepath).exists():
        print(f"✅ {description}")
        return True
    else:
        print(f"❌ {description} - FALTANDO!")
        return False

def check_requirements():
    """Verifica requirements.txt"""
    if not Path('requirements.txt').exists():
        print("❌ requirements.txt não encontrado!")
        return False
    
    with open('requirements.txt', 'r') as f:
        content = f.read()
        required = ['anthropic', 'eth-account', 'requests', 'numpy', 'pandas', 'python-dotenv']
        missing = [pkg for pkg in required if pkg not in content]
        
        if missing:
            print(f"❌ requirements.txt falta: {', '.join(missing)}")
            return False
        else:
            print("✅ requirements.txt completo")
            return True

def check_env_vars():
    """Lista variáveis que devem ser configuradas no Railway"""
    print("\n📋 VARIÁVEIS QUE VOCÊ DEVE CONFIGURAR NO RAILWAY:")
    print("-" * 60)
    
    required_vars = [
        "HYPERLIQUID_WALLET_ADDRESS",
        "HYPERLIQUID_PRIVATE_KEY",
        "HYPERLIQUID_NETWORK",
        "ANTHROPIC_API_KEY",
        "AI_MODEL",
        "LIVE_TRADING",
        "PAIRS_TO_TRADE",
        "RISK_PER_TRADE_PCT",
        "MAX_DAILY_DRAWDOWN_PCT",
        "MAX_OPEN_TRADES",
        "MAX_LEVERAGE",
        "MIN_NOTIONAL",
        "DEFAULT_STOP_PCT",
        "DEFAULT_TP_PCT",
        "TRADING_LOOP_SLEEP_SECONDS",
        "LOG_LEVEL"
    ]
    
    for var in required_vars:
        print(f"  • {var}")
    
    print("\n⚠️  Configure TODAS no Railway Dashboard → Variables")
    print("-" * 60)

def main():
    print("=" * 60)
    print("🔍 VERIFICAÇÃO PRÉ-DEPLOY - RAILWAY")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # Verifica arquivos essenciais
    print("📁 Verificando Arquivos Essenciais:")
    all_ok &= check_file('bot_hyperliquid.py', 'bot_hyperliquid.py')
    all_ok &= check_file('bot/__init__.py', 'bot/__init__.py')
    all_ok &= check_file('bot/risk_manager.py', 'bot/risk_manager.py')
    all_ok &= check_file('bot/ai_decision.py', 'bot/ai_decision.py')
    all_ok &= check_file('bot/position_manager.py', 'bot/position_manager.py')
    all_ok &= check_file('bot/market_context.py', 'bot/market_context.py')
    all_ok &= check_file('bot/indicators.py', 'bot/indicators.py')
    print()
    
    # Verifica arquivos Railway
    print("🚀 Verificando Arquivos Railway:")
    all_ok &= check_file('Procfile', 'Procfile')
    all_ok &= check_file('railway.json', 'railway.json')
    all_ok &= check_file('runtime.txt', 'runtime.txt')
    all_ok &= check_file('.gitignore', '.gitignore')
    all_ok &= check_file('.railwayignore', '.railwayignore')
    all_ok &= check_file('README_RAILWAY.md', 'README_RAILWAY.md')
    print()
    
    # Verifica requirements
    print("📦 Verificando Dependências:")
    all_ok &= check_requirements()
    print()
    
    # Lista variáveis de ambiente
    check_env_vars()
    print()
    
    # Verifica se .env está no .gitignore
    if Path('.gitignore').exists():
        with open('.gitignore', 'r') as f:
            if '.env' in f.read():
                print("✅ .env está no .gitignore (não será commitado)")
            else:
                print("⚠️  ADICIONE .env ao .gitignore!")
                all_ok = False
    print()
    
    # Resultado final
    print("=" * 60)
    if all_ok:
        print("✅ TUDO OK! PRONTO PARA DEPLOY!")
        print()
        print("📋 PRÓXIMOS PASSOS:")
        print("1. Crie repositório PRIVATE no GitHub")
        print("2. Faça upload destes arquivos (MENOS o .env)")
        print("3. Acesse railway.app e crie novo projeto")
        print("4. Conecte ao repositório GitHub")
        print("5. Configure as variáveis listadas acima")
        print("6. Railway fará deploy automático!")
        print()
        print("📖 Leia README_RAILWAY.md para instruções detalhadas")
        return 0
    else:
        print("❌ PROBLEMAS ENCONTRADOS!")
        print("Corrija os itens marcados com ❌ antes de fazer deploy")
        return 1
    print("=" * 60)

if __name__ == "__main__":
    sys.exit(main())
