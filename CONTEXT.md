# SPED Autocorretor — Contexto Completo do Projeto

> Arquivo de referência para o Cursor. Gerado a partir das sessões de desenvolvimento.  
> Última atualização: março/2026

---

## 1. Visão Geral

Aplicação full-stack para **validação e correção automática de arquivos SPED**, suportando duas escriturações:

- **EFD ICMS/IPI** — Escrituração Fiscal Digital de ICMS e IPI
- **EFD-Contribuições** — Escrituração Fiscal Digital de PIS/COFINS

O sistema elimina ou reduz ao mínimo os erros de importação no **PVA SERPRO** (validador oficial da Receita Federal).

### Contexto de negócio
- Contadores e empresas geram arquivos SPED via ERP que chegam com erros estruturais e fiscais
- O PVA valida e rejeita com mensagens genéricas difíceis de interpretar
- A ferramenta processa o arquivo, corrige o que é automatizável e expõe o restante para intervenção manual assistida
- O tipo de SPED (ICMS/IPI ou Contribuições) é detectado automaticamente pelo registro 0000

### Clientes testados

| Empresa | UF | Escrituração | Período | Resultado |
|---|---|---|---|---|
| COSTA RIBEIRO SOLUCOES EM EPIS LTDA | MG | ICMS/IPI | fev/2026 | 0 erros após correção |
| MB PLASTIC INDUSTRIA E COMERCIO LTDA | SP | ICMS/IPI | jan/2026 | 0 erros após correção |
| CARVALHO E LAURENTI COMERCIO LTDA | — | Contribuições | nov/2025 | 0 erros (arquivo limpo) |
| COSTA RIBEIRO SOLUCOES EM EPIS LTDA | MG | Contribuições | dez/2025 | 730→3 erros (3 manuais) |

---

## 2. Stack Tecnológica

| Camada | Tecnologia | Versão |
|---|---|---|
| Backend | Python + FastAPI | 3.10+ / 0.115.0 |
| Engine ICMS/IPI | Python puro | — |
| Engine Contribuições | Python puro | — |
| Banco de dados | SQLite | embutido |
| Frontend | Next.js + React | 14.2.5 / 18 |
| Estilização | Tailwind CSS | 3.4.1 |
| Gráficos | Recharts | 2.12.7 |
| Ícones | Lucide React | 0.383.0 |
| Servidor backend | Uvicorn | 0.30.6 |

### Decisão: sem Docker, sem servidor
Roda 100% local (`localhost`). Backend na porta `8000`, frontend na `3000`.  
Scripts de inicialização: `iniciar.bat` (Windows) e `iniciar.sh` (Linux/Mac).

---

## 3. Estrutura de Arquivos

```
sped-app/
├── backend/
│   ├── main.py                  # FastAPI — endpoints REST (dual engine)
│   ├── engine.py                # Engine ICMS/IPI (~685 linhas)
│   ├── engine_contrib.py        # Engine Contribuições (~1080 linhas)
│   ├── dados_pva.json           # Leiaute + tabelas PVA ICMS/IPI (448 KB)
│   ├── dados_pva_contrib.json   # Leiaute + tabelas PVA Contribuições
│   ├── converter_pva_contrib.py # Script para gerar dados_pva_contrib.json
│   ├── requirements.txt         # fastapi, uvicorn, python-multipart
│   ├── sped.db                  # SQLite (gerado em runtime)
│   └── arquivos/                # SPEDs corrigidos por ID (gerado em runtime)
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Página principal — upload + tabs (dual type)
│   │   ├── layout.tsx           # Layout raiz Next.js
│   │   └── globals.css          # Tailwind + fontes IBM Plex
│   ├── components/
│   │   ├── Dashboard.tsx        # Dashboard ICMS (alíquotas) ou Contribuições (PIS/COFINS)
│   │   ├── Historico.tsx        # Lista de processamentos anteriores
│   │   ├── Comparativo.tsx      # Gráficos de série temporal por CNPJ
│   │   └── PendenciasManual.tsx # CHV_NFE + COD_REC + E116 + M205/M605
│   ├── next.config.js           # Proxy /api/* → localhost:8000
│   ├── tailwind.config.js
│   └── tsconfig.json
│
├── iniciar.bat
├── iniciar.sh
├── CONTEXT.md
└── README.md
```

