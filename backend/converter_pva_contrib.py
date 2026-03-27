"""
Converte o descritor.xml do PVA EFD-Contribuições + tabelas auxiliares
para um JSON unificado (dados_pva_contrib.json) no mesmo formato do dados_pva.json.

Uso:
    python converter_pva_contrib.py
"""
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

EXTRACT_DIR = Path(__file__).parent / "pva_contrib_extract"
DESCRITOR_XML = EXTRACT_DIR / "descritor" / "escrituracao" / "estrutura7006" / "v3" / "descritor.xml"
TABELAS_DIR = Path(r"c:\Arquivos de Programas RFB\Programas SPED\EFD-Contribuicoes\recursos\tabelas")
OUTPUT = Path(__file__).parent / "dados_pva_contrib.json"

JAR_PATH = Path(r"c:\Arquivos de Programas RFB\Programas SPED\EFD-Contribuicoes\lib\br.gov.serpro.sped.piscofinspva\piscofinspva-infra.jar")


def extract_if_needed():
    if DESCRITOR_XML.exists():
        return
    print("Extraindo descritor.xml do JAR...")
    os.makedirs(EXTRACT_DIR, exist_ok=True)
    os.system(f'jar xf "{JAR_PATH}" "descritor/escrituracao/estrutura7006/v3/descritor.xml"')


def parse_tamanho(tam_str: str) -> int:
    """Converte atributo 'tamanho' do XML para inteiro (ex: '[3]' -> 3, '14' -> 14, '8-' -> 8)."""
    if not tam_str:
        return 0
    s = tam_str.strip().strip("[]").rstrip("-").split(",")[0].split("-")[0]
    try:
        return int(s)
    except ValueError:
        return 0


def parse_leiaute(root) -> dict:
    """Extrai leiaute: para cada registro, retorna n, tam, obr, idx, bloco."""
    leiaute = {}

    def walk(element, bloco_id=""):
        for reg_el in element.findall("registro"):
            reg_id = reg_el.get("id", "")
            if not reg_id:
                continue

            campos = reg_el.findall("campo")
            n = len(campos)

            tam = {}
            obr = []
            idx = {}

            for campo in campos:
                campo_id = campo.get("id", "")
                campo_n = int(campo.get("n", 0))
                campo_tam = parse_tamanho(campo.get("tamanho", "0"))
                campo_obr = campo.get("obrigatorio", "0")

                tam[campo_id] = campo_tam
                idx[campo_id] = campo_n
                if campo_obr == "1":
                    obr.append(campo_id)

            leiaute[reg_id] = {
                "n": n,
                "tam": tam,
                "obr": obr,
                "idx": idx,
                "bloco": bloco_id,
            }

            walk(reg_el, bloco_id)

    for bloco in root.findall("bloco"):
        bloco_id = bloco.get("id", "")
        walk(bloco, bloco_id)

    return leiaute


def parse_pai_filho(root) -> dict:
    """Monta hierarquia pai->filhos dos registros."""
    pai_filho = {}

    def walk(element, parent_id=None):
        for reg_el in element.findall("registro"):
            reg_id = reg_el.get("id", "")
            if not reg_id:
                continue
            if parent_id:
                pai_filho.setdefault(parent_id, []).append(reg_id)
            walk(reg_el, reg_id)

    for bloco in root.findall("bloco"):
        walk(bloco)

    return pai_filho


def parse_valores_validos(root) -> dict:
    """Extrai valores-validos de cada campo para registros que possuem."""
    vv = {}

    def walk(element):
        for reg_el in element.findall("registro"):
            reg_id = reg_el.get("id", "")
            if not reg_id:
                continue
            for campo in reg_el.findall("campo"):
                campo_id = campo.get("id", "")
                vv_el = campo.find("valores-validos")
                if vv_el is not None:
                    valores = vv_el.get("valores", "")
                    if valores:
                        vv.setdefault(reg_id, {})[campo_id] = valores
            walk(reg_el)

    for bloco in root.findall("bloco"):
        walk(bloco)

    return vv


def read_tabela(filepath: Path) -> list:
    """Lê um arquivo de tabela do PVA (formato pipe-delimited com header na primeira linha)."""
    try:
        raw = filepath.read_bytes()
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return []

        lines = text.strip().splitlines()
        if not lines:
            return []

        rows = []
        for line in lines[1:]:
            parts = line.split("|")
            rows.append(parts)
        return rows
    except Exception:
        return []


def parse_table_code_desc(filepath: Path) -> dict:
    """Parseia tabela com colunas COD|DESCRICAO (ou similar)."""
    rows = read_tabela(filepath)
    result = {}
    for parts in rows:
        if len(parts) >= 2:
            result[parts[0].strip()] = parts[1].strip()
    return result


