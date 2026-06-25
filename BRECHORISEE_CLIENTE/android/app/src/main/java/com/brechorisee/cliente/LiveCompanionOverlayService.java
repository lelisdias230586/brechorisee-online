package com.brechorisee.cliente;

import android.app.Service;
import android.widget.Toast;
import android.content.pm.PackageManager;
import android.os.Process;
import android.app.usage.UsageStatsManager;
import android.app.usage.UsageEvents;
import android.app.AppOpsManager;
import android.app.PendingIntent;
import android.app.NotificationManager;
import android.app.NotificationChannel;
import android.app.Notification;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.PixelFormat;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;

import org.json.JSONObject;

public class LiveCompanionOverlayService extends Service {
    private static final String DEFAULT_URL = "https://brechorisee-online.onrender.com/cliente";
    private static final String OVERLAY_NOTIFICATION_CHANNEL = "brechorisee_cliente_overlay";
    private static final int OVERLAY_NOTIFICATION_ID = 230586;
    private static final String PREFS = "brechorisee_prefs";
    private static final String KEY_URL = "server_url";

    private WindowManager windowManager;
    private LinearLayout overlayView;
    private LinearLayout buttonsRow;
    private WindowManager.LayoutParams params;
    private Handler handler = new Handler(Looper.getMainLooper());

    private boolean running = false;
    private boolean compact = false;
    private int currentPollMs = 1000;
    private int fullCardSeconds = 6;
    private int staleSeconds = 999999;
    private int outsideInstagramCount = 0;
    private boolean instagramMode = false;

    private String currentUrl = "";
    private String currentChatUrl = "";
    private String instagramUrl = "";
    private String lastEventKey = "";
    private String dismissedEventKey = "";
    private String lastImageUrl = "";

    private ImageView thumbnailView;
    private TextView titleView;
    private TextView priceView;
    private TextView metaView;
    private TextView statusView;
    private Button actionButton;
    private Button chatButton;
    private Button instagramButton;
    private Button hideButton;

    private final Runnable pollRunnable = new Runnable() {
        @Override
        public void run() {
            if (!running) return;
            if (instagramMode && shouldStopBecauseInstagramClosed()) {
                hideOverlay();
                stopSelf();
                return;
            }
            fetchLiveCompanion();
            handler.postDelayed(this, Math.max(800, currentPollMs));
        }
    };

    private Runnable autoCompactRunnable;

    @Override
    public void onCreate() {
        super.onCreate();
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        createOverlayNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForegroundSafely();
        if (!canDrawOverlay()) {
            Toast.makeText(this, "Permita Sobrepor a outros apps para mostrar o card BRECHORISEE.", Toast.LENGTH_LONG).show();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (intent != null && intent.getStringExtra("server_root") != null) {
            getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit()
                    .putString(KEY_URL, intent.getStringExtra("server_root") + "/cliente")
                    .apply();
        }
        instagramMode = intent != null && "instagram".equals(intent.getStringExtra("mode"));
        outsideInstagramCount = 0;
        showOverlay();
        ensureOverlayVisible();
        statusView.setText("BRECHORISEE • carregando card");
        titleView.setText("Aguardando peça atual");
        setCompact(true);
        running = true;
        handler.removeCallbacks(pollRunnable);
        handler.post(pollRunnable);
        return START_STICKY;
    }


    private void createOverlayNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    OVERLAY_NOTIFICATION_CHANNEL,
                    "Card Instagram BRECHORISEE",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Mantém o card flutuante do Cliente ativo sobre o Instagram.");
            NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }

    private void startForegroundSafely() {
        try {
            Intent openIntent = new Intent(this, MainActivity.class);
            openIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent pendingIntent = PendingIntent.getActivity(
                    this,
                    230586,
                    openIntent,
                    Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0
            );
            Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                    ? new Notification.Builder(this, OVERLAY_NOTIFICATION_CHANNEL)
                    : new Notification.Builder(this);
            Notification notification = builder
                    .setContentTitle("BRECHORISEE Cliente")
                    .setContentText("Card flutuante ativo para Instagram")
                    .setSmallIcon(android.R.drawable.ic_dialog_info)
                    .setContentIntent(pendingIntent)
                    .setOngoing(true)
                    .build();
            startForeground(OVERLAY_NOTIFICATION_ID, notification);
        } catch (Exception ignored) {}
    }

