"""Reading a mixed-mode CD image: .cue + .bin (one file or one per track) or CloneCD .ccd + .img.
The data track's ISO 9660 file system is read straight from the raw sectors; audio tracks are
returned as 16-bit stereo 44.1 kHz PCM."""
import os, re, struct, sys


class Track:
    def __init__(self, n, kind, path, start, end, sector):
        self.n, self.kind, self.path, self.start, self.end, self.sector = n, kind, path, start, end, sector


def parse_cue(cue):
    base = os.path.dirname(os.path.abspath(cue)); files = []
    for line in open(cue, encoding="utf-8", errors="replace"):
        t = line.strip()
        m = re.match(r'FILE\s+"?(.*?)"?\s+\w+$', t)
        if m: files.append((os.path.join(base, m.group(1)), [])); continue
        m = re.match(r'TRACK\s+(\d+)\s+(\S+)', t)
        if m: files[-1][1].append([int(m.group(1)), m.group(2).upper(), {}]); continue
        m = re.match(r'INDEX\s+(\d+)\s+(\d+):(\d+):(\d+)', t)
        if m:
            i, mm, ss, ff = map(int, m.groups()); files[-1][1][-1][2][i] = (mm * 60 + ss) * 75 + ff
    tracks = []
    for path, trks in files:
        sector = 2048 if trks and trks[0][1].endswith("/2048") else 2352
        total = os.path.getsize(path) // sector
        for i, (n, kind, idx) in enumerate(trks):
            start = idx.get(1, idx.get(0, 0))
            end = (trks[i + 1][2].get(0) or trks[i + 1][2][1]) if i + 1 < len(trks) else total
            tracks.append(Track(n, kind, path, start, end, sector))
    return tracks


def parse_ccd(ccd):
    sec, cur = {}, None
    for line in open(ccd, encoding="utf-8", errors="replace"):
        t = line.strip()
        if t.startswith("["): cur = t[1:-1]; sec[cur] = {}
        elif "=" in t and cur: k, v = t.split("=", 1); sec[cur][k.strip()] = v.strip()
    img = os.path.splitext(ccd)[0] + ".img"
    starts = {int(e["Point"], 0): int(e["PLBA"]) for name, e in sec.items()
              if name.startswith("Entry") and int(e["Point"], 0) <= 99}
    total = os.path.getsize(img) // 2352
    nums = sorted(starts); tracks = []
    for i, n in enumerate(nums):
        mode = sec.get(f"TRACK {n}", {}).get("MODE", "0")
        kind = {"0": "AUDIO", "1": "MODE1/2352", "2": "MODE2/2352"}[mode]
        end = starts[nums[i + 1]] if i + 1 < len(nums) else total
        tracks.append(Track(n, kind, img, starts[n], end, 2352))
    return tracks


def tracks(path):
    if path.lower().endswith(".ccd"): return parse_ccd(path)
    if path.lower().endswith(".cue"): return parse_cue(path)
    sys.exit(f"{path}: give the .cue or .ccd file of the image")


class DataTrack:
    """2048-byte user data of an ISO 9660 data track, by logical sector."""
    def __init__(self, t):
        self.f = open(t.path, "rb"); self.t = t
        self.skip = {"MODE1/2352": 16, "MODE2/2352": 24}.get(t.kind, 0)   # MODE2: CD-XA Form 1

    def read(self, lba, count=1):
        s = self.t.sector
        self.f.seek((self.t.start + lba) * s); raw = self.f.read(count * s)
        if s == 2048: return raw
        return b"".join(raw[i * s + self.skip:i * s + self.skip + 2048] for i in range(len(raw) // s))

    def label(self):
        pvd = self.read(16)
        if pvd[1:6] != b"CD001": sys.exit("the data track has no ISO 9660 file system (wrong image?)")
        return pvd[40:72].decode("ascii", "replace").strip()

    def joliet(self):
        """The Joliet supplementary volume descriptor (long, mixed-case names), or None."""
        for lba in range(17, 32):
            vd = self.read(lba)
            if vd[1:6] != b"CD001" or vd[0] == 255: return None
            if vd[0] == 2 and vd[88:91] in (b"%/@", b"%/C", b"%/E"): return vd
        return None

    def walk(self, joliet=False):
        """Yields (path with / separators, is_dir, lba, size), depth first. joliet: the names from the Joliet
        tree when the disc has one (what Windows shows), else the ISO 9660 ones (often upper-case 8.3)."""
        pvd = self.read(16); self.label()
        svd = self.joliet() if joliet else None
        if svd: pvd = svd
        def records(lba, size):
            data = self.read(lba, (size + 2047) // 2048)
            for s in range(0, len(data), 2048):
                o = s
                while o < s + 2048 and data[o]:
                    r = data[o:o + data[o]]; o += data[o]
                    name = r[33:33 + r[32]]
                    if name in (b"\x00", b"\x01"): continue
                    name = name.decode("utf-16-be") if svd else name.decode("ascii")
                    yield (name.split(";")[0].rstrip("."), bool(r[25] & 2),
                           struct.unpack_from("<I", r, 2)[0], struct.unpack_from("<I", r, 10)[0])
        def walk(lba, size, prefix):
            for name, is_dir, l, sz in records(lba, size):
                yield prefix + name, is_dir, l, sz
                if is_dir: yield from walk(l, sz, prefix + name + "/")
        root = pvd[156:190]
        yield from walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")

    def read_file(self, lba, size):
        return self.read(lba, (size + 2047) // 2048)[:size]

    def copy_file(self, lba, size, dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as o:
            left = size
            while left > 0:
                chunk = self.read(lba, min(512, (left + 2047) // 2048))
                o.write(chunk[:left]); left -= len(chunk); lba += 512

    def write_iso(self, dst):
        with open(dst, "wb") as o:
            for lba in range(0, self.t.end - self.t.start, 512):
                o.write(self.read(lba, min(512, self.t.end - self.t.start - lba)))


def audio(t):
    with open(t.path, "rb") as f:
        f.seek(t.start * 2352); return f.read((t.end - t.start) * 2352)
