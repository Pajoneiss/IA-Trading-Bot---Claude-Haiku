# PATCH: Telegram Execution Mode Control

## Resumo

Este patch adiciona controle do modo de execução (LIVE/PAPER_ONLY/SHADOW) via Telegram.

---

## O Que Foi Implementado

### 1. Novo Botão no Teclado
- **Botão:** `⚙️ Execução` (na 4ª linha do teclado)
- Abre o menu de seleção de modo de execução

### 2. Novo Comando
- **Comando:** `/execucao` (também aceita `/execution` e `/exec`)
- Exibe o modo atual e botões para trocar

### 3. Modo de Execução no Resumo
- O resumo (`📊 Resumo`) agora mostra:
  - `Execução: 🟢 LIVE` ou
  - `Execução: 📝 PAPER_ONLY` ou
  - `Execução: 👥 SHADOW`

### 4. Verificação de Permissão
- Apenas o usuário com `TELEGRAM_CHAT_ID` pode alterar o modo
- Outros usuários recebem: "⛔ Você não tem permissão..."

### 5. Logs Detalhados
```
[EXECUTION_MODE] Menu exibido para chat_id=123456789, modo atual=LIVE
[EXECUTION_MODE] Alterado de LIVE para PAPER_ONLY por user_id=123456789
[EXECUTION_MODE] Tentativa de alteração negada para chat_id=999999999
```

---

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `bot/telegram_interactive_pro.py` | Handlers, botões, verificação de permissão |
| `bot_hyperliquid.py` | Inicialização do ExecutionManager |
| `data/execution_state.json` | Estado inicial (PAPER_ONLY) |

---

## Como Usar

### Via Telegram:

1. **Ver modo atual:**
   - Clique em `📊 Resumo` - mostra o modo na segunda linha
   - Ou use `/execucao` para ver detalhes

2. **Trocar modo:**
   - Clique em `⚙️ Execução`
   - Ou use `/execucao`
   - Clique no botão do modo desejado: `[LIVE]` `[PAPER]` `[SHADOW]`

3. **Verificar se mudou:**
   - O menu reaparece com ✅ no modo selecionado
   - O resumo mostra o novo modo

---

## Modos Disponíveis

| Modo | Descrição | Ícone |
|------|-----------|-------|
| **LIVE** | Envia ordens reais na Hyperliquid | 🟢 |
| **PAPER_ONLY** | Apenas simulação (sem ordens reais) | 📝 |
| **SHADOW** | Ordens reais + experimentos paper em paralelo | 👥 |

---

## Segurança

- ⚠️ O modo é persistido em `data/execution_state.json`
- ⚠️ Apenas o dono (TELEGRAM_CHAT_ID) pode alterar
- ⚠️ O modo inicial padrão é PAPER_ONLY (seguro)
- ⚠️ Alterações são logadas com user_id

---

## O Que NÃO Foi Alterado

✅ Lógica de risco (2.5% por trade, circuit breaker)
✅ Risk Manager, Position Manager
✅ Quality Gate, Market Regime
✅ Modos de trading (Conservador/Balanceado/Agressivo)
✅ Integração Hyperliquid

---

## Exemplo de Logs

```
[EXECUTION] Modo inicial: PAPER_ONLY
[TELEGRAM] /execucao recebido de chat_id=123456789
[EXECUTION_MODE] Menu exibido para chat_id=123456789, modo atual=PAPER_ONLY
[EXECUTION] Modo alterado: PAPER_ONLY -> LIVE (fonte: telegram_user_123456789)
[EXECUTION_MODE] Alterado de PAPER_ONLY para LIVE por user_id=123456789
```

---

## Troubleshooting

### "Execution Manager não disponível"
- Verifique se `bot_hyperliquid.py` está inicializando `self.execution_manager`

### "Você não tem permissão"
- Verifique se seu `TELEGRAM_CHAT_ID` está correto no `.env`

### Modo não persiste após reiniciar
- Verifique se `data/execution_state.json` existe e é gravável