    private boolean hasUsageStatsPermission() {
        try {
            AppOpsManager appOps = (AppOpsManager) getSystemService(Context.APP_OPS_SERVICE);
            if (appOps == null) return false;
            int mode = appOps.checkOpNoThrow(
                    AppOpsManager.OPSTR_GET_USAGE_STATS,
                    Process.myUid(),
                    getPackageName()
            );
            return mode == AppOpsManager.MODE_ALLOWED;
        } catch (Exception ignored) {
            return false;
        }
    }

    private String getForegroundPackage() {
        try {
            UsageStatsManager usageStatsManager = (UsageStatsManager) getSystemService(Context.USAGE_STATS_SERVICE);
            if (usageStatsManager == null) return "";
            long end = System.currentTimeMillis();
            long begin = end - 15000;
            UsageEvents events = usageStatsManager.queryEvents(begin, end);
            UsageEvents.Event event = new UsageEvents.Event();
            String lastPackage = "";
            while (events.hasNextEvent()) {
                events.getNextEvent(event);
                if (event.getEventType() == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                    lastPackage = event.getPackageName();
                }
            }
            return lastPackage == null ? "" : lastPackage;
        } catch (Exception ignored) {
            return "";
        }
    }

    private boolean shouldStopBecauseInstagramClosed() {
        if (!hasUsageStatsPermission()) {
            // Sem Acesso ao uso, o Android não informa qual app está aberto.
            // Nesse caso o botão × continua sendo o fechamento manual.
            return false;
        }
        String pkg = getForegroundPackage();
        if (pkg.length() == 0) return false;
        if ("com.instagram.android".equals(pkg) || getPackageName().equals(pkg)) {
            outsideInstagramCount = 0;
            return false;
        }
        outsideInstagramCount++;
        return outsideInstagramCount >= 2;
    }

    private boolean canDrawOverlay() {
        return Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(this);
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }

    private String getServerRoot() {
        SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String url = prefs.getString(KEY_URL, DEFAULT_URL);
        int schemeEnd = url.indexOf("://");
        if (schemeEnd >= 0) {
            int slash = url.indexOf("/", schemeEnd + 3);
            if (slash > 0) return url.substring(0, slash);
        }
        return url.replaceAll("/+$", "");
    }

