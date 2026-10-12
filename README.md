# AmmoCash (Borderlands 4)

Ammo slots in chests, ammo crates, lockers, toolboxes and similar lootables drop **cash instead of ammo when that ammo type is full**. Ammo types that are not full drop as usual.

There are four versions, by how often a full type's ammo turns into cash:

| Pak | Cash when the type is full |
|---|---|
| `AmmoCash25_999_P.pak` | 25% |
| `AmmoCash50_999_P.pak` | 50% |
| `AmmoCash75_999_P.pak` | 75% |
| `AmmoCash100_999_P.pak` | 100% (weight 1,000,000 : 1, so effectively always) |

Install only one of them.

## How it works

In vanilla, each ammo type's drop weight comes from an `OakAmmoWeightResolver` (`evaluator_ammo_<type>_weight`), driven by `DataTable_PlayerAmmoResourceBalance`. Above a fill threshold (40% for AR/pistol/SMG/shotgun, 30% for sniper), the type's weight drops to 1–2%. Below it, the weight is between 1 and 5. Vanilla has no cash fallback, so a full type just makes the other types more likely.

The mod adds:

- `attribute0`: `evaluator_ammocash_<type>_weight`. This is an `OakAmmoWeightResolver` for that ammo type. Its weight is 0 below 99% fill and `p / (1 - p)` above it, where `p` is the cash chance.
- `itempool0`: a two-stage roll.
  - `itempool_ammocash` picks the ammo type with the vanilla weights.
  - `itempool_ammocash_<type>` then picks between that ammo (weight 1) and `currency_money_singlestack` (the cash resolver). The cash weight is 0 unless the type is full. Each type pool keeps the vanilla game-stage gate of its ammo.
- `loot_config0/4/6`: every socket that used `LootPreset_Ammo` (or `itempool_ammo`) now uses `itempool_ammocash`. That is 66 sockets.

Ammo types you need drop exactly as often as in vanilla. Only the share of a full type is split between its ammo and cash.

## Build

NCS patch files are cumulative. The newest copy of each file holds the whole table, so the mod ships full copies of these files with the patches applied. **After every game update, run the build again.**

```
py build.py [--game "D:/Games/SteamLibrary/steamapps/common/Borderlands 4"] [--threshold 0.99] [--chance 50 | --all]
```

`--chance` sets the cash percentage (default 50) and writes `dist/AmmoCash<chance>_999_P.pak`. `--all` builds the 25/50/75/100 versions.

`tools/` must contain these files (they are not in the repo):

- `repak.exe`: https://github.com/trumank/repak/releases
- `ncs_parser.exe`: https://github.com/Cr4nkSt4r/Borderlands-4.NcsParser/releases
- `oo2core_9_win64.dll`: the Oodle 2.9 redist DLL (for example from the Unreal Engine SDK folder `EpicGames.Oodle/Sdk/2.9.x/win/redist`)

## Install

Download one `AmmoCash<chance>_999_P.pak` from [Releases](https://github.com/GlcrTE/AmmoCash/releases), or build it yourself. Remove any other AmmoCash pak first (including the older `AmmoCash_999_P.pak` or `pakchunk99-Windows_999_P.pak`). Copy it to `Borderlands 4/OakGame/Content/Paks/`. If it does not load there, try `Paks/~mods/`.

## Compatibility

Conflicts with any mod that ships its own `Nexus-Data-attribute0.ncs`, `itempool0.ncs` or `loot_config0/4/6.ncs`. Works with asset mods such as MaxLootLuck.

## Credits

`build.py` calls these tools as separate programs. They are not part of this repository and keep their own licenses:

- [repak](https://github.com/trumank/repak) by trumank (MIT/Apache-2.0)
- [Borderlands-4.NcsParser](https://github.com/Cr4nkSt4r/Borderlands-4.NcsParser) by Cr4nkSt4r (AGPL-3.0)
- Oodle by Epic Games Tools (proprietary, not redistributed)

## License

MIT, see [LICENSE](LICENSE). This covers only the build script and docs. Borderlands 4 and its game data belong to Gearbox Software / 2K. The repository contains no game files.