---

## 4. Detecção Automática do Tipo de SPED

```python
def detectar_tipo_sped(conteudo: str) -> str:
    # ICMS/IPI: 0000 tem 15 campos (inclui COD_FIN, IE, IM, IND_PERFIL)
    # Contribuições: 0000 tem 14 campos (inclui TIPO_ESCRIT, IND_NAT_PJ, IND_ATIV)
    for line in conteudo.split("\n"):
        if line.startswith("|0000|"):
            n_campos = len(line.split("|")) - 2
            return "contrib" if n_campos <= 14 else "icms"
    return "icms"
```

---

## 5. Engine ICMS/IPI (`engine.py`)

### Fluxo principal

```python
def processar(conteudo: str) -> Resultado:
    # Passagem 1: leitura global, acumuladores, mapa pai-filho
    # Passagem 2: validação e correção campo a campo
    # Geração de C190 (pai-filho)
    # Recálculo de contadores (xXX990, 9900, 9999)
    # Validações cruzadas pós-passagem
    # Sumário e aliq_map
```

### Correções automáticas

| Registro | Campo | Correção |
|---|---|---|
| `0000` | `COD_VER` | Detecta versão correta pelo período |
| `0200` | `DESCR_ITEM` | Remove pipe literal (`fix_pipe`) |
| `0190`, `C170`, `H010` | `UNID` | Trunca para 6 chars |
| `C100` | `DT_DOC`, `DT_E_S` | Normaliza formato de data |
| `C100` | `CHV_NFE` | Detecta ausência em MOD=55/65 e reporta como erro |
| `C170` | `VL_ICMS`, `VL_ICMS_ST` | Recalcula BC × alíquota |
| `C190` | Geração automática | Via C170 filhos ou CST=300/CFOP=5102 para NFC-e |
| `E110` | `VL_ICMS_RECOLHER` | Fórmula: `tot_cred - tot_deb` |
| `E116` | `COD_REC` | Auto-detecção por UF + tipo empresa |
| `E250` | Geração automática | Quando E210 tem ICMS-ST a recolher |
| `H010` | `VL_ITEM` | Recalcula `QTD × VL_UNIT` |
| `H010` | `IND_PROP` | Corrige valores inválidos para `0` |
| `K200` | `DT_EST` | Fallback para `DT_FIN` do `0000` |
| Todos xXX990 | `QTD_LIN_X` | Recalcula após qualquer modificação |
| `9900` | `QTD_REG_BLC` | Recalcula contadores por tipo de registro |
| `9999` | `QTD_LIN` | Recalcula total de linhas não-vazias |

### Fórmula E110

```python
tot_cred = f[6] + f[8] + f[9] + f[10]
tot_deb  = f[2] + f[4] + f[5]
saldo    = tot_cred - tot_deb
f[13] = max(0, -saldo)   # VL_ICMS_RECOLHER
f[14] = max(0,  saldo)   # VL_SLD_CREDOR_TRANSPORTAR
```

### Detecção de COD_REC (E116) por UF

```python
COD_REC_UNICO_POR_UF = {
    "SP": "046-2", "ES": "101-5", "RS": "0057", "GO": "108",
    "MA": "101",   "TO": "101",   "MS": "310",  "SE": "0139",
    "BA": "0741",  "PA": "0900",  "PE": "0051", "RJ": "0213",
    "AM": "1303",  "PR": "1015",  "CE": "1015", "AC": "1013",
    "AP": "1111",  "MT": "1112",  "RO": "1112", "DF": "1314",
    "PB": "1047",
}
# MG e RN: distinguem comércio vs indústria pelo TIPO_ITEM do 0200
# AL, PI, SC: dropdown manual
```

---

## 6. Engine Contribuições (`engine_contrib.py`)

### Fluxo principal