    private void showOverlay() {
        if (overlayView != null) return;

        overlayView = new LinearLayout(this);
        overlayView.setOrientation(LinearLayout.VERTICAL);
        overlayView.setPadding(dp(8), dp(6), dp(8), dp(6));
        // Card lateral em miniatura: visível sobre o Instagram, mas discreto.
        overlayView.setBackgroundColor(Color.argb(155, 31, 23, 20));

        TextView dragHandle = new TextView(this);
        dragHandle.setText("⠿ BRECHORISEE");
        dragHandle.setTextColor(Color.rgb(255, 224, 232));
        dragHandle.setTextSize(12);
        dragHandle.setGravity(Gravity.CENTER);
        dragHandle.setPadding(0, 0, 0, dp(4));

        statusView = new TextView(this);
        statusView.setText("BRECHORISEE • aguardando");
        statusView.setTextColor(Color.rgb(255, 210, 225));
        statusView.setTextSize(12);
        statusView.setGravity(Gravity.CENTER_VERTICAL);

        thumbnailView = new ImageView(this);
        thumbnailView.setBackgroundColor(Color.argb(255, 255, 248, 244));
        thumbnailView.setAdjustViewBounds(true);
        thumbnailView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        thumbnailView.setPadding(dp(4), dp(4), dp(4), dp(4));

        titleView = new TextView(this);
        titleView.setText("Aguardando peça atual");
        titleView.setTextColor(Color.WHITE);
        titleView.setTextSize(16);
        titleView.setMaxLines(2);

        priceView = new TextView(this);
        priceView.setText("");
        priceView.setTextColor(Color.rgb(255, 236, 224));
        priceView.setTextSize(18);
        priceView.setTypeface(null, 1);

        metaView = new TextView(this);
        metaView.setText("");
        metaView.setTextColor(Color.rgb(230, 218, 210));
        metaView.setTextSize(12);
        metaView.setMaxLines(2);

        buttonsRow = new LinearLayout(this);
        buttonsRow.setOrientation(LinearLayout.HORIZONTAL);
        buttonsRow.setGravity(Gravity.CENTER_VERTICAL);

        actionButton = makeButton("Reservar");
        actionButton.setOnClickListener(v -> openUrl(currentUrl.length() > 0 ? currentUrl : getServerRoot() + "/cliente/live"));

        chatButton = makeButton("Perguntar");
        chatButton.setOnClickListener(v -> openUrl(currentChatUrl.length() > 0 ? currentChatUrl : getServerRoot() + "/cliente/chat?origem=live"));

        instagramButton = makeButton("Instagram");
        instagramButton.setOnClickListener(v -> {
            if (instagramUrl != null && instagramUrl.startsWith("http")) {
                openExternal(instagramUrl);
            }
        });

        hideButton = makeButton("×");
        hideButton.setOnClickListener(v -> {
            dismissedEventKey = lastEventKey;
            hideOverlay();
        });

        buttonsRow.addView(actionButton, new LinearLayout.LayoutParams(0, -2, 1));
        buttonsRow.addView(chatButton, new LinearLayout.LayoutParams(0, -2, 1));
        buttonsRow.addView(instagramButton, new LinearLayout.LayoutParams(0, -2, 1));
        buttonsRow.addView(hideButton, new LinearLayout.LayoutParams(dp(42), -2));

        overlayView.addView(dragHandle, new LinearLayout.LayoutParams(-1, -2));
        overlayView.addView(statusView, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout.LayoutParams thumbParams = new LinearLayout.LayoutParams(dp(72), dp(84));
        thumbParams.gravity = Gravity.CENTER_HORIZONTAL;
        thumbParams.setMargins(0, dp(4), 0, dp(6));
        overlayView.addView(thumbnailView, thumbParams);
        overlayView.addView(titleView, new LinearLayout.LayoutParams(-1, -2));
        overlayView.addView(priceView, new LinearLayout.LayoutParams(-1, -2));
        overlayView.addView(metaView, new LinearLayout.LayoutParams(-1, -2));
        overlayView.addView(buttonsRow, new LinearLayout.LayoutParams(-1, -2));

        int type = Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE;
        params = new WindowManager.LayoutParams(
                dp(180),
                WindowManager.LayoutParams.WRAP_CONTENT,
                type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.CENTER_VERTICAL | Gravity.LEFT;
        SharedPreferences overlayPrefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        params.x = overlayPrefs.getInt("overlay_x", dp(10));
        params.y = overlayPrefs.getInt("overlay_y", dp(0));

        overlayView.setOnTouchListener(new View.OnTouchListener() {
            private int initialX;
            private int initialY;
            private float initialTouchX;
            private float initialTouchY;
            private long downAt;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                if (params == null || windowManager == null) return false;
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = params.x;
                        initialY = params.y;
                        initialTouchX = event.getRawX();
                        initialTouchY = event.getRawY();
                        downAt = System.currentTimeMillis();
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        params.x = initialX - Math.round(event.getRawX() - initialTouchX);
                        params.y = initialY + Math.round(event.getRawY() - initialTouchY);
                        try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                                .edit()
                                .putInt("overlay_x", params.x)
                                .putInt("overlay_y", params.y)
                                .apply();
                        // Toque fora dos botões não abre nada. Assim o card não atrapalha a live do Instagram.
                        return true;
                }
                return false;
            }
        });

        try {
            windowManager.addView(overlayView, params);
        } catch (Exception e) {
            overlayView = null;
        }
    }

