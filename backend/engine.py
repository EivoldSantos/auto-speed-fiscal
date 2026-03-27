"""
Engine de validação e correção SPED EFD ICMS/IPI
Baseada no descritor.xml oficial do PVA SERPRO
"""
from __future__ import annotations
import json, re, os
from dataclasses import dataclass, field
from pathlib import Path
from datetime import date, datetime
from typing import Optional

# ── Carregar dados PVA ────────────────────────────────────────────
_BASE = Path(__file__).parent
with open(_BASE / "dados_pva.json", encoding="utf-8") as _f:
    _D = json.load(_f)

LEIAUTE      = _D["leiaute"]
CFOP_SET     = set(_D["cfop"].keys())
CST_ICMS_SET = set(_D["cst_icms"].keys())
CST_IPI_SET  = set(_D["cst_ipi"].keys())
CST_PIS_SET  = set(_D["cst_pis"].keys())
MOD_DOC_SET  = set(_D["mod_doc"].keys())
COD_SIT_SET  = set(_D["cod_sit"].keys())
CFOP_SAI_ENT = _D["cfop_sai_to_ent"]
CFOP_ENT_SAI = _D["cfop_ent_to_sai"]
VERSOES      = _D["versoes"]
UF_COD       = _D["uf_cod"]
F2           = _D["f2"]

PAI_FILHO = {
    "C100": ["C190"], "C400": ["C405"], "C500": ["C590"],
    "C600": ["C690"], "C800": ["C860"], "D100": ["D190"],
    "D500": ["D590"], "E100": ["E110"], "E500": ["E520"],
    "H001": ["H005"],
}


DISPENSAR_COD_SIT = {"02","03","04","05","06","07","08"}

# ── Códigos de receita padrão para ICMS próprio (COD_OR=000) por UF ──────────
# Para UFs com único código padrão: auto-corriger
# Para MG/RN: depende de comércio(00) vs indústria(01-06)
COD_REC_UNICO_POR_UF = {
    "SP": "046-2",
    "ES": "101-5",
    "RS": "0057",
    "GO": "108",
    "MA": "101",
    "TO": "101",
    "MS": "310",
    "SE": "0139",
    "BA": "0741",
    "PA": "0900",
    "PE": "0051",
    "RJ": "0213",
    "AM": "1303",
    "PR": "1015",
    "CE": "1015",
    "AC": "1013",
    "AP": "1111",
    "MT": "1112",
    "RO": "1112",
    "DF": "1314",
    "PB": "1047",
}
# MG e RN precisam distinguir comércio vs indústria
COD_REC_MG_COMERCIO  = "1206"
COD_REC_MG_INDUSTRIA = "1214"

# ── Códigos de receita para ICMS-ST (E250) por UF ─────────────────
COD_REC_ST_POR_UF = {
    "SP": "063-2",
    "AM": "1304",
    "MG": "2097",
    "MT": "2810",
    "MS": "312",
    "PA": "0901",
}

def detectar_cod_rec_st(uf: str) -> Optional[str]:
    """Retorna o COD_REC padrão para ICMS-ST (E250) da UF, ou None se não mapeado."""
    if not uf: return None
    return COD_REC_ST_POR_UF.get(uf)

def calc_dt_vcto_st(dt_ini: str) -> str:
    """DT_VCTO para E250: dia 10 do mês seguinte ao período."""
    dt = parse_date(dt_ini)
    if not dt: return ""
    if dt.month == 12:
        m, y = 1, dt.year + 1
    else:
        m, y = dt.month + 1, dt.year
    return f"10{m:02d}{y}"

def detectar_cod_rec(uf: str, tipo_item_counts: dict) -> Optional[str]:
    """
    Retorna o COD_REC padrão para ICMS próprio (COD_OR=000) da UF.
    Para MG/RN: usa TIPO_ITEM predominante para distinguir comércio/indústria.
    Retorna None se não conseguir determinar (precisa de dropdown).
    """
    if not uf: return None
    # UF com código único conhecido
    if uf in COD_REC_UNICO_POR_UF:
        return COD_REC_UNICO_POR_UF[uf]
    # MG: comércio (TIPO_ITEM=00 maioria) ou indústria (01-06)
    if uf in ("MG", "RN"):
        rev = tipo_item_counts.get("00", 0)
        ind = sum(v for k, v in tipo_item_counts.items() if k in ("01","02","03","04","05","06"))
        if rev > ind:
            return COD_REC_MG_COMERCIO   # 1206
        elif ind > 0:
            return COD_REC_MG_INDUSTRIA  # 1214
        else:
            return COD_REC_MG_COMERCIO   # default comércio se sem itens
    return None  # UF não mapeada → dropdown manual


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
        ini = parse_date(v["ini"])
        fim = parse_date(v["fim"]) if v.get("fim") else date(9999, 1, 1)
        if ini and ini <= dt <= fim:
            return {"cod": cod, "versao": v["v"]}
    return None

