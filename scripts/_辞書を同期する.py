"""OneDriveの正典（master）を、クラウドが読めるようにリポジトリへ写す。

コピーである以上、放っておけば必ず食い違う。
そこで各コピーの先頭に `_コピー元` と `_写した日` を入れ、
週次のお知らせタスクが master と突き合わせてズレを知らせる。
"""

import json
import pathlib

DESKTOP = pathlib.Path(r"C:\Users\Owner\OneDrive\デスクトップ")
REPO = pathlib.Path(r"C:\Users\Owner\repos\unizom-insta")
BRAND = REPO / "brand"
BRAND.mkdir(parents=True, exist_ok=True)

TODAY = "2026-08-13"

PAIRS = [
    (DESKTOP / "ai記事自動" / "インスタ" / "brand" / "ng_dictionary.json",
     BRAND / "ng_dictionary.json",
     "ai記事自動/インスタ/brand/ng_dictionary.json"),
    (DESKTOP / "_tools" / "画像QA" / "禁止語辞書.json",
     BRAND / "禁止語辞書.json",
     "_tools/画像QA/禁止語辞書.json"),
]

for src, dst, rel in PAIRS:
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    stamped = {
        "_コピー元": f"OneDriveデスクトップ/{rel}（こちらがmaster）",
        "_注意": "これは写し。直すときはmasterを直し、Claudeに「インスタの辞書を同期して」と言う。"
                 "週次のお知らせがmasterとの差を見張っている。",
        "_写した日": TODAY,
    }
    stamped.update(data)
    dst.write_text(json.dumps(stamped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"写した: {rel} -> brand/{dst.name}  ({dst.stat().st_size // 1024} KB)")