```python
def processar(conteudo: str) -> Resultado:
    # Passagem 1: coleta global (CNPJ, regime, participantes, itens, acumuladores)
    # Fase A0: IND_REG_CUM auto-correção (0110)
    # Fase A1: IND_ESCRI auto-correção (C010)
    # Fase A2: Blocos ausentes — insere X001+X990 na ordem correta
    # Fase A3: IND_MOV consistência (header vs dados)
    # Passagem 2: validações e correções campo a campo
    # Fase G2: Gerar C175 para NFC-e (MOD 65) + VL_MERC
    # Fase E1: Auto-geração Bloco M (M200, M210, M400, M410, M600, M610, M800, M810)
    # Fase E4: Recálculo contadores (9900, C990, 9999)
    # Validações cruzadas (C1-C4, D3)
    # Sumário
```

### Resultado retornado (mesmo formato de ambas engines)

```python
@dataclass
class Resultado:
    erros: list[Erro]       # Erros críticos
    flags: list[Flag]       # Alertas para revisão manual
    fixes: list[Fix]        # Correções aplicadas automaticamente
    sumario: Sumario        # Métricas e nome/CNPJ/período
    fixed_lines: list[str]  # Linhas do arquivo após correções
```

### Fases de correção detalhadas

#### Fase A0 — IND_REG_CUM (registro 0110)
Quando `COD_INC_TRIB=2` (cumulativo) e o arquivo possui registros C100, corrige `IND_REG_CUM` para `9` (detalhamento por documento), evitando que o PVA exija F500 (consolidação).

#### Fase A1 — IND_ESCRI (registro C010)
Detecta se o estabelecimento tem operações no Bloco C. Se tem, define `IND_ESCRI=2` (consolidado). Se não tem movimentação, define `IND_ESCRI=1` (escrituração detalhada padrão).

#### Fase A2 — Blocos ausentes
Insere blocos faltantes (`X001|1|` + `X990|2|`) na posição correta segundo `BLOCOS_CONTRIB_ORDERED = [0, A, C, D, F, I, M, P, 1, 9]`. Para regime cumulativo (`COD_INC_TRIB=2`), remove o Bloco I (imobilizado não cumulativo).

#### Fase A3 — IND_MOV
Corrige `IND_MOV` nos headers de bloco: se IND_MOV=0 (tem movimento) mas bloco vazio → corrige para 1. Se IND_MOV=1 (sem movimento) mas bloco tem registros → corrige para 0.

#### Passagem 2 — Validações por registro

| Registro | Validação/Correção |
|---|---|
| `0000` | COD_VER pelo período, formatos de data |
| `0150` | Tamanho do NOME (100 chars) |
| `0190` | Tamanho da UNID (6 chars) |
| `C100` | Datas, COD_MOD, COD_SIT, CHV_NFE (44 dígitos), CNPJ da chave vs participante, COD_PART vs 0150, período |
| `C170` | UNID, CFOP, CST PIS/COFINS (validade + simetria + entrada/saída), CST IPI, BC PIS = BC COFINS, alíquota vs regime, recálculo VL_PIS/VL_COFINS, COD_ITEM vs 0200, **G1: preenche CST vazio com 49 para saída** |
| `C175` | CST PIS/COFINS, BC, alíquota vs regime, recálculo VL_PIS/VL_COFINS |
| `A100` | Datas, COD_MOD |
| Genérico | Campos insuficientes (pipes faltantes), tamanhos máximos |

#### Fase G2 — C175 para NFC-e (MOD 65)
Para cada C100 com MOD=65 sem C175 filho:
1. Preenche `VL_MERC` (campo 16) com `VL_DOC` se estiver zerado
2. Gera C175 com `CFOP=5102`, `VL_OPR=VL_DOC`, `CST_PIS=49`, `CST_COFINS=49`, alíquotas zero

#### Fase E1 — Auto-geração Bloco M
Gera registros M obrigatórios quando ausentes:
- `M200` (PIS) + `M210` (detalhamento por CST)
- `M400` (PIS crédito) + `M410` (detalhamento)
- `M600` (COFINS) + `M610` (detalhamento por CST)
- `M800` (COFINS crédito) + `M810` (detalhamento)

#### Fase E4 — Contadores
Recalcula `9900` (contagem por tipo de registro), `C990`/etc (fechamento de bloco) e `9999` (QTD_LIN total).

