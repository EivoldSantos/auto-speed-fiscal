"""
Engine de validação e correção SPED EFD-Contribuições (PIS/COFINS)
Baseada no descritor.xml oficial do PVA SERPRO (182 registros)
+ Guia Prático EFD-Contribuições (Seção 4 — Obrigatoriedade)
+ Auto-geração do Bloco M quando ausente/incompleto
"""
from __future__ import annotations
import json, re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from datetime import date
from typing import Optional

# ── Carregar dados PVA Contribuições ──────────────────────────────
_BASE = Path(__file__).parent
with open(_BASE / "dados_pva_contrib.json", encoding="utf-8") as _f:
    _D = json.load(_f)

LEIAUTE      = _D["leiaute"]
CFOP_SET     = set(_D["cfop"].keys())
CST_PIS_SET  = set(_D["cst_pis"].keys())
CST_COFINS_SET = set(_D["cst_cofins"].keys())
CST_IPI_SET  = set(_D.get("cst_ipi", {}).keys())
MOD_DOC_SET  = set(_D["mod_doc"].keys())
VERSOES      = _D["versoes"]
UF_COD       = _D["uf_cod"]

COD_SIT_SET  = {"00","01","02","03","04","05","06","07","08"}

CST_PIS_TRIBUTAVEL  = {"01","02","03","04","05"}
CST_COFINS_TRIBUTAVEL = {"01","02","03","04","05"}
CST_ENTRADA = {f"{i:02d}" for i in range(50, 67)} | {f"{i:02d}" for i in range(70, 76)} | {"98","99"}
CST_SAIDA   = {f"{i:02d}" for i in range(1, 50)} | {"99"}
CST_ISENTO_ZERO_SUSP = {"04","06","07","08","09"}

BLOCOS_CONTRIB_ORDERED = ["0","A","C","D","F","I","M","P","1","9"]


# ── Helpers ───────────────────────────────────────────────────────
def to_num(s: str) -> Optional[float]:
    if s is None or s.strip() == "": return None
    try: return float(s.strip().replace(",", "."))
    except: return None

def fmt_n(n: float, d: int = 2) -> str:
    return f"{n:.{d}f}".replace(".", ",")

def parse_date(s: str) -> Optional[date]:
    if not s or len(s) != 8: return None
    try:
        d, m, y = int(s[:2]), int(s[2:4]), int(s[4:])
        return date(y, m, d)
    except: return None

def valid_date(s: str) -> bool:
    return parse_date(s) is not None

def fix_date_fmt(s: str) -> Optional[str]:
    if not s: return None
    d = re.sub(r"\D", "", s)
    return d if len(d) == 8 and valid_date(d) else None

def get_uf_from_mun(mun: str) -> Optional[str]:
    if not mun or len(mun) < 2: return None
    return UF_COD.get(mun[:2])

def get_cod_ver(dt_ini: str) -> Optional[dict]:
    dt = parse_date(dt_ini)
    if not dt: return None
    for cod, v in VERSOES.items():
        ini = parse_date(v["dt_ini"])
        fim = parse_date(v["dt_fim"]) if v.get("dt_fim") else date(9999, 1, 1)
        if ini and ini <= dt <= fim:
            return {"cod": cod}
    return None


# ── Dataclasses de resultado ──────────────────────────────────────
@dataclass
class Erro:
    reg: str
    linha: int
    desc: str

@dataclass
class Flag:
    reg: str
    linha: int
    desc: str
    hint: str = ""

@dataclass
class Fix:
    reg: str
    linha: int
    desc: str
    orig: str
    novo: str

@dataclass
class Sumario:
    total_linhas: int = 0
    total_regs: int = 0
    dt_ini: str = "—"
    dt_fin: str = "—"
    versao: str = "—"
    uf: str = "—"
    cnpj: str = ""
    nome: str = ""
    reg_count: dict = field(default_factory=dict)
    aliq_map: dict = field(default_factory=dict)

@dataclass
class Resultado:
    erros: list[Erro] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    fixes: list[Fix]  = field(default_factory=list)
    sumario: Sumario  = field(default_factory=Sumario)
    fixed_lines: list[str] = field(default_factory=list)


