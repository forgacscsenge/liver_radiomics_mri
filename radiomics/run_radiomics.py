import os
import json
import glob
import argparse
import numpy as np
import pandas as pd
import ants
from radiomics import featureextractor


#ebben a szakaszban a tobbhelyrol erkezo szamszeru adatokat lebegopontos szabba alakitja, ahol nincs adat, ott none-t ad vissza
def to_float(x):
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"na", "nan", "none"}:
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

#egysegesiti a tobbhelyrol erkezo sesid-ket (levagja a ses elotagot/valtozatlanul hagyja ha nincs)
def norm_session_id(s: str) -> str:
    s = str(s).strip()
    if s.startswith("ses-"):
        s = s[4:]
    return s

#dontest hoz, hogy ket sesid ugyanaz-e (tsvben pontok a szeparalok, fileneveben I)
def session_ids_equivalent(a: str, b: str) -> bool:
    a = norm_session_id(a)
    b = norm_session_id(b)

    if a == b:
        return True

#a lenti modszereken megy vegig, hogy egyenloek a sesid-k
    if a.replace("I", ".") == b:
        return True
    if a == b.replace("I", "."):
        return True
    if a.replace(".", "I") == b:
        return True
    if a == b.replace(".", "I"):
        return True

    return False

#megkeresi a DataFrameban az elso olyan oszlopot, amit kerni akarok (fuggetlenul attol, hogy kis/nagy betu/eliras van-e benne)
def pick_col_case_insensitive(df: pd.DataFrame, wanted: list[str]):
    cols = list(df.columns)
    lower_map = {c.lower(): c for c in cols}
    for w in wanted:
        if w.lower() in lower_map:
            return lower_map[w.lower()]
    return None

#a session.tsvbol kiolvassa egy adott beteghez tartozo sesid alapjan a testsulyt es magassagot, majd BMI-t szamol.
def read_sessions_meta(rawdata_root: str, taj: str, sesid: str) -> dict:
    sesid = norm_session_id(sesid)
#alapertelmezett kimenet az out, akkoris ha nincs adat
    out = {"Patient_Weight_kg": None, "Patient_Size_m": None, "BMI": None}

#session.tsv megkeresese, ha nincs, NONE ertekkel ter vissza
    sessions_tsv = os.path.join(rawdata_root, f"sub-{taj}", "sessions.tsv")
    if not os.path.isfile(sessions_tsv):
        return out

    #a tsv beolvasasa rugalmas szeparatorokkal (; tab, vesszo+szokoz)
    df = pd.read_csv(
        sessions_tsv,
        sep=r"\t|;|\s*,\s*",
        engine="python",
        dtype=str,
        skipinitialspace=True,
    )
    df.columns = [c.strip() for c in df.columns] #veletlen/felesleges szokozok leszedese
#sesid oszlop megkeresese a lenti elofordulhatosagok alapjan
    sid_col = pick_col_case_insensitive(df, ["session-id", "session_id", "session", "sesid", "ses"])
    if sid_col is None:
        return out
#size es weight oszlopok megkeresese
    w_col = pick_col_case_insensitive(df, ["weight", "patient_weight", "Patient_Weight", "testsuly"])
    s_col = pick_col_case_insensitive(df, ["size", "patient_size", "Patient_Size", "magassag"])

    #sesidhez tartozo sor megkeresese (ha tobb is van, az utolso sort hagyja meg)
    hit = None
    for _, row in df.iterrows():
        sid_val = (row.get(sid_col, "") or "").strip()
        if session_ids_equivalent(sid_val, sesid):
            hit = row

    #weight: csak az aktualis sesidbol
    w = None
    if hit is not None and w_col:
        w = to_float(hit.get(w_col))

    #size: elsosorban az aktualis sesid-hez tartozo sorbol
    s = None
    if hit is not None and s_col:
        s = to_float(hit.get(s_col))

    #ha veletlenul cm-ben fordulna elo, akkor m-re konvertalja
    if isinstance(s, float) and s > 3.0:
        s = s / 100.0

    #ha nincs az aktualis sesidben size, akkor megnezi, hogy masikban van-e, es az utolso elofordulot valasztja
    if (s is None or not isinstance(s, float) or s <= 0) and s_col:
        fallback_s = None
        for _, row in df.iterrows():
            cand = to_float(row.get(s_col))
            if isinstance(cand, float) and cand > 0:
                # cm -> m
                if cand > 3.0:
                    cand = cand / 100.0
                fallback_s = cand
        s = fallback_s

    out["Patient_Weight_kg"] = w
    out["Patient_Size_m"] = s

#BMI szamolasa
    if isinstance(w, float) and isinstance(s, float) and s > 0:
        out["BMI"] = w / (s ** 2)

    return out

#adott sub-taj/ses-sesid alatti mappaban keres .json filet es kiolvassa a Station/Institution/Manufacturer model neveket.
def read_ses_json_meta(rawdata_root: str, taj: str, sesid: str) -> dict:
    sesid = norm_session_id(sesid)
#alapertelmezett kimenet az out
    out = {
        "Station_Name": None,
        "Institution_Name": None,
        "Manufacturers_Model_Name": None,
    }