def parse_cst_table(filepath: Path) -> dict:
    rows = read_tabela(filepath)
    result = {}
    for parts in rows:
        if parts:
            result[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else ""
    return result


def parse_cfop_table(filepath: Path) -> dict:
    rows = read_tabela(filepath)
    result = {}
    for parts in rows:
        if len(parts) >= 2:
            result[parts[0].strip()] = parts[1].strip()
    return result


def parse_versoes_table(filepath: Path) -> dict:
    """Parseia tabela de versões do leiaute."""
    rows = read_tabela(filepath)
    result = {}
    for parts in rows:
        if len(parts) >= 3:
            cod = parts[0].strip()
            result[cod] = {
                "versao": parts[1].strip() if len(parts) > 1 else "",
                "dt_ini": parts[2].strip() if len(parts) > 2 else "",
                "dt_fim": parts[3].strip() if len(parts) > 3 else "",
            }
    return result


def parse_modelos_table(filepath: Path) -> dict:
    rows = read_tabela(filepath)
    result = {}
    for parts in rows:
        if len(parts) >= 2:
            result[parts[0].strip()] = parts[1].strip()
    return result


def parse_uf_tables(dir_path: Path) -> dict:
    uf_cod = {}
    fname_sigla = "SPEDPISCOFINS_GLOBAL$SPEDPISCOFINS_UF_CODIGO_SIGLA$1$134"
    fpath = dir_path / fname_sigla
    rows = read_tabela(fpath)
    for parts in rows:
        if len(parts) >= 2:
            uf_cod[parts[0].strip()] = parts[1].strip()
    return uf_cod


def find_tabela_files(dir_path: Path) -> dict:
    """Mapeia nomes curtos para caminhos de arquivos de tabela."""
    mapping = {}
    if not dir_path.exists():
        return mapping
    for f in dir_path.iterdir():
        if f.is_file() and f.name != "metadados":
            parts = f.name.split("$")
            if len(parts) >= 2:
                short_name = parts[1].replace("SPEDPISCOFINS_", "").lower()
                mapping[short_name] = f
    return mapping


def build_cfop_maps(cfop_data: dict):
    """Constrói mapas de CFOP saída→entrada e entrada→saída."""
    sai_to_ent = {}
    ent_to_sai = {}
    for cfop in cfop_data:
        c = cfop.strip()
        if len(c) == 4 and c[0] in ("5", "6", "7"):
            ent = c[0].replace("5", "1").replace("6", "2").replace("7", "3") + c[1:]
            if ent in cfop_data:
                sai_to_ent[c] = ent
                ent_to_sai[ent] = c
    return sai_to_ent, ent_to_sai


def main():
    extract_if_needed()

    if not DESCRITOR_XML.exists():
        print(f"ERRO: {DESCRITOR_XML} não encontrado.")
        return

    print(f"Parseando {DESCRITOR_XML}...")
    tree = ET.parse(DESCRITOR_XML)
    root = tree.getroot()

    leiaute = parse_leiaute(root)
    print(f"  {len(leiaute)} registros extraídos do leiaute")

    pai_filho = parse_pai_filho(root)
    valores_validos = parse_valores_validos(root)

    tab_files = find_tabela_files(TABELAS_DIR)
    print(f"  {len(tab_files)} arquivos de tabelas encontrados")

    cst_pis = {}
    cst_cofins = {}
    cst_ipi = {}
    cfop = {}
    mod_doc = {}
    versoes = {}
    uf_cod = {}

    for short, fpath in tab_files.items():
        if short == "cst_pis":
            cst_pis = parse_cst_table(fpath)
            print(f"  CST PIS: {len(cst_pis)} códigos")
        elif short == "cst_cofins":
            cst_cofins = parse_cst_table(fpath)
            print(f"  CST COFINS: {len(cst_cofins)} códigos")
        elif short == "cst_ipi":
            cst_ipi = parse_cst_table(fpath)
            print(f"  CST IPI: {len(cst_ipi)} códigos")
        elif short == "cst_icms":
            pass
        elif short == "cfop":
            cfop = parse_cfop_table(fpath)
            print(f"  CFOP: {len(cfop)} códigos")
        elif short == "modelos":
            mod_doc = parse_modelos_table(fpath)
            print(f"  Modelos documento: {len(mod_doc)} códigos")
        elif short == "versoes_leiaute":
            versoes = parse_versoes_table(fpath)
            print(f"  Versões leiaute: {len(versoes)} versões")

    uf_cod = parse_uf_tables(TABELAS_DIR)
    print(f"  UF: {len(uf_cod)} estados")

    cfop_sai_to_ent, cfop_ent_to_sai = build_cfop_maps(cfop)

    nat_bc_cred = {}
    tipo_cred = {}
    for short, fpath in tab_files.items():
        if short == "bc_cred":
            nat_bc_cred = parse_table_code_desc(fpath)
            print(f"  Natureza BC Crédito: {len(nat_bc_cred)} códigos")
        elif short == "tipo_cred":
            tipo_cred = parse_table_code_desc(fpath)
            print(f"  Tipo Crédito: {len(tipo_cred)} códigos")

    cod_rec_f600 = {}
    cod_rec_p200 = {}
    for short, fpath in tab_files.items():
        if short == "cod_rec_f600":
            cod_rec_f600 = parse_table_code_desc(fpath)
            print(f"  COD_REC F600: {len(cod_rec_f600)} códigos")
        elif short == "cod_rec_p200":
            cod_rec_p200 = parse_table_code_desc(fpath)
            print(f"  COD_REC P200: {len(cod_rec_p200)} códigos")

    result = {
        "leiaute": leiaute,
        "pai_filho": pai_filho,
        "valores_validos": valores_validos,
        "cfop": cfop,
        "cfop_sai_to_ent": cfop_sai_to_ent,
        "cfop_ent_to_sai": cfop_ent_to_sai,
        "cst_pis": cst_pis,
        "cst_cofins": cst_cofins,
        "cst_ipi": cst_ipi,
        "mod_doc": mod_doc,
        "versoes": versoes,
        "uf_cod": uf_cod,
        "nat_bc_cred": nat_bc_cred,
        "tipo_cred": tipo_cred,
        "cod_rec_f600": cod_rec_f600,
        "cod_rec_p200": cod_rec_p200,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"\nGerado: {OUTPUT}")
    print(f"Tamanho: {size_kb:.1f} KB")
    print(f"Registros no leiaute: {len(leiaute)}")
    print(f"Relações pai-filho: {len(pai_filho)}")


if __name__ == "__main__":
    main()
