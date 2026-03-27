# SPED Autocorretor — Contexto Completo do Projeto

> Arquivo de referência para o Cursor. Gerado a partir da sessão de desenvolvimento completa.  
> Última atualização: março/2026

---

## 1. Visão Geral

Aplicação full-stack para **validação e correção automática de arquivos SPED EFD ICMS/IPI** (Sistema Público de Escrituração Digital), eliminando ou reduzindo ao mínimo os erros de importação no **PVA SERPRO** (validador oficial da Receita Federal).

### Contexto de negócio
- Contadores e empresas geram arquivos SPED via ERP que chegam com erros estruturais e fiscais
- O PVA valida e rejeita com mensagens genéricas difíceis de interpretar
- A ferramenta processa o arquivo, corrige o que é automatizável e expõe o restante para intervenção manual assistida

### Clientes testados
| Empresa | UF | Período | Resultado |
|---|---|---|---|
| COSTA RIBEIRO SOLUCOES EM EPIS LTDA | MG | fev/2026 | 0 erros após correção |
| MB PLASTIC INDUSTRIA E COMERCIO LTDA | SP | jan/2026 | 0 erros após correção |

---

## 2. Stack Tecnológica

| Camada | Tecnologia | Versão |
|---|---|---|
| Backend | Python + FastAPI | 3.10+ / 0.115.0 |
| Engine de validação | Python puro | — |
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
│   ├── main.py              # FastAPI — 10 endpoints REST
│   ├── engine.py            # Engine de validação/correção (685 linhas)
│   ├── dados_pva.json       # Leiaute + tabelas do PVA (448 KB)
│   ├── requirements.txt     # fastapi, uvicorn, python-multipart
│   ├── sped.db              # SQLite (gerado em runtime)
│   └── arquivos/            # SPEDs corrigidos por ID (gerado em runtime)
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Página principal — upload + tabs
│   │   ├── layout.tsx       # Layout raiz Next.js
│   │   └── globals.css      # Tailwind + fontes IBM Plex
│   ├── components/
│   │   ├── Dashboard.tsx    # Gráfico de alíquotas efetivas por CFOP
│   │   ├── Historico.tsx    # Lista de processamentos anteriores
│   │   ├── Comparativo.tsx  # Gráficos de série temporal por CNPJ
│   │   └── PendenciasManual.tsx  # CHV_NFE + COD_REC + E116
│   ├── next.config.js       # Proxy /api/* → localhost:8000
│   ├── tailwind.config.js
│   └── tsconfig.json
│
├── iniciar.bat
├── iniciar.sh
└── README.md
```

---

## 4. Dados de Referência (dados_pva.json)

Gerado a partir do `descritor_v20.xml` oficial do PVA SERPRO. Contém:

| Chave | Conteúdo |
|---|---|
| `leiaute` | 267 registros com campos, tamanhos máximos e índices |
| `cfop` | 620 CFOPs válidos |
| `cfop_sai_to_ent` / `cfop_ent_to_sai` | Conversão entrada↔saída |
| `cst_icms` | CSTs ICMS válidos |
| `cst_ipi` | CSTs IPI válidos |
| `cst_pis` | CSTs PIS válidos |
| `mod_doc` | Modelos de documento (55=NF-e, 65=NFC-e, etc.) |
| `cod_sit` | Códigos de situação (00-09) |
| `versoes` | Versões do leiaute por período |
| `uf_cod` | Mapeamento COD_MUN IBGE → UF |
| `f2.aj` | Códigos de ajuste E111 por UF (vigência histórica) |
| `f2.rec` | Códigos de receita E116 por UF (vigência histórica) |

---

## 5. Engine de Validação (`engine.py`)

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

### Resultado retornado

```python
@dataclass
class Resultado:
    erros: list[Erro]       # Erros críticos que impedem importação
    flags: list[Flag]       # Alertas que requerem revisão manual
    fixes: list[Fix]        # Correções aplicadas automaticamente
    sumario: Sumario        # Métricas + aliq_map por CFOP
    fixed_lines: list[str]  # Linhas do arquivo após correções
