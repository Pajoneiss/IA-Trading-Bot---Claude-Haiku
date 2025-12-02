import sys
import os

# Adiciona o diretório raiz ao path para importar os módulos
sys.path.append(os.path.abspath("g:/Pajôneis/Mercado Financeiro/IA BOT/Versão 4 (Telegram Adicionado)/PRIVATE-main"))

from bot.risk_manager import RiskManager

def verify_fix():
    print("Verifying RiskManager fix...")
    try:
        rm = RiskManager()
        # Simula atualização de equity
        rm.update_equity(1000)
        
        # Tenta acessar o atributo que estava faltando
        pnl = rm.daily_pnl_pct
        
        print(f"SUCCESS: RiskManager.daily_pnl_pct accessed successfully. Value: {pnl}")
        return True
    except AttributeError as e:
        print(f"FAILURE: AttributeError still present: {e}")
        return False
    except Exception as e:
        print(f"FAILURE: Unexpected error: {e}")
        return False

if __name__ == "__main__":
    if verify_fix():
        sys.exit(0)
    else:
        sys.exit(1)
