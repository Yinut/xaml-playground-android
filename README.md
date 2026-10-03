# XamlPlayground · Avalonia XAML 演练场（Android 版）

在手机上运行的 Avalonia XAML 演练场：把上游 [AvaloniaUI/XamlPlayground](https://github.com/AvaloniaUI/XamlPlayground)
编译成 WebAssembly，外面套一层 Android WebView 壳打包成 APK，并补上中文化、中文字形和移动端触屏适配。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 上游 XamlPlayground 源码（.NET / 浏览器 WASM），原样保留，见 `src/README.md` |
| `android/` | Android WebView 壳工程（`com.xamlplayground.app`，应用名「Avalonia 演练场」） |
| `scripts/` | 站点补丁脚本（视口/触摸/汉化/字体）与本地静态服务器 |
| `LICENSE.md` | MIT，上游版权归 Wiesław Šoltés |

## 构建

### 1. 生成站点

需要 .NET 10 SDK：

```bash
dotnet publish src/XamlPlayground.Browser -c Release -o dist/site
```

Release 配置会开启 AOT，首次构建较慢。也可以直接用上游已部署的站点文件作为起点。

### 2. 打补丁

```bash
python3 scripts/patch_site.py dist/site
python3 scripts/patch_cn.py dist/site/_framework/XamlPlayground.*.wasm
python3 scripts/build_font.py dist/site/_framework/Avalonia.Fonts.Inter.*.wasm   # 可选
```

- `patch_site.py`：`index.html` 注入最小逻辑宽度 520px 的视口/缩放脚本和手势拦截；
  `app.css` 追加触摸、软键盘适配；`_framework/avalonia.js` 把 `isMobile()` 改成恒 `false`，强制桌面布局。
- `patch_cn.py`：等长改写 WebCIL 程序集 `#US` 堆里的界面文案（UTF-16LE），元数据偏移与码元数不变，
  打完可用 `--dry` 先预览。
- `build_font.py`：把 CJK 字形并入 Inter 各字重并按原字节长度回写。依赖 `fontTools`（`pip install fonttools`）
  和系统里的文泉驿微米黑（`/usr/share/fonts/truetype/wqy/wqy-microhei.ttc`，GPL + 字体嵌入例外，
  分发打包产物前请自行确认许可）；中间字体缓存目录默认在临时目录，可用 `XPG_FONTS` 覆盖。

### 3. 打包 Android

```bash
mkdir -p android/app/src/main/assets/site
cp -r dist/site/* android/app/src/main/assets/site/
cd android && ./gradlew assembleDebug
# 产物：android/app/build/outputs/apk/debug/app-debug.apk
```

- `assets/site` 是构建产物，已 gitignore（目录里留了说明）。
- aarch64 Linux 上 Maven 下发的 aapt2 是 x86_64，需要在 `android/gradle.properties` 里打开
  `android.aapt2FromMavenOverride` 指向本地 arm64 aapt2（仓库里默认注释掉）。
- Gradle 与 Maven 仓库默认走国内镜像（华为云 / 阿里云），可按需改回官方源。

### 本地预览

```bash
python3 scripts/serve.py dist/site 8099
```

## 壳工程做了什么

`android/` 是一个只有 WebView 的薄壳，站点全部打包进 `assets/site`，通过
`https://appassets.androidplatform.net` 同源拦截本地资源：

- 外部链接（Gist 等）跳系统浏览器，页面内不下载文件；
- 文件选择走 `ACTION_GET_CONTENT`，喂给 Avalonia 的打开对话框；
- 返回键先把 Escape 派发给 Avalonia 关掉弹层（用画布像素差判断是否真的关掉了），
  没关掉任何东西时才进入「再按一次退出」流程；
- 关闭 WebView 自带的双指缩放/双击/长按菜单，交给 Avalonia 自己处理。

## 上游与许可

上游 [AvaloniaUI/XamlPlayground](https://github.com/AvaloniaUI/XamlPlayground) 以 MIT 发布，
版权见 `LICENSE.md`。本仓库新增的 `android/`、`scripts/` 与本文档同样以 MIT 提供。