### Validações cruzadas (Fase C/D)

| Código | Validação |
|---|---|
| C1 | M210.VL_CONT vs soma real dos registros de origem |
| C2 | CSTs usados no arquivo vs M-blocks existentes |
| C3 | CST COFINS usados vs M600/M610 existentes |
| C4 | Registro 1900 obrigatório a partir de 04/2013 |
| D3 | Alíquotas C170 vs regime tributário (cumulativo/não-cumulativo) |

### Campos-chave do regime

| Campo | Registro | Significado |
|---|---|---|
| `COD_INC_TRIB` | 0110 campo 2 | `1`=não-cumulativo, `2`=cumulativo, `3`=ambos |
| `IND_REG_CUM` | 0110 campo 5 | `1`=consolidado F500, `9`=detalhado C100/C170 |
| `IND_ESCRI` | C010 campo 3 | `1`=detalhada, `2`=consolidada |
| `TIPO_ESCRIT` | 0000 campo 3 | `0`=original, `1`=retificadora |

### Alíquotas por regime

```python
# Não-cumulativo (COD_INC_TRIB=1)
ALIQ_PIS  = 1.65%
ALIQ_COFINS = 7.60%

# Cumulativo (COD_INC_TRIB=2)
ALIQ_PIS  = 0.65%
ALIQ_COFINS = 3.00%
```

---

## 7. Dados de Referência

### dados_pva.json (ICMS/IPI)

| Chave | Conteúdo |
|---|---|
| `leiaute` | 267 registros com campos, tamanhos máximos e índices |
| `cfop` | 620 CFOPs válidos |
| `cfop_sai_to_ent` / `cfop_ent_to_sai` | Conversão entrada↔saída |
| `cst_icms` | CSTs ICMS válidos |
| `cst_ipi` / `cst_pis` | CSTs IPI e PIS válidos |
| `mod_doc` | Modelos de documento (55=NF-e, 65=NFC-e, etc.) |
| `versoes` | Versões do leiaute por período |
| `uf_cod` | Mapeamento COD_MUN IBGE → UF |
| `f2.aj` | Códigos de ajuste E111 por UF |
| `f2.rec` | Códigos de receita E116 por UF |

### dados_pva_contrib.json (Contribuições)

Gerado por `converter_pva_contrib.py` a partir do `descritor.xml` + tabelas auxiliares do PVA Contribuições.

| Chave | Conteúdo |
|---|---|
| `leiaute` | 182 registros com campos, tamanhos máximos e índices |
| `cfop` | CFOPs válidos para PIS/COFINS |
| `cst_pis` / `cst_cofins` | CSTs PIS e COFINS válidos |
| `cst_ipi` | CSTs IPI válidos |
| `mod_doc` | Modelos de documento |
| `versoes` | Versões do leiaute por período |
| `uf_cod` | Mapeamento COD_MUN IBGE → UF |

---

## 8. API REST (main.py)

### Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Status do servidor |
| `POST` | `/processar` | Upload do .txt → detecta tipo → processa → retorna `{id, tipo, cache}` |
| `GET` | `/resultado/{id}` | Busca resultado completo (erros, fixes, flags, sumário) |
| `GET` | `/download/{id}` | Download do arquivo corrigido em ISO-8859-1 |
| `GET` | `/historico?limit=50` | Lista todos os processamentos |
| `GET` | `/dashboard/comparativo?cnpj=&limite=12` | Série temporal por CNPJ |
| `DELETE` | `/processamento/{id}` | Remove processamento e arquivo |
| `POST` | `/editar/chave/{id}?linha=N` | Insere CHV_NFE ou exclui C100+filhos |
| `POST` | `/editar/cod_rec/{id}` | Substitui COD_REC em todos os E116 |
| `POST` | `/editar/cod_rec_st/{id}` | Substitui COD_REC nos E250 (por UF_ST) |
| `GET` | `/pendencias/{id}` | Lista pendências manuais com códigos válidos da UF |

### Endpoint `/processar` — fluxo