#session konyvtar meghatarozasa
    ses_dir = os.path.join(rawdata_root, f"sub-{taj}", f"ses-{sesid}")
    if not os.path.isdir(ses_dir):
        return out

#rekurziv .json kereses, mert a konyvtarak felepitese nem mindig egyforma, igy a sesid alatt minden mappaban keresi
    for jp in sorted(glob.glob(os.path.join(ses_dir, "**", "*.json"), recursive=True)):
        try:
            with open(jp, "r", encoding="utf-8") as f:
                d = json.load(f)

#mindegyik json-t beolvassa, ha talal benne kulcsot es csak akkor irja be, ha addig None volt a cella erteke. ha mindharom erteke megvan, akkor kilep
#tobbfele modon keresi a kulcsokat a json-okben
            if out["Manufacturers_Model_Name"] is None and "ManufacturersModelName" in d:
                v = str(d["ManufacturersModelName"]).strip()
                out["Manufacturers_Model_Name"] = v or None

            if out["Institution_Name"] is None and "InstitutionName" in d:
                v = str(d["InstitutionName"]).strip()
                out["Institution_Name"] = v or None

            if out["Station_Name"] is None:
                # előfordulhat több kulcsnév is
                for key in ["StationName", "Station", "Station_Name"]:
                    if key in d:
                        v = str(d[key]).strip()
                        if v:
                            out["Station_Name"] = v
                            break

#kilepesi pont, ha mindharom cella erteke megvan
            if all(out[k] is not None for k in out):
                break

#ha serult a json, nem fog leallni a radiomika
        except Exception:
            continue

    return out


#radiomika
def main():
#argumentumok a Process.shbol
    ap = argparse.ArgumentParser()
    ap.add_argument("--adc_in_atlas", required=True)
    ap.add_argument("--taj", required=True)
    ap.add_argument("--sesid", required=True)
    ap.add_argument("--gender", required=True, help="M or F (pontosan)")
    ap.add_argument("--voi_male", required=True)
    ap.add_argument("--voi_female", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--rawdata", required=True)
    ap.add_argument("--out_csv", required=True)
    ap.add_argument("--out_masks_dir", required=True)
    args = ap.parse_args()

#gender validalasa (csak M es F lehet male, female nem)
    if args.gender not in {"M", "F"}:
        raise ValueError("Gender must be exactly 'M' or 'F'.")
#voi megvalasztasa a nem alapjan
    voi_path = args.voi_female if args.gender == "F" else args.voi_male
#kimeneti mappak letrehozasa a resamplezott voiknak es a csvnek
    os.makedirs(args.out_masks_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)
#radiomics extractor inicializalasa a params.yaml-bol, hogy milyen featureokat szamoljon
    extractor = featureextractor.RadiomicsFeatureExtractor(args.params)
#patientid kiharapasa a filenevebol, ez lesz az oszlop nev a csvben
    adc_path = args.adc_in_atlas
    patient_id = os.path.basename(adc_path).replace("_adc_in_atlas.nii.gz", "")

    #adc kep beolvasasa
    img = ants.image_read(adc_path)

    #biztonsagi lepes arra, hogy a voimaszk biztosan az adc-re legyen resamplezva (ha mas spaceban lenennek)
    voi = ants.image_read(voi_path)
    voi_on_img = ants.resample_image_to_target(voi, img, interp_type="nearestNeighbor")
    #a voi kimentese
    mask_path = os.path.join(args.out_masks_dir, f"{patient_id}_voi_on_adc.nii.gz")
    ants.image_write(voi_on_img, mask_path)

    #radiomika futtatasa
    feats = extractor.execute(adc_path, mask_path, label=1)

    #a kimeneti csv osszeallitasa, eloszor a testsuly/magassag, utana a statname stb.
    row = {}
    row.update(read_sessions_meta(args.rawdata, args.taj, args.sesid))
    row.update(read_ses_json_meta(args.rawdata, args.taj, args.sesid))

    #radiomikai featureok hozzadasa, csak az original_ elotaguak
    for k, v in feats.items():
        if not k.startswith("original_"):
            continue
        try:
            row[k] = float(v)
        except Exception:
            row[k] = np.nan

#oszlop letrehozasa, taj_sesid lesz az oszlop neve
    new_col = pd.Series(row, name=patient_id)

    #betolti a mx-ot vagy general ha meg nincs
    if os.path.isfile(args.out_csv):
        df = pd.read_csv(args.out_csv, index_col=0)
    else:
        df = pd.DataFrame()

    #ha az oszlop mar letezett, akkor felulirja, ha nem letezett, hozzaadja
    df[new_col.name] = new_col

    #metasorok felul, utana jonnek a radiomikai featureok
    meta_order = [
        "Patient_Weight_kg",
        "Patient_Size_m",
        "BMI",
        "Station_Name",
        "Institution_Name",
        "Manufacturers_Model_Name",
    ]
    meta_order = [m for m in meta_order if m in df.index]
    other = [f for f in df.index if f not in meta_order]
    df = df.loc[meta_order + other]

#mentes es kiiratas
    df.to_csv(args.out_csv)
    print(f"OK: {patient_id} -> {args.out_csv}")

if __name__ == "__main__":
    main()
