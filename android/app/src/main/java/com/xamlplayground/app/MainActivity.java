package com.xamlplayground.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.webkit.ConsoleMessage;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class MainActivity extends Activity {

    private static final String TAG = "XamlPlayground";
    private static final String HOST = "appassets.androidplatform.net";
    private static final String ORIGIN = "https://" + HOST;
    private static final String ENTRY = ORIGIN + "/index.html";

    private static final int REQ_PICK = 1001;
    private static final long BACK_EXIT_WINDOW_MS = 2500L;
    private static final double POPUP_DIFF_THRESHOLD = 0.004d;

    /* 返回键：先给 Avalonia 派发 Escape 关弹层，用画布像素差判断是否真的关掉了弹层。
       只有「什么都没关掉」时才进入二次返回退出流程，避免误退。 */
    private static final String JS_SNAP =
            "(function(){try{var c=document.querySelector('.avalonia-canvas');"
                    + "if(!c){window.__b1=null;return 0}"
                    + "var d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;"
                    + "var n=Math.min(4096,Math.floor(d.length/199));"
                    + "var a=new Uint8Array(n);"
                    + "for(var i=0,j=0;j<n;i+=199,j++)a[j]=d[i];"
                    + "window.__b1=a;return n}catch(e){window.__b1=null;return 0}})()";

    private static final String JS_DIFF =
            "(function(){var b=window.__b1;if(!b)return 0;"
                    + "try{var c=document.querySelector('.avalonia-canvas');"
                    + "var d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;"
                    + "var n=Math.min(b.length,Math.floor(d.length/199));"
                    + "var x=0;"
                    + "for(var i=0,j=0;j<n;i+=199,j++)if(d[i]!==b[j])x++;"
                    + "return n?x/n:0}catch(e){return 0}})()";

    private static final String JS_ESCAPE =
            "(function(){var h=document.querySelector('.avalonia-container')||document.body;"
                    + "h.dispatchEvent(new KeyboardEvent('keydown',"
                    + "{key:'Escape',code:'Escape',keyCode:27,which:27,bubbles:true,cancelable:true}));"
                    + "return 1})()";

    private WebView web;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private long lastBackAt;
    private ValueCallback<Uri[]> fileCallback;
    private WebChromeClient.FileChooserParams fileParams;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // targetSdk 35+ 在 Android 15 上强制 edge-to-edge，会让界面顶到状态栏下面；关掉。
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(true);
        }

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(false);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setTextZoom(100);
        if (Build.VERSION.SDK_INT >= 26) {
            s.setSafeBrowsingEnabled(false);
        }

        web.setBackgroundColor(0xFFFFFFFF);
        web.setWebViewClient(new AppWebViewClient());
        web.setWebChromeClient(new AppChromeClient());
        web.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> {
            // 页面本身不下载文件；外部链接交给浏览器处理
            openExternally(url);
        });

        web.loadUrl(ENTRY);
    }

    /* ------------------------------------------------------------------ */
    /* 资源加载：站点全部打包在 assets/site，同源走本地，外部链接跳浏览器   */
    /* ------------------------------------------------------------------ */

    private final class AppWebViewClient extends WebViewClient {

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            Uri u = request.getUrl();
            if (u == null || !HOST.equals(u.getHost())) {
                return null; // 外部资源（Gist 等）走正常网络
            }
            String path = u.getPath();
            if (path == null || path.isEmpty() || "/".equals(path)) {
                path = "/index.html";
            }
            if (path.endsWith("/")) {
                path = path + "index.html";
            }
            return serveAsset("site" + path);
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            String host = request.getUrl().getHost();
            if (host == null || HOST.equals(host)) {
                return false;
            }
            openExternally(request.getUrl().toString());
            return true;
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request != null && request.isForMainFrame()) {
                Log.e(TAG, "main frame error: " + error.getDescription());
                Toast.makeText(MainActivity.this, "页面加载失败", Toast.LENGTH_SHORT).show();
            }
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            Log.i(TAG, "load " + url);
        }
    }

    private WebResourceResponse serveAsset(String assetPath) {
        try {
            InputStream in = getAssets().open(assetPath);
            String mime = mimeFor(assetPath);
            boolean text = mime.startsWith("text/")
                    || "application/javascript".equals(mime)
                    || "application/json".equals(mime)
                    || "image/svg+xml".equals(mime);
            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-store");
            headers.put("Access-Control-Allow-Origin", "*");
            return new WebResourceResponse(mime, text ? "UTF-8" : null, 200, "OK", headers, in);
        } catch (IOException e) {
            byte[] body = "404 Not Found".getBytes();
            return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found",
                    Collections.emptyMap(), new ByteArrayInputStream(body));
        }
    }

    private static String mimeFor(String path) {
        String p = path.toLowerCase();
        int dot = p.lastIndexOf('.');
        String ext = dot >= 0 ? p.substring(dot) : "";
        switch (ext) {
            case ".html":
            case ".htm":
                return "text/html";
            case ".js":
            case ".mjs":
                return "text/javascript";
            case ".css":
                return "text/css";
            case ".json":
            case ".map":
                return "application/json";
            case ".wasm":
                return "application/wasm";
            case ".ico":
                return "image/x-icon";
            case ".png":
                return "image/png";
            case ".jpg":
            case ".jpeg":
                return "image/jpeg";
            case ".svg":
                return "image/svg+xml";
            case ".ttf":
                return "font/ttf";
            case ".woff":
                return "font/woff";
            case ".woff2":
                return "font/woff2";
            default:
                return "application/octet-stream";
        }
    }

    private void openExternally(String url) {
        try {
            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        } catch (Exception e) {
            Log.w(TAG, "no handler for " + url);
        }
    }

    /* ------------------------------------------------------------------ */
    /* 文件选择：Avalonia 的打开对话框在 WebView 里走 <input type=file>   */
    /* ------------------------------------------------------------------ */

    private final class AppChromeClient extends WebChromeClient {

        @Override
        public boolean onShowFileChooser(WebView webView,
                                         ValueCallback<Uri[]> filePathCallback,
                                         FileChooserParams params) {
            if (fileCallback != null) {
                fileCallback.onReceiveValue(null);
            }
            fileCallback = filePathCallback;
            fileParams = params;
            try {
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                String[] types = params.getAcceptTypes();
                if (types != null && types.length > 0 && types[0] != null && !types[0].isEmpty()) {
                    i.putExtra(Intent.EXTRA_MIME_TYPES, types);
                }
                startActivityForResult(Intent.createChooser(i, "选择文件"), REQ_PICK);
                return true;
            } catch (Exception e) {
                Log.w(TAG, "file chooser failed", e);
                fileCallback = null;
                return false;
            }
        }

        @Override
        public boolean onConsoleMessage(ConsoleMessage m) {
            Log.d(TAG, m.messageLevel() + " " + m.sourceId() + ":" + m.lineNumber() + " " + m.message());
            return true;
        }

        @Override
        public Bitmap getDefaultVideoPoster() {
            return Bitmap.createBitmap(1, 1, Bitmap.Config.ARGB_8888);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_PICK) {
            Uri[] result = null;
            if (fileParams != null) {
                result = fileParams.parseResult(resultCode, data);
            } else if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                result = new Uri[]{data.getData()};
            }
            ValueCallback<Uri[]> cb = fileCallback;
            fileCallback = null;
            fileParams = null;
            if (cb != null) {
                cb.onReceiveValue(result);
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    /* ------------------------------------------------------------------ */
    /* 返回键                                                              */
    /* ------------------------------------------------------------------ */

    @Override
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        web.evaluateJavascript(JS_SNAP, v -> web.evaluateJavascript(JS_ESCAPE, v2 ->
                ui.postDelayed(() -> web.evaluateJavascript(JS_DIFF, r -> {
                    double diff = 0;
                    try {
                        diff = Double.parseDouble(r);
                    } catch (Exception ignored) {
                    }
                    if (diff > POPUP_DIFF_THRESHOLD) {
                        Toast.makeText(MainActivity.this, "已关闭面板", Toast.LENGTH_SHORT).show();
                    } else {
                        doubleBackExit();
                    }
                }), 300)));
    }

    private void doubleBackExit() {
        long now = System.currentTimeMillis();
        if (now - lastBackAt < BACK_EXIT_WINDOW_MS) {
            finish();
        } else {
            lastBackAt = now;
            Toast.makeText(this, "再按一次返回键退出", Toast.LENGTH_SHORT).show();
        }
    }

    /* ------------------------------------------------------------------ */

    @Override
    public void onLowMemory() {
        super.onLowMemory();
        if (web != null) {
            web.freeMemory();
        }
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            ViewParent parent = web.getParent();
            if (parent instanceof ViewGroup) {
                ((ViewGroup) parent).removeView(web);
            }
            web.stopLoading();
            web.setWebChromeClient(null);
            web.setWebViewClient(null);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
