package com.brechorisee.admin;

import android.Manifest;
import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Build;
import android.os.Environment;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.ViewGroup;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebChromeClient.FileChooserParams;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.EditText;
import android.text.InputType;
import android.provider.MediaStore;
import android.provider.Settings;
import android.widget.FrameLayout;
import android.content.ClipData;
import android.util.Log;
import android.widget.Toast;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;

import java.io.File;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final String DEFAULT_URL = "http://100.121.45.12:8000/admin-acesso";
    private static final String DEFAULT_ROOT = "http://100.121.45.12:8000";
    private static final String PREFS = "brechorisee_prefs";
    private static final String KEY_URL = "server_url";
    private static final int FILE_CHOOSER_REQUEST = 8307;
    private static final int PERMISSION_REQUEST = 8308;

    private WebView webView;
    private LinearLayout offlineView;
    private SharedPreferences prefs;
    private Handler handler = new Handler(Looper.getMainLooper());
    private FrameLayout rootLayout;
    private Button assistantButton;

    private ValueCallback<Uri[]> filePathCallback;
    private Uri cameraPhotoUri;
    private PermissionRequest pendingWebPermissionRequest;
    private static final String KEY_PENDING_ASSISTANT = "pending_instagram_assistant";
    private static final String KEY_PENDING_INSTAGRAM_URI = "pending_instagram_uri";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        try {
            requestBasicPermissions();
            setupWebView();
            if (!handleIntent(getIntent())) {
                loadHome();
            }
        } catch (Throwable ex) {
            showSafeStartupError(ex);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    private void requestBasicPermissions() {
        if (Build.VERSION.SDK_INT >= 23) {
            java.util.ArrayList<String> permissions = new java.util.ArrayList<>();
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.CAMERA);
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.RECORD_AUDIO);
            }
            if (Build.VERSION.SDK_INT >= 33) {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_IMAGES) != PackageManager.PERMISSION_GRANTED) {
                    permissions.add(Manifest.permission.READ_MEDIA_IMAGES);
                }
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_VIDEO) != PackageManager.PERMISSION_GRANTED) {
                    permissions.add(Manifest.permission.READ_MEDIA_VIDEO);
                }
            } else {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                    permissions.add(Manifest.permission.READ_EXTERNAL_STORAGE);
                }
            }
            if (!permissions.isEmpty()) {
                ActivityCompat.requestPermissions(this, permissions.toArray(new String[0]), PERMISSION_REQUEST);
            }
        }
    }

    private void setupWebView() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT
                && (getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }
        webView = new WebView(this);
        webView.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setTextZoom(100);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        if (Build.VERSION.SDK_INT >= 21) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }
        try {
            settings.setUserAgentString(settings.getUserAgentString() + " BRECHORISEE-Android-Admin");
            CookieManager cookieManager = CookieManager.getInstance();
            cookieManager.setAcceptCookie(true);
            if (Build.VERSION.SDK_INT >= 21) {
                cookieManager.setAcceptThirdPartyCookies(webView, true);
            }
        } catch (Exception ignored) {}

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> handleWebPermissionRequest(request));
            }

            @Override
            public void onPermissionRequestCanceled(final PermissionRequest request) {
                if (pendingWebPermissionRequest == request) {
                    pendingWebPermissionRequest = null;
                }
            }

            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (MainActivity.this.filePathCallback != null) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                }
                MainActivity.this.filePathCallback = filePathCallback;
                cameraPhotoUri = null;

                Intent contentIntent = new Intent(Intent.ACTION_GET_CONTENT);
                contentIntent.addCategory(Intent.CATEGORY_OPENABLE);
                contentIntent.setType("*/*");

                String[] acceptTypes = fileChooserParams != null ? fileChooserParams.getAcceptTypes() : null;
                java.util.ArrayList<String> mimeList = new java.util.ArrayList<>();
                if (acceptTypes != null) {
                    for (String accept : acceptTypes) {
                        if (accept != null && accept.trim().length() > 0 && !accept.equals("*/*")) {
                            mimeList.add(accept.trim());
                        }
                    }
                }
                if (mimeList.isEmpty()) {
                    mimeList.add("image/*");
                    mimeList.add("video/*");
                }
                contentIntent.putExtra(Intent.EXTRA_MIME_TYPES, mimeList.toArray(new String[0]));

                boolean allowMultiple = fileChooserParams != null && fileChooserParams.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE;
                contentIntent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, allowMultiple);

                java.util.ArrayList<Intent> initialIntents = new java.util.ArrayList<>();

                try {
                    Intent cameraIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    File photoFile = createImageFile();
                    cameraPhotoUri = FileProvider.getUriForFile(MainActivity.this, getPackageName() + ".fileprovider", photoFile);
                    cameraIntent.putExtra(MediaStore.EXTRA_OUTPUT, cameraPhotoUri);
                    cameraIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                    initialIntents.add(cameraIntent);
                } catch (Exception ignored) {}

                try {
                    Intent videoIntent = new Intent(MediaStore.ACTION_VIDEO_CAPTURE);
                    videoIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                    initialIntents.add(videoIntent);
                } catch (Exception ignored) {}

                Intent chooserIntent = Intent.createChooser(contentIntent, "Selecionar foto ou vídeo");
                if (!initialIntents.isEmpty()) {
                    chooserIntent.putExtra(Intent.EXTRA_INITIAL_INTENTS, initialIntents.toArray(new Intent[0]));
                }

                try {
                    startActivityForResult(chooserIntent, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (Exception e) {
                    MainActivity.this.filePathCallback = null;
                    return false;
                }
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
                if (scheme.equals("http") || scheme.equals("https")) {
                    if (isInstagramUri(uri)) {
                        openInstagramApp(uri);
                        return true;
                    }
                    if (isPublicStorePath(uri)) {
                        view.loadUrl(adminUrlForPublicStore(uri));
                        return true;
                    }
                    return false;
                }
                if (isInstagramUri(uri)) {
                    openInstagramApp(uri);
                    return true;
                }
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW, uri);
                    startActivity(intent);
                } catch (Exception ignored) {}
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                updateAssistantButtonVisibility(url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                updateAssistantButtonVisibility(url);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showOfflineScreen();
                    updateAssistantButtonVisibility(null);
                }
            }
        });

        rootLayout = new FrameLayout(this);
        rootLayout.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));
        assistantButton = new Button(this);
        final Button assistant = assistantButton;
        assistant.setText("Instagram");
        assistant.setAllCaps(false);
        assistant.setTextSize(11);
        assistant.setAlpha(0.92f);
        assistant.setVisibility(View.GONE);
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP | Gravity.LEFT
        );
        params.leftMargin = prefs.getInt("assistant_btn_x", 18);
        params.topMargin = prefs.getInt("assistant_btn_y", Math.max(80, getResources().getDisplayMetrics().heightPixels - 170));
        rootLayout.addView(assistant, params);
        assistant.setOnClickListener(v -> startInstagramAssistant(null));
        assistant.setOnTouchListener(new View.OnTouchListener() {
            private int startLeft;
            private int startTop;
            private float downX;
            private float downY;
            private boolean moved;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        startLeft = params.leftMargin;
                        startTop = params.topMargin;
                        downX = event.getRawX();
                        downY = event.getRawY();
                        moved = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        int dx = Math.round(event.getRawX() - downX);
                        int dy = Math.round(event.getRawY() - downY);
                        if (Math.abs(dx) > 8 || Math.abs(dy) > 8) moved = true;
                        params.leftMargin = Math.max(0, startLeft + dx);
                        params.topMargin = Math.max(0, startTop + dy);
                        rootLayout.updateViewLayout(assistant, params);
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        prefs.edit()
                                .putInt("assistant_btn_x", params.leftMargin)
                                .putInt("assistant_btn_y", params.topMargin)
                                .apply();
                        if (!moved) v.performClick();
                        return true;
                }
                return false;
            }
        });
        setContentView(rootLayout);
    }

    private void updateAssistantButtonVisibility(String currentUrl) {
        if (assistantButton == null) return;
        final boolean visible = shouldShowAssistantShortcut(currentUrl);
        assistantButton.post(() -> assistantButton.setVisibility(visible ? View.VISIBLE : View.GONE));
    }

    private boolean shouldShowAssistantShortcut(String currentUrl) {
        String value = currentUrl == null ? "" : currentUrl.trim().toLowerCase(Locale.US);
        if (value.isEmpty() && webView != null && webView.getUrl() != null) {
            value = webView.getUrl().trim().toLowerCase(Locale.US);
        }
        if (value.isEmpty()) return false;

        // O atalho é apenas para abrir o assistente no Instagram. Ele não deve
        // ficar por cima da vitrine, área da cliente, formulários, cadastro de
        // peças, seletor de fotos ou páginas de relatório.
        if (value.contains("/cliente")
                || value.contains("/loja")
                || value.contains("/vitrine")
                || value.contains("/online")
                || value.contains("/site")
                || value.contains("/products")
                || value.contains("/caderno")
                || value.contains("/usuarios")
                || value.contains("/loja-admin")
                || value.contains("/entregas")
                || value.contains("/gestao")
                || value.contains("/config")
                || value.contains("/settings")
                || value.contains("/cashier")
                || value.contains("/ai")) {
            return false;
        }
        return value.contains("/admin-acesso")
                || value.contains("/instagram")
                || value.contains("/live");
    }

    private void startInstagramAssistant(String instagramUri) {
        try {
            String target = (instagramUri == null || instagramUri.trim().isEmpty()) ? "instagram://app" : instagramUri.trim();

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
                prefs.edit()
                        .putBoolean(KEY_PENDING_ASSISTANT, true)
                        .putString(KEY_PENDING_INSTAGRAM_URI, target)
                        .apply();
                Toast.makeText(this, "Ative Sobrepor a outros apps. Ao voltar, vou abrir o Instagram com o Assistente por cima.", Toast.LENGTH_LONG).show();
                Intent perm = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
                startActivity(perm);
                return;
            }

            Intent serviceIntent = new Intent(this, InstagramAssistantOverlayService.class);
            serviceIntent.putExtra("base_url", getBaseUrl());
            serviceIntent.putExtra("target_instagram_uri", target);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }

            Intent capture = new Intent(this, ScreenCapturePermissionActivity.class);
            capture.putExtra("base_url", getBaseUrl());
            capture.putExtra("open_instagram_after", true);
            capture.putExtra("target_instagram_uri", target);
            startActivity(capture);
        } catch (Exception ex) {
            Toast.makeText(this, "Não foi possível abrir o Instagram com Assistente: " + ex.getMessage(), Toast.LENGTH_LONG).show();
        }
    }



    private String ensureSchemeForServer(String raw) {
        String url = raw == null ? "" : raw.trim();
        if (url.length() == 0) url = DEFAULT_ROOT;
        if (url.startsWith("http://") || url.startsWith("https://")) return url;
        String lower = url.toLowerCase(Locale.US);
        if (lower.startsWith("192.") || lower.startsWith("10.") || lower.startsWith("172.") || lower.startsWith("127.")
                || lower.startsWith("localhost") || lower.matches("^\\d+\\.\\d+\\.\\d+\\.\\d+.*")) {
            return "http://" + url;
        }
        return "https://" + url;
    }

    private String normalizeServerRoot(String raw) {
        String url = ensureSchemeForServer(raw).replaceAll("/+$", "");
        String lower = url.toLowerCase(Locale.US);
        if (lower.endsWith("/admin-acesso")) return url.substring(0, url.length() - "/admin-acesso".length());
        if (lower.endsWith("/admin")) return url.substring(0, url.length() - "/admin".length());
        if (lower.endsWith("/app/cliente")) return url.substring(0, url.length() - "/app/cliente".length());
        return url;
    }

    private String getBaseUrl() {
        String base = prefs.getString(KEY_URL, DEFAULT_URL);
        if (base == null || base.trim().isEmpty()) base = DEFAULT_URL;
        String root = normalizeServerRoot(base);
        return root + "/admin-acesso";
    }

    private void handleWebPermissionRequest(final PermissionRequest request) {
        if (request == null) return;
        if (Build.VERSION.SDK_INT < 23) {
            request.grant(request.getResources());
            return;
        }

        java.util.ArrayList<String> missing = new java.util.ArrayList<>();
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)
                    && ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                if (!missing.contains(Manifest.permission.CAMERA)) missing.add(Manifest.permission.CAMERA);
            }
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)
                    && ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                if (!missing.contains(Manifest.permission.RECORD_AUDIO)) missing.add(Manifest.permission.RECORD_AUDIO);
            }
        }

        if (!missing.isEmpty()) {
            pendingWebPermissionRequest = request;
            ActivityCompat.requestPermissions(this, missing.toArray(new String[0]), PERMISSION_REQUEST);
            return;
        }

        try {
            request.grant(request.getResources());
        } catch (Exception e) {
            Log.e("BRECHORISEE", "Falha ao liberar câmera/microfone no WebView", e);
            try { request.deny(); } catch (Exception ignored) {}
        }
    }

    private boolean canGrantPendingWebPermission(PermissionRequest request) {
        if (request == null) return false;
        if (Build.VERSION.SDK_INT < 23) return true;
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)
                    && ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                return false;
            }
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)
                    && ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                return false;
            }
        }
        return true;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != PERMISSION_REQUEST) return;

        if (pendingWebPermissionRequest != null) {
            PermissionRequest request = pendingWebPermissionRequest;
            pendingWebPermissionRequest = null;
            if (canGrantPendingWebPermission(request)) {
                try {
                    request.grant(request.getResources());
                    Toast.makeText(this, "Câmera liberada para a live.", Toast.LENGTH_SHORT).show();
                } catch (Exception e) {
                    Log.e("BRECHORISEE", "Erro ao conceder permissão do WebView", e);
                    try { request.deny(); } catch (Exception ignored) {}
                }
            } else {
                try { request.deny(); } catch (Exception ignored) {}
                Toast.makeText(this, "Permita câmera e microfone para abrir o Studio da Live.", Toast.LENGTH_LONG).show();
            }
        }
    }

    private File createImageFile() throws IOException {
        String timeStamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
        File storageDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
        if (storageDir != null && !storageDir.exists()) {
            storageDir.mkdirs();
        }
        return File.createTempFile("BRECHORISEE_" + timeStamp + "_", ".jpg", storageDir);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER_REQUEST) return;

        if (filePathCallback == null) return;

        Uri[] results = null;
        if (resultCode == Activity.RESULT_OK) {
            java.util.ArrayList<Uri> uris = new java.util.ArrayList<>();

            if (data != null) {
                ClipData clipData = data.getClipData();
                if (clipData != null) {
                    for (int i = 0; i < clipData.getItemCount(); i++) {
                        Uri uri = clipData.getItemAt(i).getUri();
                        if (uri != null) uris.add(uri);
                    }
                } else if (data.getData() != null) {
                    uris.add(data.getData());
                }
            }

            if (uris.isEmpty() && cameraPhotoUri != null) {
                uris.add(cameraPhotoUri);
            }

            if (!uris.isEmpty()) {
                results = uris.toArray(new Uri[0]);
            }
        }

        filePathCallback.onReceiveValue(results);
        filePathCallback = null;
        cameraPhotoUri = null;
    }
    private void setBaseUrl(String url) {
        if (url == null || url.trim().isEmpty()) url = DEFAULT_ROOT;
        String root = normalizeServerRoot(url);
        prefs.edit().putString(KEY_URL, root + "/admin-acesso").apply();
    }

    private void loadHome() {
        String url = getBaseUrl();
        webView.setVisibility(View.VISIBLE);
        webView.loadUrl(url);
    }

    private String getServerRoot() {
        String url = getBaseUrl();
        int schemeEnd = url.indexOf("://");
        if (schemeEnd >= 0) {
            int slash = url.indexOf("/", schemeEnd + 3);
            if (slash > 0) return url.substring(0, slash);
        }
        return url.replaceAll("/+$", "").replaceAll("/admin-acesso/?$", "");
    }


    private boolean isInstagramUri(Uri uri) {
        if (uri == null) return false;
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.US);
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.US);
        return scheme.equals("instagram")
                || host.equals("instagram.com")
                || host.equals("www.instagram.com")
                || host.endsWith(".instagram.com");
    }

    private boolean openInstagramApp(Uri uri) {
        Uri target = uri;
        if (target == null || !isInstagramUri(target)) {
            target = Uri.parse("instagram://app");
        }
        startInstagramAssistant(target.toString());
        return true;
    }

    private boolean isPublicStorePath(Uri uri) {
        if (uri == null) return false;
        String path = uri.getPath() == null ? "" : uri.getPath().toLowerCase(Locale.US);
        return path.equals("/loja")
                || path.startsWith("/loja/")
                || path.startsWith("/vitrine/")
                || path.startsWith("/cliente/vitrine")
                || path.startsWith("/cliente/peca");
    }

    private String adminUrlForPublicStore(Uri uri) {
        String root = getServerRoot();
        String path = uri.getPath() == null ? "" : uri.getPath();
        if (path.startsWith("/cliente/peca/")) {
            String code = path.substring("/cliente/peca/".length());
            return root + "/products?q=" + code;
        }
        if (path.startsWith("/vitrine/peca/")) {
            String code = path.substring("/vitrine/peca/".length());
            int slash = code.indexOf("/");
            if (slash >= 0) code = code.substring(0, slash);
            return root + "/products?q=" + code;
        }
        return root + "/loja-admin";
    }

    private boolean handleIntent(Intent intent) {
        if (intent == null || intent.getData() == null) return false;
        Uri data = intent.getData();
        String scheme = data.getScheme() == null ? "" : data.getScheme().toLowerCase(Locale.US);
        if (scheme.equals("http") || scheme.equals("https")) {
            if (isInstagramUri(data)) {
                openInstagramApp(data);
                return true;
            }
            webView.loadUrl(data.toString());
            return true;
        }
        if (isInstagramUri(data)) {
            openInstagramApp(data);
            return true;
        }
        String host = data.getHost() == null ? "" : data.getHost().toLowerCase(Locale.US);
        String id = data.getQueryParameter("id");
        String code = data.getQueryParameter("code");
        String token = data.getQueryParameter("token");
        String url = getBaseUrl();
        int slash = url.indexOf("/", "https://".length());
        String root = slash > 0 ? url.substring(0, slash) : url;

        if (host.equals("produto") || host.equals("peca") || host.equals("product")) {
            if (id != null && id.length() > 0) {
                webView.loadUrl(root + "/products/" + id);
            } else if (code != null && code.length() > 0) {
                webView.loadUrl(root + "/abrir-peca?code=" + Uri.encode(code) + "&origem=app_admin");
            } else {
                webView.loadUrl(root + "/products");
            }
            return true;
        }
        if (host.equals("pagamento") || host.equals("pedido") || host.equals("order")) {
            if (token != null && token.length() > 0) {
                webView.loadUrl(root + "/loja/pedido/" + Uri.encode(token));
            } else if (id != null && id.length() > 0) {
                webView.loadUrl(root + "/loja-admin?pedido=" + Uri.encode(id));
            } else {
                webView.loadUrl(root + "/loja-admin");
            }
            return true;
        }
        if (host.equals("live") || host.equals("aovivo") || host.equals("ao-vivo")) {
            webView.loadUrl(root + "/live/central");
            return true;
        }
        if (host.equals("studio")) {
            webView.loadUrl(root + "/live/central");
            return true;
        }
        if (host.equals("caderno") || host.equals("notebook") || host.equals("ocr")) {
            webView.loadUrl(root + "/caderno");
            return true;
        }
        if (host.equals("caixa") || host.equals("cashier")) {
            webView.loadUrl(root + "/cashier");
            return true;
        }
        if (host.equals("entregas") || host.equals("delivery") || host.equals("deliveries")) {
            webView.loadUrl(root + "/deliveries");
            return true;
        }
        return false;
    }

    private void showOfflineScreen() {
        offlineView = new LinearLayout(this);
        offlineView.setOrientation(LinearLayout.VERTICAL);
        offlineView.setGravity(Gravity.CENTER);
        offlineView.setPadding(34, 34, 34, 34);
        offlineView.setBackgroundColor(Color.rgb(251,246,239));

        TextView titleView = new TextView(this);
        titleView.setText("BRECHORISEE Admin");
        titleView.setTextSize(28);
        titleView.setTextColor(Color.rgb(44,29,27));
        titleView.setGravity(Gravity.CENTER);
        titleView.setPadding(0,0,0,16);

        TextView msg = new TextView(this);
        msg.setText("Não foi possível conectar agora. Verifique se o celular servidor BRECHORISEE está ligado e na mesma rede Wi-Fi.\n\nEndereço atual:");
        msg.setTextSize(16);
        msg.setTextColor(Color.rgb(124,107,100));
        msg.setGravity(Gravity.CENTER);

        EditText urlInput = new EditText(this);
        urlInput.setSingleLine(true);
        urlInput.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        urlInput.setText(getServerRoot());
        urlInput.setSelectAllOnFocus(false);
        urlInput.setPadding(18, 12, 18, 12);

        Button retry = button("Tentar novamente");
        retry.setOnClickListener(v -> {
            setBaseUrl(urlInput.getText().toString());
            setContentView(rootLayout != null ? rootLayout : webView);
            loadHome();
        });

        Button cloud = button("Usar Tailscale 100.121.45.12");
        cloud.setOnClickListener(v -> {
            urlInput.setText(DEFAULT_ROOT);
        });

        Button pasteExternal = button("Colar link Tailscale/MagicDNS");
        pasteExternal.setOnClickListener(v -> {
            try {
                android.content.ClipboardManager cb = (android.content.ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cb != null && cb.hasPrimaryClip() && cb.getPrimaryClip() != null && cb.getPrimaryClip().getItemCount() > 0) {
                    CharSequence clip = cb.getPrimaryClip().getItemAt(0).coerceToText(this);
                    if (clip != null) urlInput.setText(clip.toString().trim());
                }
            } catch (Exception ignored) {}
        });

        Button browser = button("Abrir no navegador");
        browser.setOnClickListener(v -> {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(getBaseUrl())));
            } catch (Exception ignored) {}
        });

        offlineView.addView(titleView, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(msg, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(urlInput, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(retry, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(cloud, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(pasteExternal, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(browser, new LinearLayout.LayoutParams(-1, -2));
        setContentView(offlineView);
    }

    private Button button(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(16);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(0, 12, 0, 0);
        b.setLayoutParams(params);
        return b;
    }

    private void showSafeStartupError(Throwable ex) {
        try {
            LinearLayout view = new LinearLayout(this);
            view.setOrientation(LinearLayout.VERTICAL);
            view.setGravity(Gravity.CENTER);
            view.setPadding(32, 32, 32, 32);
            view.setBackgroundColor(Color.rgb(251,246,239));

            TextView title = new TextView(this);
            title.setText("BRECHORISEE Admin");
            title.setTextSize(26);
            title.setTextColor(Color.rgb(44,29,27));
            title.setGravity(Gravity.CENTER);
            title.setPadding(0, 0, 0, 16);

            TextView msg = new TextView(this);
            String detail = ex == null ? "erro desconhecido" : String.valueOf(ex.getClass().getSimpleName() + ": " + ex.getMessage());
            msg.setText("O app abriu em modo seguro.\n\nPossível causa: WebView/Chrome desatualizado, servidor ainda não iniciado ou permissão do Android.\n\nDetalhe técnico:\n" + detail + "\n\nAtualize o Android System WebView/Chrome na Play Store e tente novamente.");
            msg.setTextSize(15);
            msg.setTextColor(Color.rgb(124,107,100));
            msg.setGravity(Gravity.CENTER);

            Button retry = button("Tentar abrir novamente");
            retry.setOnClickListener(v -> {
                try {
                    setupWebView();
                    loadHome();
                } catch (Throwable e) {
                    showSafeStartupError(e);
                }
            });

            Button webview = button("Abrir Play Store / WebView");
            webview.setOnClickListener(v -> {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.google.android.webview")));
                } catch (Exception e1) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=com.google.android.webview")));
                    } catch (Exception ignored) {}
                }
            });

            Button chrome = button("Abrir Play Store / Chrome");
            chrome.setOnClickListener(v -> {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.android.chrome")));
                } catch (Exception e1) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=com.android.chrome")));
                    } catch (Exception ignored) {}
                }
            });

            Button browser = button("Abrir Admin no navegador");
            browser.setOnClickListener(v -> {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(getBaseUrl() + "/admin-acesso")));
                } catch (Exception ignored) {}
            });

            view.addView(title, new LinearLayout.LayoutParams(-1, -2));
            view.addView(msg, new LinearLayout.LayoutParams(-1, -2));
            view.addView(retry, new LinearLayout.LayoutParams(-1, -2));
            view.addView(webview, new LinearLayout.LayoutParams(-1, -2));
            view.addView(chrome, new LinearLayout.LayoutParams(-1, -2));
            view.addView(browser, new LinearLayout.LayoutParams(-1, -2));
            setContentView(view);
        } catch (Throwable ignored) {
            try {
                TextView fallback = new TextView(this);
                fallback.setText("BRECHORISEE Admin - falha ao iniciar. Atualize Android System WebView/Chrome.");
                fallback.setPadding(30, 30, 30, 30);
                setContentView(fallback);
            } catch (Throwable ignored2) {}
        }
    }



    @Override
    protected void onDestroy() {
        try { stopService(new Intent(this, InstagramAssistantOverlayService.class)); } catch (Exception ignored) {}
        try { CookieManager.getInstance().flush(); } catch (Exception ignored) {}
        super.onDestroy();
    }

    @Override
    protected void onPause() {
        try {
            if (webView != null) {
                webView.evaluateJavascript(
                    "try{if(window.brechoriseePauseLiveStudio){window.brechoriseePauseLiveStudio();}}catch(e){}",
                    null
                );
                webView.onPause();
                webView.pauseTimers();
            }
        } catch (Exception ignored) {}
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        try {
            if (webView != null) {
                webView.onResume();
                webView.resumeTimers();
                webView.postDelayed(() -> {
                    try {
                        webView.evaluateJavascript(
                            "try{if(window.brechoriseeResumeLiveStudio){window.brechoriseeResumeLiveStudio();}}catch(e){}",
                            null
                        );
                    } catch (Exception ignored) {}
                }, 450);
            }
        } catch (Exception ignored) {}

        try {
            updateAssistantButtonVisibility(webView != null ? webView.getUrl() : null);
        } catch (Exception ignored) {}

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                    && Settings.canDrawOverlays(this)
                    && prefs.getBoolean(KEY_PENDING_ASSISTANT, false)) {
                String target = prefs.getString(KEY_PENDING_INSTAGRAM_URI, "instagram://app");
                prefs.edit()
                        .putBoolean(KEY_PENDING_ASSISTANT, false)
                        .remove(KEY_PENDING_INSTAGRAM_URI)
                        .apply();
                handler.postDelayed(() -> startInstagramAssistant(target), 500);
            }
        } catch (Exception ignored) {}
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.getVisibility() == View.VISIBLE && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