```python
# 1. Ler raw bytes → hash SHA-256 → verificar cache
# 2. Decodificar ISO-8859-1 + normalizar \n
# 3. detectar_tipo_sped(conteudo) → "icms" ou "contrib"
# 4. Roteamento: processar_icms(conteudo) ou processar_contrib(conteudo)
# 5. Salvar no SQLite + arquivo corrigido em /arquivos/{id}.txt
# 6. Retornar {id, tipo, cache}
```

### Schema SQLite

```sql
CREATE TABLE processamentos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hash         TEXT UNIQUE,
    nome         TEXT,
    cnpj         TEXT,
    uf           TEXT,
    dt_ini       TEXT,
    dt_fin       TEXT,
    versao       TEXT,
    criado_em    TEXT,
    total_erros  INTEGER,
    total_flags  INTEGER,
    total_fixes  INTEGER,
    total_linhas INTEGER,
    sumario_json TEXT,
    erros_json   TEXT,
    flags_json   TEXT,
    fixes_json   TEXT,
    tipo         TEXT DEFAULT 'icms'   -- 'icms' ou 'contrib'
)
```

---

## 9. Frontend (Next.js)

### Proxy API

```javascript
// next.config.js
rewrites: [{ source: '/api/:path*', destination: 'http://localhost:8000/:path*' }]
```

### Detecção dual de tipo

O frontend recebe `tipo` ("icms" ou "contrib") na resposta de `/processar` e adapta:
- **Título do header**: "SPED EFD ICMS/IPI" ou "SPED EFD-Contribuições"
- **Dashboard**: `DashboardICMS` (alíquotas por CFOP) ou `DashboardContrib` (métricas PIS/COFINS)
- **Pendências**: Exibe campos específicos para cada tipo

### Tabs disponíveis

| Tab | Componente | Quando aparece |
|---|---|---|
| Erros | Cards filtráveis | Sempre que há resultado |
| Corrigidos | Cards com orig→novo | Sempre que há resultado |
| Flags | Cards com hint | Sempre que há resultado |
| Pendências | `PendenciasManual` | Com resultado + procId |
| Dashboard | `Dashboard` | Com resultado |
| Histórico | `Historico` | Sempre |
| Comparativo | `Comparativo` | Com resultado |

### Tema e design

```javascript
// tailwind.config.js — cores customizadas
colors: {
  bg: '#0f1117', bg2: '#161922', bg3: '#1e2330',
  border: '#2a3040', border2: '#3a4560',
  green: '#00d084', red: '#ff4757', amber: '#ffb347',
  blue: '#4da6ff', purple: '#b088ff',
}
// Fonte: IBM Plex Mono + IBM Plex Sans
```

---

## 10. Bugs Resolvidos (histórico)

### ICMS/IPI

| # | Bug | Causa | Fix |
|---|---|---|---|
| 1 | `\n\n` no arquivo | ERP gerava linhas duplas | Normalizar entrada com `re.sub` |
| 2 | 9999 deslocado | `r9999_idx` antes dos inserts de C190 | Re-buscar `\|9999\|` após inserts |
| 3 | Fórmula E110 | Campos errados no cálculo | Corrigido para `tot_cred - tot_deb` |
| 4 | K200.DT_EST | ERP colocava total de linhas como data | Fallback para `DT_FIN` do 0000 |
| 5 | Contadores pós-exclusão | `_salvar_fixed` não recalculava | Recalcula C990/9900/9999 |
| 6 | COD_REC inválido | Código de outra UF | Auto-detecção por UF |
| 7 | E250 ausente | E210 com ICMS-ST sem obrigação | Geração automática |

### Contribuições

| # | Bug | Causa | Fix |
|---|---|---|---|
| 8 | 507 erros C010/C100 | `IND_REG_CUM=1` (consolidado) com C100 presente | Corrigir `IND_REG_CUM=9` |
| 9 | I001/I990 hierarquia | Bloco I sem dados mas header presente | Remoção condicional para cumulativo |
| 10 | IndexError passagem 2 | Remoção de linhas alterava tamanho do array | Substituir por string vazia |
| 11 | 381 CST_PIS vazio | C170 saída sem CST preenchido | Preencher com 49 |
| 12 | 346 NFC-e sem C175 | MOD=65 sem detalhamento PIS/COFINS | Gerar C175 automaticamente |
| 13 | 346 VL_MERC zerado | C100 NFC-e com VL_MERC=0 + C175 com VL_OPR>0 | Preencher VL_MERC com VL_DOC |

