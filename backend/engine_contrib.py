"""
Engine de validação e correção SPED EFD-Contribuições (PIS/COFINS)
Baseada no descritor.xml oficial do PVA SERPRO (182 registros)
"""
from __future__ import annotations
import json, re
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

CST_PIS_TRIBUTAVEL = {"01","02","03","04","05"}
CST_COFINS_TRIBUTAVEL = {"01","02","03","04","05"}

BLOCOS_CONTRIB = list("0ACDFIMPK19")


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
    """Retorna COD_VER correto para o período, usando tabela de versões."""
    dt = parse_date(dt_ini)
    if not dt: return None
    for cod, v in VERSOES.items():
        ini = parse_date(v["dt_ini"])
        fim = parse_date(v["dt_fim"]) if v.get("dt_fim") else date(9999, 1, 1)
        if ini and ini <= dt <= fim:
            return {"cod": cod}
    return None


# ── Dataclasses de resultado (mesmas do engine.py) ────────────────
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
    uf = None
    r9999_idx = -1
    reg_count: dict[str, int] = {}

    # ── Acumuladores para cross-check Bloco M ──
    # PIS: somar BC e VL dos C170/C175 com CST tributável
    acum_pis_bc = 0.0
    acum_pis_vl = 0.0
    acum_cofins_bc = 0.0
    acum_cofins_vl = 0.0
    # M210/M610 para validação
    m210_bc = 0.0; m210_aliq = 0.0; m210_vl_cont = 0.0; m210_ln = -1
    m610_bc = 0.0; m610_aliq = 0.0; m610_vl_cont = 0.0; m610_ln = -1
    m200_vl_tot_cont = 0.0; m200_ln = -1
    m600_vl_tot_cont = 0.0; m600_ln = -1

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

        if reg == "0000":
            # Contribuições: campo 6=DT_INI, 7=DT_FIN, 8=NOME, 9=CNPJ, 10=UF, 11=COD_MUN
            dt_ini0000 = p[6].strip() if len(p) > 6 else ""
            dt_fin0000 = p[7].strip() if len(p) > 7 else ""
            res.sumario.nome = p[8].strip() if len(p) > 8 else ""
            res.sumario.cnpj = p[9].strip() if len(p) > 9 else ""
            uf_dir = p[10].strip() if len(p) > 10 else ""
            if len(uf_dir) == 2 and uf_dir.isalpha():
                uf = uf_dir.upper()
            else:
                uf = get_uf_from_mun(p[11].strip() if len(p) > 11 else "")

        if reg == "9999": r9999_idx = i

        # Acumuladores C170 PIS/COFINS
        if reg == "C170" and len(p) > 36:
            cst_pis = p[25].strip() if len(p) > 25 else ""
            cst_cofins = p[31].strip() if len(p) > 31 else ""
            bc_pis = to_num(p[26]) or 0
            vl_pis = to_num(p[30]) or 0
            bc_cofins = to_num(p[32]) or 0
            vl_cofins = to_num(p[36]) or 0
            if cst_pis in CST_PIS_TRIBUTAVEL:
                acum_pis_bc += bc_pis
                acum_pis_vl += vl_pis
            if cst_cofins in CST_COFINS_TRIBUTAVEL:
                acum_cofins_bc += bc_cofins
                acum_cofins_vl += vl_cofins

        # Acumuladores C175 PIS/COFINS
        if reg == "C175" and len(p) > 16:
            cst_pis = p[5].strip() if len(p) > 5 else ""
            cst_cofins = p[11].strip() if len(p) > 11 else ""
            bc_pis = to_num(p[6]) or 0
            vl_pis = to_num(p[10]) or 0
            bc_cofins = to_num(p[12]) or 0
            vl_cofins = to_num(p[16]) or 0
            if cst_pis in CST_PIS_TRIBUTAVEL:
                acum_pis_bc += bc_pis
                acum_pis_vl += vl_pis
            if cst_cofins in CST_COFINS_TRIBUTAVEL:
                acum_cofins_bc += bc_cofins
                acum_cofins_vl += vl_cofins

        # M200/M600
        if reg == "M200" and len(p) > 13:
            m200_vl_tot_cont = to_num(p[13]) or 0
            m200_ln = i + 1
        if reg == "M600" and len(p) > 13:
            m600_vl_tot_cont = to_num(p[13]) or 0
            m600_ln = i + 1

        # M210/M610
        if reg == "M210" and len(p) > 16:
            m210_bc = to_num(p[7]) or 0
            m210_aliq = to_num(p[8]) or 0
            m210_vl_cont = to_num(p[11]) or 0
            m210_ln = i + 1
        if reg == "M610" and len(p) > 16:
            m610_bc = to_num(p[7]) or 0
            m610_aliq = to_num(p[8]) or 0
            m610_vl_cont = to_num(p[11]) or 0
            m610_ln = i + 1

    # ── PASSAGEM 2: validações e correções ────────────────────────
    for i, l in enumerate(lines):
        if not l.strip() or not l.startswith("|"): continue
        f = fixed[i].split("|")
        reg = f[1].strip() if len(f) > 1 else ""
        ln = i + 1

        # Validação genérica via leiaute
        lei = LEIAUTE.get(reg)
        if lei:
            n_esp = lei["n"]
            n_real = len(f) - 2
            if n_real > n_esp:
                if reg == "0200": fix_pipe(i, f, 3, n_esp, reg, ln, "DESCR_ITEM")
                elif n_real > n_esp + 2:
                    rec_flag(reg, ln, f"Número de campos: {n_real}, esperado {n_esp}",
                             "Verifique pipe em campo texto")
            # fixLen genérico
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
            # COD_VER (campo 2)
            ver = get_cod_ver(dt_ini0000)
            cod_ver_atual = f[2].strip() if len(f) > 2 else ""
            if ver and cod_ver_atual != ver["cod"]:
                rec_fix(i, 2, f[2], ver["cod"], reg, ln,
                        f"COD_VER corrigido para {ver['cod']}")
                f[2] = ver["cod"]
            # Datas: DT_INI(6), DT_FIN(7)
            for fi, nm in [(6, "DT_INI"), (7, "DT_FIN")]:
                if len(f) > fi and f[fi] and not valid_date(f[fi]):
                    fx = fix_date_fmt(f[fi])
                    if fx: rec_fix(i, fi, f[fi], fx, reg, ln, f"{nm} formato corrigido")

        elif reg == "0190":
            fix_len(i, f, 2, 6, reg, ln, "UNID")

        elif reg == "0150":
            fix_len(i, f, 3, 100, reg, ln, "NOME")

        elif reg == "C100":
            # Datas: DT_DOC(10), DT_E_S(11)
            for fi, nm in [(10, "DT_DOC"), (11, "DT_E_S")]:
                if len(f) > fi and f[fi] and not valid_date(f[fi]):
                    fx = fix_date_fmt(f[fi])
                    if fx: rec_fix(i, fi, f[fi], fx, reg, ln, f"{nm} corrigida")
            # COD_MOD (5), COD_SIT (6)
            cod_mod = f[5].strip() if len(f) > 5 else ""
            cod_sit = f[6].strip() if len(f) > 6 else ""
            if cod_mod and cod_mod not in MOD_DOC_SET:
                rec_flag(reg, ln, f'COD_MOD "{cod_mod}" inválido', "Consulte tabela MOD_DOC")
            if cod_sit and cod_sit not in COD_SIT_SET:
                rec_flag(reg, ln, f'COD_SIT "{cod_sit}" inválido', "Valores: 00-08")
            # CHV_NFE (campo 9)
            if cod_mod in ("55", "65") and len(f) > 9:
                chv = re.sub(r"\D", "", f[9])
                if not chv and cod_sit not in {"05"}:
                    num_doc = f[8].strip() if len(f) > 8 else "?"
                    rec_err(reg, ln,
                            f"CHV_NFE obrigatória (MOD={cod_mod} NF={num_doc})")
                elif chv and len(chv) != 44:
                    rec_flag(reg, ln, f"CHV_NFE com {len(chv)} dígitos (esperado 44)",
                             "Verifique a chave de acesso")

        elif reg == "C170" and len(f) > 25:
            # UNID (campo 6)
            fix_len(i, f, 6, 6, reg, ln, "UNID")
            # CFOP (campo 11)
            cfop = f[11].strip() if len(f) > 11 else ""
            if cfop and cfop not in CFOP_SET:
                rec_flag(reg, ln, f'CFOP "{cfop}" inválido')
            # CST PIS (campo 25)
            cst_pis = f[25].strip() if len(f) > 25 else ""
            if cst_pis and cst_pis not in CST_PIS_SET:
                rec_flag(reg, ln, f'CST PIS "{cst_pis}" inválido')
            # CST COFINS (campo 31)
            cst_cofins = f[31].strip() if len(f) > 31 else ""
            if cst_cofins and cst_cofins not in CST_COFINS_SET:
                rec_flag(reg, ln, f'CST COFINS "{cst_cofins}" inválido')
            # CST IPI (campo 20)
            cst_ipi = f[20].strip() if len(f) > 20 else ""
            if cst_ipi and cst_ipi not in CST_IPI_SET:
                rec_flag(reg, ln, f'CST IPI "{cst_ipi}" inválido')
            # Recálculo VL_PIS = VL_BC_PIS * ALIQ_PIS / 100
            aliq_pis = to_num(f[27]) if len(f) > 27 else None
            bc_pis = to_num(f[26]) if len(f) > 26 else None
            vl_pis = to_num(f[30]) if len(f) > 30 else None
            if aliq_pis and bc_pis and vl_pis is not None and aliq_pis > 0 and bc_pis > 0:
                calc = round(bc_pis * aliq_pis / 100, 2)
                if abs(calc - vl_pis) > 0.02:
                    rec_fix(i, 30, f[30], fmt_n(calc), reg, ln,
                            f"VL_PIS: {fmt_n(bc_pis)} × {aliq_pis}% = {fmt_n(calc)}")
                    f[30] = fmt_n(calc)
            # Recálculo VL_COFINS = VL_BC_COFINS * ALIQ_COFINS / 100
            aliq_cof = to_num(f[33]) if len(f) > 33 else None
            bc_cof = to_num(f[32]) if len(f) > 32 else None
            vl_cof = to_num(f[36]) if len(f) > 36 else None
            if aliq_cof and bc_cof and vl_cof is not None and aliq_cof > 0 and bc_cof > 0:
                calc = round(bc_cof * aliq_cof / 100, 2)
                if abs(calc - vl_cof) > 0.02:
                    rec_fix(i, 36, f[36], fmt_n(calc), reg, ln,
                            f"VL_COFINS: {fmt_n(bc_cof)} × {aliq_cof}% = {fmt_n(calc)}")
                    f[36] = fmt_n(calc)

        elif reg == "C175" and len(f) > 11:
            # CST PIS (campo 5), CST COFINS (campo 11)
            cst_pis = f[5].strip() if len(f) > 5 else ""
            cst_cofins = f[11].strip() if len(f) > 11 else ""
            if cst_pis and cst_pis not in CST_PIS_SET:
                rec_flag(reg, ln, f'CST PIS "{cst_pis}" inválido')
            if cst_cofins and cst_cofins not in CST_COFINS_SET:
                rec_flag(reg, ln, f'CST COFINS "{cst_cofins}" inválido')
            # CFOP (campo 2)
            cfop = f[2].strip() if len(f) > 2 else ""
            if cfop and cfop not in CFOP_SET:
                rec_flag(reg, ln, f'CFOP "{cfop}" inválido')

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

    # ── Inserir 9900 para registros sem referência ────────────────
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
    for bloco in BLOCOS_CONTRIB:
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
    # M210: VL_BC_CONT_AJUS (campo 7) × ALIQ_PIS (campo 8) = VL_CONT_APUR (campo 11)
    if m210_ln > 0 and m210_bc > 0 and m210_aliq > 0:
        calc_pis = round(m210_bc * m210_aliq / 100, 2)
        if abs(calc_pis - m210_vl_cont) > 1.0:
            rec_flag("M210", m210_ln,
                     f"VL_CONT_APUR ({fmt_n(m210_vl_cont)}) ≠ VL_BC × ALIQ "
                     f"({fmt_n(m210_bc)} × {m210_aliq}% = {fmt_n(calc_pis)})")

    # M610: VL_BC_CONT_AJUS (campo 7) × ALIQ_COFINS (campo 8) = VL_CONT_APUR (campo 11)
    if m610_ln > 0 and m610_bc > 0 and m610_aliq > 0:
        calc_cof = round(m610_bc * m610_aliq / 100, 2)
        if abs(calc_cof - m610_vl_cont) > 1.0:
            rec_flag("M610", m610_ln,
                     f"VL_CONT_APUR ({fmt_n(m610_vl_cont)}) ≠ VL_BC × ALIQ "
                     f"({fmt_n(m610_bc)} × {m610_aliq}% = {fmt_n(calc_cof)})")

    # M200: soma C170/C175 PIS vs M200 VL_TOT_CONT_REC
    if m200_ln > 0 and acum_pis_vl > 0:
        if abs(acum_pis_vl - m200_vl_tot_cont) > 1.0:
            rec_flag("M200", m200_ln,
                     f"VL_TOT_CONT_REC ({fmt_n(m200_vl_tot_cont)}) ≠ soma PIS dos "
                     f"C170/C175 ({fmt_n(acum_pis_vl)})")

    # M600: soma C170/C175 COFINS vs M600 VL_TOT_CONT_REC
    if m600_ln > 0 and acum_cofins_vl > 0:
        if abs(acum_cofins_vl - m600_vl_tot_cont) > 1.0:
            rec_flag("M600", m600_ln,
                     f"VL_TOT_CONT_REC ({fmt_n(m600_vl_tot_cont)}) ≠ soma COFINS dos "
                     f"C170/C175 ({fmt_n(acum_cofins_vl)})")

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

    # Dashboard de alíquotas PIS/COFINS por CFOP
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
