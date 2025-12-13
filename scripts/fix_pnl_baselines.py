#!/usr/bin/env python3
"""
Script para corrigir baselines de PnL no InspetorPro.

Uso:
    python fix_pnl_baselines.py --all-time 10.0 --all-time-date 2024-11-01
    python fix_pnl_baselines.py --week 42.0 --week-date 2024-12-06
    python fix_pnl_baselines.py --month 35.0 --month-date 2024-12-01
    
Ou todos de uma vez:
    python fix_pnl_baselines.py \\
        --all-time 10.0 --all-time-date 2024-11-01 \\
        --week 42.0 --week-date 2024-12-06 \\
        --month 35.0 --month-date 2024-12-01
"""

import argparse
import requests
import os
from datetime import datetime, timedelta

# Configuração
API_BASE_URL = os.getenv('BOT_API_URL', 'https://inspetorpro.up.railway.app')
API_KEY = os.getenv('BOT_API_KEY', 'inspetorpro159')

def set_baseline(period: str, equity: float, date: str):
    """
    Define baseline para um período específico.
    
    Args:
        period: 'all_time', 'week', 'month', ou 'day'
        equity: Equity naquela data
        date: Data no formato YYYY-MM-DD
    """
    url = f"{API_BASE_URL}/api/set-initial-equity"
    headers = {
        'X-API-KEY': API_KEY,
        'Content-Type': 'application/json'
    }
    payload = {
        'initial_equity': equity,
        'start_date': date
    }
    
    print(f"📊 Setando baseline {period.upper()}: ${equity} @ {date}")
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'ok':
            print(f"✅ Baseline {period} atualizado com sucesso!")
            return True
        else:
            print(f"❌ Erro: {data.get('error', 'Unknown error')}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def estimate_dates():
    """Estima datas baseado em hoje."""
    today = datetime.now()
    
    return {
        'day': today.replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d'),
        'week': (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d'),
        'month': today.replace(day=1).strftime('%Y-%m-%d'),
    }

def get_current_pnl():
    """Busca PnL atual para referência."""
    url = f"{API_BASE_URL}/api/pnl/summary"
    headers = {'X-API-KEY': API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        print("\n📈 PnL Atual:")
        print(f"  Current Equity: ${data.get('current_equity', 0):.2f}")
        print(f"  ALL TIME: {data.get('pnl_all_time_pct', 0):.2f}% (${data.get('pnl_all_time_usd', 0):.2f})")
        print(f"  24H: {data.get('pnl_day_pct', 0):.2f}% (${data.get('pnl_day_usd', 0):.2f})")
        print(f"  7D: {data.get('pnl_week_pct', 0):.2f}% (${data.get('pnl_week_usd', 0):.2f})")
        print(f"  30D: {data.get('pnl_month_pct', 0):.2f}% (${data.get('pnl_month_usd', 0):.2f})")
        print()
        
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao buscar PnL: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Fix InspetorPro PnL baselines')
    
    # ALL TIME
    parser.add_argument('--all-time', type=float, help='Equity inicial (ALL TIME)')
    parser.add_argument('--all-time-date', type=str, help='Data inicial (YYYY-MM-DD)')
    
    # WEEK
    parser.add_argument('--week', type=float, help='Equity há 7 dias')
    parser.add_argument('--week-date', type=str, help='Data há 7 dias (YYYY-MM-DD)')
    
    # MONTH
    parser.add_argument('--month', type=float, help='Equity há 30 dias')
    parser.add_argument('--month-date', type=str, help='Data há 30 dias (YYYY-MM-DD)')
    
    # DAY
    parser.add_argument('--day', type=float, help='Equity no início do dia')
    parser.add_argument('--day-date', type=str, help='Data do dia (YYYY-MM-DD)')
    
    # Options
    parser.add_argument('--show-current', action='store_true', help='Mostrar PnL atual')
    parser.add_argument('--estimate-dates', action='store_true', help='Estimar datas baseado em hoje')
    
    args = parser.parse_args()
    
    print("🔧 InspetorPro - Fix PnL Baselines")
    print("=" * 50)
    
    # Show current PnL
    if args.show_current or (not any([args.all_time, args.week, args.month, args.day])):
        get_current_pnl()
    
    # Estimate dates
    if args.estimate_dates:
        dates = estimate_dates()
        print("📅 Datas estimadas:")
        for period, date in dates.items():
            print(f"  {period}: {date}")
        print()
    
    # Set baselines
    success_count = 0
    total_count = 0
    
    if args.all_time and args.all_time_date:
        total_count += 1
        if set_baseline('all_time', args.all_time, args.all_time_date):
            success_count += 1
    
    if args.week and args.week_date:
        total_count += 1
        if set_baseline('week', args.week, args.week_date):
            success_count += 1
    
    if args.month and args.month_date:
        total_count += 1
        if set_baseline('month', args.month, args.month_date):
            success_count += 1
    
    if args.day and args.day_date:
        total_count += 1
        if set_baseline('day', args.day, args.day_date):
            success_count += 1
    
    # Summary
    if total_count > 0:
        print("\n" + "=" * 50)
        print(f"✅ {success_count}/{total_count} baselines atualizados com sucesso!")
        print("\n🔄 Aguarde alguns segundos e verifique o dashboard:")
        print(f"   {API_BASE_URL}")
        print("\n💡 Dica: Use --show-current para ver os novos valores de PnL")
    else:
        print("\n💡 Uso:")
        print("  python fix_pnl_baselines.py --show-current")
        print("  python fix_pnl_baselines.py --all-time 10.0 --all-time-date 2024-11-01")
        print("\nPara mais opções: python fix_pnl_baselines.py --help")

if __name__ == '__main__':
    main()
