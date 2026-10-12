"""Build AmmoCash: chest ammo slots drop cash instead of ammo (25/50/75/100%) when that ammo type is full.

Pipeline:
  1. Find the newest copy of each needed NCS file in the game's paks (patch paks are cumulative).
  2. Decode NCS -> JSON with ncs_parser.
  3. Patch the JSON:
       attribute0   + evaluator_ammocash_<type>_weight  (cash weight per ammo type, only when full)
       itempool0    + itempool_ammocash                  (picks the ammo type with vanilla weights)
                    + itempool_ammocash_<type>           (ammo vs. cash, 50/50 only when that type is full)
       loot_config* ammo sockets -> itempool_ammocash
  4. Encode JSON -> NCS and pack everything into an unencrypted .pak.

Run from anywhere:  py build.py [--game "D:/.../Borderlands 4"] [--threshold 0.99] [--chance 50 | --all]
"""

import argparse
import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
WORK = ROOT / "work"
DIST = ROOT / "dist"

REPAK = TOOLS / "repak.exe"
NCS_PARSER = TOOLS / "ncs_parser.exe"
NCS_OUTPUT = TOOLS / "output"  # ncs_parser always writes next to its binary

AES_KEY = "0x33A604DF49A07FFD4A4C919962161F5C35A134D37EFA98DB37A34F6450D7D386"
DEFAULT_GAME = Path("D:/Games/SteamLibrary/steamapps/common/Borderlands 4")
CHANCES = [25, 50, 75, 100]  # --all builds one pak per cash chance (percent)
NCS_DIR = "Engine/Content/_NCS"

POOL_NAME = "itempool_ammocash"
CASH_ITEM = "inv'currency_money_singlestack'"
AMMO_PRESET = "criteria_preset'LootPreset_Ammo'"
AMMO_POOL = "itempool'itempool_ammo'"

# (ammo sub-pool, original weight evaluator, mod cash evaluator)
AMMO_TYPES = [
    ("itempool_ammo_assaultrifle", "evaluator_ammo_assaultrifle_weight", "evaluator_ammocash_assaultrifle_weight"),
    ("itempool_ammo_pistol", "evaluator_ammo_pistol_weight", "evaluator_ammocash_pistol_weight"),
    ("itempool_ammo_shotgun", "evaluator_ammo_shotgun_weight", "evaluator_ammocash_shotgun_weight"),
    ("itempool_ammo_smg", "evaluator_ammo_smg_weight", "evaluator_ammocash_smg_weight"),
    ("itempool_ammo_sniperrifle", "evaluator_ammo_sniper_weight", "evaluator_ammocash_sniper_weight"),
]

# Files to patch. loot_config4/6 are DLC chunks; they are optional.
ATTRIBUTE = "attribute0"
ITEMPOOL = "itempool0"
LOOT_CONFIGS = ["loot_config0", "loot_config4", "loot_config6"]


def run(args, **kw):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, **kw)
    if result.returncode != 0:
        sys.exit(f"command failed: {args}\n{result.stdout}\n{result.stderr}")
    return result.stdout


# --- JSON helpers (ncs_parser wraps every value as {"__typeFlags": n, "value": v}) ---

def s(value):
    return {"__typeFlags": 513, "value": value}


def obj(**fields):
    return {"__typeFlags": 515, "value": fields}


def arr(items):
    return {"__typeFlags": 514, "value": items}


def entries(table):
    top = next(iter(table))
    for record in table[top]["records"]:
        yield record, record["entries"]


def find_entry(table, key):
    for record, ents in entries(table):
        for e in ents:
            if key in e:
                return record, e
    return None, None


# --- Step 1: locate newest NCS copies ---

def pak_version(pak: Path):
    m = re.search(r"_(\d+)_P\.pak$", pak.name)
    return int(m.group(1)) if m else -1


def locate(paks_dir: Path, names):
    found = {}
    for chunk in sorted({re.search(r"\d+", n).group() for n in names}):
        paks = sorted(paks_dir.glob(f"pakchunk{chunk}-Windows_*_P.pak"), key=pak_version)
        for pak in paks:
            result = subprocess.run([str(REPAK), "-a", AES_KEY, "list", str(pak)], capture_output=True, text=True)
            if result.returncode != 0:
                continue  # some patch paks have no file index (IoStore-only chunks)
            listing = result.stdout.splitlines()
            for n in names:
                if f"{NCS_DIR}/Nexus-Data-{n}.ncs" in listing:
                    found[n] = pak  # later (higher) versions overwrite earlier ones
    return found


# --- Step 3: patches ---

def cash_weight(chance):
    """Cash weight next to an ammo weight of 1 that gives `chance` cash when the type is full."""
    return 1_000_000.0 if chance >= 1 else chance / (1 - chance)


