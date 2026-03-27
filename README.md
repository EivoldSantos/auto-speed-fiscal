# SPED Autocorretor — Projeto Full Stack

Validação e correção automática de arquivos **SPED EFD ICMS/IPI** e **SPED EFD-Contribuições (PIS/COFINS)**.

## Stack

- **Backend:** Python 3.10+ · FastAPI · SQLite
- **Frontend:** Next.js 14 · React 18 · Tailwind CSS · Recharts
- **Engines:** Baseadas nos `descritor.xml` oficiais do PVA SERPRO (267 registros ICMS/IPI + 182 registros Contribuições)

## Pré-requisitos

- Python 3.10 ou superior
- Node.js 18 ou superior
- npm

## Instalação e execução

### Windows
```
iniciar.bat
```

### Linux / Mac
```bash
chmod +x iniciar.sh
./iniciar.sh
```

### Manual

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Acesse **http://localhost:3000**

## Tipos de SPED suportados

O sistema detecta automaticamente o tipo de arquivo SPED enviado e aplica a engine correta.

### SPED EFD ICMS/IPI

| Correção | Descrição |
|----------|-----------|
| COD_VER | Corrige versão do leiaute pelo período |
| H010 IND_PROP | Corrige campo de propriedade do estoque |
| DESCR_ITEM | Trunca para 60 chars, remove pipe literal |
| UNID | Trunca para 6 chars (0190, C170, H010) |
| C190 | Gera automaticamente via C170 ou CST=300/CFOP=5102 para NFC-e |
| E110 | Recalcula VL_ICMS_RECOLHER e VL_SLD_CREDOR_TRANSPORTAR |
| E250 | Gera E250 quando E210 tem ICMS-ST a recolher |
| C990/9900/9999 | Atualiza todos os contadores de bloco |
| fixLen genérico | Aplica tamanhos máximos do leiaute em todos os 267 registros |

### SPED EFD-Contribuições (PIS/COFINS)

| Correção | Descrição |
|----------|-----------|
| COD_VER | Corrige versão do leiaute pelo período |
| IND_REG_CUM | Auto-corrige para regime cumulativo com detalhamento C100 |
| IND_ESCRI (C010) | Detecta e corrige indicador de escrituração por estabelecimento |
| Blocos ausentes | Insere blocos faltantes (X001+X990) na ordem correta |
| Bloco I | Remove condicionalmente para regime cumulativo |
| IND_MOV | Corrige inconsistência de movimento vs dados nos blocos |
| CST_PIS/CST_COFINS vazio | Preenche com 49 para operações de saída (C170) |
| C175 para NFC-e | Gera registro C175 para cada C100 MOD=65 sem detalhamento |
| VL_MERC (C100 NFC-e) | Preenche VL_MERC com VL_DOC quando zerado |
| Bloco M completo | Auto-gera M200/M210/M400/M410/M600/M610/M800/M810 |
| Recálculo PIS/COFINS | Recalcula VL_PIS e VL_COFINS em C170 e C175 |
| Campos insuficientes | Completa pipes faltantes conforme leiaute |
| C990/9900/9999 | Atualiza todos os contadores de bloco |

## API

Documentação interativa disponível em **http://localhost:8000/docs**

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/processar` | POST | Envia arquivo .txt (detecta tipo automaticamente) |
| `/resultado/{id}` | GET | Busca resultado completo |
| `/download/{id}` | GET | Baixa arquivo corrigido |
| `/historico` | GET | Lista todos os processamentos |
| `/dashboard/comparativo` | GET | Série temporal por CNPJ |
| `/processamento/{id}` | DELETE | Remove processamento |
| `/pendencias/{id}` | GET | Lista pendências manuais |

## Estrutura

```
sped-app/
├── backend/
│   ├── main.py                  # FastAPI — endpoints e banco (dual engine)
│   ├── engine.py                # Engine ICMS/IPI
│   ├── engine_contrib.py        # Engine Contribuições (PIS/COFINS)
│   ├── dados_pva.json           # Leiaute + tabelas PVA ICMS/IPI
│   ├── dados_pva_contrib.json   # Leiaute + tabelas PVA Contribuições
│   ├── converter_pva_contrib.py # Script para gerar dados_pva_contrib.json
│   ├── requirements.txt
│   └── arquivos/                # SPEDs corrigidos (gerado automaticamente)
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Página principal (dual type)
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── Dashboard.tsx        # Dashboard ICMS ou Contribuições
│   │   ├── Historico.tsx        # Lista de processamentos
│   │   ├── Comparativo.tsx      # Gráficos mês a mês
│   │   └── PendenciasManual.tsx # Pendências ICMS e Contribuições
│   └── package.json                 # Arquivos SPED de teste e relatórios PVA
├── iniciar.bat                  # Windows
├── iniciar.sh                   # Linux/Mac
├── CONTEXT.md                   # Contexto técnico completo
└── README.md
```
