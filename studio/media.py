"""リール・スタジオの「決まった手順」部分（声・BGM・合成）。Claudeには触らせず、この関数だけが実行する。
2026-09-29 インソールのリール（ai記事自動\\インスタ\\制作\\2026-09-29_インソール好評発売中）で作った道具を汎用化したもの。

- make_voice: 1文ずつ AivisSpeech で合成し、文ごとに速さを測って target_rate（拍/秒）にそろえる（早口の文をなくす）
- check_readings: 各文の「実際の読み」をカタカナで返す（ひらがなに開くと は→ワ と誤読する事故があった）
- make_audio: BGMをコードで作曲し、声・冒頭動画の環境音と混ぜる（声の間はBGMを下げる）
- compose: 黒地＋冒頭動画＋コマ連番＋音 → 1080×1920/30fps の mp4
"""
import io, json, os, subprocess, time, wave, urllib.parse, urllib.request
from pathlib import Path
import numpy as np

AIVIS = "http://127.0.0.1:10101"
SR = 48000


# ---------------- 声 ----------------
def start_engine(timeout=180):
    def ok():
        try:
            urllib.request.urlopen(f"{AIVIS}/version", timeout=2); return True
        except Exception:
            return False
    if ok(): return True
    exe = Path(os.environ["USERPROFILE"]) / "aivisspeech" / "Windows-x64" / "run.exe"
    if not exe.exists(): raise RuntimeError(f"AivisSpeech が無い: {exe}")
    subprocess.Popen([str(exe)], creationflags=0x08000000)  # CREATE_NO_WINDOW
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ok(): return True
        time.sleep(3)
    raise RuntimeError("AivisSpeech Engine が起動しない")


def _query(text, spk, extra):
    u = f"{AIVIS}/audio_query?" + urllib.parse.urlencode({"text": text, "speaker": spk})
    q = json.load(urllib.request.urlopen(urllib.request.Request(u, method="POST")))
    q.update(extra or {})
    return q


def _synth(q, spk):
    req = urllib.request.Request(f"{AIVIS}/synthesis?speaker={spk}", data=json.dumps(q).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    w = wave.open(io.BytesIO(urllib.request.urlopen(req).read()))
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32), w.getframerate()


def _trim(x, sr):
    win = int(sr * 0.01)
    e = np.array([np.sqrt(np.mean(x[i:i + win] ** 2)) for i in range(0, len(x) - win, win)])
    idx = np.where(e > e.max() * 0.02)[0]
    a = max(0, idx[0] * win - int(sr * 0.03)); b = min(len(x), (idx[-1] + 1) * win + int(sr * 0.06))
    return x[a:b]


def check_readings(script):
    """各文の読み（カタカナ・アクセント句の区切り）を返す。書き手に見せて誤読を直させるため。"""
    out = []
    for s in script["scenes"]:
        for sent in s["sentences"]:
            q = _query(sent, script["speaker"], {})
            phr = " / ".join("".join(m["text"] for m in ap["moras"]) + ("、" if ap.get("pause_mora") else "")
                             for ap in q["accent_phrases"])
            out.append({"scene": s["id"], "text": sent, "reading": phr})
    return out