def patch_attributes(table, threshold, chance):
    _, template_entry = find_entry(table, AMMO_TYPES[0][1])
    if template_entry is None:
        sys.exit("attribute0: ammo weight evaluators not found")
    for _, src_name, mod_name in AMMO_TYPES:
        record, src = find_entry(table, src_name)
        if find_entry(table, mod_name)[1] is not None:
            continue
        body = copy.deepcopy(src[src_name])
        body["value"]["attribute"] = s(mod_name)
        resolver = body["value"]["value"]["value"]
        # Cash weight is cash_weight(chance) above the threshold and 0 everywhere else,
        # so cash only competes once the type is (nearly) full.
        resolver["threshold"] = obj(constant=s(f"{threshold:.6f}"))
        resolver["abovethresholdweight"] = obj(constant=s(f"{cash_weight(chance):.6f}"))
        for field in ("noweight", "minbelowthresholdweight", "maxbelowthresholdweight"):
            resolver[field] = obj(constant=s("0.000000"))
        new = {"__op": src["__op"], mod_name: body}
        ents = record["entries"]
        ents.insert(ents.index(src) + 1, new)


def pool_item(handle, weight_attribute):
    return obj(
        item=obj(item=obj(handle=s(handle))),
        weight=obj(attribute=s(f"attribute'{weight_attribute}'")),
    )


def constant_item(handle, weight):
    return obj(
        item=obj(item=obj(handle=s(handle))),
        weight=obj(constant=s(f"{weight:.6f}")),
    )


def type_pool_name(sub_pool):
    return sub_pool.replace("itempool_ammo_", f"{POOL_NAME}_")


def patch_itempool(table):
    """Two-stage roll so ammo you need drops exactly as in vanilla:
    itempool_ammocash picks the ammo type with the vanilla weights, then
    itempool_ammocash_<type> picks ammo (weight 1) vs. cash (weight 0, or cash_weight() when full)."""
    record, ammo = find_entry(table, "itempool_ammo")
    if ammo is None:
        sys.exit("itempool0: itempool_ammo not found")
    if find_entry(table, POOL_NAME)[1] is not None:
        return
    op = ammo["__op"]
    new_entries = []
    outer_items = []
    for sub_pool, ammo_eval, cash_eval in AMMO_TYPES:
        _, sub = find_entry(table, sub_pool)
        if sub is None:
            sys.exit(f"itempool0: {sub_pool} not found")
        name = type_pool_name(sub_pool)
        fields = {
            "itempool": s(name),
            "items": arr([constant_item(f"itempool'{sub_pool}'", 1.0), pool_item(CASH_ITEM, cash_eval)]),
        }
        # Same game-stage gate as the ammo sub-pool, so a locked type never rolls cash-only.
        if "mingamestage" in sub[sub_pool]["value"]:
            fields["mingamestage"] = copy.deepcopy(sub[sub_pool]["value"]["mingamestage"])
        new_entries.append({"__op": op, name: obj(**fields)})
        outer_items.append(pool_item(f"itempool'{name}'", ammo_eval))
    new_entries.append({"__op": op, POOL_NAME: obj(itempool=s(POOL_NAME), items=arr(outer_items))})
    ents = record["entries"]
    at = ents.index(ammo) + 1
    ents[at:at] = new_entries


def patch_loot_config(table):
    """Point every ammo socket at the mod pool. Returns number of sockets changed."""
    changed = 0
    new_handle = f"itempool'{POOL_NAME}'"

    def walk(node):
        nonlocal changed
        if isinstance(node, dict):
            value = node.get("value")
            # "configurations" sockets: item = {item?: {handle}, criteria: {preset: LootPreset_Ammo}}
            if isinstance(value, dict) and "criteria" in value:
                crit = value["criteria"].get("value", {})
                preset = crit.get("preset", {}).get("value") if isinstance(crit, dict) else None
                if preset == AMMO_PRESET:
                    del value["criteria"]
                    value["item"] = obj(handle=s(new_handle))
                    changed += 1
                    return
            # "configs" sockets: itempool = itempool'itempool_ammo'
            if isinstance(value, dict) and value.get("itempool", {}).get("value") == AMMO_POOL:
                value["itempool"] = s(new_handle)
                changed += 1
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(table)
    return changed


# --- main ---

def pak_name(percent):
    return f"AmmoCash{percent}_999_P.pak"


def add_key_strings(meta, new_strings):
    """New entry names must exist in the key string table (table 1) or the encoder refuses them."""
    table = meta["stringTables"][1]
    for name in new_strings:
        if name not in table["strings"]:
            table["strings"].append(name)
    table["declaredCount"] = len(table["strings"])