---

## 11. Pendências Manuais (não automatizáveis)

### ICMS/IPI

| Registro | Campo | Motivo |
|---|---|---|
| C100 MOD=65 | CHV_NFE | Chave de acesso não está no SPED, precisa do ERP |
| E116 | COD_REC (AL, PI, SC) | UFs sem mapeamento definido |
| E250 | COD_REC (UFs sem mapeamento ST) | Depende da legislação estadual |

### Contribuições

| Registro | Campo | Motivo |
|---|---|---|
| 0150 | IE | Inscrição Estadual inválida no cadastro do participante |
| C170 | CST PIS ≠ CST COFINS | Assimetria de CSTs em itens específicos |
| C100 | CHV_NFE vs COD_PART | CNPJ da chave diverge do participante |
| M205/M605 | COD_REC | Código de receita para contribuição |

---

## 12. Notas de Arquitetura

### Encoding
Todos os arquivos SPED são **ISO-8859-1** (latin-1). Usar sempre `encoding='iso-8859-1', errors='replace'` para leitura e escrita.

### Indexação de campos
Campos do SPED são acessados por índice no array `split('|')`. O índice `0` é sempre `""` (antes do primeiro `|`) e o último também é `""` (depois do último `|`). Campo `REG` está sempre em `f[1]`.

### Linhas não-vazias vs total de linhas
O PVA conta **linhas não-vazias** para o `9999`. A engine usa `sum(1 for l in fixed if l.strip())` para o total correto.

### Cache por hash
O endpoint `/processar` calcula SHA-256 do raw bytes. Se já existe no banco, retorna `{id, cache: true}` sem reprocessar. Para forçar reprocessamento, é necessário deletar o registro primeiro.

### Duas engines, mesmo formato
Ambas engines (`engine.py` e `engine_contrib.py`) retornam o mesmo `Resultado` dataclass, permitindo que o `main.py` e o frontend tratem ambos os tipos de forma unificada.

### Blocos obrigatórios Contribuições
```python
BLOCOS_CONTRIB_ORDERED = ["0", "A", "C", "D", "F", "I", "M", "P", "1", "9"]
# Bloco I: removido para regime cumulativo (COD_INC_TRIB=2)
# Bloco P: opcional (SCP - Sociedade em Conta de Participação)
```

---

## 13. Comandos de Desenvolvimento

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Testar engine ICMS/IPI
python3 -c "
import sys; sys.path.insert(0, 'backend')
from engine import processar
with open('arquivo.txt', encoding='iso-8859-1') as f:
    res = processar(f.read())
print(f'Erros: {len(res.erros)} Fixes: {len(res.fixes)} Flags: {len(res.flags)}')
"

# Testar engine Contribuições
python3 -c "
import sys; sys.path.insert(0, 'backend')
from engine_contrib import processar
with open('arquivo_contrib.txt', encoding='iso-8859-1') as f:
    res = processar(f.read())
print(f'Erros: {len(res.erros)} Fixes: {len(res.fixes)} Flags: {len(res.flags)}')
"
```

---

## 14. Próximas Funcionalidades Sugeridas

### ICMS/IPI — Alta prioridade
1. **Crédito de ICMS sobre energia elétrica** — CIAP
2. **Crédito de fretes de entrada** — CFOP 1351/2351
3. **Bloco G (CIAP)** — crédito de ativo imobilizado em 48 avos
4. **Validação NCM + UF + CST** — detectar CST incorreto por benefício fiscal

### Contribuições — Alta prioridade
1. **Validação de IE no 0150** — auto-corrigir IEs inválidas conhecidas
2. **Simetria CST PIS/COFINS** — auto-correção quando apenas um dos CSTs está preenchido
3. **CNPJ CHV_NFE vs participante** — flag detalhado com sugestão de participante correto

### Arquitetura
4. **Processamento em lote** — múltiplos arquivos de uma vez
5. **Multi-cliente** — separar histórico por CNPJ com login simples
