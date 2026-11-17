"""Membuat icon.ico (rounded square biru-teal dengan dua panah) tanpa library tambahan."""
import struct
import zlib


def png(size):
    ss = 4  # supersampling

    def inside_arrow(u, v, y, right):
        if not right:
            u = 1 - u
        bar = 0.24 <= u <= 0.62 and abs(v - y) <= 0.05
        head = 0.58 <= u <= 0.80 and abs(v - y) <= 0.15 * (0.80 - u) / 0.22
        return bar or head

    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    u = (px + (sx + .5) / ss) / size
                    v = (py + (sy + .5) / ss) / size
                    r = 0.22
                    cx = min(max(u, r), 1 - r)
                    cy = min(max(v, r), 1 - r)
                    if (u - cx) ** 2 + (v - cy) ** 2 > r * r:
                        continue
                    t = (u + v) / 2
                    col = (int(47 + (22 - 47) * t), int(111 + (179 - 111) * t), int(237 + (165 - 237) * t))
                    if inside_arrow(u, v, 0.37, True) or inside_arrow(u, v, 0.63, False):
                        col = (255, 255, 255)
                    acc[0] += col[0]; acc[1] += col[1]; acc[2] += col[2]; acc[3] += 255
            n = ss * ss
            a = acc[3] // n
            if a:
                row += bytes([acc[0] * 255 // acc[3], acc[1] * 255 // acc[3], acc[2] * 255 // acc[3], a])
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [png(s) for s in sizes]
out = struct.pack("<HHH", 0, 1, len(sizes))
offset = 6 + 16 * len(sizes)
for s, d in zip(sizes, imgs):
    out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(d), offset)
    offset += len(d)
out += b"".join(imgs)
open("icon.ico", "wb").write(out)
open("icon-preview.png", "wb").write(imgs[-1])
print("icon.ico dibuat")