def build_pak(percent, threshold, json_dir, loot_configs):
    """Patch the decoded tables in json_dir (left untouched) and pack them into dist/."""
    work = WORK / f"build{percent}"
    enc_dir, ncs_dir = work / "encode", work / "pak" / NCS_DIR
    for d in (enc_dir, ncs_dir):
        d.mkdir(parents=True)

    def load(n):
        return json.loads((json_dir / f"{n}.json").read_text(encoding="utf-8"))

    def save(n, table, new_strings=()):
        (enc_dir / f"{n}.json").write_text(json.dumps(table), encoding="utf-8")
        meta = json.loads((json_dir / f"{n}_metadata.json").read_text(encoding="utf-8"))
        add_key_strings(meta, new_strings)
        (enc_dir / f"{n}_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    t = load(ATTRIBUTE); patch_attributes(t, threshold, percent / 100)
    save(ATTRIBUTE, t, [m for _, _, m in AMMO_TYPES])
    t = load(ITEMPOOL); patch_itempool(t)
    save(ITEMPOOL, t, [POOL_NAME] + [type_pool_name(p) for p, _, _ in AMMO_TYPES])
    patched = [ATTRIBUTE, ITEMPOOL]
    for n in loot_configs:
        t = load(n)
        count = patch_loot_config(t)
        print(f"  {n}: {count} ammo sockets redirected")
        if count:
            save(n, t)
            patched.append(n)

    # Encode
    shutil.rmtree(NCS_OUTPUT, ignore_errors=True)
    run([NCS_PARSER, enc_dir], cwd=TOOLS)
    for n in patched:
        shutil.copy(NCS_OUTPUT / "ncs" / f"{n}.ncs", ncs_dir / f"Nexus-Data-{n}.ncs")

    # Verify: re-decode and check the new entries survived
    shutil.rmtree(NCS_OUTPUT, ignore_errors=True)
    run([NCS_PARSER, ncs_dir], cwd=TOOLS)
    check = {
        f"Nexus-Data-{ATTRIBUTE}": [m for _, _, m in AMMO_TYPES] + [f"{cash_weight(percent / 100):.6f}"],
        f"Nexus-Data-{ITEMPOOL}": [POOL_NAME] + [type_pool_name(p) for p, _, _ in AMMO_TYPES],
    }
    for n in patched[2:]:
        check[f"Nexus-Data-{n}"] = [f"itempool'{POOL_NAME}'"]
    for n, needles in check.items():
        text = (NCS_OUTPUT / "json" / f"{n}.json").read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                sys.exit(f"verification failed: {needle} missing in {n}")
    shutil.rmtree(NCS_OUTPUT, ignore_errors=True)

    # Pack
    DIST.mkdir(exist_ok=True)
    out = DIST / pak_name(percent)
    out.unlink(missing_ok=True)
    run([REPAK, "pack", "--version", "V11", "--mount-point", "../../../", work / "pak", out])
    print(f"  built {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--threshold", type=float, default=0.99,
                    help="ammo fill fraction above which cash can replace that ammo type")
    ap.add_argument("--chance", type=int, default=50,
                    help="percent of a full type's ammo drops that become cash (1-100)")
    ap.add_argument("--all", action="store_true", help=f"build one pak for each of {CHANCES}")
    args = ap.parse_args()
    if not 1 <= args.chance <= 100:
        sys.exit("--chance must be between 1 and 100")

    paks_dir = args.game / "OakGame/Content/Paks"
    if not paks_dir.is_dir():
        sys.exit(f"Paks folder not found: {paks_dir}")

    shutil.rmtree(WORK, ignore_errors=True)
    raw_dir, json_dir = WORK / "raw", WORK / "json"
    for d in (raw_dir, json_dir):
        d.mkdir(parents=True, exist_ok=True)

    names = [ATTRIBUTE, ITEMPOOL] + LOOT_CONFIGS
    sources = locate(paks_dir, names)
    for n in (ATTRIBUTE, ITEMPOOL, "loot_config0"):
        if n not in sources:
            sys.exit(f"{n}.ncs not found in game paks")

    for n, pak in sources.items():
        print(f"{n}: {pak.name}")
        data = subprocess.run([str(REPAK), "-a", AES_KEY, "get", str(pak), f"{NCS_DIR}/Nexus-Data-{n}.ncs"],
                              capture_output=True, check=True).stdout
        (raw_dir / f"{n}.ncs").write_bytes(data)

    # Decode
    shutil.rmtree(NCS_OUTPUT, ignore_errors=True)
    run([NCS_PARSER, raw_dir], cwd=TOOLS)
    for f in (NCS_OUTPUT / "json").glob("*.json"):
        shutil.copy(f, json_dir / f.name)

    loot_configs = [n for n in LOOT_CONFIGS if n in sources]
    for percent in (CHANCES if args.all else [args.chance]):
        print(f"{percent}% cash:")
        build_pak(percent, args.threshold, json_dir, loot_configs)
    print("verification ok")


if __name__ == "__main__":
    main()
