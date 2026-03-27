# SPED Autocorretor — Projeto Full Stack

Validação e correção automática de arquivos SPED EFD ICMS/IPI.

## Stack

- **Backend:** Python 3.10+ · FastAPI · SQLite
- **Frontend:** Next.js 14 · React 18 · Tailwind CSS · Recharts
- **Engine:** Baseada no `descritor.xml` oficial do PVA SERPRO (267 registros)

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

## O que faz automaticamente

| Correção | Descrição |
|----------|-----------|
| COD_VER | Corrige versão do leiaute pelo período |
| H010 IND_PROP | Corrige campo de propriedade do estoque |
| DESCR_ITEM | Trunca para 60 chars, remove pipe literal |
| UNID | Trunca para 6 chars (0190, C170, H010) |
| C190 | Gera automaticamente via C170 ou CST=300/CFOP=5102 para NFC-e |
| E110 | Recalcula VL_ICMS_RECOLHER e VL_SLD_CREDOR_TRANSPORTAR |
| C990/9900/9999 | Atualiza todos os contadores de bloco |
| fixLen genérico | Aplica tamanhos máximos do leiaute em todos os 267 registros |

## API

Documentação interativa disponível em **http://localhost:8000/docs**

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/processar` | POST | Envia arquivo .txt e retorna ID |
| `/resultado/{id}` | GET | Busca resultado completo |
| `/download/{id}` | GET | Baixa arquivo corrigido |
| `/historico` | GET | Lista todos os processamentos |
| `/dashboard/comparativo` | GET | Série temporal por CNPJ |
| `/processamento/{id}` | DELETE | Remove processamento |

## Estrutura

```
sped-app/
├── backend/
│   ├── main.py          # FastAPI — endpoints e banco
│   ├── engine.py        # Engine de validação/correção
│   ├── dados_pva.json   # Leiaute + tabelas do PVA
│   ├── requirements.txt
│   └── arquivos/        # SPEDs corrigidos (gerado automaticamente)
├── frontend/
│   ├── app/
│   │   ├── page.tsx     # Página principal
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── Dashboard.tsx    # Alíquotas efetivas
│   │   ├── Historico.tsx    # Lista de processamentos
│   │   └── Comparativo.tsx  # Gráficos mês a mês
│   └── package.json
├── iniciar.bat          # Windows
└── iniciar.sh           # Linux/Mac
```
