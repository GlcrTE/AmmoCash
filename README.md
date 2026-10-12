# AmmoCash (Borderlands 4)

Ammo slots in chests, ammo crates, lockers, toolboxes and similar lootables drop **cash instead of ammo 50% of the time when that ammo type is full**. Ammo types that are not full drop as usual.

## How it works

In vanilla, each ammo type's drop weight comes from an `OakAmmoWeightResolver` (`evaluator_ammo_<type>_weight`), driven by `DataTable_PlayerAmmoResourceBalance`. Above a fill threshold (40% for AR/pistol/SMG/shotgun, 30% for sniper), the type's weight drops to 1–2%. Below it, the weight is between 1 and 5. Vanilla has no cash fallback, so a full type just makes the other types more likely.

The mod adds:

- `attribute0`: `evaluator_ammocash_<type>_weight`. This copies the ammo resolver, but the weight is 0 below 99% fill and equals the ammo type's own above-threshold weight above it.
- `itempool0`: `itempool_ammocash`, which pairs each ammo sub-pool with a `currency_money_singlestack` entry weighted by the matching cash resolver.
- `loot_config0/4/6`: every socket that used `LootPreset_Ammo` (or `itempool_ammo`) now uses `itempool_ammocash`. That is 66 sockets.

When a type is full, that type's share of the roll is split 50/50 between its ammo and cash.

## Build

NCS patch files are cumulative. The newest copy of each file holds the whole table, so the mod ships full copies of these files with the patches applied. **After every game update, run the build again.**

```
py build.py [--game "D:/Games/SteamLibrary/steamapps/common/Borderlands 4"] [--threshold 0.99]
```

The output is `dist/pakchunk99-Windows_999_P.pak`.

`tools/` must contain these files (they are not in the repo):

- `repak.exe`: https://github.com/trumank/repak/releases
- `ncs_parser.exe`: https://github.com/Cr4nkSt4r/Borderlands-4.NcsParser/releases
- `oo2core_9_win64.dll`: the Oodle 2.9 redist DLL (for example from the Unreal Engine SDK folder `EpicGames.Oodle/Sdk/2.9.x/win/redist`)

## Install

Copy `pakchunk99-Windows_999_P.pak` to `Borderlands 4/OakGame/Content/Paks/`. If it does not load there, try `Paks/~mods/`.

## Compatibility

Conflicts with any mod that ships its own `Nexus-Data-attribute0.ncs`, `itempool0.ncs` or `loot_config0/4/6.ncs`. Works with asset mods such as MaxLootLuck.

## Credits

`build.py` calls these tools as separate programs. They are not part of this repository and keep their own licenses:

- [repak](https://github.com/trumank/repak) by trumank (MIT/Apache-2.0)
- [Borderlands-4.NcsParser](https://github.com/Cr4nkSt4r/Borderlands-4.NcsParser) by Cr4nkSt4r (AGPL-3.0)
- Oodle by Epic Games Tools (proprietary, not redistributed)

## License

MIT, see [LICENSE](LICENSE). This covers only the build script and docs. Borderlands 4 and its game data belong to Gearbox Software / 2K. The repository contains no game files.