    private Button makeButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(10);
        b.setTextColor(Color.WHITE);
        b.setMinHeight(dp(30));
        b.setMinimumHeight(dp(30));
        b.setPadding(dp(2), 0, dp(2), 0);
        b.setBackgroundColor(Color.argb(165, 168, 77, 58));
        return b;
    }

    private void fetchLiveCompanion() {
        new Thread(() -> {
            try {
                String root = getServerRoot();
                HttpURLConnection con = (HttpURLConnection) new URL(root + "/api/live/companion").openConnection();
                con.setRequestMethod("GET");
                con.setConnectTimeout(5000);
                con.setReadTimeout(5000);
                con.setRequestProperty("Accept", "application/json");
                String cookies = CookieManager.getInstance().getCookie(root);
                if (cookies != null && cookies.trim().length() > 0) {
                    con.setRequestProperty("Cookie", cookies);
                }
                if (con.getResponseCode() != 200) return;
                BufferedReader reader = new BufferedReader(new InputStreamReader(con.getInputStream()));
                StringBuilder body = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) body.append(line);
                reader.close();

                JSONObject data = new JSONObject(body.toString());
                JSONObject display = data.optJSONObject("display");
                if (display != null) {
                    currentPollMs = Math.max(800, Math.min(5000, display.optInt("poll_ms", currentPollMs)));
                    fullCardSeconds = Math.max(8, Math.min(120, display.optInt("full_card_seconds", fullCardSeconds)));
                    // No Android cliente, o card lateral fica ativo até a live encerrar ou a cliente fechar.
                    staleSeconds = 999999;
                }

                JSONObject links = data.optJSONObject("links");
                if (links != null) {
                    instagramUrl = links.optString("instagram_live", instagramUrl);
                    currentUrl = links.optString("current_product", root + "/cliente/live");
                }

                JSONObject session = data.optJSONObject("session");
                final String sessionStatus = session != null ? session.optString("status", "ao_vivo") : "";
                JSONObject product = data.optJSONObject("current_product");
                final String eventKey = data.optString("event_key", product != null ? product.optString("event_key_seed", "") : "sem-peca");
                final int elapsed = data.optInt("current_elapsed_seconds", display != null ? display.optInt("current_elapsed_seconds", 0) : 0);

                if (!data.optBoolean("ok", false) || product == null || !"ao_vivo".equals(sessionStatus)) {
                    handler.post(() -> {
                        lastEventKey = "sem-peca";
                        hideOverlay();
                    });
                    return;
                }

                if (eventKey.length() > 0 && eventKey.equals(dismissedEventKey)) {
                    handler.post(this::hideOverlay);
                    return;
                }

                final boolean isNewEvent = eventKey.length() > 0 && !eventKey.equals(lastEventKey);
                final String title = product.optString("title", "Peça atual");
                final String price = product.optString("price_label", "");
                final String code = product.optString("code", "");
                final String chatUrl = root + "/cliente/chat?origem=live&live=1&produto=" + Uri.encode(code == null ? "" : code);
                final String size = product.optString("size", "");
                final String status = product.optString("status", "");
                final String source = product.optString("source", "");
                String rawImageUrl = product.optString("image_url", "");
                if (rawImageUrl != null && rawImageUrl.startsWith("/")) {
                    rawImageUrl = root + rawImageUrl;
                }
                final String imageUrl = rawImageUrl == null ? "" : rawImageUrl;
                final String meta = String.format(Locale.getDefault(), "%s  •  Tam. %s  •  %s", code, size.length() > 0 ? size : "-", status);

                handler.post(() -> {
                    if (isNewEvent) {
                        lastEventKey = eventKey;
                        dismissedEventKey = "";
                    }
                    ensureOverlayVisible();
                    currentChatUrl = chatUrl;
                    updateOverlay(title, price, meta, sessionStatus, source, imageUrl, isNewEvent);
                    setCompact(elapsed >= fullCardSeconds);
                    scheduleAutoCompact(eventKey, elapsed);
                });
            } catch (Exception ignored) {
            }
        }).start();
    }

    private void scheduleAutoCompact(final String eventKey, int elapsedSeconds) {
        if (autoCompactRunnable != null) handler.removeCallbacks(autoCompactRunnable);
        int delayMs = Math.max(1000, (fullCardSeconds - Math.max(0, elapsedSeconds)) * 1000);
        autoCompactRunnable = () -> {
            if (eventKey != null && eventKey.equals(lastEventKey)) {
                setCompact(true);
            }
        };
        handler.postDelayed(autoCompactRunnable, delayMs);
    }

    private void ensureOverlayVisible() {
        showOverlay();
        if (overlayView != null && overlayView.getVisibility() != View.VISIBLE) {
            overlayView.setVisibility(View.VISIBLE);
        }
    }

    private void hideOverlay() {
        if (autoCompactRunnable != null) handler.removeCallbacks(autoCompactRunnable);
        if (overlayView != null) overlayView.setVisibility(View.GONE);
    }

    private void setCompact(boolean compactMode) {
        if (overlayView == null || params == null) return;
        compact = compactMode;
        int detailsVisibility = compact ? View.GONE : View.VISIBLE;
        priceView.setVisibility(detailsVisibility);
        metaView.setVisibility(detailsVisibility);
        // Em modo miniatura, mantém somente o botão fechar visível.
        buttonsRow.setVisibility(View.VISIBLE);
        if (actionButton != null) actionButton.setVisibility(detailsVisibility);
        if (chatButton != null) chatButton.setVisibility(detailsVisibility);
        if (instagramButton != null) instagramButton.setVisibility(detailsVisibility);
        if (hideButton != null) hideButton.setVisibility(View.VISIBLE);
        titleView.setMaxLines(compact ? 1 : 2);
        statusView.setTextSize(compact ? 10 : 12);
        if (thumbnailView != null) {
            ViewGroup.LayoutParams lp = thumbnailView.getLayoutParams();
            if (lp != null) {
                lp.width = compact ? dp(48) : dp(64);
                lp.height = compact ? dp(56) : dp(72);
                thumbnailView.setLayoutParams(lp);
            }
        }
        params.width = compact ? dp(108) : dp(160);
        try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
    }

    private void updateOverlay(String title, String price, String meta, String status, String source, String imageUrl, boolean isNewEvent) {
        if (titleView == null) return;
        String normalizedStatus = status == null || status.length() == 0 ? "live" : status.replace("_", " ");
        String prefix = isNewEvent ? "NOVA PEÇA" : "BRECHORISEE";
        if (source != null && source.length() > 0 && !source.equals("central")) {
            prefix += " • " + source.replace("_", " ");
        }
        statusView.setText(prefix + " • " + normalizedStatus);
        titleView.setText(title);
        priceView.setText(price);
        metaView.setText(meta);
        updateThumbnail(imageUrl);
    }

    private void updateThumbnail(String imageUrl) {
        if (thumbnailView == null) return;
        if (imageUrl == null || imageUrl.trim().length() == 0) {
            thumbnailView.setVisibility(View.GONE);
            lastImageUrl = "";
            return;
        }
        thumbnailView.setVisibility(View.VISIBLE);
        if (imageUrl.equals(lastImageUrl)) return;
        lastImageUrl = imageUrl;
        new Thread(() -> {
            try {
                HttpURLConnection con = (HttpURLConnection) new URL(imageUrl).openConnection();
                con.setConnectTimeout(5000);
                con.setReadTimeout(5000);
                con.setRequestProperty("Accept", "image/*");
                InputStream input = con.getInputStream();
                final Bitmap bitmap = BitmapFactory.decodeStream(input);
                try { input.close(); } catch (Exception ignored) {}
                if (bitmap != null) {
                    handler.post(() -> {
                        if (thumbnailView != null && imageUrl.equals(lastImageUrl)) {
                            thumbnailView.setImageBitmap(bitmap);
                        }
                    });
                }
            } catch (Exception ignored) {}
        }).start();
    }

    private void openUrl(String url) {
        try {
            Intent intent = new Intent(this, MainActivity.class);
            intent.setAction(Intent.ACTION_VIEW);
            intent.setData(Uri.parse(url));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            startActivity(intent);
        } catch (Exception ignored) {}
    }

    private void openExternal(String url) {
        if (isInstagramUrl(url)) {
            openInstagramApp(url);
            return;
        }
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception ignored) {}
    }

    private boolean isInstagramUrl(String url) {
        if (url == null) return false;
        try {
            Uri uri = Uri.parse(url);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.US);
            String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.US);
            return scheme.equals("instagram")
                    || host.equals("instagram.com")
                    || host.equals("www.instagram.com")
                    || host.endsWith(".instagram.com");
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean openInstagramApp(String url) {
        Uri target = Uri.parse("instagram://app");
        try {
            if (url != null && url.trim().length() > 0) {
                Uri parsed = Uri.parse(url);
                if (isInstagramUrl(url)) target = parsed;
            }
        } catch (Exception ignored) {}

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
            return true;
        } catch (Exception ignored) {}
        return false;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        running = false;
        handler.removeCallbacks(pollRunnable);
        if (autoCompactRunnable != null) handler.removeCallbacks(autoCompactRunnable);
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        running = false;
        handler.removeCallbacks(pollRunnable);
        if (autoCompactRunnable != null) handler.removeCallbacks(autoCompactRunnable);
        if (windowManager != null && overlayView != null) {
            try { windowManager.removeView(overlayView); } catch (Exception ignored) {}
            overlayView = null;
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