```

### Correções automáticas implementadas

| Registro | Campo | Correção |
|---|---|---|
| `0000` | `COD_VER` | Detecta versão correta pelo período |
| `0200` | `DESCR_ITEM` | Remove pipe literal (`fix_pipe`) |
| `0190`, `C170`, `H010` | `UNID` | Trunca para 6 chars |
| `C100` | `DT_DOC`, `DT_E_S` | Normaliza formato de data |
| `C100` | `CHV_NFE` | Detecta ausência em MOD=55/65 e reporta como erro |
| `C170` | `VL_ICMS`, `VL_ICMS_ST` | Recalcula BC × alíquota |
| `C190` | Geração automática | Via C170 filhos ou CST=300/CFOP=5102 para NFC-e |
| `E110` | `VL_ICMS_RECOLHER`, `VL_SLD_CREDOR_TRANSPORTAR` | Fórmula correta: `tot_cred - tot_deb` |
| `E116` | `MES_REF` | Sempre `mmaaaa` do `DT_INI` do `0000` |
| `E116` | `COD_REC` | Auto-detecção por UF + tipo empresa (ver seção 6) |
| `H005` | `DT_INV` | Normaliza formato de data |
| `H010` | `VL_ITEM` | Recalcula `QTD × VL_UNIT` |
| `H010` | `IND_PROP` | Corrige valores inválidos para `0` |
| `K200` | `DT_EST` | Fallback para `DT_FIN` do `0000` quando ERP coloca lixo |
| `K200` | `IND_EST` | Valida `0` ou `1` |
| `E250` | Geração automática | Quando E210.VL_ICMS_RECOL_ST+DEB_ESP_ST > 0 e sem E250 filho |
| Todos xXX990 | `QTD_LIN_X` | Recalcula após qualquer modificação |
| `9900` | `QTD_REG_BLC` | Recalcula contadores por tipo de registro |
| `9999` | `QTD_LIN` | Recalcula total de linhas não-vazias |

### Fórmula E110 (crítica — estava errada nas versões anteriores)

```python
# Campos conforme leiaute oficial:
# f[2]=VL_TOT_DEBITOS  f[4]=VL_TOT_AJ_DEBITOS  f[5]=VL_ESTORNOS_CRED
# f[6]=VL_TOT_CREDITOS f[8]=VL_TOT_AJ_CREDITOS  f[9]=VL_ESTORNOS_DEB
# f[10]=VL_SLD_CREDOR_ANT  f[13]=VL_ICMS_RECOLHER  f[14]=VL_SLD_CREDOR_TRANSPORTAR

tot_cred = f[6] + f[8] + f[9] + f[10]
tot_deb  = f[2] + f[4] + f[5]
saldo    = tot_cred - tot_deb

f[13] = max(0, -saldo)   # VL_ICMS_RECOLHER
f[14] = max(0,  saldo)   # VL_SLD_CREDOR_TRANSPORTAR
```

> **Bug histórico**: versões anteriores usavam `f[4]-f[8]-f[10]` (campos errados), zerando saldo credor legítimo (ex: R$ 3.801,22 virava R$ 0,00).

### Geração automática de C190

```python
# Para cada C100 sem C190:
# 1. COD_SIT in {02,03,04,05,06,07,08} → dispensar
# 2. Tem C170 filhos → consolidar por CST+CFOP+ALIQ → gerar C190
# 3. MOD=65 (NFC-e) e IND_OPER=1 (saída) → gerar: CST=300/CFOP=5102/VL_OPR=VL_DOC
# 4. Outros sem C170 → rec_err para revisão manual

PAI_FILHO = {
    "C100": ["C190"], "C400": ["C405"], "C500": ["C590"],
    "C600": ["C690"], "C800": ["C860"], "D100": ["D190"],
    "D500": ["D590"], "E100": ["E110"], "E500": ["E520"],
    "H001": ["H005"],
}
DISPENSAR_COD_SIT = {"02","03","04","05","06","07","08"}
```

> **Bug crítico resolvido**: `r9999_idx` era calculado antes dos `fixed.insert()` dos C190 gerados, causando deslocamento de índice. Resolvido re-buscando `|9999|` em `fixed` após todos os inserts.

### Geração automática de E250 (ICMS-ST obrigações)

```python
# Para cada E210 com VL_ICMS_RECOL_ST + DEB_ESP_ST > 0 e sem E250:
# 1. Obter UF_ST do E200 pai
# 2. VL_OR = VL_ICMS_RECOL_ST (f[13]) + DEB_ESP_ST (f[15])
# 3. MES_REF = mmaaaa do DT_INI do E200
# 4. DT_VCTO = dia 10 do mês seguinte ao período
# 5. COD_REC = detectar_cod_rec_st(uf_st) — mapeamento por UF

