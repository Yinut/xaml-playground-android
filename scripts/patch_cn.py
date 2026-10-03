#!/usr/bin/env python3
"""等长替换 WebCIL 程序集 #US 堆里的用户可见文案（UTF-16LE，码元数必须一致）。"""
import struct, sys, shutil

PATCH = {
    'Samples': '示例',
    'Avalonia Play': 'Avalonia 演练场',
    'File': '文件',
    'Open Xaml...': '打开 Xaml...',
    'Save Xaml As...': '另存为 Xaml...',
    'Open Code...': '打开 Code...',
    'Save Code As...': '另存为 Code...',
    'Run': '运行',
    'The GitHub gist must contain file named Main.axaml':
        'GitHub Gist 必须包含名为 Main.axaml 的文件',
    'Get': '获取',
    'Id:': '编号:',
    'Settings': '设置',
    'Live Preview': '实时预览',
    'Font size:': '字号:',
    'Font size': '字号',
    'Avalonia Xaml Playground': 'Avalonia Xaml 演练场',
    'Open code': '打开代码',
    'Open xaml': '打开 Xaml',
    'Failed to compile code.': '代码编译失败。',
    'Save code': '保存代码',
    'Save xaml': '保存 Xaml',
}


def us_entries(d):
    md = d.find(b'BSJB')
    verlen = struct.unpack_from('<I', d, md + 12)[0]
    p = md + 16 + verlen
    p = (p + 3) & ~3
    nstreams = struct.unpack_from('<H', d, p + 2)[0]
    p += 4
    streams = {}
    for _ in range(nstreams):
        off = struct.unpack_from('<I', d, p)[0]
        sz = struct.unpack_from('<I', d, p + 4)[0]
        p += 8
        name = b''
        while d[p] != 0:
            name += bytes([d[p]])
            p += 1
        p += 1
        p = (p + 3) & ~3
        streams[name.decode(errors='replace')] = (md + off, sz)
    us_off, us_sz = streams['#US']
    heap = d[us_off:us_off + us_sz]
    i = 1
    out = []
    while i < us_sz:
        b0 = heap[i]
        if b0 == 0:
            i += 1
            continue
        if (b0 & 0x80) == 0:
            ln, pre = b0, 1
            i += 1
        elif (b0 & 0xC0) == 0x80:
            ln, pre = ((b0 & 0x3F) << 8) | heap[i + 1], 2
            i += 2
        else:
            ln = ((b0 & 0x1F) << 24) | (heap[i + 1] << 16) | (heap[i + 2] << 8) | heap[i + 3]
            pre = 4
            i += 4
        data_off = i
        raw = heap[i:i + ln]
        i += ln
        if ln >= 2:
            try:
                s = raw[:-1].decode('utf-16-le')
            except Exception:
                s = None
            if s is not None:
                out.append((us_off + data_off, len(raw[:-1]) // 2, s))
    return out


def main(path, dry=False):
    d = bytearray(open(path, 'rb').read())
    entries = us_entries(bytes(d))
    by_text = {}
    for off, chars, s in entries:
        by_text.setdefault(s, []).append((off, chars))
    done, missing, ambiguous = [], [], []
    for old, new in PATCH.items():
        hits = by_text.get(old)
        if not hits:
            missing.append(old)
            continue
        if len(hits) > 1:
            ambiguous.append((old, len(hits)))
            continue
        off, chars = hits[0]
        if len(new) > chars:
            print('TOO LONG', old, '->', new, len(new), '>', chars)
            sys.exit(1)
        padded = new + ' ' * (chars - len(new))
        enc = padded.encode('utf-16-le')
        assert len(enc) // 2 == chars, (old, len(enc) // 2, chars)
        if not dry:
            d[off:off + len(enc)] = enc
        done.append((old, padded, chars))
    print(f'patched {len(done)} / target {len(PATCH)}')
    for old, new, c in done:
        print(f'  [{c:3d}] {old!r} -> {new!r}')
    if missing:
        print('MISSING:', missing)
    if ambiguous:
        print('AMBIGUOUS:', ambiguous)
    if not dry:
        import os
        if not os.path.exists(path + '.orig'):
            shutil.copyfile(path, path + '.orig')
        open(path, 'wb').write(bytes(d))
        # 复核
        entries2 = us_entries(open(path, 'rb').read())
        assert len(entries2) == len(entries), 'count changed'
        for (o1, c1, s1), (o2, c2, s2) in zip(entries, entries2):
            assert o1 == o2 and c1 == c2, (o1, o2, c1, c2)
        print('verified: offsets and code-unit counts unchanged')


if __name__ == '__main__':
    main(sys.argv[1], dry='--dry' in sys.argv)