# ── Engine principal ──────────────────────────────────────────────
def processar(conteudo: str) -> Resultado:
    lines = conteudo.split("\n")
    fixed = list(lines)
    res   = Resultado()

    # ── Estado global ──
    dt_ini0000 = ""
    dt_fin0000 = ""
    cnpj0000 = ""
    uf = None
    r9999_idx = -1
    reg_count: dict[str, int] = {}
    cod_inc_trib = ""
    ind_reg_cum = ""
    idx_0110 = -1
    has_c100_global = False

    # ── Cadastros para referência cruzada (D1/D2) ──
    participantes_0150: set[str] = set()
    itens_0200: set[str] = set()

    # ── Rastrear C010 e seus filhos para IND_ESCRI (A1) ──
    c010_info: list[dict] = []
    current_c010_idx = -1

    # ── Rastrear blocos presentes (A2/A3) ──
    blocos_presentes: set[str] = set()
    regs_abertura: dict[str, int] = {}
    regs_fechamento: dict[str, int] = {}

    # ── Acumuladores para cross-check Bloco M ──
    acum_pis_bc = 0.0
    acum_pis_vl = 0.0
    acum_cofins_bc = 0.0
    acum_cofins_vl = 0.0

    # E1: acumuladores para auto-geração M
    acum_rec_brt_pis = 0.0
    acum_rec_brt_cofins = 0.0
    acum_isento_pis: dict[str, float] = defaultdict(float)
    acum_isento_cofins: dict[str, float] = defaultdict(float)
    cod_cta_saida = ""
    cod_cta_entrada = ""
    cod_cta_freq: dict[str, int] = defaultdict(int)

    # M210/M610: acumular TODOS (C1)
    m210_entries: list[dict] = []
    m610_entries: list[dict] = []
    m200_vl_tot_cont = 0.0; m200_ln = -1; m200_idx = -1
    m600_vl_tot_cont = 0.0; m600_ln = -1; m600_idx = -1
    m990_idx = -1

    # Registros M presentes
    cst_pis_usados: set[str] = set()
    cst_cofins_usados: set[str] = set()
    tem_m205 = False; tem_m605 = False
    tem_m400 = False; tem_m800 = False
    tem_m410 = False; tem_m810 = False
    tem_m100 = False; tem_m500 = False
    tem_1900 = False

    def rec_err(reg, ln, desc):
        res.erros.append(Erro(reg, ln, desc))

    def rec_flag(reg, ln, desc, hint=""):
        res.flags.append(Flag(reg, ln, desc, hint))

    def rec_fix(idx, fi, orig, novo, reg, ln, desc):
        res.fixes.append(Fix(reg, ln, desc, str(orig), str(novo)))
        p = fixed[idx].split("|")
        p[fi] = novo
        fixed[idx] = "|".join(p)

    def fix_len(idx, f, fi, max_len, reg, ln, nome):
        val = (f[fi] if fi < len(f) else "").strip()
        if max_len > 0 and len(val) > max_len:
            novo = val[:max_len]
            rec_fix(idx, fi, val, novo, reg, ln, f"{nome} truncado ({len(val)}>{max_len})")
            f[fi] = novo

    def fix_pipe(idx, f, fi, n_esperado, reg, ln, nome):
        excess = len(f) - 2 - n_esperado
        if excess <= 0: return
        parts = f[fi:fi+excess+1]
        joined = " - ".join(p.strip() for p in parts if p.strip())
        rec_fix(idx, fi, "|".join(parts), joined, reg, ln, f"{nome}: pipe removido")
        new_f = f[:fi] + [joined] + f[fi+excess+1:]
        f.clear(); f.extend(new_f)

    # ── PASSAGEM 1: coletar estado global ─────────────────────────
    for i, l in enumerate(lines):
        if not l.strip() or not l.startswith("|"): continue
        p = l.split("|")
        if len(p) < 2: continue
        reg = p[1].strip()
        reg_count[reg] = reg_count.get(reg, 0) + 1
        res.sumario.total_regs += 1

        if reg and len(reg) >= 2:
            bloco_letra = reg[0]
            blocos_presentes.add(bloco_letra)
            if reg.endswith("001"):
                regs_abertura[bloco_letra] = i
            elif reg.endswith("990"):
                regs_fechamento[bloco_letra] = i

        if reg == "0000":
            dt_ini0000 = p[6].strip() if len(p) > 6 else ""
            dt_fin0000 = p[7].strip() if len(p) > 7 else ""
            res.sumario.nome = p[8].strip() if len(p) > 8 else ""
            cnpj0000 = p[9].strip() if len(p) > 9 else ""
            res.sumario.cnpj = cnpj0000
            uf_dir = p[10].strip() if len(p) > 10 else ""
            if len(uf_dir) == 2 and uf_dir.isalpha():
                uf = uf_dir.upper()
            else:
                uf = get_uf_from_mun(p[11].strip() if len(p) > 11 else "")

        elif reg == "0110":
            cod_inc_trib = p[2].strip() if len(p) > 2 else ""
            ind_reg_cum = p[5].strip() if len(p) > 5 else ""
            idx_0110 = i

        elif reg == "0150" and len(p) > 2:
            participantes_0150.add(p[2].strip())

        elif reg == "0200" and len(p) > 2:
            itens_0200.add(p[2].strip())

        elif reg == "C010":
            ind_escri = p[3].strip() if len(p) > 3 else ""
            c010_info.append({"idx": i, "ind_escri": ind_escri, "cnpj": p[2].strip() if len(p) > 2 else "",
                              "has_c100": False, "has_c170": False, "has_c175": False,
                              "has_c180": False, "has_c190": False, "has_c490": False})
            current_c010_idx = len(c010_info) - 1

        if reg == "C100":
            has_c100_global = True

        if reg in ("C100", "C170", "C175", "C180", "C190", "C490") and current_c010_idx >= 0:
            key = f"has_{reg.lower()}"
            if key in c010_info[current_c010_idx]:
                c010_info[current_c010_idx][key] = True

        if reg == "9999": r9999_idx = i
        if reg == "1900": tem_1900 = True
        if reg == "M205": tem_m205 = True
        if reg == "M605": tem_m605 = True
        if reg == "M400": tem_m400 = True
        if reg == "M800": tem_m800 = True
        if reg == "M410": tem_m410 = True
        if reg == "M810": tem_m810 = True
        if reg == "M100": tem_m100 = True
        if reg == "M500": tem_m500 = True
        if reg == "M990": m990_idx = i

        # Acumuladores C170 PIS/COFINS
        if reg == "C170" and len(p) > 25:
            cst_pis = p[25].strip() if len(p) > 25 else ""
            cst_cofins = p[31].strip() if len(p) > 31 else ""
            vl_item = to_num(p[7]) or 0
            bc_pis = to_num(p[26]) or 0
            vl_pis = to_num(p[30]) or 0
            bc_cofins = to_num(p[32]) if len(p) > 32 else None
            bc_cofins = (bc_cofins or 0) if bc_cofins is not None else 0
            vl_cofins = to_num(p[36]) if len(p) > 36 else None
            vl_cofins = (vl_cofins or 0) if vl_cofins is not None else 0
            if cst_pis: cst_pis_usados.add(cst_pis)
            if cst_cofins: cst_cofins_usados.add(cst_cofins)
            if cst_pis in CST_PIS_TRIBUTAVEL:
                acum_pis_bc += bc_pis
                acum_pis_vl += vl_pis
                acum_rec_brt_pis += vl_item
            if cst_cofins in CST_COFINS_TRIBUTAVEL:
                acum_cofins_bc += bc_cofins
                acum_cofins_vl += vl_cofins
                acum_rec_brt_cofins += vl_item
            if cst_pis in CST_ISENTO_ZERO_SUSP:
                acum_isento_pis[cst_pis] += vl_item
            if cst_cofins in CST_ISENTO_ZERO_SUSP:
                acum_isento_cofins[cst_cofins] += vl_item
            # COD_CTA frequency
            cod_cta = p[37].strip() if len(p) > 37 else ""
            if cod_cta:
                cod_cta_freq[cod_cta] += 1

        # Acumuladores C175 PIS/COFINS
        if reg == "C175" and len(p) > 5:
            cst_pis = p[5].strip() if len(p) > 5 else ""
            cst_cofins = p[11].strip() if len(p) > 11 else ""
            vl_item_c175 = to_num(p[3]) or 0
            bc_pis = to_num(p[6]) if len(p) > 6 else None
            bc_pis = (bc_pis or 0) if bc_pis is not None else 0
            vl_pis = to_num(p[10]) if len(p) > 10 else None
            vl_pis = (vl_pis or 0) if vl_pis is not None else 0
            bc_cofins = to_num(p[12]) if len(p) > 12 else None
            bc_cofins = (bc_cofins or 0) if bc_cofins is not None else 0
            vl_cofins = to_num(p[16]) if len(p) > 16 else None
            vl_cofins = (vl_cofins or 0) if vl_cofins is not None else 0
            if cst_pis: cst_pis_usados.add(cst_pis)
            if cst_cofins: cst_cofins_usados.add(cst_cofins)
            if cst_pis in CST_PIS_TRIBUTAVEL:
                acum_pis_bc += bc_pis
                acum_pis_vl += vl_pis
                acum_rec_brt_pis += vl_item_c175
            if cst_cofins in CST_COFINS_TRIBUTAVEL:
                acum_cofins_bc += bc_cofins
                acum_cofins_vl += vl_cofins
                acum_rec_brt_cofins += vl_item_c175
            if cst_pis in CST_ISENTO_ZERO_SUSP:
                acum_isento_pis[cst_pis] += vl_item_c175
            if cst_cofins in CST_ISENTO_ZERO_SUSP:
                acum_isento_cofins[cst_cofins] += vl_item_c175

        # M200/M600 índices
        if reg == "M200":
            m200_idx = i
            m200_ln = i + 1
            if len(p) > 13: m200_vl_tot_cont = to_num(p[13]) or 0
        if reg == "M600":
            m600_idx = i
            m600_ln = i + 1
            if len(p) > 13: m600_vl_tot_cont = to_num(p[13]) or 0

        # M210/M610 — acumular TODOS (C1)
        if reg == "M210" and len(p) > 16:
            m210_entries.append({
                "ln": i + 1, "cod_cont": p[2].strip() if len(p) > 2 else "",
                "bc": to_num(p[7]) or 0, "aliq": to_num(p[8]) or 0,
                "vl_cont": to_num(p[11]) or 0,
            })
        if reg == "M610" and len(p) > 16:
            m610_entries.append({
                "ln": i + 1, "cod_cont": p[2].strip() if len(p) > 2 else "",
                "bc": to_num(p[7]) or 0, "aliq": to_num(p[8]) or 0,
                "vl_cont": to_num(p[11]) or 0,
            })

    # Determinar COD_CTA mais frequente para saída e entrada
    if cod_cta_freq:
        cod_cta_saida = max(cod_cta_freq, key=cod_cta_freq.get)
        cta_sorted = sorted(cod_cta_freq.keys())
        for cta in cta_sorted:
            if cta.startswith("1"): cod_cta_entrada = cta; break
        if not cod_cta_entrada:
            cod_cta_entrada = cod_cta_saida

    # Alíquotas do regime
    if cod_inc_trib in ("1", "3"):
        aliq_pis_regime = 1.65; aliq_cof_regime = 7.60
    elif cod_inc_trib == "2":
        aliq_pis_regime = 0.65; aliq_cof_regime = 3.00
    else:
        aliq_pis_regime = 1.65; aliq_cof_regime = 7.60

    # ── FASE A0: IND_REG_CUM auto-correção ─────────────────────────
    if cod_inc_trib == "2" and has_c100_global and ind_reg_cum != "9" and idx_0110 >= 0:
        f0110 = fixed[idx_0110].split("|")
        while len(f0110) <= 5: f0110.insert(len(f0110) - 1, "")
        old_val = f0110[5] if f0110[5].strip() else "(vazio)"
        f0110[5] = "9"
        fixed[idx_0110] = "|".join(f0110)
        res.fixes.append(Fix("0110", idx_0110 + 1,
            f"IND_REG_CUM corrigido de {old_val} para 9 (cumulativo com C100 detalhado)",
            old_val, "9"))

    # ── FASE A1: IND_ESCRI auto-correção ──────────────────────────
    for info in c010_info:
        idx = info["idx"]
        has_indiv = info["has_c100"] or info["has_c170"] or info["has_c175"]
        has_consol = info["has_c180"] or info["has_c190"] or info["has_c490"]
        ind_atual = info["ind_escri"]

        if has_indiv and not has_consol:
            if ind_atual != "2":
                f = fixed[idx].split("|")
                while len(f) <= 3: f.append("")
                old = f[3]
                f[3] = "2"
                fixed[idx] = "|".join(f)
                res.fixes.append(Fix("C010", idx + 1,
                    f"IND_ESCRI corrigido para 2 (individualizado — C100/C170 presentes)",
                    old or "(vazio)", "2"))
        elif has_consol and not has_indiv:
            if ind_atual != "1":
                f = fixed[idx].split("|")
                while len(f) <= 3: f.append("")
                old = f[3]
                f[3] = "1"
                fixed[idx] = "|".join(f)
                res.fixes.append(Fix("C010", idx + 1,
                    f"IND_ESCRI corrigido para 1 (consolidado — C180/C190 presentes)",
                    old or "(vazio)", "1"))
        elif has_indiv and has_consol:
            rec_flag("C010", idx + 1,
                     "Estabelecimento com registros individualizados (C100) e consolidados (C180) simultaneamente",
                     "Verifique se IND_ESCRI está correto para este estabelecimento")

    # ── FASE A2: Blocos ausentes (inserir na posição hierárquica) ──
    blocos_skip = set()
    if cod_inc_trib == "2":
        blocos_skip.add("I")

    # Remover bloco I vazio se cumulativo e já existe sem dados
    if "I" in blocos_skip and "I" in blocos_presentes:
        i_has_data = False
        for ln in fixed:
            if not ln.strip() or not ln.startswith("|"): continue
            pr = ln.split("|")
            rr = pr[1].strip() if len(pr) > 1 else ""
            if rr.startswith("I") and rr not in ("I001", "I990"):
                i_has_data = True; break
        if not i_has_data:
            for idx_rm, ln in enumerate(fixed):
                if ln.startswith("|I001|") or ln.startswith("|I990|"):
                    fixed[idx_rm] = ""
            res.fixes.append(Fix("I001", 0,
                "Bloco I removido (vazio, não aplicável ao regime cumulativo)", "I001+I990", "(removido)"))

    for bloco in BLOCOS_CONTRIB_ORDERED:
        if bloco in blocos_presentes or bloco == "9" or bloco in blocos_skip:
            continue
        # Encontrar posição correta: antes do próximo bloco existente na ordem
        bloco_idx_na_ordem = BLOCOS_CONTRIB_ORDERED.index(bloco)
        ins_pos = None
        for prox_bloco in BLOCOS_CONTRIB_ORDERED[bloco_idx_na_ordem + 1:]:
            for j, ln in enumerate(fixed):
                if not ln.strip() or not ln.startswith("|"): continue
                pr = ln.split("|")
                rr = pr[1].strip() if len(pr) > 1 else ""
                if rr and rr[0] == prox_bloco:
                    ins_pos = j; break
            if ins_pos is not None: break
        if ins_pos is None:
            ins_pos = next((j for j, ln in enumerate(fixed) if ln.startswith("|9001|") or ln.startswith("|9999|")), len(fixed))

        reg_open = f"{bloco}001"
        reg_close = f"{bloco}990"
        line_open = f"|{reg_open}|1|"
        line_close = f"|{reg_close}|2|"
        fixed.insert(ins_pos, line_close)
        fixed.insert(ins_pos, line_open)
        res.fixes.append(Fix(reg_open, ins_pos + 1,
            f"Bloco {bloco} inserido na posição correta (IND_MOV=1)", "(ausente)", line_open))

    # ── FASE E2: X001 ausente quando X990 existe ──────────────────
    for i, l in enumerate(fixed):
        if not l.strip() or not l.startswith("|"): continue
        p = l.split("|")
        if len(p) < 2: continue
        reg = p[1].strip()
        if not reg.endswith("990") or reg == "9990": continue
        bloco = reg[0]
        reg001 = f"{bloco}001"
        has_001 = any(fl.startswith(f"|{reg001}|") for fl in fixed)
        if not has_001:
            line_001 = f"|{reg001}|1|"
            fixed.insert(i, line_001)
            res.fixes.append(Fix(reg001, i + 1,
                f"{reg001} inserido (ausente, {reg} existe sem abertura)", "(ausente)", line_001))

    # ── FASE A3: IND_MOV consistência ─────────────────────────────
    for i, l in enumerate(fixed):
        if not l.strip() or not l.startswith("|"): continue
        f = l.split("|")
        if len(f) < 3: continue
        reg = f[1].strip()
        if not reg.endswith("001") or reg == "0001": continue

        bloco = reg[0]
        ind_mov = f[2].strip() if len(f) > 2 else ""

        data_regs = 0
        j = i + 1
        while j < len(fixed):
            if not fixed[j].strip() or not fixed[j].startswith("|"):
                j += 1; continue
            pj = fixed[j].split("|")
            rj = pj[1].strip() if len(pj) > 1 else ""
            if rj.endswith("990") and rj[0] == bloco: break
            if rj[0] == bloco and not rj.endswith("001"):
                data_regs += 1
            j += 1

        if ind_mov == "0" and data_regs == 0:
            rec_fix(i, 2, ind_mov, "1", reg, i + 1,
                    f"{reg}: IND_MOV=0 mas sem registros de dados → corrigido para 1")
        elif ind_mov == "1" and data_regs > 0:
            rec_fix(i, 2, ind_mov, "0", reg, i + 1,
                    f"{reg}: IND_MOV=1 mas tem {data_regs} registros → corrigido para 0")

    # ── PASSAGEM 2: validações e correções ────────────────────────
    dt_ini_date = parse_date(dt_ini0000)
    dt_fin_date = parse_date(dt_fin0000)

    for i, l in enumerate(lines):
        if not l.strip() or not l.startswith("|"): continue
        f = fixed[i].split("|")
        reg = f[1].strip() if len(f) > 1 else ""
        ln = i + 1

        # ── FASE A4: Campos insuficientes ──
        lei = LEIAUTE.get(reg)
        if lei:
            n_esp = lei["n"]
            n_real = len(f) - 2
            if n_real < n_esp:
                while len(f) - 2 < n_esp:
                    f.insert(len(f) - 1, "")
                fixed[i] = "|".join(f)
                res.fixes.append(Fix(reg, ln,
                    f"Campos completados: {n_real}→{n_esp}",
                    str(n_real), str(n_esp)))
            elif n_real > n_esp:
                if reg == "0200": fix_pipe(i, f, 3, n_esp, reg, ln, "DESCR_ITEM")
                elif n_real > n_esp + 2:
                    rec_flag(reg, ln, f"Número de campos: {n_real}, esperado {n_esp}",
                             "Verifique pipe em campo texto")

            idx_map = lei.get("idx", {})
            for nome_campo, max_len in lei.get("tam", {}).items():
                if nome_campo == "REG": continue
                fi = idx_map.get(nome_campo)
                if fi and fi < len(f):
                    val = f[fi].strip()
                    if max_len > 0 and len(val) > max_len:
                        novo = val[:max_len]
                        rec_fix(i, fi, val, novo, reg, ln,
                                f"{nome_campo} truncado ({len(val)}>{max_len})")
                        f[fi] = novo

        # ── Por registro ─────────────────────────────────────────
        if reg == "0000":
            ver = get_cod_ver(dt_ini0000)
            cod_ver_atual = f[2].strip() if len(f) > 2 else ""
            if ver and cod_ver_atual != ver["cod"]:
                rec_fix(i, 2, f[2], ver["cod"], reg, ln,
                        f"COD_VER corrigido para {ver['cod']}")
                f[2] = ver["cod"]
            for fi, nm in [(6, "DT_INI"), (7, "DT_FIN")]:
                if len(f) > fi and f[fi] and not valid_date(f[fi]):
                    fx = fix_date_fmt(f[fi])
                    if fx: rec_fix(i, fi, f[fi], fx, reg, ln, f"{nm} formato corrigido")

        elif reg == "0190":
            fix_len(i, f, 2, 6, reg, ln, "UNID")

        elif reg == "0150":
            fix_len(i, f, 3, 100, reg, ln, "NOME")

        elif reg == "C100":
            for fi, nm in [(10, "DT_DOC"), (11, "DT_E_S")]:
                if len(f) > fi and f[fi] and not valid_date(f[fi]):
                    fx = fix_date_fmt(f[fi])
                    if fx: rec_fix(i, fi, f[fi], fx, reg, ln, f"{nm} corrigida")
            cod_mod = f[5].strip() if len(f) > 5 else ""
            cod_sit = f[6].strip() if len(f) > 6 else ""
            if cod_mod and cod_mod not in MOD_DOC_SET:
                rec_flag(reg, ln, f'COD_MOD "{cod_mod}" inválido', "Consulte tabela MOD_DOC")
            if cod_sit and cod_sit not in COD_SIT_SET:
                rec_flag(reg, ln, f'COD_SIT "{cod_sit}" inválido', "Valores: 00-08")
            if cod_mod in ("55", "65") and len(f) > 9:
                chv = re.sub(r"\D", "", f[9])
                if not chv and cod_sit not in {"05"}:
                    num_doc = f[8].strip() if len(f) > 8 else "?"
                    rec_err(reg, ln,
                            f"CHV_NFE obrigatória (MOD={cod_mod} NF={num_doc})")
                elif chv and len(chv) != 44:
                    rec_flag(reg, ln, f"CHV_NFE com {len(chv)} dígitos (esperado 44)",
                             "Verifique a chave de acesso")
                elif chv and len(chv) == 44:
                    cnpj_chv = chv[6:20]
                    num_doc_chv = chv[25:34].lstrip("0")
                    num_doc_campo = (f[8].strip() if len(f) > 8 else "").lstrip("0")
                    if cnpj0000 and cnpj_chv != cnpj0000:
                        ind_emit = f[3].strip() if len(f) > 3 else ""
                        if ind_emit == "0":
                            rec_flag(reg, ln,
                                f"CNPJ na CHV_NFE ({cnpj_chv}) ≠ CNPJ do arquivo ({cnpj0000})",
                                "Verifique se a chave pertence a este emitente")
                    if num_doc_campo and num_doc_chv and num_doc_chv != num_doc_campo:
                        rec_flag(reg, ln,
                            f"NUM_DOC na CHV_NFE ({num_doc_chv}) ≠ campo NUM_DOC ({num_doc_campo})")

            if dt_ini_date and dt_fin_date and len(f) > 10:
                dt_doc_s = f[10].strip()
                if dt_doc_s:
                    dt_doc = parse_date(dt_doc_s)
                    if dt_doc and (dt_doc < dt_ini_date or dt_doc > dt_fin_date):
                        rec_flag(reg, ln,
                            f"DT_DOC ({dt_doc_s}) fora do período {dt_ini0000}–{dt_fin0000}")

            cod_part = f[4].strip() if len(f) > 4 else ""
            if cod_part and cod_part not in participantes_0150:
                rec_flag(reg, ln,
                    f'COD_PART "{cod_part}" não encontrado no registro 0150')

        elif reg == "C170" and len(f) > 25:
            fix_len(i, f, 6, 6, reg, ln, "UNID")
            cfop = f[11].strip() if len(f) > 11 else ""
            if cfop and cfop not in CFOP_SET:
                rec_flag(reg, ln, f'CFOP "{cfop}" inválido')
            cst_pis = f[25].strip() if len(f) > 25 else ""
            cst_cofins = f[31].strip() if len(f) > 31 else ""

            # G1: CST_PIS/CST_COFINS vazio — preencher com 49 para saída
            if not cst_pis and cfop and cfop[0] in "567":
                cst_pis = "49"
                rec_fix(i, 25, "(vazio)", "49", reg, ln, "CST_PIS vazio preenchido com 49 (saída)")
                f[25] = "49"
            if not cst_cofins and cfop and cfop[0] in "567":
                cst_cofins = "49"
                rec_fix(i, 31, "(vazio)", "49", reg, ln, "CST_COFINS vazio preenchido com 49 (saída)")
                f[31] = "49"

            if cst_pis and cst_pis not in CST_PIS_SET:
                rec_flag(reg, ln, f'CST PIS "{cst_pis}" inválido')
            if cst_cofins and cst_cofins not in CST_COFINS_SET:
                rec_flag(reg, ln, f'CST COFINS "{cst_cofins}" inválido')
            cst_ipi = f[20].strip() if len(f) > 20 else ""
            if cst_ipi and cst_ipi not in CST_IPI_SET:
                rec_flag(reg, ln, f'CST IPI "{cst_ipi}" inválido')

            if cfop and cst_pis:
                if cfop[0] in "123" and cst_pis not in CST_ENTRADA:
                    rec_flag(reg, ln,
                        f"CFOP entrada ({cfop}) com CST PIS de saída ({cst_pis})",
                        "Entradas exigem CST 50-66, 70-75, 98 ou 99")
                elif cfop[0] in "567" and cst_pis not in CST_SAIDA:
                    rec_flag(reg, ln,
                        f"CFOP saída ({cfop}) com CST PIS de entrada ({cst_pis})",
                        "Saídas exigem CST 01-49 ou 99")

            if cst_pis and cst_cofins and cst_pis != cst_cofins:
                if not (cst_pis in {"98","99"} or cst_cofins in {"98","99"}):
                    rec_flag(reg, ln,
                        f"CST PIS ({cst_pis}) ≠ CST COFINS ({cst_cofins})",
                        "PVA exige simetria entre CST PIS e CST COFINS")
            bc_pis_v = to_num(f[26]) if len(f) > 26 else None
            bc_cof_v = to_num(f[32]) if len(f) > 32 else None
            if bc_pis_v is not None and bc_cof_v is not None and bc_pis_v > 0 and bc_cof_v > 0:
                if abs(bc_pis_v - bc_cof_v) > 0.02:
                    rec_flag(reg, ln,
                        f"BC PIS ({fmt_n(bc_pis_v)}) ≠ BC COFINS ({fmt_n(bc_cof_v)})",
                        "PVA exige BC PIS = BC COFINS")

            # E3: Alíquota C170 vs regime
            aliq_pis = to_num(f[27]) if len(f) > 27 else None
            aliq_cof = to_num(f[33]) if len(f) > 33 else None
            if cod_inc_trib and aliq_pis and aliq_pis > 0:
                if abs(aliq_pis - aliq_pis_regime) > 0.1:
                    rec_flag(reg, ln,
                        f"ALIQ_PIS ({aliq_pis}%) ≠ regime ({aliq_pis_regime}%)",
                        f"COD_INC_TRIB={cod_inc_trib} exige {aliq_pis_regime}%")
            if cod_inc_trib and aliq_cof and aliq_cof > 0:
                if abs(aliq_cof - aliq_cof_regime) > 0.1:
                    rec_flag(reg, ln,
                        f"ALIQ_COFINS ({aliq_cof}%) ≠ regime ({aliq_cof_regime}%)",
                        f"COD_INC_TRIB={cod_inc_trib} exige {aliq_cof_regime}%")

            # Recálculo VL_PIS
            bc_pis = to_num(f[26]) if len(f) > 26 else None
            vl_pis = to_num(f[30]) if len(f) > 30 else None
            if aliq_pis and bc_pis and vl_pis is not None and aliq_pis > 0 and bc_pis > 0:
                calc = round(bc_pis * aliq_pis / 100, 2)
                if abs(calc - vl_pis) > 0.02:
                    rec_fix(i, 30, f[30], fmt_n(calc), reg, ln,
                            f"VL_PIS: {fmt_n(bc_pis)} × {aliq_pis}% = {fmt_n(calc)}")
                    f[30] = fmt_n(calc)
            # Recálculo VL_COFINS
            bc_cof = to_num(f[32]) if len(f) > 32 else None
            vl_cof = to_num(f[36]) if len(f) > 36 else None
            if aliq_cof and bc_cof and vl_cof is not None and aliq_cof > 0 and bc_cof > 0:
                calc = round(bc_cof * aliq_cof / 100, 2)
                if abs(calc - vl_cof) > 0.02:
                    rec_fix(i, 36, f[36], fmt_n(calc), reg, ln,
                            f"VL_COFINS: {fmt_n(bc_cof)} × {aliq_cof}% = {fmt_n(calc)}")
                    f[36] = fmt_n(calc)

            cod_item = f[3].strip() if len(f) > 3 else ""
            if cod_item and cod_item not in itens_0200:
                rec_flag(reg, ln,
                    f'COD_ITEM "{cod_item}" não encontrado no registro 0200')

        elif reg == "C175" and len(f) > 11:
            cst_pis = f[5].strip() if len(f) > 5 else ""
            cst_cofins = f[11].strip() if len(f) > 11 else ""
            if cst_pis and cst_pis not in CST_PIS_SET:
                rec_flag(reg, ln, f'CST PIS "{cst_pis}" inválido')
            if cst_cofins and cst_cofins not in CST_COFINS_SET:
                rec_flag(reg, ln, f'CST COFINS "{cst_cofins}" inválido')
            cfop = f[2].strip() if len(f) > 2 else ""
            if cfop and cfop not in CFOP_SET:
                rec_flag(reg, ln, f'CFOP "{cfop}" inválido')

            aliq_pis = to_num(f[7]) if len(f) > 7 else None
            bc_pis = to_num(f[6]) if len(f) > 6 else None
            vl_pis = to_num(f[10]) if len(f) > 10 else None
            if aliq_pis and bc_pis and vl_pis is not None and aliq_pis > 0 and bc_pis > 0:
                calc = round(bc_pis * aliq_pis / 100, 2)
                if abs(calc - vl_pis) > 0.02:
                    rec_fix(i, 10, f[10], fmt_n(calc), reg, ln,
                            f"VL_PIS C175: {fmt_n(bc_pis)} × {aliq_pis}% = {fmt_n(calc)}")
                    f[10] = fmt_n(calc)
            aliq_cof = to_num(f[13]) if len(f) > 13 else None
            bc_cof = to_num(f[12]) if len(f) > 12 else None
            vl_cof = to_num(f[16]) if len(f) > 16 else None
            if aliq_cof and bc_cof and vl_cof is not None and aliq_cof > 0 and bc_cof > 0:
                calc = round(bc_cof * aliq_cof / 100, 2)
                if abs(calc - vl_cof) > 0.02:
                    rec_fix(i, 16, f[16], fmt_n(calc), reg, ln,
                            f"VL_COFINS C175: {fmt_n(bc_cof)} × {aliq_cof}% = {fmt_n(calc)}")
                    f[16] = fmt_n(calc)

        elif reg == "A100":
            for fi, nm in [(10, "DT_DOC"), (11, "DT_E_S")]:
                if len(f) > fi and f[fi] and not valid_date(f[fi]):
                    fx = fix_date_fmt(f[fi])
                    if fx: rec_fix(i, fi, f[fi], fx, reg, ln, f"{nm} corrigida")
            if len(f) > 5:
                cod_mod = f[5].strip()
                if cod_mod and cod_mod not in MOD_DOC_SET:
                    rec_flag(reg, ln, f'COD_MOD "{cod_mod}" inválido')

        fixed[i] = "|".join(f)

    # ── FASE G2: Gerar C175 para NFC-e (MOD 65) sem C175 ─────────
    c175_inserts: list[tuple[int, str]] = []
    for idx_f, ln_f in enumerate(fixed):
        if not ln_f.startswith("|C100|"): continue
        pf = ln_f.split("|")
        cod_mod_f = pf[5].strip() if len(pf) > 5 else ""
        if cod_mod_f != "65": continue
        vl_doc = pf[12].strip() if len(pf) > 12 else "0,00"
        if not vl_doc: vl_doc = "0,00"
        # G2b: VL_MERC (campo 16) deve ser >= VL_OPR do C175
        vl_merc = pf[16].strip() if len(pf) > 16 else ""
        if (not vl_merc or to_num(vl_merc) == 0) and to_num(vl_doc) > 0:
            pf[16] = vl_doc
            fixed[idx_f] = "|".join(pf)
            res.fixes.append(Fix("C100", idx_f + 1,
                f"VL_MERC preenchido com VL_DOC para NFC-e ({vl_doc})",
                vl_merc or "0,00", vl_doc))
        next_idx = idx_f + 1
        while next_idx < len(fixed) and not fixed[next_idx].strip():
            next_idx += 1
        if next_idx < len(fixed) and fixed[next_idx].startswith("|C175|"):
            continue
        cta = cod_cta_saida or ""
        c175_line = (f"|C175|5102|{vl_doc}|0,00|49|{vl_doc}|0,0000|||0,00"
                     f"|49|{vl_doc}|0,0000|||0,00|{cta}||")
        c175_inserts.append((idx_f + 1, c175_line))

    if c175_inserts:
        for offset, (pos, line) in enumerate(c175_inserts):
            fixed.insert(pos + offset, line)
        res.fixes.append(Fix("C175", 0,
            f"{len(c175_inserts)} registros C175 gerados para NFC-e (MOD 65) sem detalhamento",
            "(ausente)", f"{len(c175_inserts)} C175"))

    # ── FASE E1: Auto-geração Bloco M ─────────────────────────────
    # Localizar M200 e M600 no fixed atual (posições podem ter mudado)
    m200_fix_idx = next((i for i, l in enumerate(fixed) if l.startswith("|M200|")), -1)
    m600_fix_idx = next((i for i, l in enumerate(fixed) if l.startswith("|M600|")), -1)
    m990_fix_idx = next((i for i, l in enumerate(fixed) if l.startswith("|M990|")), -1)

    m_lines_to_insert: list[tuple[str, str]] = []  # (line, desc)

    if not m210_entries and acum_pis_vl > 0:
        vl_cont_pis = round(acum_pis_vl, 2)
        # M205: NUM_CAMPO=08 (campo VL_CONT_PER), COD_REC, VL_DEBITO
        m205_line = f"|M205|08|691201|{fmt_n(vl_cont_pis)}|"
        m210_line = (f"|M210|01|{fmt_n(acum_rec_brt_pis)}|{fmt_n(acum_pis_bc)}"
                     f"|0,00|0,00|{fmt_n(acum_pis_bc)}|{fmt_n(aliq_pis_regime, 4)}"
                     f"|0,00||{fmt_n(vl_cont_pis)}|0,00|0,00|0,00|0,00|{fmt_n(vl_cont_pis)}|")
        m_lines_to_insert.append(("M205", m205_line))
        m_lines_to_insert.append(("M210", m210_line))
        res.fixes.append(Fix("M205", 0, f"M205 gerado (COD_REC=691201, VL={fmt_n(vl_cont_pis)})",
                             "(ausente)", m205_line))
        res.fixes.append(Fix("M210", 0, f"M210 gerado (BC={fmt_n(acum_pis_bc)}, ALIQ={aliq_pis_regime}%)",
                             "(ausente)", m210_line))

        # Atualizar M200 com valores corretos
        if m200_fix_idx >= 0:
            if cod_inc_trib in ("1", "3"):
                m200_new = (f"|M200|{fmt_n(vl_cont_pis)}|0,00|0,00|{fmt_n(vl_cont_pis)}"
                           f"|0,00|0,00|{fmt_n(vl_cont_pis)}|0,00|0,00|0,00|0,00|{fmt_n(vl_cont_pis)}|")
            else:
                m200_new = (f"|M200|0,00|0,00|0,00|0,00|0,00|0,00|0,00"
                           f"|{fmt_n(vl_cont_pis)}|0,00|0,00|0,00|{fmt_n(vl_cont_pis)}|")
            res.fixes.append(Fix("M200", m200_fix_idx + 1,
                f"M200 atualizado com totais PIS ({fmt_n(vl_cont_pis)})",
                fixed[m200_fix_idx], m200_new))
            fixed[m200_fix_idx] = m200_new

    if not m610_entries and acum_cofins_vl > 0:
        vl_cont_cofins = round(acum_cofins_vl, 2)
        m605_line = f"|M605|08|585601|{fmt_n(vl_cont_cofins)}|"
        m610_line = (f"|M610|01|{fmt_n(acum_rec_brt_cofins)}|{fmt_n(acum_cofins_bc)}"
                     f"|0,00|0,00|{fmt_n(acum_cofins_bc)}|{fmt_n(aliq_cof_regime, 4)}"
                     f"|0,00||{fmt_n(vl_cont_cofins)}|0,00|0,00|0,00|0,00|{fmt_n(vl_cont_cofins)}|")
        m_lines_to_insert.append(("M605", m605_line))
        m_lines_to_insert.append(("M610", m610_line))
        res.fixes.append(Fix("M605", 0, f"M605 gerado (COD_REC=585601, VL={fmt_n(vl_cont_cofins)})",
                             "(ausente)", m605_line))
        res.fixes.append(Fix("M610", 0, f"M610 gerado (BC={fmt_n(acum_cofins_bc)}, ALIQ={aliq_cof_regime}%)",
                             "(ausente)", m610_line))

        if m600_fix_idx >= 0:
            if cod_inc_trib in ("1", "3"):
                m600_new = (f"|M600|{fmt_n(vl_cont_cofins)}|0,00|0,00|{fmt_n(vl_cont_cofins)}"
                           f"|0,00|0,00|{fmt_n(vl_cont_cofins)}|0,00|0,00|0,00|0,00|{fmt_n(vl_cont_cofins)}|")
            else:
                m600_new = (f"|M600|0,00|0,00|0,00|0,00|0,00|0,00|0,00"
                           f"|{fmt_n(vl_cont_cofins)}|0,00|0,00|0,00|{fmt_n(vl_cont_cofins)}|")
            res.fixes.append(Fix("M600", m600_fix_idx + 1,
                f"M600 atualizado com totais COFINS ({fmt_n(vl_cont_cofins)})",
                fixed[m600_fix_idx], m600_new))
            fixed[m600_fix_idx] = m600_new

    # M400/M410 para CST isento/zero/suspensão PIS
    if not tem_m400 and acum_isento_pis:
        for cst, vl_rec in sorted(acum_isento_pis.items()):
            if vl_rec > 0:
                cta = cod_cta_entrada or cod_cta_saida or ""
                m400_line = f"|M400|{cst}|{fmt_n(vl_rec)}|{cta}||"
                m410_line = f"|M410|999|{fmt_n(vl_rec)}|{cta}||"
                m_lines_to_insert.append(("M400", m400_line))
                m_lines_to_insert.append(("M410", m410_line))
                res.fixes.append(Fix("M400", 0,
                    f"M400 gerado (CST={cst}, VL_REC={fmt_n(vl_rec)})", "(ausente)", m400_line))
                res.fixes.append(Fix("M410", 0,
                    f"M410 gerado (NAT_REC=999, VL_REC={fmt_n(vl_rec)})", "(ausente)", m410_line))

    # M800/M810 para CST isento/zero/suspensão COFINS
    if not tem_m800 and acum_isento_cofins:
        for cst, vl_rec in sorted(acum_isento_cofins.items()):
            if vl_rec > 0:
                cta = cod_cta_entrada or cod_cta_saida or ""
                m800_line = f"|M800|{cst}|{fmt_n(vl_rec)}|{cta}||"
                m810_line = f"|M810|999|{fmt_n(vl_rec)}|{cta}||"
                m_lines_to_insert.append(("M800", m800_line))
                m_lines_to_insert.append(("M810", m810_line))
                res.fixes.append(Fix("M800", 0,
                    f"M800 gerado (CST={cst}, VL_REC={fmt_n(vl_rec)})", "(ausente)", m800_line))
                res.fixes.append(Fix("M810", 0,
                    f"M810 gerado (NAT_REC=999, VL_REC={fmt_n(vl_rec)})", "(ausente)", m810_line))

    # Inserir todos os registros M gerados na posição correta
    if m_lines_to_insert:
        # Registros devem ir entre M600 e M990 (para os de COFINS) ou entre M200 e M600 (para os de PIS)
        # Ordenar: M205, M210, M400, M410 vão ANTES do M600; M605, M610, M800, M810 vão DEPOIS do M600
        m600_fix_idx = next((i for i, l in enumerate(fixed) if l.startswith("|M600|")), -1)
        m990_fix_idx = next((i for i, l in enumerate(fixed) if l.startswith("|M990|")), -1)

        pis_regs = [ln for reg, ln in m_lines_to_insert if reg in ("M205", "M210", "M400", "M410")]
        cofins_regs = [ln for reg, ln in m_lines_to_insert if reg in ("M605", "M610", "M800", "M810")]

        # Inserir PIS antes do M600
        if pis_regs and m600_fix_idx >= 0:
            for line in reversed(pis_regs):
                fixed.insert(m600_fix_idx, line)
            m600_fix_idx += len(pis_regs)
            m990_fix_idx = next((i for i, l in enumerate(fixed) if l.startswith("|M990|")), -1)

        # Inserir COFINS antes do M990
        if cofins_regs and m990_fix_idx >= 0:
            for line in reversed(cofins_regs):
                fixed.insert(m990_fix_idx, line)

    # ── Inserir 9900 para registros sem referência (E4) ───────────
    all_regs: set[str] = set()
    existing_9900_refs: set[str] = set()
    for l in fixed:
        if not l.strip() or not l.startswith("|"): continue
        p = l.split("|")
        if len(p) < 2: continue
        r = p[1].strip()
        all_regs.add(r)
        if r == "9900" and len(p) > 2:
            existing_9900_refs.add(p[2].strip())

    missing_refs = all_regs - existing_9900_refs
    if missing_refs:
        ins_9900 = next((i for i, l in enumerate(fixed)
                         if l.startswith("|9990|") or l.startswith("|9999|")), len(fixed))
        for ref in sorted(missing_refs):
            qtd = sum(1 for l in fixed if l.strip() and l.startswith("|") and
                      len(l.split("|")) > 1 and l.split("|")[1].strip() == ref)
            if qtd > 0:
                new_line = f"|9900|{ref}|{qtd}|"
                fixed.insert(ins_9900, new_line)
                res.fixes.append(Fix("9900", ins_9900 + 1,
                                     f"9900 criado para {ref}: {qtd}", "(ausente)", new_line))
                ins_9900 += 1

    # ── Atualizar xXX990 e contadores de bloco ────────────────────
    for bloco in BLOCOS_CONTRIB_ORDERED:
        reg990 = bloco + "990"
        idx990 = next((i for i, l in enumerate(fixed)
                       if l.startswith(f"|{reg990}|")), -1)
        if idx990 < 0: continue
        qtd_real = sum(1 for l in fixed if l.strip() and l.startswith("|") and
                       len(l.split("|")) > 1 and l.split("|")[1].strip().startswith(bloco))
        p990 = fixed[idx990].split("|")
        qtd_atual = int(p990[2]) if len(p990) > 2 and p990[2].strip().isdigit() else 0
        if qtd_atual != qtd_real:
            res.fixes.append(Fix(reg990, idx990 + 1, f"{reg990}: {qtd_atual}→{qtd_real}",
                                 str(qtd_atual), str(qtd_real)))
            p990[2] = str(qtd_real)
            fixed[idx990] = "|".join(p990)

    # ── Atualizar contadores 9900 ─────────────────────────────────
    new_count: dict[str, int] = {}
    for l in fixed:
        if not l.strip() or not l.startswith("|"): continue
        p = l.split("|")
        if len(p) > 1: new_count[p[1].strip()] = new_count.get(p[1].strip(), 0) + 1

    for i, l in enumerate(fixed):
        if not l.startswith("|9900|"): continue
        p = l.split("|")
        ref = p[2].strip() if len(p) > 2 else ""
        qtd_inf = int(p[3]) if len(p) > 3 and p[3].strip().isdigit() else 0
        qtd_real = new_count.get(ref, 0)
        if qtd_real > 0 and qtd_inf != qtd_real:
            res.fixes.append(Fix("9900", i + 1, f"Contador {ref}: {qtd_inf}→{qtd_real}",
                                 str(qtd_inf), str(qtd_real)))
            p[3] = str(qtd_real)
            fixed[i] = "|".join(p)

    # ── 9999 QTD_LIN ──────────────────────────────────────────────
    real_9999_idx = next((i for i, l in enumerate(fixed) if l.startswith("|9999|")), r9999_idx)
    if real_9999_idx >= 0:
        total = sum(1 for l in fixed if l.strip())
        p = fixed[real_9999_idx].split("|")
        qtd_inf = int(p[2]) if len(p) > 2 and p[2].strip().isdigit() else 0
        if qtd_inf != total:
            res.fixes.append(Fix("9999", real_9999_idx + 1, f"QTD_LIN: {qtd_inf}→{total}",
                                 str(qtd_inf), str(total)))
            p[2] = str(total)
            fixed[real_9999_idx] = "|".join(p)

    # ── Validações cruzadas Bloco M ───────────────────────────────
    for entry in m210_entries:
        if entry["bc"] > 0 and entry["aliq"] > 0:
            calc = round(entry["bc"] * entry["aliq"] / 100, 2)
            if abs(calc - entry["vl_cont"]) > 1.0:
                rec_flag("M210", entry["ln"],
                    f"VL_CONT_APUR ({fmt_n(entry['vl_cont'])}) ≠ "
                    f"VL_BC × ALIQ ({fmt_n(entry['bc'])} × {entry['aliq']}% = {fmt_n(calc)})")

    for entry in m610_entries:
        if entry["bc"] > 0 and entry["aliq"] > 0:
            calc = round(entry["bc"] * entry["aliq"] / 100, 2)
            if abs(calc - entry["vl_cont"]) > 1.0:
                rec_flag("M610", entry["ln"],
                    f"VL_CONT_APUR ({fmt_n(entry['vl_cont'])}) ≠ "
                    f"VL_BC × ALIQ ({fmt_n(entry['bc'])} × {entry['aliq']}% = {fmt_n(calc)})")

    if m200_ln > 0 and acum_pis_vl > 0:
        if abs(acum_pis_vl - m200_vl_tot_cont) > 1.0 and m210_entries:
            rec_flag("M200", m200_ln,
                     f"VL_TOT_CONT_REC ({fmt_n(m200_vl_tot_cont)}) ≠ soma PIS dos "
                     f"C170/C175 ({fmt_n(acum_pis_vl)})")

    if m600_ln > 0 and acum_cofins_vl > 0:
        if abs(acum_cofins_vl - m600_vl_tot_cont) > 1.0 and m610_entries:
            rec_flag("M600", m600_ln,
                     f"VL_TOT_CONT_REC ({fmt_n(m600_vl_tot_cont)}) ≠ soma COFINS dos "
                     f"C170/C175 ({fmt_n(acum_cofins_vl)})")

    # C2/C3: obrigatoriedade M400/M800/M100/M500 (só flag se não gerado)
    cst_isento_pis = cst_pis_usados & CST_ISENTO_ZERO_SUSP
    cst_isento_cofins = cst_cofins_usados & CST_ISENTO_ZERO_SUSP
    has_m400_now = any(l.startswith("|M400|") for l in fixed)
    has_m800_now = any(l.startswith("|M800|") for l in fixed)
    if cst_isento_pis and not has_m400_now:
        rec_flag("M400", 0,
            f"CST PIS {sorted(cst_isento_pis)} exigem registro M400",
            "Inclua M400 com detalhamento por CST")
    if cst_isento_cofins and not has_m800_now:
        rec_flag("M800", 0,
            f"CST COFINS {sorted(cst_isento_cofins)} exigem registro M800",
            "Inclua M800 com detalhamento por CST")

    cst_credito_pis = cst_pis_usados & {f"{i:02d}" for i in range(50, 67)}
    cst_credito_cofins = cst_cofins_usados & {f"{i:02d}" for i in range(50, 67)}
    if cst_credito_pis and not tem_m100:
        rec_flag("M100", 0,
            f"CST PIS {sorted(cst_credito_pis)} exigem registro M100 (crédito PIS)",
            "Inclua M100 para cada tipo de crédito")
    if cst_credito_cofins and not tem_m500:
        rec_flag("M500", 0,
            f"CST COFINS {sorted(cst_credito_cofins)} exigem registro M500 (crédito COFINS)",
            "Inclua M500 para cada tipo de crédito")

    # C4: Alíquota básica vs regime (M210/M610 existentes)
    if cod_inc_trib:
        for entry in m210_entries:
            if entry["cod_cont"] in ("01", "51") and entry["aliq"] > 0:
                if abs(entry["aliq"] - aliq_pis_regime) > 0.1:
                    rec_flag("M210", entry["ln"],
                        f"Alíquota PIS ({entry['aliq']}%) ≠ básica do regime ({aliq_pis_regime}%)",
                        f"COD_INC_TRIB={cod_inc_trib}")
        for entry in m610_entries:
            if entry["cod_cont"] in ("01", "51") and entry["aliq"] > 0:
                if abs(entry["aliq"] - aliq_cof_regime) > 0.1:
                    rec_flag("M610", entry["ln"],
                        f"Alíquota COFINS ({entry['aliq']}%) ≠ básica do regime ({aliq_cof_regime}%)",
                        f"COD_INC_TRIB={cod_inc_trib}")

    # D3: Registro 1900 obrigatório
    if dt_ini_date and dt_ini_date >= date(2013, 4, 1) and not tem_1900:
        rec_flag("1900", 0,
            "Registro 1900 obrigatório a partir de 04/2013 (consolidação docs emitidos)",
            "Inclua pelo menos um registro 1900")

    # ── Sumário ───────────────────────────────────────────────────
    ver = get_cod_ver(dt_ini0000)
    dt_ini = parse_date(dt_ini0000)
    dt_fin_d = parse_date(dt_fin0000)

    res.sumario.total_linhas = sum(1 for l in fixed if l.strip())
    res.sumario.dt_ini = dt_ini.strftime("%d/%m/%Y") if dt_ini else "—"
    res.sumario.dt_fin = dt_fin_d.strftime("%d/%m/%Y") if dt_fin_d else "—"
    res.sumario.versao = ver["cod"] if ver else "—"
    res.sumario.uf = uf or "—"
    res.sumario.reg_count = new_count

    for l in fixed:
        if not l.startswith("|C170|"): continue
        p = l.split("|")
        if len(p) < 37: continue
        cfop = p[11].strip()
        bc_pis = to_num(p[26]) or 0
        vl_pis = to_num(p[30]) or 0
        bc_cofins = to_num(p[32]) or 0
        vl_cofins = to_num(p[36]) or 0
        vl_item = to_num(p[7]) or 0
        if not cfop: continue
        if cfop not in res.sumario.aliq_map:
            res.sumario.aliq_map[cfop] = {
                "bc_pis": 0, "vl_pis": 0,
                "bc_cofins": 0, "vl_cofins": 0,
                "vl_item": 0, "n": 0,
            }
        m = res.sumario.aliq_map[cfop]
        m["bc_pis"] += bc_pis
        m["vl_pis"] += vl_pis
        m["bc_cofins"] += bc_cofins
        m["vl_cofins"] += vl_cofins
        m["vl_item"] += vl_item
        m["n"] += 1

    res.fixed_lines = fixed
    return res
