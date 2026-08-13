"""投稿テキストの安全チェック。人の目視ではなく機械で照合する。

使い方: python3 scripts/safe_check.py <テキストファイル> [...]
        終了コード 0 = PASS / 1 = 要修正

2つの辞書を両方見る（どちらも brand/ にある。masterはOneDrive側＝ファイル冒頭の _コピー元 を参照）:
  ① brand/ng_dictionary.json  … Instagram専用（薬機法・景表法・Amazon規約）
  ② brand/禁止語辞書.json      … 全社共通の正典（画像・A+と共通。こちらが上位）

②には「例外文脈」「例外パターン」がある。
  例外文脈  … 打ち消しの言い回しなど、その並びなら許される（例:「完全防水ではありません」）
  例外パターン … 正規表現で許される（例:「ナイロン100%」は成分表記なのでOK）
🔴 例外を**このファイルに直接書かないこと**。辞書側に足す。2か所に書くと必ず食い違う。
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
BRAND = HERE.parent / "brand"
INSTA_DICT = BRAND / "ng_dictionary.json"
COMMON_DICT = BRAND / "禁止語辞書.json"


def load(path):
    if not path.is_file():
        print(f"警告: 辞書が見つからない -> {path}", file=sys.stderr)
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mask_allowed(text, common):
    """辞書の「例外文脈」に載っている言い回しを、検査の前に伏せる。

    打ち消しの注記（「完全防水ではありません」）は優良誤認を防ぐ正しい書き方なので、
    ここで伏せないと、正しく注記を入れた投稿ほど警告が出てチェッカーが信用されなくなる。
    """
    for ex in common.get("例外文脈", []):
        for phrase in ex.get("許可", []):
            text = text.replace(phrase, "〓" * len(phrase))
    return text


def find_hits(text, insta, common):
    """(語, 言い換え/理由, どの辞書) のリストを返す。"""
    text = mask_allowed(text, common)
    hits = []

    # ① インスタ辞書の置換ルール
    for rule in insta.get("replace", []):
        for word in re.split(r"\s*/\s*", rule["ng"]):
            word = word.strip()
            if word and word in text:
                hits.append((word, f"→ {rule['ok']}", "インスタ辞書"))

    # ② 全社の正典
    patterns = [
        (p.get("語", ""), re.compile(p["正規表現"]))
        for p in common.get("例外パターン", []) if p.get("正規表現")
    ]
    for rule in common.get("禁止語", []):
        word = rule.get("語", "")
        if not word or word not in text:
            continue
        if any(w == word and rx.search(text) for w, rx in patterns):
            continue          # 例外パターンに当てはまる（例: ナイロン100%）
        why = rule.get("言い換え") or rule.get("理由") or ""
        hits.append((word, why, "共通の正典"))

    return hits


def check_manual(text):
    """辞書に載らない、数えれば分かる項目。"""
    notes = []
    tags = re.findall(r"#\S+", text)
    if len(tags) > 8:
        notes.append(f"ハッシュタグが{len(tags)}個。1投稿5個前後が方針")
    if len(text) > 2200:
        notes.append(f"{len(text)}文字。Instagramの上限2200を超えている")
    return notes


def main(paths):
    insta = load(INSTA_DICT)
    common = load(COMMON_DICT)
    if not insta or not common:
        print("辞書が読めないので検査を打ち切る（素通りさせない）", file=sys.stderr)
        return 1

    ng_total = 0
    for p in paths:
        path = pathlib.Path(p)
        text = path.read_text(encoding="utf-8-sig")
        hits = find_hits(text, insta, common)
        notes = check_manual(text)

        print(f"\n=== {path.name} ({len(text)}文字) ===")
        if hits:
            ng_total += len(hits)
            for word, why, src in hits:
                print(f"  NG [{src}] 「{word}」 {why}")
        else:
            print("  禁止語の検出なし")
        for n in notes:
            print(f"  注意 {n}")

    print()
    if ng_total:
        print(f"要修正: 禁止語 {ng_total}件")
        return 1
    print("PASS: 禁止語ゼロ")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
