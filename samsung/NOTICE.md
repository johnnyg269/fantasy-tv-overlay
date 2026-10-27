# Source and asset provenance

`FantasyOverlay.cs` is derived from `payloads/qn90f/Qn90fEflTextOverlayProbe.cs` in [chris-ritsen/samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root), pinned for setup to v0.0.12, commit `3b97edf3762db7670585d73e29623dc56195bf98`. That project is released under the Unlicense; its license is retained in this folder. This project adds bounded JSON state, atomic scene replacement, stale-heartbeat hiding, remote interaction, typography and the fantasy presentation. It does not redistribute Samsung's platform libraries or SDB.

`QuietInter-Medium.ttf` and `QuietInter-Semibold.ttf` are renamed/subset Inter assets from [jss8649/quiet-tizen](https://github.com/jss8649/quiet-tizen), commit `cf518d7a9278dca7990e27756218258e44044a29`. The Inter Project Authors' SIL Open Font License is retained at `licenses/Inter-OFL.txt`. These font assets remain under that font license.

`BebasNeue-Regular.ttf` is the Bebas Neue font distributed by [Google Fonts](https://github.com/google/fonts/tree/main/ofl/bebasneue). Its SIL Open Font License is retained beside it in `assets/fonts/BebasNeue-OFL.txt`.

The button and continuous corner-fade PNG assets are project artwork. Their geometry/profile metadata is included in `assets/ui/`. The public demo and test fixtures use invented manager/team labels and synthetic matchups. No household photos, production league responses, pairing stores, session receipts, custom font downloads or credentials are part of this source distribution.
