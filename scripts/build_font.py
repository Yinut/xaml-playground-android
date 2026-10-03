#!/usr/bin/env python3
"""把 CJK 字形并入 Inter 各字重，并按原字节数等长回写到 WebCIL 里。"""
import os, sys, struct, importlib.util, shutil, tempfile

from fontTools.ttLib import TTFont, TTCollection
from fontTools import subset
from fontTools.ttLib.scaleUpem import scale_upem

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.environ.get('XPG_FONTS', os.path.join(tempfile.gettempdir(), 'xamlplayground-fonts'))

# Inter 各字重在 Avalonia.Fonts.Inter wasm 中的偏移与长度
INTER_SPEC = [
    (679, 316100),
    (316779, 310420),
    (627199, 314712),
    (941911, 309828),
    (1251739, 315756),
    (1567495, 310516),
]


def cjk_chars():
    spec = importlib.util.spec_from_file_location('patch_cn', os.path.join(HERE, 'patch_cn.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    chars = set()
    for new in m.PATCH.values():
        chars.update(new)
    return sorted(c for c in chars if ord(c) > 0x2000)


def latin_ranges():
    s = set()
    for a, b in [(0x0000, 0x024F), (0x02B0, 0x02FF), (0x0370, 0x03FF), (0x0400, 0x04FF),
                 (0x1E00, 0x1EFF), (0x2000, 0x206F), (0x20A0, 0x20CF), (0x2100, 0x214F),
                 (0x2190, 0x21FF), (0x2200, 0x22FF), (0x25A0, 0x25FF), (0x2600, 0x26FF),
                 (0x2700, 0x27BF), (0xFB00, 0xFB06), (0xFE00, 0xFE0F)]:
        s.update(range(a, b + 1))
    return sorted(s)


def sub_opts():
    o = subset.Options()
    o.layout_features = ['*']
    o.name_IDs = ['*']
    o.name_legacy = True
    o.notdef_outline = True
    o.drop_tables = ['FFTM', 'STAT']
    o.recommended_glyphs = False
    o.glyph_names = True
    return o


def build_cjk_source(upem):
    path = os.path.join(FONTS, 'wqy_src.ttf')
    if not os.path.exists(path):
        coll = TTCollection('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc')
        f = coll.fonts[0]
        s = subset.Subsetter(options=sub_opts())
        s.populate(text=''.join(cjk_chars()))
        s.subset(f)
        if f['head'].unitsPerEm != upem:
            scale_upem(f, upem)
        f.save(path)
    return path


def merge_into(inter_path, out_path, cjk_path):
    inter = TTFont(inter_path)
    wqy = TTFont(cjk_path)
    glyf = inter['glyf']
    hmtx = inter['hmtx']
    order = list(inter.getGlyphOrder())
    worder = list(wqy.getGlyphOrder())
    existing = set(order)
    mapping = {}
    for g in worder:
        if g == '.notdef':
            continue
        new = g + ' cjk'
        while new in existing:
            new += '_'
        existing.add(new)
        mapping[g] = new
    for g in worder:
        if g == '.notdef':
            continue
        gl = wqy['glyf'][g]
        if gl.isComposite():
            for c in gl.components:
                if c.glyphName in mapping:
                    c.glyphName = mapping[c.glyphName]
        glyf.glyphs[mapping[g]] = gl
        hmtx.metrics[mapping[g]] = wqy['hmtx'].metrics[g]
    order.extend(mapping[g] for g in worder if g != '.notdef')
    inter.setGlyphOrder(order)
    inter['maxp'].numGlyphs = len(order)

    wmap = {}
    wcm = wqy.getBestCmap()
    for cp, g in wcm.items():
        if g in mapping:
            wmap[cp] = mapping[g]
    cmap = inter['cmap']
    touched = 0
    for st in cmap.tables:
        if st.format in (4, 12) and (st.platformID == 3 and st.platEncID in (1, 10)):
            st.cmap.update(wmap)
            touched += 1
    if touched == 0:
        for st in cmap.tables:
            if st.format in (4, 12):
                st.cmap.update(wmap)
                touched += 1
    if touched == 0:
        raise SystemExit('no unicode cmap subtable found')

    inter['post'].formatType = 3.0
    try:
        os2 = inter['OS/2']
        os2.usFirstCharIndex = 0x20
        os2.usLastCharIndex = 0xFFFD
    except Exception:
        pass
    inter.save(out_path)
    return out_path


def find_fonts(data):
    import struct as _s
    out = []
    for o in range(0, len(data) - 12):
        if data[o:o + 4] != b'\x00\x01\x00\x00':
            continue
        nt = _s.unpack_from('>H', data, o + 4)[0]
        if not (4 <= nt <= 60):
            continue
        ok = True
        last = 0
        for t in range(nt):
            p = o + 12 + t * 16
            if p + 16 > len(data):
                ok = False
                break
            tag = data[p:p + 4]
            if not all(32 <= c < 127 for c in tag):
                ok = False
                break
            off, ln = _s.unpack_from('>II', data, p + 8)
            if off < 12 or o + off + ln > len(data):
                ok = False
                break
            last = max(last, off + ln)
        if ok and 20000 < last < 3000000:
            out.append((o, last))
    return out


def main():
    wasm = sys.argv[1]
    os.makedirs(FONTS, exist_ok=True)
    d = bytearray(open(wasm, 'rb').read())
    orig = bytes(d)
    specs = find_fonts(orig)
    if not specs:
        raise SystemExit('no fonts found in ' + wasm)
    print('fonts found:', specs)
    cjk_path = build_cjk_source(2816)
    for i, (off, size) in enumerate(specs):
        blob = orig[off:off + size]
        if len(blob) != size:
            raise SystemExit('bad slice')
        tag = f'{off}_{size}'
        raw_in = os.path.join(FONTS, f'font_{tag}.ttf')
        open(raw_in, 'wb').write(blob)
        sub_in = os.path.join(FONTS, f'font_{tag}_sub.ttf')
        if not os.path.exists(sub_in):
            f = TTFont(raw_in)
            s = subset.Subsetter(options=sub_opts())
            s.populate(unicodes=latin_ranges())
            s.subset(f)
            f.save(sub_in)
        out = os.path.join(FONTS, f'font_{tag}_final.ttf')
        merge_into(sub_in, out, cjk_path)
        data = open(out, 'rb').read()
        if len(data) > size:
            raise SystemExit(f'inter{i}: {len(data)} > {size} (需进一步精简)')
        padded = data + b'\x00' * (size - len(data))
        d[off:off + size] = padded
        print(f'inter{i}: {len(data)} / {size} bytes  padding={size-len(data)}')

    backup = wasm + '.fontorig'
    if not os.path.exists(backup):
        shutil.copyfile(wasm, backup)
    open(wasm, 'wb').write(bytes(d))
    print('wrote(inter)', wasm, 'size', len(d))

    # RobotoMono（编辑器字体）：只加少量 CJK，同样等长回写
    if not specs:
        return
    mono_off, mono_size = specs[-1]
    if mono_size > 200000:
        print('skip large font', mono_size)
        return
    mono_raw = os.path.join(FONTS, os.path.basename(wasm) + '.mono.ttf')
    if not os.path.exists(mono_raw):
        open(mono_raw, 'wb').write(orig[mono_off:mono_off + mono_size])
    mt = TTFont(mono_raw)
    upem = mt['head'].unitsPerEm
    mono_cjk = os.path.join(FONTS, f'wqy_mono_{upem}.ttf')
    if not os.path.exists(mono_cjk):
        coll = TTCollection('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc')
        f = coll.fonts[0]
        s = subset.Subsetter(options=sub_opts())
        s.populate(text=''.join(cjk_chars()))
        s.subset(f)
        if f['head'].unitsPerEm != upem:
            scale_upem(f, upem)
        f.save(mono_cjk)
    mono_sub = os.path.join(FONTS, f'mono_{mono_off}_{mono_size}_sub.ttf')
    if not os.path.exists(mono_sub):
        f = TTFont(mono_raw)
        s = subset.Subsetter(options=sub_opts())
        s.populate(unicodes=latin_ranges())
        s.subset(f)
        f.save(mono_sub)
    mono_out = os.path.join(FONTS, f'mono_{mono_off}_{mono_size}_final.ttf')
    merge_into(mono_sub, mono_out, mono_cjk)
    mdata = open(mono_out, 'rb').read()
    if len(mdata) > mono_size:
        raise SystemExit(f'roboto: {len(mdata)} > {mono_size}')
    d[mono_off:mono_off + mono_size] = mdata + b'\x00' * (mono_size - len(mdata))
    print(f'roboto: {len(mdata)} / {mono_size} bytes padding={mono_size-len(mdata)}')

    backup = wasm + '.fontorig'
    if not os.path.exists(backup):
        shutil.copyfile(wasm, backup)
    open(wasm, 'wb').write(bytes(d))
    print('wrote', wasm, 'size', len(d))


if __name__ == '__main__':
    main()
