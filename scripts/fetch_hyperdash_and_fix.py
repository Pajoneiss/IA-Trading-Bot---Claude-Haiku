#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para buscar dados históricos do HyperDash e corrigir baselines de PnL.

Uso:
    python fetch_hyperdash_and_fix.py
"""

import requests
from datetime import datetime, timedelta, timezone
import time
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Configuração
WALLET_ADDRESS = "0x96E09Fb536CfB0E424Df3B496F9353b98704bA24"
BOT_API_URL = "https://inspetorpro.up.railway.app"
BOT_API_KEY = "inspetorpro159"

def fetch_hyperdash_history():
    """
    Busca histórico de equity do HyperDash.
    
    HyperDash API endpoints (baseado em análise da página):
    - https://api.hyperliquid.xyz/info
    - Method: POST
    - Body: {"type": "userFunding", "user": "0x..."}
    """
    
    print("[*] Buscando dados históricos do HyperDash...")
    
    # Endpoint da Hyperliquid para dados do usuário
    url = "https://api.hyperliquid.xyz/info"
    
    # Tenta buscar snapshots de account value
    headers = {"Content-Type": "application/json"}
    
    # Primeiro, vamos buscar o estado atual
    payload = {
        "type": "clearinghouseState",
        "user": WALLET_ADDRESS
    }
    
    try:
        print(f"[*] Consultando Hyperliquid API para {WALLET_ADDRESS[:10]}...")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        print("[+] Dados recebidos!")
        
        # Extrai account value atual
        if 'marginSummary' in data:
            current_equity = float(data['marginSummary']['accountValue'])
            print(f"[+] Equity atual: ${current_equity:.2f}")
            return current_equity
        else:
            print("[!] Formato de resposta inesperado")
            print(f"Resposta: {data}")
            return None
            
    except Exception as e:
        print(f"[-] Erro ao buscar dados: {e}")
        return None

def estimate_historical_equity(current_equity):
    """
    Estima equity histórico baseado em PnL médio.
    
    Como não temos acesso direto ao histórico do HyperDash via API pública,
    vamos usar uma abordagem conservadora:
    
    1. Buscar PnL summary atual do bot
    2. Calcular equity histórico baseado nos PnLs realizados
    """
    
    print("\n[*] Estimando equity histórico...")
    
    # Busca PnL summary do bot
    url = f"{BOT_API_URL}/api/pnl/summary"
    headers = {"X-API-KEY": BOT_API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        pnl = response.json()
        
        print("[*] PnL Summary atual:")
        print(f"  Current Equity: ${pnl.get('current_equity', 0):.2f}")
        print(f"  ALL TIME: {pnl.get('pnl_all_time_pct', 0):.2f}% (${pnl.get('pnl_all_time_usd', 0):.2f})")
        
        # Se temos ALL TIME PnL, podemos calcular equity inicial
        all_time_usd = pnl.get('pnl_all_time_usd', 0)
        
        if all_time_usd > 0:
            # Equity inicial = Equity atual - PnL ALL TIME
            initial_equity = current_equity - all_time_usd
            print(f"\n[+] Equity inicial estimado: ${initial_equity:.2f}")
            
            # Estima equity há 7 dias (assumindo crescimento linear)
            # Isso é uma aproximação - idealmente usaríamos dados reais
            days_total = 43  # Aproximadamente de 01/11 até hoje (13/12)
            daily_growth = all_time_usd / days_total if days_total > 0 else 0
            
            equity_7d_ago = current_equity - (daily_growth * 7)
            equity_30d_ago = current_equity - (daily_growth * 30)
            
            print(f"[+] Equity há 7 dias (estimado): ${equity_7d_ago:.2f}")
            print(f"[+] Equity há 30 dias (estimado): ${equity_30d_ago:.2f}")
            
            return {
                'initial': initial_equity,
                'week': equity_7d_ago,
                'month': equity_30d_ago
            }
        else:
            print("[!] Sem dados de PnL ALL TIME suficientes")
            return None
            
    except Exception as e:
        print(f"[-] Erro ao buscar PnL: {e}")
        return None

def set_baseline(equity: float, date: str, period: str = "all_time"):
    """Define baseline via API."""
    
    url = f"{BOT_API_URL}/api/set-initial-equity"
    headers = {
        'X-API-KEY': BOT_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = {
        'initial_equity': equity,
        'start_date': date
    }
    
    print(f"\n[*] Setando baseline {period.upper()}: ${equity:.2f} @ {date}")
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'ok':
            print(f"[+] Baseline {period} atualizado!")
            return True
        else:
            print(f"[-] Erro: {data.get('error', 'Unknown')}")
            return False
            
    except Exception as e:
        print(f"[-] Erro na requisição: {e}")
        return False

def main():
    print("=" * 60)
    print("InspetorPro - Auto Fix PnL Baselines")
    print("=" * 60)
    print(f"Wallet: {WALLET_ADDRESS}")
    print("=" * 60)
    
    # 1. Busca equity atual do HyperDash
    current_equity = fetch_hyperdash_history()
    
    if not current_equity:
        print("\n[-] Não foi possível obter equity atual. Abortando.")
        return
    
    # 2. Estima equity histórico
    historical = estimate_historical_equity(current_equity)
    
    if not historical:
        print("\n[!] Usando equity atual como baseline (opção conservadora)")
        historical = {
            'initial': current_equity,
            'week': current_equity,
            'month': current_equity
        }
    
    # 3. Calcula datas
    today = datetime.now(timezone.utc)
    date_all_time = "2024-11-01"  # Data aproximada de início
    date_week = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    date_month = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    
    print("\n" + "=" * 60)
    print("Baselines a serem aplicados:")
    print("=" * 60)
    print(f"ALL TIME: ${historical['initial']:.2f} @ {date_all_time}")
    print(f"WEEK:     ${historical['week']:.2f} @ {date_week}")
    print(f"MONTH:    ${historical['month']:.2f} @ {date_month}")
    print("=" * 60)
    
    # Confirmação
    print("\n[!] ATENÇÃO: Isso vai sobrescrever os baselines atuais!")
    print("Pressione ENTER para continuar ou Ctrl+C para cancelar...")
    try:
        input()
    except KeyboardInterrupt:
        print("\n[!] Cancelado pelo usuário.")
        return
    
    # 4. Aplica baselines
    success_count = 0
    
    if set_baseline(historical['initial'], date_all_time, 'all_time'):
        success_count += 1
        time.sleep(1)
    
    if set_baseline(historical['week'], date_week, 'week'):
        success_count += 1
        time.sleep(1)
    
    if set_baseline(historical['month'], date_month, 'month'):
        success_count += 1
    
    # 5. Resultado
    print("\n" + "=" * 60)
    print(f"[+] {success_count}/3 baselines atualizados com sucesso!")
    print("=" * 60)
    
    if success_count == 3:
        print("\n[+] Sucesso! Aguarde 10-30 segundos e recarregue o dashboard:")
        print(f"   {BOT_API_URL}")
        print("\n[+] Agora os PnLs 24H, 7D e 30D devem mostrar valores diferentes!")
    else:
        print("\n[!] Alguns baselines falharam. Verifique os logs acima.")

if __name__ == '__main__':
    main()
