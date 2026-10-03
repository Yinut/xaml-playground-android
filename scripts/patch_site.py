#!/usr/bin/env python3
"""对发布的 XamlPlayground 站点打移动端适配补丁（幂等，可重复执行）。

用法:  patch_site.py <站点目录>          例如 patch_site.py dist/site

做了三件事：
  1. index.html  加 theme-color，并注入「最小逻辑宽度 520px」的视口/缩放脚本
                 （HeaderView 的 Gist/Settings 按钮需要 >=512px，汉化后更宽），
                 同时拦截浏览器的双指缩放/双击/长按菜单手势。
  2. app.css     追加触摸与软键盘适配（overscroll-behavior、touch-action、
                 #out 固定到布局视口等）。
  3. _framework/avalonia.js  把 isMobile() 改成恒为 false，强制走桌面布局。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OV = os.path.join(HERE, 'site_overrides')
LINK_LINE = '    <link rel="stylesheet" href="./app.css" />'


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def ov(name):
    return read(os.path.join(OV, name))


def patch_index(site):
    path = os.path.join(site, 'index.html')
    s = read(path)
    if 'name="theme-color"' in s:
        print('index.html: 已打过补丁，跳过')
        return
    extra = ov('index_head_extra.html').rstrip('\n')
    if LINK_LINE not in s:
        raise SystemExit('index.html: 找不到样式表引用，上游页面结构可能变了')
    s = s.replace(LINK_LINE, extra, 1)
    write(path, s)
    print('index.html: 已注入视口/手势脚本')


def patch_css(site):
    path = os.path.join(site, 'app.css')
    raw = read(path)
    bom = raw.startswith('﻿')
    s = raw.lstrip('﻿')
    if '手机/触屏适配' in s:
        print('app.css: 已打过补丁，跳过')
        return
    write(path, ('﻿' if bom else '') + ov('touch.css') + '\n' + s)
    print('app.css: 已追加触摸/软键盘适配')


def patch_runtime(site):
    path = os.path.join(site, '_framework', 'avalonia.js')
    if not os.path.exists(path):
        print('avalonia.js: 不存在，跳过')
        return
    s = read(path)
    if 'static isMobile(){return!1}' in s:
        print('avalonia.js: 已打过补丁，跳过')
        return
    new, n = re.subn(r'static isMobile\(\)\{.*?\}static isTv',
                     'static isMobile(){return!1}static isTv', s, count=1, flags=re.S)
    if n != 1:
        raise SystemExit('avalonia.js: 没匹配到 isMobile()，上游实现可能变了')
    write(path, new)
    print('avalonia.js: isMobile() -> false')


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    site = sys.argv[1]
    if not os.path.isdir(site):
        raise SystemExit('站点目录不存在: ' + site)
    patch_index(site)
    patch_css(site)
    patch_runtime(site)


if __name__ == '__main__':
    main()
