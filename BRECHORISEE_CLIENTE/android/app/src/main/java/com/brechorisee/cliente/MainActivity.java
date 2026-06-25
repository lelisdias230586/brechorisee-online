package com.brechorisee.cliente;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
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
import android.widget.Toast;
import android.widget.EditText;
import android.text.InputType;
import android.provider.MediaStore;
import android.provider.Settings;
import android.content.ClipData;

import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final String DEFAULT_URL = "http://100.121.45.12:8000/cliente/inicio";
    private static final String DEFAULT_ROOT = "http://100.121.45.12:8000";
    private static final String PREFS = "brechorisee_prefs";
    private static final String KEY_URL = "server_url";
    private static final String KEY_TUTORIAL_VERSION_SEEN = "cliente_tutorial_seen_v4";
    private static final String KEY_FIRST_SETUP_DONE = "cliente_first_setup_done_v1";
    private static final int FILE_CHOOSER_REQUEST = 8307;
    private static final int PERMISSION_REQUEST = 8308;
    private static final int OVERLAY_PERMISSION_REQUEST = 8310;
    private static final String LIVE_NOTIFICATION_CHANNEL = "brechorisee_live";
    private static final String KEY_LAST_LIVE_NOTIFICATION_ID = "last_live_notification_id";
    private static final String KEY_PENDING_CLIENT_INSTAGRAM = "pending_client_instagram";
    private static final String KEY_PENDING_CLIENT_INSTAGRAM_URI = "pending_client_instagram_uri";

    private WebView webView;
    private LinearLayout offlineView;
    private SharedPreferences prefs;
    private Handler handler = new Handler(Looper.getMainLooper());

    private ValueCallback<Uri[]> filePathCallback;
    private Uri cameraPhotoUri;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        requestBasicPermissions();
        createLiveNotificationChannel();
        setupWebView();
        if (!prefs.getBoolean(KEY_FIRST_SETUP_DONE, false)) {
            showFirstRunSetup();
        } else if (!handleIntent(getIntent())) {
            loadHome();
        }
        startLiveNotificationPolling();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        checkLiveNotification();
        try {
            if (Build.VERSION.SDK_INT >= 23
                    && Settings.canDrawOverlays(this)
                    && prefs.getBoolean(KEY_PENDING_CLIENT_INSTAGRAM, false)) {
                String target = prefs.getString(KEY_PENDING_CLIENT_INSTAGRAM_URI, "instagram://app");
                prefs.edit()
                        .putBoolean(KEY_PENDING_CLIENT_INSTAGRAM, false)
                        .remove(KEY_PENDING_CLIENT_INSTAGRAM_URI)
                        .apply();
                handler.postDelayed(() -> openInstagramApp(Uri.parse(target)), 450);
            }
        } catch (Exception ignored) {}
    }

    private void requestBasicPermissions() {
        if (Build.VERSION.SDK_INT >= 23) {
            java.util.ArrayList<String> permissions = new java.util.ArrayList<>();
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.CAMERA);
            }
            if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.POST_NOTIFICATIONS);
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
        if (lower.endsWith("/app/cliente")) {
            return url.substring(0, url.length() - "/app/cliente".length());
        }
        if (lower.endsWith("/cliente")) {
            return url.substring(0, url.length() - "/cliente".length());
        }
        if (lower.endsWith("/admin") || lower.endsWith("/admin-acesso")) {
            int idx = lower.lastIndexOf(lower.endsWith("/admin") ? "/admin" : "/admin-acesso");
            if (idx > 0) return url.substring(0, idx);
        }
        return url;
    }

    private String normalizeClientUrl(String raw) {
        String root = normalizeServerRoot(raw);
        return root + "/cliente/inicio";
    }

    private void showFirstRunSetup() {
        final String currentBase = getServerRootFromUrl(getBaseUrl());
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(34, 34, 34, 34);
        root.setBackgroundColor(Color.rgb(250, 242, 239));

        TextView title = new TextView(this);
        title.setText("Configurar BRECHORISEE Cliente");
        title.setTextColor(Color.rgb(48, 32, 29));
        title.setTextSize(22);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 0, 0, 22);
        root.addView(title, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView help = new TextView(this);
        help.setText("Primeiro acesso: escolha o servidor. Use o IP local dentro do Wi-Fi ou cole o link público lhr.life/Tailscale/MagicDNS. O app abre a área da cliente; a live só abre quando você tocar em Entrar na live.");
        help.setTextColor(Color.rgb(78, 61, 57));
        help.setTextSize(15);
        help.setPadding(0, 0, 0, 18);
        root.addView(help);

        TextView label = new TextView(this);
        label.setText("Servidor BRECHORISEE");
        label.setTextColor(Color.rgb(48, 32, 29));
        label.setTextSize(15);
        root.addView(label);

        final EditText serverInput = new EditText(this);
        serverInput.setSingleLine(true);
        serverInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        serverInput.setText(currentBase == null || currentBase.length() == 0 ? "http://100.121.45.12:8000" : currentBase);
        serverInput.setHint("https://seu-link.lhr.life ou http://192.168.1.18:8000");
        serverInput.setTextColor(Color.rgb(32, 24, 22));
        serverInput.setHintTextColor(Color.rgb(140, 120, 115));
        root.addView(serverInput, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));
        Button useLocalBtn = makeSetupButton("Usar servidor padrão/Tailscale");
        useLocalBtn.setOnClickListener(v -> serverInput.setText(DEFAULT_ROOT));
        root.addView(useLocalBtn);

        Button pasteExternalBtn = makeSetupButton("Colar link público/Tailscale/MagicDNS");
        pasteExternalBtn.setOnClickListener(v -> {
            try {
                android.content.ClipboardManager cb = (android.content.ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cb != null && cb.hasPrimaryClip() && cb.getPrimaryClip() != null && cb.getPrimaryClip().getItemCount() > 0) {
                    CharSequence clip = cb.getPrimaryClip().getItemAt(0).coerceToText(this);
                    if (clip != null) serverInput.setText(clip.toString().trim());
                } else {
                    Toast.makeText(this, "Copie o link externo antes e toque aqui novamente.", Toast.LENGTH_LONG).show();
                }
            } catch (Exception ignored) {}
        });
        root.addView(pasteExternalBtn);


        TextView status = new TextView(this);
        status.setText(getSetupStatusText());
        status.setTextColor(Color.rgb(90, 70, 64));
        status.setTextSize(14);
        status.setPadding(0, 18, 0, 18);
        root.addView(status);

        Button overlayBtn = makeSetupButton("1. Permitir cards sobre o Instagram");
        overlayBtn.setOnClickListener(v -> {
            try {
                Intent permissionIntent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
                startActivity(permissionIntent);
            } catch (Exception e) {
                try { startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION)); } catch (Exception ignored) {}
            }
        });
        root.addView(overlayBtn);

        Button usageBtn = makeSetupButton("2. Permitir fechar card ao sair do Instagram");
        usageBtn.setOnClickListener(v -> {
            try {
                startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS));
            } catch (Exception e) {
                Toast.makeText(this, "Abra Acesso ao uso nas configurações do Android.", Toast.LENGTH_LONG).show();
            }
        });
        root.addView(usageBtn);

        Button batteryBtn = makeSetupButton("3. Deixar bateria sem restrição");
        batteryBtn.setOnClickListener(v -> {
            try {
                Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                intent.setData(Uri.parse("package:" + getPackageName()));
                startActivity(intent);
                Toast.makeText(this, "Entre em Bateria e selecione Sem restrição.", Toast.LENGTH_LONG).show();
            } catch (Exception ignored) {}
        });
        root.addView(batteryBtn);

        Button testBtn = makeSetupButton("Testar conexão");
        testBtn.setOnClickListener(v -> {
            String clientUrl = normalizeClientUrl(serverInput.getText().toString());
            setBaseUrl(clientUrl);
            status.setText("Testando " + getServerRootFromUrl(clientUrl) + " ...");
            testServerConnection(getServerRootFromUrl(clientUrl), ok -> runOnUiThread(() -> {
                status.setText((ok ? "✅ Servidor conectado. " : "⚠️ Não conectou. ") + getSetupStatusText());
                Toast.makeText(this, ok ? "Servidor conectado." : "Não conectou ao servidor. Confira IP/Wi-Fi.", Toast.LENGTH_LONG).show();
            }));
        });
        root.addView(testBtn);

        Button saveBtn = makeSetupButton("Salvar e abrir BRECHORISEE Cliente");
        saveBtn.setOnClickListener(v -> {
            String clientUrl = normalizeClientUrl(serverInput.getText().toString());
            setBaseUrl(clientUrl);
            prefs.edit().putBoolean(KEY_FIRST_SETUP_DONE, true).apply();
            Toast.makeText(this, "Configuração salva.", Toast.LENGTH_SHORT).show();
            setContentView(webView);
            loadHome();
        });
        root.addView(saveBtn);

        Button instagramBtn = makeSetupButton("Salvar e abrir Instagram com cards");
        instagramBtn.setOnClickListener(v -> {
            String clientUrl = normalizeClientUrl(serverInput.getText().toString());
            setBaseUrl(clientUrl);
            prefs.edit().putBoolean(KEY_FIRST_SETUP_DONE, true).apply();
            startLiveCompanionOverlay(true);
        });
        root.addView(instagramBtn);

        setContentView(root);
    }

    private Button makeSetupButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(15);
        b.setPadding(10, 12, 10, 12);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        lp.setMargins(0, 8, 0, 8);
        b.setLayoutParams(lp);
        return b;
    }

    private String getSetupStatusText() {
        boolean overlayOk = Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(this);
        return "Cards sobre Instagram: " + (overlayOk ? "permitido" : "precisa permitir")
                + "\nServidor recomendado: http://100.121.45.12:8000"
                + "\nDepois toque em Salvar ou em Abrir Instagram com cards.";
    }

    private interface ServerTestCallback {
        void onResult(boolean ok);
    }

    private void testServerConnection(String root, ServerTestCallback callback) {
        new Thread(() -> {
            boolean ok = false;
            try {
                URL u = new URL(root);
                HttpURLConnection con = (HttpURLConnection) u.openConnection();
                con.setConnectTimeout(5000);
                con.setReadTimeout(5000);
                con.setRequestMethod("GET");
                int code = con.getResponseCode();
                ok = code >= 200 && code < 500;
                con.disconnect();
            } catch (Exception ignored) {}
            callback.onResult(ok);
        }).start();
    }


    private void setupWebView() {
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
            settings.setUserAgentString(settings.getUserAgentString() + " BRECHORISEE-Android-Cliente");
            CookieManager cookieManager = CookieManager.getInstance();
            cookieManager.setAcceptCookie(true);
            if (Build.VERSION.SDK_INT >= 21) {
                cookieManager.setAcceptThirdPartyCookies(webView, true);
            }
        } catch (Exception ignored) {}

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> {
                    java.util.ArrayList<String> allowed = new java.util.ArrayList<>();
                    for (String resource : request.getResources()) {
                        if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) {
                            allowed.add(resource);
                        }
                    }
                    if (allowed.isEmpty()) {
                        request.deny();
                    } else {
                        request.grant(allowed.toArray(new String[0]));
                    }
                });
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
                    if (isBlockedClientPath(uri)) {
                        view.loadUrl(normalizeClientUrl(getBaseUrl()));
                        return true;
                    }
                    return false;
                }
                if (scheme.equals("brechorisee")) {
                    Intent internalIntent = new Intent(Intent.ACTION_VIEW, uri);
                    handleIntent(internalIntent);
                    return true;
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
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showOfflineScreen();
                }
            }
        });

        setContentView(webView);
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

    private String getBaseUrl() {
        return prefs.getString(KEY_URL, DEFAULT_URL);
    }

    private void setBaseUrl(String url) {
        if (url == null || url.trim().isEmpty()) url = DEFAULT_ROOT;
        url = normalizeClientUrl(url);
        prefs.edit().putString(KEY_URL, url).apply();
    }

    private void loadHome() {
        String url = getBaseUrl();
        webView.setVisibility(View.VISIBLE);
        if (!prefs.getBoolean(KEY_TUTORIAL_VERSION_SEEN, false)) {
            prefs.edit().putBoolean(KEY_TUTORIAL_VERSION_SEEN, true).apply();
            String root = getServerRootFromUrl(url);
            webView.loadUrl(root + "/cliente/tutorial?origem=app&primeiro=1");
            return;
        }
        webView.loadUrl(url);
    }

    private String getServerRootFromUrl(String url) {
        if (url == null || url.trim().isEmpty()) return DEFAULT_ROOT;
        int schemeEnd = url.indexOf("://");
        if (schemeEnd >= 0) {
            int slash = url.indexOf("/", schemeEnd + 3);
            if (slash > 0) return url.substring(0, slash);
        }
        return url.replaceAll("/+$", "").replaceAll("/app/cliente/?$", "").replaceAll("/cliente/inicio/?$", "").replaceAll("/cliente/home/?$", "").replaceAll("/cliente/?$", "");
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
            if (isBlockedClientPath(data)) return false;
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
                webView.loadUrl(root + "/cliente/peca/" + Uri.encode(id));
            } else if (code != null && code.length() > 0) {
                webView.loadUrl(root + "/cliente/peca/" + Uri.encode(code));
            } else {
                webView.loadUrl(root + "/cliente/vitrine");
            }
            return true;
        }
        if (host.equals("pagamento") || host.equals("pedido") || host.equals("order")) {
            if (token != null && token.length() > 0) {
                webView.loadUrl(root + "/loja/pedido/" + Uri.encode(token));
            } else if (id != null && id.length() > 0) {
                webView.loadUrl(root + "/loja/pedido/" + Uri.encode(id));
            } else {
                webView.loadUrl(root + "/loja/carrinho");
            }
            return true;
        }
        if (host.equals("live-companion") || host.equals("companion")) {
            boolean openInstagram = "1".equals(data.getQueryParameter("abrir_instagram")) || "true".equalsIgnoreCase(data.getQueryParameter("abrir_instagram"));
            startLiveCompanionOverlay(openInstagram);
            webView.loadUrl(root + "/cliente/live-companion");
            return true;
        }
        if (host.equals("tutorial") || host.equals("como-usar") || host.equals("ajuda-cliente")) {
            webView.loadUrl(root + "/cliente/tutorial");
            return true;
        }
        if (host.equals("live") || host.equals("aovivo") || host.equals("ao-vivo")) {
            boolean openInstagram = "1".equals(data.getQueryParameter("abrir_instagram")) || "true".equalsIgnoreCase(data.getQueryParameter("abrir_instagram"));
            startLiveCompanionOverlay(openInstagram);
            webView.loadUrl(root + "/cliente/live-opcoes");
            return true;
        }
        if (host.equals("sacola") || host.equals("cart") || host.equals("carrinho")) {
            webView.loadUrl(root + "/loja/carrinho");
            return true;
        }
        if (host.equals("entregas") || host.equals("delivery") || host.equals("minhas-entregas")) {
            webView.loadUrl(root + "/cliente/entregas");
            return true;
        }
        return false;
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

        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) {
            prefs.edit()
                    .putBoolean(KEY_PENDING_CLIENT_INSTAGRAM, true)
                    .putString(KEY_PENDING_CLIENT_INSTAGRAM_URI, target.toString())
                    .apply();
            try {
                Intent permissionIntent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
                startActivityForResult(permissionIntent, OVERLAY_PERMISSION_REQUEST);
            } catch (Exception ignored) {}
            Toast.makeText(this, "Ative Sobrepor a outros apps. Ao voltar, vou abrir o Instagram com o card BRECHORISEE por cima.", Toast.LENGTH_LONG).show();
            return true;
        }

        startOverlayServiceForInstagram();

        final Uri finalTarget = target;
        handler.postDelayed(() -> openInstagramNativeOnly(finalTarget), 350);
        return true;
    }


    private void startOverlayServiceForInstagram() {
        try {
            Intent serviceIntent = new Intent(this, LiveCompanionOverlayService.class);
            serviceIntent.putExtra("server_root", getServerRoot());
            serviceIntent.putExtra("mode", "instagram");
            if (Build.VERSION.SDK_INT >= 26) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
        } catch (Exception e) {
            Toast.makeText(this, "Não consegui iniciar o card flutuante. Verifique a permissão de sobreposição.", Toast.LENGTH_LONG).show();
        }
    }

    private boolean openInstagramNativeOnly(Uri uri) {
        Uri target = uri;
        if (target == null || !isInstagramUri(target)) {
            target = Uri.parse("instagram://app");
        }

        // Primeiro tenta abrir a tela principal do app nativo, que é mais estável em aparelhos Xiaomi/MIUI.
        if ("instagram".equals(target.getScheme()) && "app".equals(target.getHost())) {
            try {
                Intent launch = getPackageManager().getLaunchIntentForPackage("com.instagram.android");
                if (launch != null) {
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                    startActivity(launch);
                    return true;
                }
            } catch (Exception ignored) {}
        }

        try {
            Intent direct = new Intent(Intent.ACTION_VIEW, target);
            direct.setPackage("com.instagram.android");
            direct.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            startActivity(direct);
            return true;
        } catch (Exception ignored) {}

        try {
            Intent launch = getPackageManager().getLaunchIntentForPackage("com.instagram.android");
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                startActivity(launch);
                return true;
            }
        } catch (Exception ignored) {}

        try {
            Intent market = new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.instagram.android"));
            market.setPackage("com.android.vending");
            market.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(market);
            Toast.makeText(this, "Instagram não encontrado. Instale ou atualize o Instagram.", Toast.LENGTH_LONG).show();
            return true;
        } catch (Exception ignored) {
            Toast.makeText(this, "Instagram não encontrado no celular.", Toast.LENGTH_LONG).show();
        }
        return false;
    }

    private boolean isBlockedClientPath(Uri uri) {
        if (uri == null) return false;
        String path = uri.getPath() == null ? "" : uri.getPath().toLowerCase(Locale.US);
        if (path.equals("/") || path.startsWith("/admin") || path.startsWith("/admin-acesso")) return true;
        if (path.startsWith("/cashier") || path.startsWith("/products") || path.startsWith("/suppliers")) return true;
        if (path.startsWith("/sales") || path.startsWith("/reports") || path.startsWith("/stock-history")) return true;
        if (path.startsWith("/professional") || path.startsWith("/profissional") || path.startsWith("/gestao")) return true;
        if (path.startsWith("/sincronizacao") || path.startsWith("/notificacoes") || path.startsWith("/marketing")) return true;
        if (path.startsWith("/live/peca-atual") || path.startsWith("/live/companion") || path.startsWith("/live/carrinho")) return false;
        if (path.startsWith("/ai") || path.startsWith("/ia-clientes") || path.startsWith("/live") || path.startsWith("/labels")) return true;
        if (path.startsWith("/deliveries") || path.startsWith("/clientes-inteligentes")) return true;
        if (path.startsWith("/loja-admin") || path.startsWith("/whatsapp-vendas") || path.startsWith("/export") || path.startsWith("/backups")) return true;
        return false;
    }

    private void startLiveCompanionOverlay(boolean openInstagram) {
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) {
            if (openInstagram) {
                prefs.edit()
                        .putBoolean(KEY_PENDING_CLIENT_INSTAGRAM, true)
                        .putString(KEY_PENDING_CLIENT_INSTAGRAM_URI, "instagram://app")
                        .apply();
            }
            try {
                Intent permissionIntent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
                startActivityForResult(permissionIntent, OVERLAY_PERMISSION_REQUEST);
            } catch (Exception ignored) {}
            if (webView != null) {
                webView.loadUrl(getServerRoot() + "/cliente/live?overlay=permissao");
            }
            return;
        }

        startOverlayServiceForInstagram();

        if (openInstagram) {
            openInstagramLiveFromServer();
        }
    }

    private void openInstagramLiveFromServer() {
        new Thread(() -> {
            String instagramUrl = "";
            try {
                String endpoint = getServerRoot() + "/api/live/companion";
                String cookies = CookieManager.getInstance().getCookie(getServerRoot());
                HttpURLConnection con = (HttpURLConnection) new URL(endpoint).openConnection();
                con.setRequestMethod("GET");
                con.setConnectTimeout(8000);
                con.setReadTimeout(8000);
                con.setRequestProperty("Accept", "application/json");
                if (cookies != null && cookies.trim().length() > 0) {
                    con.setRequestProperty("Cookie", cookies);
                }
                if (con.getResponseCode() == 200) {
                    BufferedReader reader = new BufferedReader(new InputStreamReader(con.getInputStream()));
                    StringBuilder body = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) body.append(line);
                    reader.close();
                    JSONObject data = new JSONObject(body.toString());
                    JSONObject links = data.optJSONObject("links");
                    if (links != null) instagramUrl = links.optString("instagram_live", "");
                }
            } catch (Exception ignored) {}

            final String urlToOpen = instagramUrl;
            handler.post(() -> {
                if (urlToOpen != null && urlToOpen.startsWith("http")) {
                    if (!openInstagramNativeOnly(Uri.parse(urlToOpen))) {
                        webView.loadUrl(getServerRoot() + "/cliente/live");
                    }
                } else {
                    openInstagramNativeOnly(null);
                }
            });
        }).start();
    }

    private void startLiveNotificationService() {
        try {
            Intent serviceIntent = new Intent(this, LiveNotificationService.class);
            serviceIntent.putExtra("server_root", getServerRoot());
            if (Build.VERSION.SDK_INT >= 26) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
        } catch (Exception ignored) {}
    }

    private void createLiveNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    LIVE_NOTIFICATION_CHANNEL,
                    "Lives BRECHORISEE",
                    NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Avisos quando a live da BRECHORISEE começar.");
            NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private String getServerRoot() {
        String url = getBaseUrl();
        int schemeEnd = url.indexOf("://");
        if (schemeEnd >= 0) {
            int slash = url.indexOf("/", schemeEnd + 3);
            if (slash > 0) return url.substring(0, slash);
        }
        return url.replaceAll("/+$", "");
    }

    private void startLiveNotificationPolling() {
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                checkLiveNotification();
                handler.postDelayed(this, 12000);
            }
        }, 1200);
    }

    private void checkLiveNotification() {
        new Thread(() -> {
            try {
                String root = getServerRoot();
                String endpoint = root + "/api/cliente/notificacoes/live-alert";
                String cookies = CookieManager.getInstance().getCookie(root);
                HttpURLConnection con = (HttpURLConnection) new URL(endpoint).openConnection();
                con.setRequestMethod("GET");
                con.setConnectTimeout(8000);
                con.setReadTimeout(8000);
                con.setRequestProperty("Accept", "application/json");
                if (cookies != null && !cookies.trim().isEmpty()) {
                    con.setRequestProperty("Cookie", cookies);
                }
                int code = con.getResponseCode();
                if (code != 200) return;
                BufferedReader reader = new BufferedReader(new InputStreamReader(con.getInputStream()));
                StringBuilder body = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) body.append(line);
                reader.close();

                JSONObject data = new JSONObject(body.toString());
                if (!data.optBoolean("ok")) return;
                JSONObject notification = data.optJSONObject("notification");
                if (notification == null) return;

                int id = notification.optInt("id", 0);
                int lastId = prefs.getInt(KEY_LAST_LIVE_NOTIFICATION_ID, 0);
                if (id <= 0 || id == lastId) return;
                prefs.edit().putInt(KEY_LAST_LIVE_NOTIFICATION_ID, id).apply();

                String title = notification.optString("title", "BRECHORISEE ao vivo agora ✨");
                String message = notification.optString("message", "Toque para entrar direto na live.");
                handler.post(() -> showLiveNotification(id, title, message));
            } catch (Exception ignored) {
            }
        }).start();
    }

    private void showLiveNotification(int notificationId, String title, String message) {
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[]{Manifest.permission.POST_NOTIFICATIONS}, PERMISSION_REQUEST);
            return;
        }

        Intent intent = new Intent(this, MainActivity.class);
        intent.setAction(Intent.ACTION_VIEW);
        intent.setData(Uri.parse("brechorisee://live?abrir_instagram=1"));
        intent.putExtra("notification_id", notificationId);
        intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);

        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent pendingIntent = PendingIntent.getActivity(this, notificationId, intent, flags);

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, LIVE_NOTIFICATION_CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_camera)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(pendingIntent);

        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) manager.notify(9000 + notificationId, builder.build());
    }

    private void showOfflineScreen() {
        offlineView = new LinearLayout(this);
        offlineView.setOrientation(LinearLayout.VERTICAL);
        offlineView.setGravity(Gravity.CENTER);
        offlineView.setPadding(34, 34, 34, 34);
        offlineView.setBackgroundColor(Color.rgb(251,246,239));

        TextView titleView = new TextView(this);
        titleView.setText("BRECHORISEE Cliente");
        titleView.setTextSize(28);
        titleView.setTextColor(Color.rgb(44,29,27));
        titleView.setGravity(Gravity.CENTER);
        titleView.setPadding(0,0,0,16);

        TextView msg = new TextView(this);
        msg.setText("Não foi possível conectar. Confira o servidor abaixo. Para rede externa, cole o link HTTPS do túnel.");
        msg.setTextSize(16);
        msg.setTextColor(Color.rgb(124,107,100));
        msg.setGravity(Gravity.CENTER);

        EditText urlInput = new EditText(this);
        urlInput.setSingleLine(true);
        urlInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        urlInput.setText(getServerRootFromUrl(getBaseUrl()));
        urlInput.setHint("http://100.121.45.12:8000 ou http://192.168.1.18:8000");
        urlInput.setSelectAllOnFocus(false);
        urlInput.setPadding(18, 12, 18, 12);

        Button retry = button("Salvar e tentar novamente");
        retry.setOnClickListener(v -> {
            setBaseUrl(urlInput.getText().toString());
            setContentView(webView);
            loadHome();
        });

        Button local = button("Usar servidor local");
        local.setOnClickListener(v -> urlInput.setText(DEFAULT_ROOT));

        Button paste = button("Colar link externo");
        paste.setOnClickListener(v -> {
            try {
                android.content.ClipboardManager cb = (android.content.ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cb != null && cb.hasPrimaryClip() && cb.getPrimaryClip() != null && cb.getPrimaryClip().getItemCount() > 0) {
                    CharSequence clip = cb.getPrimaryClip().getItemAt(0).coerceToText(this);
                    if (clip != null) urlInput.setText(clip.toString().trim());
                }
            } catch (Exception ignored) {}
        });

        Button setup = button("Abrir configuração completa");
        setup.setOnClickListener(v -> showFirstRunSetup());

        offlineView.addView(titleView, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(msg, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(urlInput, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(retry, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(local, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(paste, new LinearLayout.LayoutParams(-1, -2));
        offlineView.addView(setup, new LinearLayout.LayoutParams(-1, -2));
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

    @Override
    protected void onDestroy() {
        try { stopService(new Intent(this, LiveCompanionOverlayService.class)); } catch (Exception ignored) {}
        handler.removeCallbacksAndMessages(null);
        try { CookieManager.getInstance().flush(); } catch (Exception ignored) {}
        super.onDestroy();
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
