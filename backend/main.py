"""
SPED Autocorretor — Backend FastAPI
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import sqlite3, json, io, hashlib, re
from datetime import datetime
from pathlib import Path
from engine import processar as processar_icms
from engine import Resultado
from engine_contrib import processar as processar_contrib

app = FastAPI(title="SPED Autocorretor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent / "sped.db"


# ── Banco de dados ────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS processamentos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hash        TEXT UNIQUE,
            nome        TEXT,
            cnpj        TEXT,
            uf          TEXT,
            dt_ini      TEXT,
            dt_fin      TEXT,
            versao      TEXT,
            criado_em   TEXT,
            total_erros INTEGER,
            total_flags INTEGER,
            total_fixes INTEGER,
            total_linhas INTEGER,
            sumario_json TEXT,
            erros_json  TEXT,
            flags_json  TEXT,
            fixes_json  TEXT,
            tipo        TEXT DEFAULT 'icms'
        );
        """)
        try:
            db.execute("ALTER TABLE processamentos ADD COLUMN tipo TEXT DEFAULT 'icms'")
        except sqlite3.OperationalError:
            pass

init_db()


def detectar_tipo_sped(conteudo: str) -> str:
    """
    Detecta se o arquivo é ICMS/IPI ou Contribuições pelo registro 0000.
    ICMS/IPI: 0000 tem 15 campos (inclui COD_FIN, IE, IM, IND_PERFIL).
    Contribuições: 0000 tem 14 campos (inclui TIPO_ESCRIT, IND_NAT_PJ, IND_ATIV).
    """
    for line in conteudo.split("\n"):
        if line.startswith("|0000|"):
            n_campos = len(line.split("|")) - 2
            return "contrib" if n_campos <= 14 else "icms"
    return "icms"


# ── Helpers ───────────────────────────────────────────────────────
def resultado_to_dict(res: Resultado) -> dict:
    return {
        "sumario": {
            "total_linhas": res.sumario.total_linhas,
            "total_regs":   res.sumario.total_regs,
            "dt_ini":       res.sumario.dt_ini,
            "dt_fin":       res.sumario.dt_fin,
            "versao":       res.sumario.versao,
            "uf":           res.sumario.uf,
            "cnpj":         res.sumario.cnpj,
            "nome":         res.sumario.nome,
            "reg_count":    res.sumario.reg_count,
            "aliq_map":     res.sumario.aliq_map,
        },
        "erros": [{"reg": e.reg, "linha": e.linha, "desc": e.desc} for e in res.erros],
        "flags": [{"reg": f.reg, "linha": f.linha, "desc": f.desc, "hint": f.hint} for f in res.flags],
        "fixes": [{"reg": f.reg, "linha": f.linha, "desc": f.desc, "orig": f.orig, "novo": f.novo} for f in res.fixes],
    }


# ── Endpoints ─────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "versao": "1.0.0"}