COD_REC_ST_POR_UF = {
    "SP": "063-2", "AM": "1304", "MT": "2810",
    "MS": "312",   "PA": "0901",
}
# UFs sem mapeamento ST → E250 gerado sem COD_REC + flag para seleção manual
```

> **Regra PVA**: Soma(E250.VL_OR) deve ser igual a E210.VL_ICMS_RECOL_ST + E210.DEB_ESP_ST. Sem E250, o PVA gera erro "A soma das obrigações do ICMS ST a recolher...".

> **Endpoint de edição**: `POST /editar/cod_rec_st/{id}` permite substituir COD_REC nos E250, filtrado por UF_ST.

### Normalização de entrada (bug recorrente)

```python
# main.py — SEMPRE normalizar antes de processar
conteudo = conteudo.replace("\r\n", "\n").replace("\r", "\n")
conteudo = re.sub(r"\n{2,}", "\n", conteudo)
```

> **Causa**: arquivos gerados por versões com bug tinham `\n\n` entre cada linha. O PVA interpretava linhas vazias como registros inválidos, gerando ~1000 erros. Fix: normalizar na entrada + `.rstrip('\r\n')` em cada linha ao salvar.

---

## 6. Detecção Automática de COD_REC (E116)

### Problema
Cada UF tem sua própria tabela SEFAZ de códigos de receita. Um código válido em MG (`1206`) é inválido em SP — o PVA rejeita com "Código inválido".

### Condição de disparo
`E116.COD_OR = "000"` (apuração normal do período) com `COD_REC` inválido para a UF.

### Algoritmo

```python
def detectar_cod_rec(uf: str, tipo_item_counts: dict) -> Optional[str]:
    # UF com código único conhecido → auto-corrigir
    if uf in COD_REC_UNICO_POR_UF:
        return COD_REC_UNICO_POR_UF[uf]
    
    # MG e RN: distinguir comércio vs indústria pelo TIPO_ITEM do 0200
    if uf in ("MG", "RN"):
        rev = tipo_item_counts.get("00", 0)          # mercadoria p/ revenda
        ind = sum(v for k,v in tipo_item_counts.items()
                  if k in ("01","02","03","04","05","06"))  # matéria-prima, etc.
        return "1206" if rev >= ind else "1214"
    
    return None  # outros estados → dropdown manual com válidos da UF
```

### Mapa COD_REC por UF (COD_OR=000)

```python
COD_REC_UNICO_POR_UF = {
    "SP": "046-2", "ES": "101-5", "RS": "0057", "GO": "108",
    "MA": "101",   "TO": "101",   "MS": "310",  "SE": "0139",
    "BA": "0741",  "PA": "0900",  "PE": "0051", "RJ": "0213",
    "AM": "1303",  "PR": "1015",  "CE": "1015", "AC": "1013",
    "AP": "1111",  "MT": "1112",  "RO": "1112", "DF": "1314",
    "PB": "1047",
}
COD_REC_MG_COMERCIO  = "1206"   # TIPO_ITEM=00 maioria
COD_REC_MG_INDUSTRIA = "1214"   # TIPO_ITEM=01-06 maioria
# AL, PI, SC → UFs sem mapeamento definido → dropdown com válidos da UF
```

### TIPO_ITEM para distinção comércio/indústria (0200)

| Código | Descrição | Tipo |
|---|---|---|
| `00` | Mercadoria para revenda | Comércio → 1206 |
| `01` | Matéria-prima | Indústria → 1214 |
| `02` | Embalagem | Indústria → 1214 |
| `03` | Produto em elaboração | Indústria → 1214 |
| `04` | Produto acabado | Indústria → 1214 |
| `05` | Subproduto | Indústria → 1214 |
| `06` | Produto intermediário | Indústria → 1214 |
| `07` | Material de uso/consumo | Neutro |
| `08` | Ativo imobilizado | Neutro |

---

## 7. API REST (main.py)

### Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Status do servidor |
| `POST` | `/processar` | Upload do .txt → processa → retorna `{id, cache}` |
| `GET` | `/resultado/{id}` | Busca resultado completo (erros, fixes, flags, sumário) |
| `GET` | `/download/{id}` | Download do arquivo corrigido em ISO-8859-1 |
| `GET` | `/historico?limit=50` | Lista todos os processamentos |
| `GET` | `/dashboard/comparativo?cnpj=&limite=12` | Série temporal por CNPJ |
| `DELETE` | `/processamento/{id}` | Remove processamento e arquivo |
| `POST` | `/editar/chave/{id}?linha=N` | Insere CHV_NFE ou exclui C100+filhos |
| `POST` | `/editar/cod_rec/{id}` | Substitui COD_REC em todos os E116 |
| `POST` | `/editar/cod_rec_st/{id}` | Substitui COD_REC nos E250 (por UF_ST) |
| `GET` | `/pendencias/{id}` | Lista pendências manuais com códigos válidos da UF |

### Endpoint `/processar` — fluxo completo

```python
# 1. Ler raw bytes → hash SHA-256 → verificar cache
# 2. Decodificar ISO-8859-1 + normalizar \n
# 3. engine.processar(conteudo)
# 4. Salvar no SQLite + arquivo corrigido em /arquivos/{id}.txt
# 5. Retornar {id, cache: bool}
```

### Endpoint `/editar/chave` — comportamento

```python
# chave = "" → EXCLUIR C100 + todos filhos até próximo C100/C990/C001
#           → _salvar_fixed() recalcula C990, 9900, 9999 automaticamente
# chave = "44 dígitos" → inserir em f[9] do C100
```

### `_salvar_fixed` — recálculo automático de contadores

```python
def _salvar_fixed(proc_id: int, lines: list[str]):
    clean = [l.rstrip("\r\n") for l in lines]
    
    # Recalcula xXX990 (C990, D990, E990...)
    for cada reg990: qtd_real = count(linhas do bloco)
    
    # Recalcula 9900 (contador por tipo de registro)
    for cada |9900|REG|N|: N = count(REG no arquivo)
    
    # Recalcula 9999
    total = count(linhas não-vazias)
    
    write_text("\n".join(clean))