def make_voice(script, work):
    work = Path(work); (work / "voice").mkdir(parents=True, exist_ok=True)
    spk, target, gap = script["speaker"], script.get("target_rate", 7.0), script.get("sentence_gap", 0.42)
    extra = script.get("query", {"pauseLengthScale": 1.25, "intonationScale": 1.05,
                                 "prePhonemeLength": 0.05, "postPhonemeLength": 0.08})
    timing, report = [], []
    for s in script["scenes"]:
        parts, marks, t, sr = [], [], 0.0, 48000
        for i, sent in enumerate(s["sentences"]):
            q = _query(sent, spk, extra); moras = sum(len(ap["moras"]) for ap in q["accent_phrases"])
            q["speedScale"] = 1.0
            x, sr = _synth(q, spk); x = _trim(x, sr)
            q["speedScale"] = float(np.clip(target / (moras / (len(x) / sr)), 0.82, 1.15))
            x, sr = _synth(q, spk); x = _trim(x, sr)
            marks.append(round(t, 3)); parts.append(x); t += len(x) / sr
            report.append(f"{s['id']} 速さ{q['speedScale']:.2f} {moras/(len(x)/sr):.1f}拍/秒 {sent}")
            if i < len(s["sentences"]) - 1:
                parts.append(np.zeros(int(gap * sr), np.float32)); t += gap
        y = np.concatenate(parts)
        with wave.open(str(work / "voice" / f"{s['id']}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(np.clip(y, -32768, 32767).astype(np.int16).tobytes())
        dur = len(y) / sr
        timing.append({"id": s["id"], "voice": round(dur, 3), "scene": round(dur + s.get("pad", 0.8), 3), "marks": marks})
    (work / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
    return timing, report


# ---------------- 音（BGM作曲・ミックス） ----------------
def _read_wav(p):
    with wave.open(str(p)) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        x = np.interp(np.arange(int(len(x) * SR / sr)) / SR, np.arange(len(x)) / sr, x).astype(np.float32)
    return x


def make_audio(work, timing, amb_wav=None, seed=3):
    """BGM＝96BPM・D-A-Bm-G。冒頭はパッドだけ→2場面目からプラック・ベース・キック・ハット。"""
    work = Path(work); rng = np.random.default_rng(seed)
    starts, t = [], 0.0
    for s in timing: starts.append(t); t += s["scene"]
    TOTAL = t; N = int(TOTAL * SR) + SR
    note = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    BEAT = 60 / 96; BAR = BEAT * 4
    CH = [[50, 54, 57, 62], [49, 52, 57, 61], [47, 50, 54, 59], [43, 47, 50, 55]]; ROOT = [38, 37, 35, 31]
    groove_on = starts[1] if len(starts) > 1 else 0
    bgm = np.zeros(N, np.float32)

    def add(buf, x, at):
        i = int(at * SR)
        if i >= len(buf): return
        x = x[: len(buf) - i]; buf[i:i + len(x)] += x

    for b in range(int(TOTAL / BAR) + 2):
        dur = BAR + 0.6; n = int(dur * SR); tt = np.arange(n) / SR
        env = np.minimum(1, tt / 0.5) * np.minimum(1, (dur - tt) / 0.6); x = np.zeros(n, np.float32)
        for m in CH[b % 4]:
            f = note(m + 12)
            for det in (-0.12, 0.0, 0.12):
                x += np.sin(2 * np.pi * f * (1 + det / 100) * tt) * 0.5 + np.sin(2 * np.pi * 2 * f * tt) * 0.08
        add(bgm, (x * env * 0.018).astype(np.float32), b * BAR)

    def pluck(f, dur=0.9):
        n = int(dur * SR); per = int(SR / f); buf = rng.uniform(-1, 1, per).astype(np.float32); out = np.zeros(n, np.float32)
        for i in range(n):
            out[i] = buf[i % per]; buf[i % per] = 0.5 * (buf[i % per] + buf[(i + 1) % per]) * 0.994
        return out
    cache = {}; pat = [0, 2, 1, 3, 2, 1, 3, 2]; t8 = groove_on
    while t8 < TOTAL - 1.0:
        b = int(t8 / BAR); k = int(round((t8 - b * BAR) / (BEAT / 2))) % 8; m = CH[b % 4][pat[k]] + 12
        if m not in cache: cache[m] = pluck(note(m))
        add(bgm, cache[m] * 0.07, t8); t8 += BEAT / 2
    tb = groove_on - (groove_on % BEAT)
    while tb < TOTAL - 1.0:
        b = int(tb / BAR); beat_in = int(round((tb - b * BAR) / BEAT)) % 4
        if tb >= groove_on:
            if beat_in in (0, 2):
                n = int(0.5 * SR); tt = np.arange(n) / SR
                add(bgm, (np.tanh(2 * np.sin(2 * np.pi * note(ROOT[b % 4]) * tt)) * np.exp(-tt * 5) * 0.09).astype(np.float32), tb)
                n = int(0.22 * SR); tt = np.arange(n) / SR; ph = 2 * np.pi * np.cumsum(50 + 90 * np.exp(-tt * 30)) / SR
                add(bgm, (np.sin(ph) * np.exp(-tt * 16) * 0.16).astype(np.float32), tb)
            n = int(0.05 * SR); tt = np.arange(n) / SR
            add(bgm, np.diff(rng.normal(0, 1, n + 1)).astype(np.float32) * np.exp(-tt * 70) * 0.018, tb + BEAT / 2)
        tb += BEAT
    fo = int(1.4 * SR); end_i = int(TOTAL * SR); bgm[end_i - fo:end_i] *= np.linspace(1, 0, fo); bgm[end_i:] = 0

    voice = np.zeros(N, np.float32)
    for s, st in zip(timing, starts):
        add(voice, _read_wav(work / "voice" / f"{s['id']}.wav") * 0.95, st + 0.25)
    amb = np.zeros(N, np.float32)
    if amb_wav and Path(amb_wav).exists() and len(starts) > 1:
        a = _read_wav(amb_wav)[: int((starts[1] + 0.4) * SR)]
        f = min(len(a), int(0.5 * SR)); a[-f:] *= np.linspace(1, 0, f); add(amb, a * 0.55, 0)
    env = np.abs(voice); k = int(0.15 * SR); env = np.convolve(env, np.ones(k) / k, mode="same")
    duck = 1 - 0.55 * np.clip(env / (env.max() * 0.25 + 1e-9), 0, 1)
    mix = bgm * duck + voice + amb; mix = mix / np.abs(mix).max() * 0.89; mix = mix[: int(TOTAL * SR)]
    st = np.stack([mix, mix], axis=1)
    with wave.open(str(work / "mix.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype(np.int16).tobytes())
    return TOTAL


# ---------------- 合成 ----------------
def compose(work, total, out, hook_video=None, hook_until=4.4):
    work = Path(work)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=1080x1920:r=30:d={total:.2f}"]
    if hook_video:
        cmd += ["-i", str(hook_video)]
    cmd += ["-framerate", "30", "-i", str(work / "frames" / "f_%05d.png"), "-i", str(work / "mix.wav")]
    if hook_video:
        fc = (f"[1:v]trim=0:{hook_until:.2f},setpts=PTS-STARTPTS,fps=30,scale=1080:1920:force_original_aspect_ratio=increase,"
              f"crop=1080:1920,format=yuva420p[h];[0:v][h]overlay=eof_action=pass[b];[b][2:v]overlay=format=auto[v]")
        amap = "3:a"
    else:
        fc = "[0:v][1:v]overlay=format=auto[v]"; amap = "2:a"
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", amap, "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
            "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)


def contact_sheet(video, out, cols=8, fps=1, width=180):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps={fps},scale={width}:-1,tile={cols}x5",
                    "-frames:v", "1", str(out)], check=True)