def cod_valido(tab_uf: dict, cod: str, dt_ref: str) -> tuple[bool, str]:
    if not tab_uf: return False, "UF não encontrada"
    if tab_uf.get("v") and cod in tab_uf["v"]: return True, ""
    if tab_uf.get("h") and cod in tab_uf["h"]:
        dt = parse_date(dt_ref)
        if not dt: return True, ""
        for ini_s, fim_s in tab_uf["h"][cod]:
            ini = parse_date(ini_s)
            fim = parse_date(fim_s) if fim_s else date(9999, 1, 1)
            if ini and ini <= dt <= fim: return True, ""
        return False, "código com vigência encerrada"
    return False, "código não encontrado"


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

    # Estado global
    dt_ini0000 = ""
    uf = None
    ind_perfil = ""
    uf_set = False
    r9999_idx = -1
    tipo_item_counts: dict[str, int] = {}  # TIPO_ITEM do 0200 → para detectar comércio/indústria

    # Acumuladores
    acum_deb_c190 = 0.0
    acum_cred_c190 = 0.0
    acum_g110 = 0.0
    e111_map: dict[str, float] = {}
    cfops_difal: set[str] = set()
    tem_e300 = False
    e110_ln = -1
    item_qtd: dict[str, dict] = {}
    item_h010: dict[str, dict] = {}
    reg_count: dict[str, int] = {}

    # Pai-filho
    pai_map: dict[int, dict] = {}
    ultimo_pai: dict[str, int] = {}

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

    def recalc_icms(idx, f, i_aliq, i_bc, i_vl, label, reg):
        aliq = to_num(f[i_aliq] if i_aliq < len(f) else "")
        bc   = to_num(f[i_bc]   if i_bc   < len(f) else "")
        vl   = to_num(f[i_vl]   if i_vl   < len(f) else "")
        if aliq and bc and vl is not None and aliq > 0 and bc > 0:
            calc = round(bc * aliq / 100, 2)
            if abs(calc - vl) > 0.02:
                rec_fix(idx, i_vl, f[i_vl], fmt_n(calc), reg, idx+1,
                        f"{label}: {fmt_n(bc)} × {aliq}% = {fmt_n(calc)}")
                f[i_vl] = fmt_n(calc)

    # ── PASSAGEM 1 ───────────────────────────────────────────────
    for i, l in enumerate(lines):
        if not l.strip() or not l.startswith("|"): continue
        p = l.split("|")
        if len(p) < 2: continue
        reg = p[1].strip()
        reg_count[reg] = reg_count.get(reg, 0) + 1
        res.sumario.total_regs += 1

        if reg == "0200" and len(p) > 7:
            tipo = p[7].strip()
            if tipo: tipo_item_counts[tipo] = tipo_item_counts.get(tipo, 0) + 1

        if reg == "0000":
            dt_ini0000 = p[4].strip() if len(p)>4 else ""
            uf_dir = p[9].strip() if len(p)>9 else ""
            if len(uf_dir) == 2 and uf_dir.isalpha():
                uf = uf_dir.upper()
            else:
                uf = get_uf_from_mun(p[11].strip() if len(p)>11 else "")
            ind_perfil = p[14].strip() if len(p)>14 else ""
            res.sumario.cnpj = p[7].strip() if len(p)>7 else ""
            res.sumario.nome = p[6].strip() if len(p)>6 else ""

        if reg == "9999": r9999_idx = i
        if reg == "E300": tem_e300 = True

        # Pai-filho
        if reg in PAI_FILHO:
            ultimo_pai[reg] = i
            pai_map[i] = {"reg": reg, "filhos": set(), "raw": l}
        for pai_reg, filhos in PAI_FILHO.items():
            for filho in filhos:
                if reg == filho and pai_reg in ultimo_pai:
                    pi = ultimo_pai[pai_reg]
                    if pi in pai_map:
                        pai_map[pi]["filhos"].add(filho)

        # Acumuladores
        if reg == "C190" and len(p) >= 8:
            cfop = p[3].strip(); vl_icms = to_num(p[7]) or 0
            if cfop and cfop[0] in "123": acum_cred_c190 += vl_icms
            if cfop and cfop[0] in "567": acum_deb_c190  += vl_icms
            if cfop and cfop[0] == "3":   cfops_difal.add(cfop)
        if reg == "G110" and len(p) >= 10:
            acum_g110 += to_num(p[9]) or 0
        if reg == "E111" and len(p) >= 5:
            cod = p[2].strip()
            if cod: e111_map[cod] = e111_map.get(cod, 0) + (to_num(p[4]) or 0)
        if reg == "E110" and len(p) >= 15:
            e110_ln = i + 1
        if reg == "C170" and len(p) >= 12:
            item = p[3].strip(); cfop_i = p[11].strip()
            qtd  = to_num(p[5]) or 0
            if item:
                if item not in item_qtd: item_qtd[item] = {"ent": 0, "sai": 0}
                if cfop_i and cfop_i[0] in "123": item_qtd[item]["ent"] += qtd
                elif cfop_i and cfop_i[0] in "567": item_qtd[item]["sai"] += qtd
        if reg == "H010" and len(p) >= 7:
            item = p[2].strip()
            if item: item_h010[item] = {"qtd": to_num(p[4]) or 0, "vl": to_num(p[6]) or 0, "ln": i+1}

    # ── PASSAGEM 2 ───────────────────────────────────────────────
    for i, l in enumerate(lines):
        if not l.strip() or not l.startswith("|"): continue
        f = fixed[i].split("|")
        reg = f[1].strip() if len(f)>1 else ""
        ln  = i + 1

        # Validação genérica via leiaute
        lei = LEIAUTE.get(reg)
        if lei:
            n_esp  = lei["n"]
            n_real = len(f) - 2
            if n_real > n_esp:
                if reg == "0200":   fix_pipe(i, f, 3, n_esp, reg, ln, "DESCR_ITEM")
                elif n_real > n_esp + 2:
                    rec_flag(reg, ln, f"Número de campos: {n_real}, esperado {n_esp}", "Verifique pipe em campo texto")
            # fixLen genérico
            idx_map = lei.get("idx", {})
            for nome_campo, max_len in lei.get("tam", {}).items():
                if nome_campo == "REG": continue
                fi = idx_map.get(nome_campo)
                if fi and fi < len(f):
                    val = f[fi].strip()
                    if max_len > 0 and len(val) > max_len:
                        novo = val[:max_len]
                        rec_fix(i, fi, val, novo, reg, ln, f"{nome_campo} truncado ({len(val)}>{max_len})")
                        f[fi] = novo

        # ── Por registro ─────────────────────────────────────────
        if reg == "0000":
            ver = get_cod_ver(dt_ini0000)
            if ver and (f[2].strip() if len(f)>2 else "") != ver["cod"]:
                rec_fix(i, 2, f[2], ver["cod"], reg, ln, f"COD_VER corrigido para {ver['cod']}")
                f[2] = ver["cod"]
            for fi, nm in [(4,"DT_INI"),(5,"DT_FIN")]:
                if len(f)>fi and f[fi] and not valid_date(f[fi]):
                    fx = fix_date_fmt(f[fi])
                    if fx: rec_fix(i, fi, f[fi], fx, reg, ln, f"{nm} formato corrigido")

        elif reg == "0190":
            fix_len(i, f, 2, 6, reg, ln, "UNID")

        elif reg == "0150":
            fix_len(i, f, 3, 100, reg, ln, "NOME")

        elif reg == "C100":
            for fi, nm in [(10,"DT_DOC"),(11,"DT_E_S")]:
                if len(f)>fi and f[fi] and not valid_date(f[fi]):
                    fx = fix_date_fmt(f[fi])
                    if fx: rec_fix(i, fi, f[fi], fx, reg, ln, f"{nm} corrigida")
            cod_mod = f[5].strip() if len(f)>5 else ""
            cod_sit = f[6].strip() if len(f)>6 else ""
            if cod_mod and cod_mod not in MOD_DOC_SET:
                rec_flag(reg, ln, f'COD_MOD "{cod_mod}" inválido', "Consulte tabela MOD_DOC")
            if cod_sit and cod_sit not in COD_SIT_SET:
                rec_flag(reg, ln, f'COD_SIT "{cod_sit}" inválido', "Valores: 00-09")
            if cod_mod in ("55","65") and len(f)>9:
                chv = re.sub(r"\D","",f[9])
                if not chv and cod_sit not in {"05"}:
                    # NFC-e/NF-e sem chave — pendência manual
                    num_doc = f[8].strip() if len(f)>8 else "?"
                    rec_err(reg, ln, f'CHV_NFE obrigatória (MOD={cod_mod} NF={num_doc}) — insira a chave ou exclua o registro')
                elif chv and len(chv) != 44:
                    rec_flag(reg, ln, f"CHV_NFE com {len(chv)} dígitos (esperado 44)", "Verifique a chave de acesso")

        elif reg == "C170" and len(f) >= 12:
            fix_len(i, f, 6, 6, reg, ln, "UNID")
            cst  = f[10].strip() if len(f)>10 else ""
            cfop = f[11].strip() if len(f)>11 else ""
            cst_ipi = f[20].strip() if len(f)>20 else ""
            if cst  and cst  not in CST_ICMS_SET: rec_flag(reg, ln, f'CST ICMS "{cst}" inválido')
            if cfop and cfop not in CFOP_SET:      rec_flag(reg, ln, f'CFOP "{cfop}" inválido')
            if cst_ipi and cst_ipi not in CST_IPI_SET: rec_flag(reg, ln, f'CST IPI "{cst_ipi}" inválido')
            recalc_icms(i, f, 14, 13, 15, "VL_ICMS C170", reg)
            recalc_icms(i, f, 17, 16, 18, "VL_ICMS_ST C170", reg)

        elif reg == "C190" and len(f) >= 8:
            cst  = f[2].strip(); cfop = f[3].strip()
            if cst  and cst  not in CST_ICMS_SET: rec_flag(reg, ln, f'CST "{cst}" inválido')
            if cfop and cfop not in CFOP_SET:      rec_flag(reg, ln, f'CFOP "{cfop}" inválido')
            recalc_icms(i, f, 4, 6, 7, "VL_ICMS C190", reg)

        elif reg == "E110" and len(f) >= 15:
            # Fórmula PVA: créditos - débitos
            # f[2]=VL_TOT_DEBITOS  f[4]=VL_TOT_AJ_DEBITOS  f[5]=VL_ESTORNOS_CRED
            # f[6]=VL_TOT_CREDITOS f[8]=VL_TOT_AJ_CREDITOS f[9]=VL_ESTORNOS_DEB f[10]=VL_SLD_CREDOR_ANT
            tot_cred = round(
                (to_num(f[6]) or 0) + (to_num(f[8]) or 0) +
                (to_num(f[9]) or 0) + (to_num(f[10]) or 0), 2)
            tot_deb  = round(
                (to_num(f[2]) or 0) + (to_num(f[4]) or 0) +
                (to_num(f[5]) or 0), 2)
            saldo    = round(tot_cred - tot_deb, 2)
            recolher = max(0.0, -saldo)
            credor   = max(0.0,  saldo)
            vl_dev = to_num(f[13])
            if vl_dev is not None and abs(recolher - vl_dev) > 0.02:
                rec_fix(i, 13, f[13], fmt_n(recolher), reg, ln, f"VL_ICMS_RECOLHER = {fmt_n(recolher)}")
                f[13] = fmt_n(recolher)
            vl_cred = to_num(f[14])
            if vl_cred is not None and abs(credor - vl_cred) > 0.02:
                rec_fix(i, 14, f[14], fmt_n(credor), reg, ln, f"VL_SLD_CREDOR_TRANSPORTAR = {fmt_n(credor)}")
                f[14] = fmt_n(credor)

        elif reg == "E111" and len(f) >= 3:
            cod_aj = f[2].strip()
            if not cod_aj:
                rec_err(reg, ln, "COD_AJ_APUR ausente")
            elif uf and F2.get("aj", {}).get(uf):
                ok, mot = cod_valido(F2["aj"][uf], cod_aj, dt_ini0000)
                if not ok:
                    ok2, _ = cod_valido(F2["aj"].get("GENERICA", {}), cod_aj, dt_ini0000)
                    if not ok2:
                        rec_flag(reg, ln, f'COD_AJ "{cod_aj}" inválido para {uf}: {mot}')

        elif reg == "E116" and len(f) >= 6:
            # MES_REF (f[10]): corrigir automaticamente para mmaaaa do período
            if dt_ini0000 and len(dt_ini0000) == 8:
                mes_ref_correto = dt_ini0000[2:4] + dt_ini0000[4:8]
                mes_ref_atual   = (f[10].strip() if len(f)>10 else "")
                if mes_ref_atual != mes_ref_correto:
                    rec_fix(i, 10, f[10], mes_ref_correto, reg, ln,
                            f"MES_REF corrigido para {mes_ref_correto} (período do 0000)")
                    f[10] = mes_ref_correto
            cod_rec = f[5].strip() if len(f)>5 else ""
            cod_or  = f[2].strip() if len(f)>2 else ""
            # Verificar se COD_REC é válido para a UF
            invalido = False
            if uf and F2.get("rec", {}).get(uf):
                valido_uf, _ = cod_valido(F2["rec"][uf], cod_rec, dt_ini0000)
                valido_gl, _ = cod_valido(F2["rec"].get("GLOBAL",{}), cod_rec, dt_ini0000)
                invalido = not valido_uf and not valido_gl
            # Auto-corrigir COD_OR=000 (apuração normal) com código da UF
            if invalido and cod_or == "000":
                cod_sugerido = detectar_cod_rec(uf or "", tipo_item_counts)
                if cod_sugerido:
                    rec_fix(i, 5, f[5], cod_sugerido, reg, ln,
                            f"COD_REC corrigido para {cod_sugerido} (padrão {uf} COD_OR=000)")
                    f[5] = cod_sugerido
                else:
                    rec_flag(reg, ln,
                             f'COD_REC "{cod_rec}" inválido para {uf} — selecione no dropdown',
                             "cod_rec_dropdown")
            elif invalido:
                rec_flag(reg, ln,
                         f'COD_REC "{cod_rec}" inválido para {uf} (COD_OR={cod_or})',
                         "cod_rec_dropdown")

        elif reg == "H010" and len(f) >= 7:
            fix_len(i, f, 3, 6, reg, ln, "UNID")
            ind = f[7].strip() if len(f)>7 else ""
            if ind not in ("0","1","2"):
                rec_fix(i, 7, f[7], "0", reg, ln, f'IND_PROP "{f[7]}" → 0')
                f[7] = "0"
            qtd   = to_num(f[4])
            v_unit = to_num(f[5])
            v_item = to_num(f[6])
            if qtd and v_unit and v_item is not None:
                calc = round(qtd * v_unit, 2)
                if abs(calc - v_item) > 0.05:
                    rec_fix(i, 6, f[6], fmt_n(calc), reg, ln, f"VL_ITEM H010: {fmt_n(qtd)} × {fmt_n(v_unit)}")
                    f[6] = fmt_n(calc)

        elif reg == "H005" and len(f) >= 3:
            if f[2] and not valid_date(f[2]):
                fx = fix_date_fmt(f[2])
                if fx: rec_fix(i, 2, f[2], fx, reg, ln, "DT_INV H005 corrigida")

        elif reg == "K200" and len(f) >= 5:
            if not valid_date(f[2]):
                fx = fix_date_fmt(f[2])
                if not fx:
                    # Fallback: DT_EST deve ser o DT_FIN do período (0000.f[5])
                    for _l0 in lines:
                        if _l0.startswith("|0000|"):
                            _p0 = _l0.split("|")
                            _dtf = _p0[5].strip() if len(_p0)>5 else ""
                            if valid_date(_dtf): fx = _dtf
                            break
                if fx:
                    rec_fix(i, 2, f[2], fx, reg, ln, f"DT_EST K200 corrigida para {fx}")
                    f[2] = fx
                else:
                    rec_err(reg, ln, f'DT_EST K200 inválida: "{f[2]}"'  )
            ind_est = f[5].strip() if len(f)>5 else ""
            if ind_est and ind_est not in ("0","1"):
                rec_flag(reg, ln, f'IND_EST "{ind_est}" inválido', "0=próprio, 1=terceiros")

        fixed[i] = "|".join(f)

    # ── Geração C190 (pai-filho) ──────────────────────────────────
    inserts: list[tuple[int, str, str]] = []  # (pos, linha_c190, desc)

    for p_idx, info in pai_map.items():
        if info["reg"] != "C100": continue
        if "C190" in info["filhos"]: continue

        raw = info["raw"]
        real_idx = p_idx
        for delta in range(-20, 21):
            ti = real_idx + delta
            if 0 <= ti < len(fixed) and fixed[ti] == raw:
                real_idx = ti; break

        pf = fixed[real_idx].split("|")
        cod_sit = pf[6].strip() if len(pf)>6 else ""
        if cod_sit in DISPENSAR_COD_SIT: continue

        cod_mod  = pf[5].strip() if len(pf)>5 else ""
        ind_oper = pf[2].strip() if len(pf)>2 else ""
        vl_doc   = pf[12].strip() if len(pf)>12 else "0,00"

        c190_map: dict[str, dict] = {}
        j = real_idx + 1
        while j < len(fixed):
            pp = fixed[j].split("|") if fixed[j].startswith("|") else []
            if not pp: break
            r2 = pp[1].strip() if len(pp)>1 else ""
            if r2 == "C100": break
            if r2 == "C170" and len(pp) >= 16:
                cst  = pp[10].strip(); cfop = pp[11].strip()
                aliq = pp[14].strip() or "0"
                bc   = to_num(pp[13]) or 0
                icms = to_num(pp[15]) or 0
                bc_st  = to_num(pp[16]) or 0
                icms_st = to_num(pp[18]) or 0
                vl_opr = to_num(pp[7]) or 0
                key = f"{cst}|{cfop}|{aliq}"
                if key not in c190_map:
                    c190_map[key] = {"cst":cst,"cfop":cfop,"aliq":aliq,
                                     "bc":0,"icms":0,"bc_st":0,"icms_st":0,"vl_opr":0}
                c190_map[key]["bc"]     += bc
                c190_map[key]["icms"]   += icms
                c190_map[key]["bc_st"]  += bc_st
                c190_map[key]["icms_st"]+= icms_st
                c190_map[key]["vl_opr"] += vl_opr
            j += 1

        # Posição de inserção
        ins = real_idx + 1
        while ins < len(fixed):
            pp = fixed[ins].split("|") if fixed[ins].startswith("|") else []
            r2 = pp[1].strip() if len(pp)>1 else ""
            if r2 in ("C100","C990","C001"): break
            ins += 1

        if c190_map:
            for v in c190_map.values():
                c190 = (f"|C190|{v['cst']}|{v['cfop']}|{v['aliq']}|"
                        f"{fmt_n(v['vl_opr'])}|{fmt_n(v['bc'])}|{fmt_n(v['icms'])}|"
                        f"{fmt_n(v['bc_st'])}|{fmt_n(v['icms_st'])}|0,00|0,00||")
                inserts.append((ins, c190, f"C190 gerado via C170: {v['cst']}/{v['cfop']}"))
        elif cod_mod == "65" and ind_oper == "1":
            c190 = f"|C190|300|5102|0,00|{vl_doc}|0,00|0,00|0,00|0,00|0,00|0,00||"
            inserts.append((ins, c190, f"C190 gerado NFC-e: CST=300/5102/VL={vl_doc}"))
        else:
            rec_err("C100", p_idx+1, f"C100 sem C190 e sem C170 — verifique manualmente")

    # Inserir de trás para frente
    for pos, linha, desc in reversed(inserts):
        fixed.insert(pos, linha)
        res.fixes.append(Fix("C190", pos, desc, "(ausente)", linha))

    # ── Geração E250 (ICMS-ST obrigações) ─────────────────────────
    e250_inserts: list[tuple[int, str, str]] = []
    cur_e200_uf = ""
    cur_e200_dt_ini = ""

    for i, l in enumerate(fixed):
        if not l.strip() or not l.startswith("|"): continue
        p = l.split("|")
        if len(p) < 2: continue
        reg = p[1].strip()

        if reg == "E200" and len(p) > 4:
            cur_e200_uf = p[2].strip()
            cur_e200_dt_ini = p[3].strip()

        elif reg == "E210" and len(p) >= 16:
            vl_recol = to_num(p[13]) or 0
            deb_esp = to_num(p[15]) or 0
            vl_or = round(vl_recol + deb_esp, 2)
            if vl_or <= 0: continue

            has_e250 = False
            j = i + 1
            while j < len(fixed):
                if not fixed[j].strip() or not fixed[j].startswith("|"):
                    j += 1; continue
                rj = fixed[j].split("|")[1].strip() if len(fixed[j].split("|")) > 1 else ""
                if rj in ("E200", "E210", "E990", "E001", "9900"): break
                if rj == "E250": has_e250 = True; break
                j += 1

            if has_e250: continue

            ins = i + 1
            while ins < len(fixed):
                if not fixed[ins].strip() or not fixed[ins].startswith("|"):
                    ins += 1; continue
                ri = fixed[ins].split("|")[1].strip() if len(fixed[ins].split("|")) > 1 else ""
                if ri not in ("E220", "E230", "E240"): break
                ins += 1

            mes_ref = (cur_e200_dt_ini[2:4] + cur_e200_dt_ini[4:8]) if len(cur_e200_dt_ini) == 8 else ""
            dt_vcto = calc_dt_vcto_st(cur_e200_dt_ini)
            cod_rec_st = detectar_cod_rec_st(cur_e200_uf)

            if cod_rec_st and uf and F2.get("rec", {}).get(cur_e200_uf):
                v1, _ = cod_valido(F2["rec"][cur_e200_uf], cod_rec_st, dt_ini0000)
                v2, _ = cod_valido(F2["rec"].get("GLOBAL", {}), cod_rec_st, dt_ini0000)
                if not v1 and not v2:
                    cod_rec_st = None

            e250_line = f"|E250|002|{fmt_n(vl_or)}|{dt_vcto}|{cod_rec_st or ''}|||||{mes_ref}|"
            desc_e250 = f"E250 gerado: VL_OR={fmt_n(vl_or)} UF_ST={cur_e200_uf}"
            if cod_rec_st:
                desc_e250 += f" COD_REC={cod_rec_st}"
            e250_inserts.append((ins, e250_line, desc_e250))

            if not cod_rec_st:
                rec_flag("E250", i+1,
                         f"E250 gerado sem COD_REC para ICMS-ST UF {cur_e200_uf} — selecione manualmente",
                         "e250_cod_rec")

    for pos, linha, desc in reversed(e250_inserts):
        fixed.insert(pos, linha)
        res.fixes.append(Fix("E250", pos, desc, "(ausente)", linha))

    # ── Inserir 9900 para registros novos (ex: E250 gerado) ──────
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
                res.fixes.append(Fix("9900", ins_9900+1,
                                     f"9900 criado para {ref}: {qtd}", "(ausente)", new_line))
                ins_9900 += 1

    # ── Atualizar xXX990 e contadores ────────────────────────────
    blocos = list("0ABCDEGHK19")
    for bloco in blocos:
        reg990 = bloco + "990"
        idx990 = next((i for i,l in enumerate(fixed)
                       if l.startswith(f"|{reg990}|")), -1)
        if idx990 < 0: continue
        qtd_real = sum(1 for l in fixed if l.strip() and l.startswith("|") and
                       len(l.split("|"))>1 and l.split("|")[1].strip().startswith(bloco))
        p990 = fixed[idx990].split("|")
        qtd_atual = int(p990[2]) if len(p990)>2 and p990[2].isdigit() else 0
        if qtd_atual != qtd_real:
            res.fixes.append(Fix(reg990, idx990+1, f"{reg990}: {qtd_atual}→{qtd_real}",
                                 str(qtd_atual), str(qtd_real)))
            p990[2] = str(qtd_real)
            fixed[idx990] = "|".join(p990)

    # Atualizar 9900
    new_count: dict[str,int] = {}
    for l in fixed:
        if not l.strip() or not l.startswith("|"): continue
        p = l.split("|")
        if len(p)>1: new_count[p[1].strip()] = new_count.get(p[1].strip(),0)+1

    for i, l in enumerate(fixed):
        if not l.startswith("|9900|"): continue
        p = l.split("|")
        ref = p[2].strip() if len(p)>2 else ""
        qtd_inf = int(p[3]) if len(p)>3 and p[3].strip().isdigit() else 0
        qtd_real = new_count.get(ref, 0)
        if qtd_real > 0 and qtd_inf != qtd_real:
            res.fixes.append(Fix("9900", i+1, f"Contador {ref}: {qtd_inf}→{qtd_real}",
                                 str(qtd_inf), str(qtd_real)))
            p[3] = str(qtd_real)
            fixed[i] = "|".join(p)

    # 9999 — re-buscar posição real após inserts de C190
    real_9999_idx = next((i for i,l in enumerate(fixed) if l.startswith("|9999|")), r9999_idx)
    if real_9999_idx >= 0:
        total = sum(1 for l in fixed if l.strip())
        p = fixed[real_9999_idx].split("|")
        qtd_inf = int(p[2]) if len(p)>2 and p[2].strip().isdigit() else 0
        if qtd_inf != total:
            res.fixes.append(Fix("9999", real_9999_idx+1, f"QTD_LIN: {qtd_inf}→{total}",
                                 str(qtd_inf), str(total)))
            p[2] = str(total)
            fixed[real_9999_idx] = "|".join(p)

    # ── Validações cruzadas pós-passagem ─────────────────────────
    # C190 → E110
    if (acum_deb_c190 or acum_cred_c190) and e110_ln > 0:
        e110_line = next((l for l in fixed if l.startswith("|E110|")), None)
        if e110_line:
            pe = e110_line.split("|")
            e110_deb  = to_num(pe[2]) or 0
            e110_cred = to_num(pe[6]) or 0
            if acum_deb_c190 and abs(e110_deb - acum_deb_c190) > 1.0:
                rec_flag("E110", e110_ln,
                         f"VL_TOT_DEBITOS ({fmt_n(e110_deb)}) ≠ soma C190 saída ({fmt_n(acum_deb_c190)})")
            if acum_cred_c190 and abs(e110_cred - acum_cred_c190) > 1.0:
                rec_flag("E110", e110_ln,
                         f"VL_TOT_CREDITOS ({fmt_n(e110_cred)}) ≠ soma C190 entrada ({fmt_n(acum_cred_c190)})")

    # DIFAL
    if cfops_difal and not tem_e300:
        rec_flag("E300", 0, f"{len(cfops_difal)} CFOP(s) 3xxx sem Bloco E300 (DIFAL)", "EC 87/2015")

    # ── Sumário ───────────────────────────────────────────────────
    ver = get_cod_ver(dt_ini0000)
    dt_ini = parse_date(dt_ini0000)
    dt_fin_s = ""
    for l in lines:
        if l.startswith("|0000|"):
            p = l.split("|")
            dt_fin_s = p[5].strip() if len(p)>5 else ""
            break

    res.sumario.total_linhas = sum(1 for l in fixed if l.strip())
    res.sumario.dt_ini = dt_ini.strftime("%d/%m/%Y") if dt_ini else "—"
    dt_fin_d = parse_date(dt_fin_s)
    res.sumario.dt_fin = dt_fin_d.strftime("%d/%m/%Y") if dt_fin_d else "—"
    res.sumario.versao = ver["versao"] if ver else "—"
    res.sumario.uf = uf or "—"
    res.sumario.reg_count = new_count

    # Dashboard de alíquotas
    for l in fixed:
        if not l.startswith("|C190|"): continue
        p = l.split("|")
        if len(p) < 8: continue
        cfop = p[3].strip(); aliq = to_num(p[4]) or 0
        bc = to_num(p[6]) or 0; vl = to_num(p[7]) or 0
        vl_opr = to_num(p[5]) or 0
        if not cfop or bc <= 0: continue
        if cfop not in res.sumario.aliq_map:
            res.sumario.aliq_map[cfop] = {"bc": 0, "icms": 0, "vl_opr": 0, "n": 0}
        res.sumario.aliq_map[cfop]["bc"]     += bc
        res.sumario.aliq_map[cfop]["icms"]   += vl
        res.sumario.aliq_map[cfop]["vl_opr"] += vl_opr
        res.sumario.aliq_map[cfop]["n"]      += 1

    res.fixed_lines = fixed
    return res