```

> **Crítico**: toda modificação manual (exclusão de C100, troca de COD_REC) deve passar por `_salvar_fixed` para manter contadores corretos.

### Schema SQLite

```sql
CREATE TABLE processamentos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hash         TEXT UNIQUE,      -- SHA-256 do raw bytes (evita reprocessamento)
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
    fixes_json   TEXT
)
```

---

## 8. Frontend (Next.js)

### Proxy API

```javascript
// next.config.js
rewrites: [{ source: '/api/:path*', destination: 'http://localhost:8000/:path*' }]
```

### Tabs disponíveis

| Tab | Componente/Lógica | Quando aparece |
|---|---|---|
| Erros | Cards filtráveis | Sempre que há resultado |
| Corrigidos | Cards com orig→novo | Sempre que há resultado |
| Flags | Cards com hint | Sempre que há resultado |
| Diff | Mesmo que Corrigidos | Sempre que há resultado |
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

### Componente `PendenciasManual`

Gerencia dois tipos de pendência:

**1. CHV_NFE ausente (C100 NFC-e/NF-e)**
- Input de 44 dígitos com validação em tempo real
- Botão "Inserir chave" → `POST /editar/chave/{id}?linha=N` com `{chave: "44digits"}`
- Botão "Excluir registro" → `POST /editar/chave/{id}?linha=N` com `{chave: ""}` (exclui C100+filhos)
- Confirmação antes de excluir

**2. E116 — COD_REC + MES_REF**
- MES_REF: corrigido automaticamente pela engine (não precisa de ação)
- COD_REC: dropdown dinâmico carregado do backend (`validos_uf` da resposta)
- Badge `✓ (recomendado)` quando `cod_sugerido` está pré-selecionado
- Botão "Aplicar" → `POST /editar/cod_rec/{id}` com `{cod_rec: "..."}`

---

## 9. Bugs Resolvidos (histórico)

### Bug 1 — `\n\n` no arquivo gerado
**Causa**: ERP gerava arquivo com `\n\n` entre linhas → `split('\n')` preservava strings vazias → `"\n".join(fixed)` reconstituía o `\n\n`.  
**Fix**: normalizar entrada com `re.sub(r'\n{2,}', '\n', conteudo)` + `.rstrip('\r\n')` ao salvar.

### Bug 2 — 9999 não atualizado após inserção de C190
**Causa**: `r9999_idx` calculado antes dos `fixed.insert()` → índice deslocado após inserções.  
**Fix**: re-buscar `|9999|` diretamente em `fixed` após todos os inserts.

### Bug 3 — Fórmula E110 incorreta
**Causa**: usava `f[4]-f[8]-f[10]` em vez dos campos corretos do leiaute.  
**Fix**: `tot_cred = f[6]+f[8]+f[9]+f[10]`, `tot_deb = f[2]+f[4]+f[5]`.

### Bug 4 — K200.DT_EST inválida
**Causa**: ERP colocava o total de linhas do arquivo (`4580`) no campo de data.  
**Fix**: `fixDateFmt` tenta recuperar; se falha (valor com menos de 8 dígitos), usa `DT_FIN` do `0000` como fallback.

### Bug 5 — Contadores não recalculados após exclusão manual de C100
**Causa**: `_salvar_fixed` só atualizava `total_linhas` no banco.  
**Fix**: `_salvar_fixed` agora recalcula C990/9900/9999 diretamente no conteúdo do arquivo antes de salvar.

### Bug 6 — COD_REC inválido para a UF
**Causa**: código MG (`1206`) sendo usado em SP, onde é inválido.  
**Fix**: `detectar_cod_rec(uf, tipo_item_counts)` identifica automaticamente o código correto por UF.

### Bug 7 — E250 ausente para E210 com ICMS-ST a recolher
**Causa**: E210 tinha `VL_ICMS_RECOL_ST > 0` mas nenhum E250 filho era gerado. O PVA exige que `Soma(E250.VL_OR) = E210.VL_ICMS_RECOL_ST + E210.DEB_ESP_ST`.  
**Fix**: Engine agora gera E250 automaticamente após C190, com `VL_OR = VL_ICMS_RECOL_ST + DEB_ESP_ST`, `DT_VCTO = dia 10 do mês seguinte`, `COD_REC` por UF_ST (mapeamento para SP, AM, MT, MS, PA). UFs sem mapeamento geram flag para seleção manual.

---

## 10. Pendências Manuais (não automatizáveis)

| Registro | Campo | Motivo |
|---|---|---|
| C100 MOD=65 | CHV_NFE | Chave de acesso não está no SPED, precisa do ERP |
| E116 | COD_REC (AL, PI, SC) | UFs sem mapeamento definido, precisa do contador |
| E250 | COD_REC (UFs sem mapeamento ST) | E250 agora é gerado automaticamente, mas COD_REC depende de mapeamento por UF. UFs mapeadas: SP, AM, MT, MS, PA. Demais UFs precisam de seleção manual via `/editar/cod_rec_st` |

---

## 11. Próximas Funcionalidades Sugeridas

Ordenadas por impacto fiscal (menor imposto pago):

### Alta prioridade
1. **Crédito de ICMS sobre energia elétrica** — conta de luz de indústria gera crédito via CIAP; maioria dos ERPs não escritura
2. **Crédito de fretes de entrada** — CFOP 1351/2351 com C170 e C190 correspondentes
3. **Bloco G (CIAP)** — crédito de ativo imobilizado em 48 avos; G110 geralmente vazio ou errado
4. **Validação NCM + UF + CST** — detectar CST `000` em itens que deveriam ser `020` (redução de base) ou `040` (isento); tabela NCM × UF × benefício vigente

### Média prioridade
5. **Cruzamento E210 × E250** — ICMS ST pago vs aproveitado; C190 de 1401/2401 vs E250
6. **Devoluções sem C170** — C100 com CFOP 1201/2201 sem itens correspondentes
7. **DIFAL (E300)** — quando há CFOP 3xxx sem Bloco E300

### Arquitetura
8. **Processamento em lote** — múltiplos arquivos de uma vez (vários meses)
9. **Multi-cliente** — separar histórico por CNPJ com login simples

---

## 12. Comandos de Desenvolvimento

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Testar engine diretamente
python3 -c "
import sys; sys.path.insert(0, 'backend')
from engine import processar
with open('arquivo.txt', encoding='iso-8859-1') as f:
    res = processar(f.read())
print(f'Erros: {len(res.erros)} Fixes: {len(res.fixes)} Flags: {len(res.flags)}')
"
```

---

## 13. Notas de Arquitetura

### Encoding
Todos os arquivos SPED são **ISO-8859-1** (latin-1). Usar sempre `encoding='iso-8859-1', errors='replace'` para leitura e escrita.

### Indexação de campos
Campos do SPED são acessados por índice no array `split('|')`. O índice `0` é sempre `""` (antes do primeiro `|`) e o último também é `""` (depois do último `|`). Campo `REG` está sempre em `f[1]`.

### Linhas não-vazias vs total de linhas
O PVA conta **linhas não-vazias** para o `9999`. A engine usa `sum(1 for l in fixed if l.strip())` para o total correto.

### Cache por hash
O endpoint `/processar` calcula SHA-256 do raw bytes. Se já existe no banco, retorna `{id, cache: true}` sem reprocessar. Para forçar reprocessamento, é necessário deletar o registro primeiro.

### Vigência histórica de códigos
`F2["rec"][uf]["h"]` contém códigos com data de início/fim de validade. `cod_valido(tab, cod, dt_ref)` verifica tanto `"v"` (vigentes) quanto `"h"` (históricos na data de referência).
