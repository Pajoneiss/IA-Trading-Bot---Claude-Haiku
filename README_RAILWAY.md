# 🚀 DEPLOY NO RAILWAY - GUIA COMPLETO PASSO A PASSO

Este guia te ensina a colocar seu bot Hyperliquid rodando 24/7 no Railway em **menos de 10 minutos**!

---

## 📋 O QUE VOCÊ VAI PRECISAR

- ✅ Conta no GitHub (crie grátis em https://github.com)
- ✅ Conta no Railway (crie grátis em https://railway.app)
- ✅ Os arquivos deste projeto
- ✅ Suas credenciais (wallet, API keys)

**Custo:** $5/mês (Railway Hobby Plan) - Tem crédito grátis pra começar!

---

## 🎯 MÉTODO 1: VIA GITHUB (RECOMENDADO - MAIS FÁCIL!)

Este método é o mais fácil porque Railway faz deploy automático sempre que você atualizar o código.

### **Passo 1: Criar Repositório no GitHub**

1. Acesse https://github.com
2. Clique no **"+"** no canto superior direito
3. Selecione **"New repository"**
4. Configure:
   - **Repository name:** `hyperliquid-bot` (ou qualquer nome)
   - **Visibility:** 🔒 **Private** (IMPORTANTE! Tem credenciais)
   - Deixe desmarcado "Add a README file"
5. Clique **"Create repository"**

### **Passo 2: Subir Arquivos para o GitHub**

**Opção A - Via Interface Web (Mais Fácil):**

1. No repositório criado, clique em **"uploading an existing file"**
2. Arraste **TODOS** os arquivos do projeto:
   ```
   bot_hyperliquid.py
   bot/ (pasta inteira)
   requirements.txt
   Procfile
   railway.json
   runtime.txt
   .gitignore
   .railwayignore
   README_RAILWAY.md
   ```
3. ⚠️ **NÃO** envie o arquivo `.env` (tem suas credenciais!)
4. Escreva "Initial commit" na descrição
5. Clique **"Commit changes"**

**Opção B - Via Git (Linha de Comando):**

```bash
# Abra PowerShell/CMD na pasta do projeto
cd C:\Users\seu-usuario\hyperliquid-mcp-bruno

# Inicializa git
git init

# Adiciona arquivos
git add .
git commit -m "Initial commit"

# Conecta com GitHub
git remote add origin https://github.com/SEU-USUARIO/hyperliquid-bot.git
git branch -M main
git push -u origin main
```

### **Passo 3: Criar Projeto no Railway**

1. Acesse https://railway.app
2. Clique **"Login"** → Escolha **"Login with GitHub"**
3. Autorize Railway a acessar seus repositórios
4. No dashboard, clique **"New Project"**
5. Selecione **"Deploy from GitHub repo"**
6. Escolha o repositório **`hyperliquid-bot`**
7. Railway detecta automaticamente que é Python! ✅

### **Passo 4: Configurar Variáveis de Ambiente (CRÍTICO!)**

No Railway:

1. Clique no seu projeto (card azul/roxo)
2. Vá na aba **"Variables"**
3. Clique **"+ New Variable"**
4. Adicione **UMA POR UMA** estas variáveis:

```
HYPERLIQUID_WALLET_ADDRESS
→ Valor: your_wallet_address_here

HYPERLIQUID_PRIVATE_KEY
→ Valor: your_private_key_here

HYPERLIQUID_NETWORK
→ Valor: mainnet

ANTHROPIC_API_KEY
→ Valor: your_anthropic_api_key_here

AI_MODEL
→ Valor: claude-3-5-haiku-20241022

LIVE_TRADING
→ Valor: true

PAIRS_TO_TRADE
→ Valor: BTC,ETH,SOL

RISK_PER_TRADE_PCT
→ Valor: 2.0

MAX_DAILY_DRAWDOWN_PCT
→ Valor: 10.0

MAX_OPEN_TRADES
→ Valor: 3

MAX_LEVERAGE
→ Valor: 50

MIN_NOTIONAL
→ Valor: 0.5

DEFAULT_STOP_PCT
→ Valor: 2.0

DEFAULT_TP_PCT
→ Valor: 4.0

TRADING_LOOP_SLEEP_SECONDS
→ Valor: 30

LOG_LEVEL
→ Valor: INFO
```

⚠️ **ATENÇÃO:** 
- Copie e cole EXATAMENTE como está acima
- Não deixe espaços no início/fim
- Confira se `LIVE_TRADING=true` (para operar real)

### **Passo 5: Deploy Automático!**

Railway vai automaticamente:
1. ✅ Detectar que é Python
2. ✅ Instalar dependências (`requirements.txt`)
3. ✅ Rodar o bot (`Procfile`)
4. ✅ Começar a operar! 🚀

**Tempo estimado:** 2-3 minutos

### **Passo 6: Ver Logs em Tempo Real**

1. No Railway, clique no seu projeto
2. Aba **"Deployments"**
3. Clique no deployment ativo (verde)
4. Veja os logs rolando! 📊

Você deve ver:
```
[INFO] 🤖 HYPERLIQUID BOT INICIALIZADO
[INFO] Network: mainnet
[INFO] Wallet: 0x96E09Fb5...
[INFO] IA: Ativada ✅
[INFO] Modo: LIVE TRADING ⚠️

[INFO] 📊 Buscando dados de mercado...
[INFO] Equity=$112.25 | DD_Dia=+0.00% | Posições=3/3
...
```

---

## 🎯 MÉTODO 2: VIA RAILWAY CLI (ALTERNATIVO)

Se preferir usar linha de comando:

### **Passo 1: Instalar Railway CLI**

**Windows (PowerShell):**
```powershell
iwr https://railway.app/install.ps1 | iex
```

**Mac/Linux:**
```bash
curl -fsSL https://railway.app/install.sh | sh
```

### **Passo 2: Login**

```bash
railway login
```

### **Passo 3: Deploy**

```bash
cd C:\Users\seu-usuario\hyperliquid-mcp-bruno
railway init
railway up
```

### **Passo 4: Configurar Variáveis**

Via interface web (mais fácil) ou CLI:

```bash
railway variables set HYPERLIQUID_WALLET_ADDRESS="your_wallet_address_here"
railway variables set HYPERLIQUID_PRIVATE_KEY="your_private_key_here"
railway variables set ANTHROPIC_API_KEY="your_anthropic_api_key_here"
# ... etc (todas as outras)
```

---

## 📊 MONITORAMENTO

### **Ver Logs**

**Via Web:**
1. Dashboard → Seu Projeto → Deployments → View Logs

**Via CLI:**
```bash
railway logs
```

### **Status do Bot**

Você verá nos logs:
- ✅ Conexões com Hyperliquid
- ✅ Análises de mercado
- ✅ Decisões da IA
- ✅ Ordens executadas
- ✅ Stops/TPs acionados

---

## 🔧 GERENCIAMENTO

### **Pausar o Bot**

1. Railway Dashboard → Seu Projeto
2. Botão **"Stop"** (canto superior)

### **Reiniciar o Bot**

1. Railway Dashboard → Seu Projeto
2. Botão **"Restart"**

### **Atualizar o Bot**

**Se usou GitHub:**
```bash
# Edita arquivos localmente
git add .
git commit -m "Atualização"
git push

# Railway faz redeploy AUTOMÁTICO! ✅
```

**Se usou CLI:**
```bash
railway up
```

### **Mudar Configurações**

1. Variables → Edita a variável
2. Railway reinicia automaticamente

Exemplo: Mudar de `LIVE_TRADING=true` para `false`:
- Variables → LIVE_TRADING → Edit → `false` → Save

---

## 💰 CUSTOS E LIMITES

### **Plano Hobby ($5/mês):**
- ✅ 500 horas de execução/mês
- ✅ Reinício automático
- ✅ Logs ilimitados
- ✅ 5GB de RAM
- ✅ 1GB de disco

**Seu bot usa ~720h/mês (24/7), então precisa do Hobby Plan.**

### **Trial Grátis:**
- $5 de crédito grátis
- ~1 mês grátis para testar!

---

## ⚠️ SEGURANÇA

### **Protegendo suas Credenciais:**

✅ **FAÇA:**
- Use repositório **PRIVATE** no GitHub
- Configure variáveis no Railway (não no código)
- Nunca commite o `.env`
- `.gitignore` já está configurado para isso

❌ **NÃO FAÇA:**
- Repositório público com credenciais
- Hard-code de API keys no código
- Compartilhar screenshots com variáveis visíveis

### **Backups:**

Railway faz backup automático, mas recomendo:
1. Exportar variáveis ocasionalmente
2. Fazer backup do código localmente

---

## 🐛 TROUBLESHOOTING

### **Bot não inicia:**

**Erro:** "Module not found"
- **Solução:** Verifica `requirements.txt` está no repositório

**Erro:** "Environment variable not found"
- **Solução:** Confere variáveis no Railway → Variables

**Erro:** "Build failed"
- **Solução:** Verifica `Procfile` e `railway.json` estão corretos

### **Bot para depois de um tempo:**

- **Causa:** Erro não tratado
- **Solução:** Verifica logs → procura erro → corrige código

### **Não consigo ver logs:**

1. Railway Dashboard
2. Seu Projeto → Deployments
3. Clica no deployment ativo
4. Logs aparecem na parte inferior

### **Bot não executa ordens:**

1. Verifica `LIVE_TRADING=true`
2. Verifica credenciais da Hyperliquid
3. Checa saldo disponível
4. Vê logs para mensagens de erro

---

## 📱 ACESSO REMOTO

### **Ver Status de Qualquer Lugar:**

1. Acessa https://railway.app no celular/tablet
2. Login → Seu Projeto
3. Vê logs em tempo real! 📊

### **App Railway (Mobile):**

Disponível para iOS/Android:
- https://railway.app/mobile

---

## 🚀 PRÓXIMOS PASSOS APÓS DEPLOY

### **1. Verificar Primeira Execução (5 min)**

Acompanhe os logs para ver:
- ✅ Conexão com Hyperliquid
- ✅ Leitura das posições existentes
- ✅ Primeira análise de mercado
- ✅ Decisão da IA

### **2. Monitorar Primeiro Dia (24h)**

- Vê se o bot está tomando decisões sensatas
- Confere se os stops estão sendo respeitados
- Valida se o risk management está funcionando

### **3. Ajustes Finos (Depois de 2-3 dias)**

Se necessário, ajuste variáveis:
- `RISK_PER_TRADE_PCT` (mais/menos agressivo)
- `TRADING_LOOP_SLEEP_SECONDS` (frequência de análise)
- `PAIRS_TO_TRADE` (adicionar/remover pares)

---

## 📞 SUPORTE

### **Railway:**
- Docs: https://docs.railway.app
- Discord: https://discord.gg/railway
- Status: https://status.railway.app

### **Bot Issues:**
- Logs primeiro!
- Procura erro específico
- Ajusta variáveis se necessário

---

## ✅ CHECKLIST FINAL

Antes de considerar concluído:

- [ ] Repositório GitHub criado (Private)
- [ ] Arquivos enviados ao GitHub
- [ ] Projeto Railway criado
- [ ] Deploy conectado ao GitHub
- [ ] **TODAS** variáveis configuradas
- [ ] `LIVE_TRADING=true` (se quer operar real)
- [ ] Bot iniciou (vê logs)
- [ ] Primeira análise executada
- [ ] Testei pausar/reiniciar
- [ ] Salvei link do projeto Railway

---

## 🎉 PRONTO!

Seu bot está rodando 24/7 no Railway! 🚀

**Você pode:**
- ✅ Fechar o navegador
- ✅ Desligar o PC
- ✅ Sair de férias
- ✅ Bot continua operando!

**Acesse de qualquer lugar:**
- https://railway.app → Login → Seu Projeto → Logs

---

## 💡 DICAS EXTRAS

1. **Bookmark do Railway:** Salve nos favoritos para acesso rápido

2. **App Mobile:** Instale app Railway para ver logs no celular

3. **Notificações:** Railway envia email se bot crashar

4. **Upgrades:** Se quiser mais recursos, upgrade para Pro ($20/mês)

5. **Multi-Região:** Railway usa servidores na América, Europa, Ásia

---

## 🔔 IMPORTANTE - LEIA!

⚠️ **RESPONSABILIDADE:**
- Bot opera com dinheiro real
- Mercado é volátil
- Pode haver perdas
- Monitore regularmente
- Não invista mais do que pode perder

✅ **BOAS PRÁTICAS:**
- Monitore diariamente (pelo menos)
- Ajuste estratégia conforme resultados
- Faça backups das configurações
- Teste mudanças em DRY_RUN primeiro

---

**Boa sorte com seu bot! 🚀📈**

Se tiver dúvidas, consulte a documentação ou logs!