@app.post("/processar")
async def processar_arquivo(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(400, "Envie um arquivo .txt SPED")

    raw = await file.read()
    file_hash = hashlib.sha256(raw).hexdigest()

    with get_db() as db:
        row = db.execute("SELECT id, tipo FROM processamentos WHERE hash=?", (file_hash,)).fetchone()
        if row:
            return JSONResponse({"id": row["id"], "cache": True,
                                 "tipo": row["tipo"] if row["tipo"] else "icms"})

    try:
        conteudo = raw.decode("iso-8859-1", errors="replace")
    except Exception:
        raise HTTPException(400, "Não foi possível ler o arquivo")

    import re as _re
    conteudo = conteudo.replace("\r\n", "\n").replace("\r", "\n")
    conteudo = _re.sub(r"\n{2,}", "\n", conteudo)

    tipo = detectar_tipo_sped(conteudo)

    if tipo == "contrib":
        res = processar_contrib(conteudo)
    else:
        res = processar_icms(conteudo)

    data = resultado_to_dict(res)

    with get_db() as db:
        cur = db.execute("""
            INSERT OR IGNORE INTO processamentos
            (hash, nome, cnpj, uf, dt_ini, dt_fin, versao, criado_em,
             total_erros, total_flags, total_fixes, total_linhas,
             sumario_json, erros_json, flags_json, fixes_json, tipo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            file_hash,
            res.sumario.nome or file.filename,
            res.sumario.cnpj,
            res.sumario.uf,
            res.sumario.dt_ini,
            res.sumario.dt_fin,
            res.sumario.versao,
            datetime.now().isoformat(),
            len(res.erros),
            len(res.flags),
            len(res.fixes),
            res.sumario.total_linhas,
            json.dumps(data["sumario"],  ensure_ascii=False),
            json.dumps(data["erros"],    ensure_ascii=False),
            json.dumps(data["flags"],    ensure_ascii=False),
            json.dumps(data["fixes"],    ensure_ascii=False),
            tipo,
        ))
        new_id = cur.lastrowid
        _fixed_path(new_id).write_text(
            "\n".join(l.rstrip("\r\n") for l in res.fixed_lines),
            encoding="iso-8859-1", errors="replace"
        )

    return JSONResponse({"id": new_id, "cache": False, "tipo": tipo})


@app.get("/resultado/{proc_id}")
def get_resultado(proc_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM processamentos WHERE id=?", (proc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Processamento não encontrado")
    return {
        "id":          row["id"],
        "nome":        row["nome"],
        "cnpj":        row["cnpj"],
        "uf":          row["uf"],
        "dt_ini":      row["dt_ini"],
        "dt_fin":      row["dt_fin"],
        "versao":      row["versao"],
        "criado_em":   row["criado_em"],
        "total_erros": row["total_erros"],
        "total_flags": row["total_flags"],
        "total_fixes": row["total_fixes"],
        "total_linhas":row["total_linhas"],
        "tipo":        row["tipo"] if row["tipo"] else "icms",
        "sumario":     json.loads(row["sumario_json"]),
        "erros":       json.loads(row["erros_json"]),
        "flags":       json.loads(row["flags_json"]),
        "fixes":       json.loads(row["fixes_json"]),
    }


@app.get("/download/{proc_id}")
def download_corrigido(proc_id: int):
    path = _fixed_path(proc_id)
    if not path.exists():
        raise HTTPException(404, "Arquivo não encontrado")
    with get_db() as db:
        row = db.execute("SELECT nome, dt_ini FROM processamentos WHERE id=?", (proc_id,)).fetchone()
    nome = (row["nome"] if row else "SPED").replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(path.read_bytes()),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="SPED_{nome}_corrigido.txt"'},
    )


@app.get("/historico")
def historico(limit: int = 50):
    with get_db() as db:
        rows = db.execute("""
            SELECT id, nome, cnpj, uf, dt_ini, dt_fin, versao, criado_em,
                   total_erros, total_flags, total_fixes, total_linhas, tipo
            FROM processamentos ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/dashboard/comparativo")
def comparativo(cnpj: str, limite: int = 12):
    """Retorna histórico de métricas por mês para um CNPJ — base do dashboard comparativo."""
    with get_db() as db:
        rows = db.execute("""
            SELECT id, dt_ini, dt_fin, total_erros, total_flags, total_fixes,
                   total_linhas, sumario_json
            FROM processamentos
            WHERE cnpj=?
            ORDER BY dt_ini DESC LIMIT ?
        """, (cnpj, limite)).fetchall()
    result = []
    for r in rows:
        s = json.loads(r["sumario_json"])
        result.append({
            "id":           r["id"],
            "dt_ini":       r["dt_ini"],
            "dt_fin":       r["dt_fin"],
            "total_erros":  r["total_erros"],
            "total_flags":  r["total_flags"],
            "total_fixes":  r["total_fixes"],
            "total_linhas": r["total_linhas"],
            "aliq_map":     s.get("aliq_map", {}),
            "reg_count":    s.get("reg_count", {}),
        })
    return result


@app.delete("/processamento/{proc_id}")
def deletar(proc_id: int):
    with get_db() as db:
        db.execute("DELETE FROM processamentos WHERE id=?", (proc_id,))
    p = _fixed_path(proc_id)
    if p.exists(): p.unlink()
    return {"ok": True}


# ── Helpers internos ──────────────────────────────────────────────
def _fixed_path(proc_id: int) -> Path:
    d = Path(__file__).parent / "arquivos"
    d.mkdir(exist_ok=True)
    return d / f"{proc_id}.txt"


# ── Endpoints de edição manual ────────────────────────────────────
from pydantic import BaseModel

class EditarChaveRequest(BaseModel):
    chave: str  # 44 dígitos, ou "" para excluir

class EditarCodRecRequest(BaseModel):
    cod_rec: str   # ex: "1206"
    linha_e116: int  # 1-based no arquivo

def _ler_fixed(proc_id: int) -> list[str]:
    p = _fixed_path(proc_id)
    if not p.exists():
        raise HTTPException(404, "Arquivo não encontrado")
    return p.read_text(encoding="iso-8859-1", errors="replace").split("\n")

def _salvar_fixed(proc_id: int, lines: list[str]):
    # Limpar linhas
    clean = [l.rstrip("\r\n") for l in lines if l.rstrip("\r\n") != "" or False]
    # Na verdade preservar vazias só se originais — mas garantir sem \n embutido
    clean = [l.rstrip("\r\n") for l in lines]

    # ── Recalcular todos os contadores estruturais ────────────────
    # Contagem por registro
    from collections import Counter
    reg_count: Counter = Counter()
    for l in clean:
        if l.strip() and l.startswith("|"):
            p = l.split("|")
            if len(p) > 1:
                reg_count[p[1].strip()] += 1

    # Inserir 9900 para registros que existem mas não têm entrada
    existing_9900_refs: set = set()
    for l in clean:
        if l.startswith("|9900|"):
            p = l.split("|")
            if len(p) > 2:
                existing_9900_refs.add(p[2].strip())
    missing = set(reg_count.keys()) - existing_9900_refs
    if missing:
        ins_pt = next((i for i, l in enumerate(clean)
                       if l.startswith("|9990|") or l.startswith("|9999|")), len(clean))
        for ref in sorted(missing):
            if reg_count[ref] > 0:
                clean.insert(ins_pt, f"|9900|{ref}|{reg_count[ref]}|")
                ins_pt += 1
        reg_count = Counter()
        for l in clean:
            if l.strip() and l.startswith("|"):
                p = l.split("|")
                if len(p) > 1:
                    reg_count[p[1].strip()] += 1

    # xXX990 — contar linhas do bloco
    for i, l in enumerate(clean):
        if not l.startswith("|"): continue
        p = l.split("|")
        if len(p) < 3: continue
        reg = p[1].strip()
        if len(reg) == 4 and reg.endswith("990"):
            bloco = reg[0]
            qtd_real = sum(v for k, v in reg_count.items()
                           if k and k[0] == bloco)
            if p[2].strip() != str(qtd_real):
                p[2] = str(qtd_real)
                clean[i] = "|".join(p)

    # 9900 — contador por tipo de registro
    for i, l in enumerate(clean):
        if not l.startswith("|9900|"): continue
        p = l.split("|")
        if len(p) < 4: continue
        ref = p[2].strip()
        qtd_real = reg_count.get(ref, 0)
        if qtd_real > 0 and p[3].strip() != str(qtd_real):
            p[3] = str(qtd_real)
            clean[i] = "|".join(p)

    # 9999 — total de linhas não-vazias
    total = sum(1 for l in clean if l.strip())
    for i, l in enumerate(clean):
        if not l.startswith("|9999|"): continue
        p = l.split("|")
        if len(p) < 3: continue
        if p[2].strip() != str(total):
            p[2] = str(total)
            clean[i] = "|".join(p)
        break

    _fixed_path(proc_id).write_text(
        "\n".join(clean), encoding="iso-8859-1", errors="replace"
    )
    with get_db() as db:
        db.execute("UPDATE processamentos SET total_linhas=? WHERE id=?", (total, proc_id))


@app.post("/editar/chave/{proc_id}")
def editar_chave_nfe(proc_id: int, req: EditarChaveRequest, linha: int = 0):
    """
    Insere ou corrige CHV_NFE em um C100 (linha 1-based não-vazia no arquivo).
    Se chave="" → exclui o C100 e todos os seus filhos (C170, C190 etc.).
    """
    lines = _ler_fixed(proc_id)

    # Mapear linha 1-based (do PVA, contando apenas não-vazias) → índice real
    nao_vazias = [(i, l) for i, l in enumerate(lines) if l.strip()]
    if linha < 1 or linha > len(nao_vazias):
        raise HTTPException(400, f"Linha {linha} fora do intervalo (total: {len(nao_vazias)})")

    idx_real, linha_str = nao_vazias[linha - 1]
    p = linha_str.split("|")
    if len(p) < 2 or p[1].strip() != "C100":
        raise HTTPException(400, f"Linha {linha} não é um registro C100")

    chave = req.chave.strip().replace(" ", "")

    if chave == "":
        # Excluir C100 + todos filhos até próximo C100 ou C990/C001
        fim = idx_real + 1
        while fim < len(lines):
            l2 = lines[fim]
            if l2.startswith("|"):
                r2 = l2.split("|")[1].strip() if len(l2.split("|")) > 1 else ""
                if r2 in ("C100", "C990", "C001", "C990"): break
            fim += 1
        del lines[idx_real:fim]
        _salvar_fixed(proc_id, lines)
        return {"ok": True, "acao": "excluido", "linhas_removidas": fim - idx_real}
    else:
        if len(chave) != 44 or not chave.isdigit():
            raise HTTPException(400, "CHV_NFE deve ter exatamente 44 dígitos numéricos")
        while len(p) <= 9:
            p.append("")
        p[9] = chave
        lines[idx_real] = "|".join(p)
        _salvar_fixed(proc_id, lines)
        return {"ok": True, "acao": "chave_inserida", "chave": chave}


@app.post("/editar/cod_rec/{proc_id}")
def editar_cod_rec(proc_id: int, req: EditarCodRecRequest):
    """Substitui COD_REC em todos os E116 do arquivo. Aceita qualquer código válido para a UF."""
    from engine import F2, cod_valido
    lines = _ler_fixed(proc_id)
    # Obter UF do arquivo
    uf = ""
    for l in lines:
        if l.startswith("|0000|"):
            p = l.split("|")
            uf = p[9].strip() if len(p)>9 else ""
            break
    # Validar contra tabela da UF
    if uf and F2.get("rec", {}).get(uf):
        v1, _ = cod_valido(F2["rec"][uf], req.cod_rec, "")
        v2, _ = cod_valido(F2["rec"].get("GLOBAL",{}), req.cod_rec, "")
        if not v1 and not v2:
            raise HTTPException(400, f"COD_REC \"{req.cod_rec}\" inválido para {uf}")

    lines = _ler_fixed(proc_id)
    alterados = 0
    for i, l in enumerate(lines):
        if l.startswith("|E116|"):
            p = l.split("|")
            while len(p) <= 5: p.append("")
            if p[5].strip() != req.cod_rec:
                p[5] = req.cod_rec
                lines[i] = "|".join(p)
                alterados += 1
    _salvar_fixed(proc_id, lines)
    return {"ok": True, "alterados": alterados, "cod_rec": req.cod_rec}


class EditarCodRecE250Request(BaseModel):
    cod_rec: str
    uf_st: str = ""

@app.post("/editar/cod_rec_st/{proc_id}")
def editar_cod_rec_st(proc_id: int, req: EditarCodRecE250Request):
    """Substitui COD_REC nos E250 do arquivo para a UF_ST especificada."""
    from engine import F2, cod_valido
    lines = _ler_fixed(proc_id)
    uf_alvo = req.uf_st.strip().upper()

    if uf_alvo and F2.get("rec", {}).get(uf_alvo):
        v1, _ = cod_valido(F2["rec"][uf_alvo], req.cod_rec, "")
        v2, _ = cod_valido(F2["rec"].get("GLOBAL",{}), req.cod_rec, "")
        if not v1 and not v2:
            raise HTTPException(400, f"COD_REC \"{req.cod_rec}\" inválido para {uf_alvo}")

    cur_uf = ""
    alterados = 0
    for i, l in enumerate(lines):
        if l.startswith("|E200|"):
            p = l.split("|")
            cur_uf = p[2].strip() if len(p) > 2 else ""
        elif l.startswith("|E250|"):
            if uf_alvo and cur_uf != uf_alvo:
                continue
            p = l.split("|")
            while len(p) <= 5: p.append("")
            if p[5].strip() != req.cod_rec:
                p[5] = req.cod_rec
                lines[i] = "|".join(p)
                alterados += 1
    _salvar_fixed(proc_id, lines)
    return {"ok": True, "alterados": alterados, "cod_rec": req.cod_rec, "uf_st": uf_alvo}


class EditarCampoRequest(BaseModel):
    linha: int
    campo_idx: int
    novo_valor: str

@app.post("/editar/campo/{proc_id}")
def editar_campo(proc_id: int, req: EditarCampoRequest):
    """Edita um campo específico de uma linha (1-based não-vazia)."""
    lines = _ler_fixed(proc_id)
    nao_vazias = [(i, l) for i, l in enumerate(lines) if l.strip()]
    if req.linha < 1 or req.linha > len(nao_vazias):
        raise HTTPException(400, f"Linha {req.linha} fora do intervalo")
    idx_real, linha_str = nao_vazias[req.linha - 1]
    p = linha_str.split("|")
    if req.campo_idx < 0 or req.campo_idx >= len(p):
        raise HTTPException(400, f"Campo {req.campo_idx} fora do intervalo (máx {len(p)-1})")
    antigo = p[req.campo_idx]
    p[req.campo_idx] = req.novo_valor
    lines[idx_real] = "|".join(p)
    _salvar_fixed(proc_id, lines)
    return {"ok": True, "antigo": antigo, "novo": req.novo_valor, "linha": req.linha}


class EditarCodPartRequest(BaseModel):
    linha: int
    cod_part: str

@app.post("/editar/cod_part/{proc_id}")
def editar_cod_part(proc_id: int, req: EditarCodPartRequest):
    """Troca o COD_PART de um C100 específico (corrige CNPJ divergente da chave)."""
    lines = _ler_fixed(proc_id)
    nao_vazias = [(i, l) for i, l in enumerate(lines) if l.strip()]
    if req.linha < 1 or req.linha > len(nao_vazias):
        raise HTTPException(400, f"Linha {req.linha} fora do intervalo")
    idx_real, linha_str = nao_vazias[req.linha - 1]
    p = linha_str.split("|")
    if len(p) < 2 or p[1].strip() != "C100":
        raise HTTPException(400, f"Linha {req.linha} não é um registro C100")
    antigo = p[4].strip() if len(p) > 4 else ""
    while len(p) <= 4: p.append("")
    p[4] = req.cod_part
    lines[idx_real] = "|".join(p)
    _salvar_fixed(proc_id, lines)
    return {"ok": True, "antigo": antigo, "novo": req.cod_part, "linha": req.linha}


@app.get("/pendencias/{proc_id}")
def listar_pendencias(proc_id: int):
    """Retorna pendências manuais (ICMS/IPI ou Contribuições)."""
    with get_db() as db:
        row = db.execute("SELECT tipo FROM processamentos WHERE id=?", (proc_id,)).fetchone()
    tipo = (row["tipo"] if row and row["tipo"] else "icms")

    if tipo == "contrib":
        return _pendencias_contrib(proc_id)
    return _pendencias_icms(proc_id)


def _pendencias_contrib(proc_id: int) -> dict:
    """Pendências específicas de Contribuições."""
    lines = _ler_fixed(proc_id)
    nao_vazias = [l for l in lines if l.strip()]
    pendencias = []

    uf_arq = ""
    cnpj0000 = ""
    participantes: dict[str, str] = {}  # cod_part → cnpj

    for l in nao_vazias:
        p = l.split("|")
        if len(p) < 2: continue
        reg = p[1].strip()
        if reg == "0000":
            uf_arq = p[10].strip() if len(p) > 10 else ""
            cnpj0000 = p[9].strip() if len(p) > 9 else ""
        elif reg == "0150" and len(p) > 5:
            cod_part = p[2].strip()
            cnpj_part = p[5].strip() if len(p) > 5 else ""
            cpf_part = p[6].strip() if len(p) > 6 else ""
            if cod_part:
                participantes[cod_part] = cnpj_part or cpf_part

    for linha_1based, l in enumerate(nao_vazias, 1):
        p = l.split("|")
        if len(p) < 2: continue
        reg = p[1].strip()

        if reg == "C100":
            cod_mod = p[5].strip() if len(p) > 5 else ""
            cod_sit = p[6].strip() if len(p) > 6 else ""
            chv = re.sub(r"\D", "", p[9]) if len(p) > 9 else ""
            num_doc = p[8].strip() if len(p) > 8 else "?"
            dt_doc = p[10].strip() if len(p) > 10 else ""
            cod_part = p[4].strip() if len(p) > 4 else ""

            if cod_mod in ("55", "65") and cod_sit not in {"05"} and not chv:
                pendencias.append({
                    "tipo": "chv_nfe",
                    "reg": "C100",
                    "linha": linha_1based,
                    "num_doc": num_doc,
                    "dt_doc": dt_doc,
                    "cod_mod": cod_mod,
                    "raw": l[:120],
                    "descricao": f"NF-e/NFC-e nº {num_doc} sem chave de acesso"
                })

            if chv and len(chv) == 44 and cod_part:
                cnpj_chv = chv[6:20]
                ind_emit = p[3].strip() if len(p) > 3 else ""
                cnpj_part = participantes.get(cod_part, "")
                divergente = False
                if ind_emit == "1" and cnpj_part and cnpj_chv != cnpj_part:
                    divergente = True
                elif ind_emit == "0" and cnpj0000 and cnpj_chv != cnpj0000:
                    divergente = True
                if divergente:
                    part_correto = ""
                    for cp, cn in participantes.items():
                        if cn == cnpj_chv:
                            part_correto = cp
                            break
                    cnpj_esperado = cnpj_part if ind_emit == "1" else cnpj0000
                    pendencias.append({
                        "tipo": "cnpj_chv_divergente",
                        "reg": "C100",
                        "linha": linha_1based,
                        "num_doc": num_doc,
                        "dt_doc": dt_doc,
                        "cod_mod": cod_mod,
                        "raw": l[:120],
                        "descricao": f"CNPJ da chave ({cnpj_chv}) ≠ {'participante' if ind_emit == '1' else 'emitente'} ({cnpj_esperado})",
                        "cnpj_chave": cnpj_chv,
                        "cnpj_participante": cnpj_esperado,
                        "cod_part_atual": cod_part,
                        "cod_part_correto": part_correto,
                    })

        if reg == "C170" and len(p) > 32:
            cst_pis = p[25].strip() if len(p) > 25 else ""
            cst_cofins = p[31].strip() if len(p) > 31 else ""
            bc_pis_s = p[26].strip() if len(p) > 26 else ""
            bc_cof_s = p[32].strip() if len(p) > 32 else ""
            bc_pis = float(bc_pis_s.replace(",", ".")) if bc_pis_s else 0.0
            bc_cof = float(bc_cof_s.replace(",", ".")) if bc_cof_s else 0.0
            if bc_pis_s and bc_cof_s and abs(bc_pis - bc_cof) > 0.02:
                cod_item = p[3].strip() if len(p) > 3 else ""
                cfop = p[11].strip() if len(p) > 11 else ""
                pendencias.append({
                    "tipo": "bc_assimetria",
                    "reg": "C170",
                    "linha": linha_1based,
                    "raw": l[:120],
                    "descricao": f"BC PIS ({bc_pis_s}) ≠ BC COFINS ({bc_cof_s})",
                    "cod_item": cod_item,
                    "cfop": cfop,
                    "bc_pis": bc_pis_s,
                    "bc_cofins": bc_cof_s,
                    "cst_pis": cst_pis,
                    "cst_cofins": cst_cofins,
                })

        if reg == "M205" and len(p) > 3:
            cod_rec = p[3].strip()
            if not cod_rec:
                pendencias.append({
                    "tipo": "m205_cod_rec",
                    "reg": "M205",
                    "linha": linha_1based,
                    "cod_rec_atual": "",
                    "raw": l[:120],
                    "descricao": "M205: COD_REC PIS ausente"
                })

        if reg == "M605" and len(p) > 3:
            cod_rec = p[3].strip()
            if not cod_rec:
                pendencias.append({
                    "tipo": "m605_cod_rec",
                    "reg": "M605",
                    "linha": linha_1based,
                    "cod_rec_atual": "",
                    "raw": l[:120],
                    "descricao": "M605: COD_REC COFINS ausente"
                })

    return {"pendencias": pendencias, "total": len(pendencias), "uf": uf_arq,
            "tipo_sped": "contrib"}


def _pendencias_icms(proc_id: int) -> dict:
    """Pendências ICMS/IPI (lógica original)."""
    lines = _ler_fixed(proc_id)
    nao_vazias = [l for l in lines if l.strip()]

    dt_ini = ""
    for l in nao_vazias:
        if l.startswith("|0000|"):
            p = l.split("|")
            dt_ini = p[4].strip() if len(p) > 4 else ""
            break
    mes_ref_esperado = (dt_ini[2:4] + dt_ini[4:8]) if len(dt_ini) == 8 else ""

    pendencias = []
    from engine import F2, cod_valido, detectar_cod_rec, detectar_cod_rec_st
    uf_e116 = ""
    for l in nao_vazias:
        if l.startswith("|0000|"):
            p0 = l.split("|")
            uf_e116 = p0[9].strip() if len(p0) > 9 else ""
            break

    validos_uf = []
    if uf_e116 and F2.get("rec", {}).get(uf_e116):
        validos_uf = F2["rec"][uf_e116].get("v", [])[:50]

    tipo_counts: dict = {}
    for l in nao_vazias:
        if l.startswith("|0200|"):
            p0 = l.split("|")
            t = p0[7].strip() if len(p0) > 7 else ""
            if t: tipo_counts[t] = tipo_counts.get(t, 0) + 1
    cod_sugerido = detectar_cod_rec(uf_e116, tipo_counts)

    cur_e200_uf_pend = ""
    for linha_1based, l in enumerate(nao_vazias, 1):
        p = l.split("|")
        if len(p) < 2: continue
        reg = p[1].strip()

        if reg == "C100":
            cod_mod = p[5].strip() if len(p) > 5 else ""
            cod_sit = p[6].strip() if len(p) > 6 else ""
            chv = p[9].strip() if len(p) > 9 else ""
            if cod_mod in ("55", "65") and cod_sit not in {"05"} and not chv:
                num_doc = p[8].strip() if len(p) > 8 else "?"
                dt_doc = p[10].strip() if len(p) > 10 else ""
                pendencias.append({
                    "tipo": "chv_nfe",
                    "reg": "C100",
                    "linha": linha_1based,
                    "num_doc": num_doc,
                    "dt_doc": dt_doc,
                    "cod_mod": cod_mod,
                    "raw": l[:120],
                    "descricao": f"NF-e/NFC-e nº {num_doc} sem chave de acesso"
                })

        if reg == "E116":
            cod_rec = p[5].strip() if len(p) > 5 else ""
            mes_ref = p[10].strip() if len(p) > 10 else ""
            cod_invalido = False
            if uf_e116 and F2.get("rec", {}).get(uf_e116):
                v1, _ = cod_valido(F2["rec"][uf_e116], cod_rec, "")
                v2, _ = cod_valido(F2["rec"].get("GLOBAL", {}), cod_rec, "")
                cod_invalido = not v1 and not v2
            pendencias.append({
                "tipo": "e116",
                "reg": "E116",
                "linha": linha_1based,
                "cod_rec_atual": cod_rec,
                "cod_rec_invalido": cod_invalido,
                "cod_sugerido": cod_sugerido,
                "validos_uf": validos_uf,
                "uf": uf_e116,
                "mes_ref_atual": mes_ref,
                "mes_ref_esperado": mes_ref_esperado,
                "raw": l[:120],
                "descricao": f"E116: COD_REC={cod_rec or '(vazio)'} MES_REF={mes_ref or '(vazio)'}"
            })

        if reg == "E200" and len(p) > 4:
            cur_e200_uf_pend = p[2].strip()

        if reg == "E250":
            cod_rec_e250 = p[5].strip() if len(p) > 5 else ""
            uf_st = cur_e200_uf_pend if cur_e200_uf_pend else uf_e116
            cod_invalido_st = False
            validos_uf_st = []
            if uf_st and F2.get("rec", {}).get(uf_st):
                validos_uf_st = F2["rec"][uf_st].get("v", [])[:50]
                v1, _ = cod_valido(F2["rec"][uf_st], cod_rec_e250, "")
                v2, _ = cod_valido(F2["rec"].get("GLOBAL", {}), cod_rec_e250, "")
                cod_invalido_st = not v1 and not v2
            cod_sug_st = detectar_cod_rec_st(uf_st)
            if cod_invalido_st or not cod_rec_e250:
                pendencias.append({
                    "tipo": "e250",
                    "reg": "E250",
                    "linha": linha_1based,
                    "cod_rec_atual": cod_rec_e250,
                    "cod_rec_invalido": cod_invalido_st or not cod_rec_e250,
                    "cod_sugerido_st": cod_sug_st,
                    "validos_uf": validos_uf_st,
                    "uf": uf_st,
                    "raw": l[:120],
                    "descricao": f"E250: COD_REC={cod_rec_e250 or '(vazio)'} UF_ST={uf_st}"
                })

    return {"pendencias": pendencias, "total": len(pendencias), "uf": uf_e116,
            "cod_sugerido": cod_sugerido, "validos_uf": validos_uf, "tipo_sped": "icms"}
