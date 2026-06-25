package com.brechorisee.admin;

import android.app.Service;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.util.List;

/**
 * Camada flutuante do Assistente Instagram BRECHORISEE.
 *
 * Esta classe não clica no Instagram. Ela faz captura explícita, autorizada
 * pelo Android, observa a live de forma contínua e envia frames ao servidor
 * BRECHORISEE para publicar automaticamente a peça atual quando houver confiança.
 */
public class InstagramAssistantOverlayService extends Service {
    public static final String ACTION_CAPTURE_READY = "com.brechorisee.admin.CAPTURE_READY";
    private static final String CHANNEL_ID = "brechorisee_instagram_assistant";
    private static final String INSTAGRAM_PACKAGE = "com.instagram.android";

    private static final String OVERLAY_PREFS = "brechorisee_admin_overlay_position";
    private WindowManager windowManager;
    private View overlayView;
    private WindowManager.LayoutParams overlayParams;
    private TextView statusView;
    private String baseUrl = "https://brechorisee-online.onrender.com";
    private String targetInstagramUri = "instagram://app";
    private String lastText = "Assistente automático pronto. Abra a live no Instagram.";
    private String lastCopyText = "Assistente Instagram BRECHORISEE pronto.";
    private boolean lastRequestLiveMode = false;
    private int resultCode = 0;
    private Intent resultData = null;

    private MediaProjection mediaProjection = null;
    private MediaProjection.Callback projectionCallback = null;
    private ImageReader screenReader = null;
    private VirtualDisplay virtualDisplay = null;
    private int captureWidth = 0;
    private int captureHeight = 0;
    private int captureDpi = 0;
    private final Object captureLock = new Object();

    private final Handler handler = new Handler(Looper.getMainLooper());
    private Button autoLiveButton = null;
    private boolean autoLiveMode = false;
    private boolean recognitionBusy = false;
    private boolean requestingCapturePermission = false;
    private boolean pendingAutoStartAfterPermission = false;
    private static final long AUTO_RECOGNITION_INTERVAL_MS = 3500L;
    private static final long OUTSIDE_INSTAGRAM_GRACE_MS = 4500L;
    private long overlayStartedAtMs = 0L;
    private long lastInstagramSeenAtMs = 0L;
    private boolean foregroundGuardRunning = false;

    private final Runnable foregroundGuardRunnable = new Runnable() {
        @Override
        public void run() {
            String foregroundPackage = getForegroundPackageName();
            long now = System.currentTimeMillis();
            if (INSTAGRAM_PACKAGE.equals(foregroundPackage)) {
                lastInstagramSeenAtMs = now;
            } else if (foregroundPackage != null
                    && overlayStartedAtMs > 0L
                    && now - overlayStartedAtMs > OUTSIDE_INSTAGRAM_GRACE_MS
                    && (lastInstagramSeenAtMs > 0L
                        || !getPackageName().equals(foregroundPackage)
                        || now - overlayStartedAtMs > 8000L)
                    && (lastInstagramSeenAtMs == 0L || now - lastInstagramSeenAtMs > 1800L)) {
                pauseAndCloseOverlayOutsideInstagram(foregroundPackage);
                return;
            }
            handler.postDelayed(this, 900L);
        }
    };

    private final Runnable autoRecognizeRunnable = new Runnable() {
        @Override
        public void run() {
            if (!autoLiveMode) return;
            if (!recognitionBusy) {
                recognizeCurrentScreen(true);
            }
            handler.postDelayed(this, AUTO_RECOGNITION_INTERVAL_MS);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        startAssistantForeground("Assistente Instagram ativo", false);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            String extra = intent.getStringExtra("base_url");
            if (extra != null && extra.trim().length() > 0) {
                baseUrl = normalizeBaseUrl(extra);
            }
            String targetExtra = intent.getStringExtra("target_instagram_uri");
            if (targetExtra != null && targetExtra.trim().length() > 0) {
                targetInstagramUri = targetExtra.trim();
            }
            if (ACTION_CAPTURE_READY.equals(intent.getAction())) {
                requestingCapturePermission = false;
                int newResultCode = intent.getIntExtra("result_code", 0);
                Intent newResultData = intent.getParcelableExtra("result_data");

                synchronized (captureLock) {
                    releaseCaptureSessionLocked(true);
                }

                resultCode = newResultCode;
                resultData = newResultData;
                if (resultCode != 0 && resultData != null) {
                    startAssistantForeground("Captura autorizada para Post/Reels/Live", true);
                    lastText = "Captura autorizada. A captura estável foi preparada para não piscar o painel.";
                    updateStatus(lastText);
                    prepareCaptureSessionAsync();
                    if (pendingAutoStartAfterPermission) {
                        pendingAutoStartAfterPermission = false;
                        handler.postDelayed(() -> startAutoLiveMode(), 650);
                    }
                } else {
                    clearCaptureAuthorization();
                    pendingAutoStartAfterPermission = false;
                    lastText = "Captura não autorizada. Autorize uma vez para o reconhecimento automático da live.";
                    updateStatus(lastText);
                }
            }
        }
        if (overlayStartedAtMs == 0L) {
            overlayStartedAtMs = System.currentTimeMillis();
        }
        startForegroundGuard();
        showOverlay();
        handler.postDelayed(() -> startAutoLiveMode(), 900);
        return START_NOT_STICKY;
    }

    private String normalizeBaseUrl(String raw) {
        String value = raw.trim();
        if (value.endsWith("/admin-acesso")) value = value.substring(0, value.length() - "/admin-acesso".length());
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        return value;
    }

    private void startForegroundGuard() {
        if (foregroundGuardRunning) return;
        foregroundGuardRunning = true;
        handler.removeCallbacks(foregroundGuardRunnable);
        handler.postDelayed(foregroundGuardRunnable, 900L);
    }

    private void showOverlay() {
        if (overlayView != null) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Permita sobrepor a outros apps para mostrar por cima do Instagram.", Toast.LENGTH_LONG).show();
            return;
        }

        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(12, 8, 12, 8);
        box.setBackgroundColor(Color.argb(125, 31, 21, 28));
        box.setAlpha(0.72f);

        TextView dragHandle = new TextView(this);
        dragHandle.setText("⠿ BRECHORISEE");
        dragHandle.setTextColor(Color.rgb(255, 224, 232));
        dragHandle.setTextSize(10);
        dragHandle.setGravity(Gravity.CENTER);
        dragHandle.setPadding(0, 0, 0, 6);
        box.addView(dragHandle);

        TextView title = new TextView(this);
        title.setText("Assistente");
        title.setTextColor(Color.WHITE);
        title.setTextSize(12);
        title.setGravity(Gravity.CENTER);
        box.addView(title);

        statusView = new TextView(this);
        statusView.setText(lastText);
        statusView.setTextColor(Color.rgb(255, 232, 241));
        statusView.setTextSize(10);
        statusView.setPadding(0, 8, 0, 8);
        box.addView(statusView);

        LinearLayout row1 = new LinearLayout(this);
        row1.setOrientation(LinearLayout.HORIZONTAL);
        autoLiveButton = button(autoLiveMode ? "Auto ON" : "Auto", v -> toggleAutoLiveMode());
        row1.addView(autoLiveButton);
        box.addView(row1);

        LinearLayout row2 = new LinearLayout(this);
        row2.setOrientation(LinearLayout.HORIZONTAL);
        row2.addView(button("Copiar", v -> copyLastMessage()));
        row2.addView(button("Painel", v -> openPanel()));
        box.addView(row2);

        LinearLayout row3 = new LinearLayout(this);
        row3.setOrientation(LinearLayout.HORIZONTAL);
        row3.addView(button("IG", v -> openInstagram()));
        row3.addView(button("×", v -> stopSelf()));
        box.addView(row3);

        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;

        overlayParams = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT
        );
        overlayParams.gravity = Gravity.TOP | Gravity.START;
        SharedPreferences pos = getSharedPreferences(OVERLAY_PREFS, Context.MODE_PRIVATE);
        overlayParams.x = pos.getInt("x", dp(12));
        overlayParams.y = pos.getInt("y", dp(150));

        overlayView = box;
        attachDraggable(dragHandle);
        try {
            windowManager.addView(overlayView, overlayParams);
        } catch (Exception ex) {
            overlayView = null;
            Toast.makeText(this, "Falha ao mostrar overlay: " + ex.getMessage(), Toast.LENGTH_LONG).show();
        }
    }



    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }

    private void attachDraggable(View dragHandle) {
        dragHandle.setOnTouchListener(new View.OnTouchListener() {
            private int initialX;
            private int initialY;
            private float initialTouchX;
            private float initialTouchY;
            private boolean moved;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                if (overlayParams == null || windowManager == null || overlayView == null) return false;
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = overlayParams.x;
                        initialY = overlayParams.y;
                        initialTouchX = event.getRawX();
                        initialTouchY = event.getRawY();
                        moved = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        int dx = Math.round(event.getRawX() - initialTouchX);
                        int dy = Math.round(event.getRawY() - initialTouchY);
                        if (Math.abs(dx) > dp(3) || Math.abs(dy) > dp(3)) moved = true;
                        overlayParams.x = Math.max(0, initialX + dx);
                        overlayParams.y = Math.max(0, initialY + dy);
                        try { windowManager.updateViewLayout(overlayView, overlayParams); } catch (Exception ignored) {}
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        getSharedPreferences(OVERLAY_PREFS, Context.MODE_PRIVATE)
                                .edit()
                                .putInt("x", overlayParams.x)
                                .putInt("y", overlayParams.y)
                                .apply();
                        return true;
                }
                return false;
            }
        });
    }

    private Button button(String text, View.OnClickListener listener) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(9);
        b.setAlpha(0.55f);
        b.setMinHeight(dp(30));
        b.setMinimumHeight(dp(30));
        b.setPadding(2, 0, 2, 0);
        b.setOnClickListener(listener);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(34), 1);
        lp.setMargins(2, 2, 2, 2);
        b.setLayoutParams(lp);
        return b;
    }

    private void updateStatus(final String text) {
        lastText = text;
        if (statusView != null) {
            statusView.post(() -> statusView.setText(text));
        }
    }

    private void toggleAutoLiveMode() {
        if (autoLiveMode) {
            stopAutoLiveMode("Modo ao vivo automático desligado.");
            return;
        }

        if (!hasCaptureAuthorization()) {
            pendingAutoStartAfterPermission = true;
            updateStatus("Para ligar o Ao vivo auto, autorize a captura uma vez. Depois o modo automático inicia sem piscar o painel.");
            openCapturePermission();
            return;
        }

        startAutoLiveMode();
    }

    private boolean hasCaptureAuthorization() {
        return resultCode != 0 && resultData != null;
    }

    private void startAutoLiveMode() {
        if (!hasCaptureAuthorization()) {
            pendingAutoStartAfterPermission = true;
            openCapturePermission();
            return;
        }
        autoLiveMode = true;
        recognitionBusy = false;
        setAutoButtonText("Auto ligado");
        updateStatus("Ao vivo auto ligado em modo estável. O painel não será mais escondido e mostrado a cada leitura.");
        handler.removeCallbacks(autoRecognizeRunnable);
        handler.postDelayed(autoRecognizeRunnable, 350);
    }

    private void stopAutoLiveMode(String message) {
        autoLiveMode = false;
        pendingAutoStartAfterPermission = false;
        handler.removeCallbacks(autoRecognizeRunnable);
        setAutoButtonText("Automático");
        updateStatus(message);
    }

    private void setAutoButtonText(final String text) {
        if (autoLiveButton != null) {
            autoLiveButton.post(() -> autoLiveButton.setText(text));
        }
    }

    private void openCapturePermission() {
        if (requestingCapturePermission) {
            updateStatus("Pedido de autorização já está aberto. Conclua a permissão do Android.");
            return;
        }
        requestingCapturePermission = true;
        Intent intent = new Intent(this, ScreenCapturePermissionActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        intent.putExtra("base_url", baseUrl);
        intent.putExtra("target_instagram_uri", targetInstagramUri);
        startActivity(intent);
        updateStatus("Autorize a captura. Depois deixe a live do Instagram visível; o reconhecimento será automático.");
    }

    private void recognizeCurrentScreen(boolean liveMode) {
        if (recognitionBusy) return;

        String foregroundPackage = getForegroundPackageName();
        if (foregroundPackage != null && !INSTAGRAM_PACKAGE.equals(foregroundPackage)) {
            pauseAndCloseOverlayOutsideInstagram(foregroundPackage);
            return;
        }

        if (!hasCaptureAuthorization()) {
            if (liveMode) {
                stopAutoLiveMode("Ao vivo auto pausado: autorize a captura de tela para continuar.");
                pendingAutoStartAfterPermission = true;
            }
            openCapturePermission();
            return;
        }
        recognitionBusy = true;
        lastRequestLiveMode = liveMode;
        updateStatus(liveMode ? "Reconhecendo live em modo estável..." : "Capturando tela do Instagram...");

        new Thread(() -> {
            try {
                byte[] jpeg = captureScreenshotJpeg();
                String response = postRecognition(jpeg, liveMode);
                handleRecognitionResponse(response);
            } catch (Exception ex) {
                handleCaptureOrRecognitionFailure(ex, liveMode);
            } finally {
                recognitionBusy = false;
            }
        }).start();
    }

    private void prepareCaptureSessionAsync() {
        new Thread(() -> {
            try {
                synchronized (captureLock) {
                    ensureCaptureSessionLocked();
                }
            } catch (Exception ex) {
                handleCaptureOrRecognitionFailure(ex, false);
            }
        }).start();
    }

    private void ensureCaptureSessionLocked() throws Exception {
        WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        DisplayMetrics metrics = new DisplayMetrics();
        wm.getDefaultDisplay().getRealMetrics(metrics);
        final int width = metrics.widthPixels;
        final int height = metrics.heightPixels;
        final int dpi = metrics.densityDpi;

        if (mediaProjection != null && screenReader != null && virtualDisplay != null
                && captureWidth == width && captureHeight == height && captureDpi == dpi) {
            return;
        }

        if (mediaProjection != null && (captureWidth != 0 || captureHeight != 0)
                && (captureWidth != width || captureHeight != height || captureDpi != dpi)) {
            throw new Exception("tamanho da tela mudou. Renove a autorização de captura.");
        }

        if (mediaProjection == null) {
            if (!hasCaptureAuthorization()) {
                throw new Exception("permissão de captura ausente");
            }
            MediaProjectionManager manager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
            mediaProjection = manager.getMediaProjection(resultCode, resultData);
            if (mediaProjection == null) throw new Exception("permissão de captura inválida ou expirada");
            projectionCallback = new MediaProjection.Callback() {
                @Override
                public void onStop() {
                    synchronized (captureLock) {
                        releaseCaptureSessionLocked(false);
                        mediaProjection = null;
                        projectionCallback = null;
                    }
                    clearCaptureAuthorization();
                    handler.removeCallbacks(autoRecognizeRunnable);
                    autoLiveMode = false;
                    setAutoButtonText("Automático");
                    updateStatus("Captura encerrada pelo Android. Toque em Reconhecer ou Ao vivo auto para autorizar novamente.");
                }
            };
            mediaProjection.registerCallback(projectionCallback, handler);
        }

        if (screenReader == null) {
            captureWidth = width;
            captureHeight = height;
            captureDpi = dpi;
            screenReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 3);
        }

        if (virtualDisplay == null) {
            virtualDisplay = mediaProjection.createVirtualDisplay(
                    "brechorisee-instagram-live-stable",
                    captureWidth,
                    captureHeight,
                    captureDpi,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    screenReader.getSurface(),
                    null,
                    handler
            );
        }
    }

    private byte[] captureScreenshotJpeg() throws Exception {
        Image image = null;
        Bitmap bitmap = null;
        Bitmap cropped = null;
        try {
            synchronized (captureLock) {
                ensureCaptureSessionLocked();

                for (int i = 0; i < 15; i++) {
                    Thread.sleep(i == 0 ? 80 : 120);
                    Image candidate = screenReader.acquireLatestImage();
                    if (candidate != null) {
                        if (image != null) {
                            try { image.close(); } catch (Exception ignored) {}
                        }
                        image = candidate;
                        break;
                    }
                }

                if (image == null) throw new Exception("print não ficou pronto");

                Image.Plane[] planes = image.getPlanes();
                ByteBuffer buffer = planes[0].getBuffer();
                int pixelStride = planes[0].getPixelStride();
                int rowStride = planes[0].getRowStride();
                int rowPadding = rowStride - pixelStride * captureWidth;

                bitmap = Bitmap.createBitmap(captureWidth + rowPadding / pixelStride, captureHeight, Bitmap.Config.ARGB_8888);
                bitmap.copyPixelsFromBuffer(buffer);
                cropped = Bitmap.createBitmap(bitmap, 0, 0, captureWidth, captureHeight);
            }

            Bitmap outBitmap = cropped;
            int maxSide = Math.max(outBitmap.getWidth(), outBitmap.getHeight());
            if (maxSide > 760) {
                float scale = 760f / (float) maxSide;
                outBitmap = Bitmap.createScaledBitmap(
                        outBitmap,
                        Math.max(1, Math.round(outBitmap.getWidth() * scale)),
                        Math.max(1, Math.round(outBitmap.getHeight() * scale)),
                        true
                );
            }
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            outBitmap.compress(Bitmap.CompressFormat.JPEG, 66, baos);
            try { if (outBitmap != cropped && !outBitmap.isRecycled()) outBitmap.recycle(); } catch (Exception ignored) {}
            return baos.toByteArray();
        } finally {
            try { if (image != null) image.close(); } catch (Exception ignored) {}
            try { if (bitmap != null && !bitmap.isRecycled()) bitmap.recycle(); } catch (Exception ignored) {}
            try { if (cropped != null && !cropped.isRecycled()) cropped.recycle(); } catch (Exception ignored) {}
        }
    }

    private void releaseCaptureSessionLocked(boolean stopProjection) {
        try { if (virtualDisplay != null) virtualDisplay.release(); } catch (Exception ignored) {}
        virtualDisplay = null;

        try { if (screenReader != null) screenReader.close(); } catch (Exception ignored) {}
        screenReader = null;

        captureWidth = 0;
        captureHeight = 0;
        captureDpi = 0;

        if (stopProjection && mediaProjection != null) {
            try {
                if (projectionCallback != null) mediaProjection.unregisterCallback(projectionCallback);
            } catch (Exception ignored) {}
            try { mediaProjection.stop(); } catch (Exception ignored) {}
            mediaProjection = null;
            projectionCallback = null;
        }
    }

    private void clearCaptureAuthorization() {
        resultCode = 0;
        resultData = null;
        requestingCapturePermission = false;
    }

    private void handleCaptureOrRecognitionFailure(Exception ex, boolean liveMode) {
        String message = ex == null || ex.getMessage() == null ? "erro desconhecido" : ex.getMessage();
        String lower = message.toLowerCase();

        if (lower.contains("media projection")
                || lower.contains("mediaprojection")
                || lower.contains("resultdata")
                || lower.contains("virtualdisplay")
                || lower.contains("token")
                || lower.contains("captura inválida")
                || lower.contains("captura ausente")
                || lower.contains("expirada")
                || lower.contains("tamanho da tela mudou")) {
            synchronized (captureLock) {
                releaseCaptureSessionLocked(true);
            }
            clearCaptureAuthorization();
            if (liveMode) {
                stopAutoLiveMode("Ao vivo auto pausado: a permissão de captura expirou. Toque em Ao vivo auto e autorize novamente.");
                pendingAutoStartAfterPermission = true;
            } else {
                updateStatus("Permissão de captura expirada. Toque em Reconhecer para autorizar novamente.");
            }
            return;
        }

        updateStatus("Não consegui reconhecer: " + message);
    }

    private String postRecognition(byte[] jpegBytes, boolean liveMode) throws Exception {
        String boundary = "----BrechoriseeBoundary" + System.currentTimeMillis();
        URL url = new URL(baseUrl + "/api/instagram-assistant/recognize-screen");
        HttpURLConnection con = (HttpURLConnection) url.openConnection();
        con.setConnectTimeout(9000);
        con.setReadTimeout(14000);
        con.setRequestMethod("POST");
        con.setDoInput(true);
        con.setDoOutput(true);
        con.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        con.setRequestProperty("Accept", "application/json");

        DataOutputStream out = new DataOutputStream(con.getOutputStream());
        writeFormField(out, boundary, "source_text", liveMode ? "android_overlay_live" : "android_overlay_post_reels");
        writeFormField(out, boundary, "notify_telegram", "1");
        writeFormField(out, boundary, "send_to_clients", "0");
        writeFormField(out, boundary, "live_mode", liveMode ? "1" : "0");
        writeFormField(out, boundary, "auto_clear", "1");
        writeFormField(out, boundary, "assistant_token", "");

        out.writeBytes("--" + boundary + "\r\n");
        out.writeBytes("Content-Disposition: form-data; name=\"image\"; filename=\"instagram-screen.jpg\"\r\n");
        out.writeBytes("Content-Type: image/jpeg\r\n\r\n");
        out.write(jpegBytes);
        out.writeBytes("\r\n");
        out.writeBytes("--" + boundary + "--\r\n");
        out.flush();
        out.close();

        int code = con.getResponseCode();
        InputStream stream = code >= 200 && code < 300 ? con.getInputStream() : con.getErrorStream();
        String body = readAll(stream);
        if (code < 200 || code >= 300) {
            throw new Exception("servidor " + code + ": " + body);
        }
        return body;
    }

    private void writeFormField(DataOutputStream out, String boundary, String name, String value) throws Exception {
        out.writeBytes("--" + boundary + "\r\n");
        out.writeBytes("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n");
        out.writeBytes(value == null ? "" : value);
        out.writeBytes("\r\n");
    }

    private String readAll(InputStream stream) throws Exception {
        if (stream == null) return "";
        BufferedReader br = new BufferedReader(new InputStreamReader(stream, "UTF-8"));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = br.readLine()) != null) sb.append(line);
        br.close();
        return sb.toString();
    }

    private void handleRecognitionResponse(String response) {
        try {
            JSONObject json = new JSONObject(response);
            boolean responseLiveMode = json.optBoolean("live_mode", lastRequestLiveMode);
            boolean outsideInstagram = json.optBoolean("outside_instagram", false)
                    || "fora_instagram".equalsIgnoreCase(json.optString("screen_context", ""));

            if (outsideInstagram) {
                lastCopyText = "";
                stopAutoLiveMode("Saí do Instagram. Assistente pausado automaticamente.");
                updateStatus(json.optString("message", "Fora do Instagram. O assistente foi pausado para evitar reconhecimento falso."));
                handler.postDelayed(() -> stopSelf(), 900);
                return;
            }

            JSONArray products = json.optJSONArray("products");
            JSONObject top = json.optJSONObject("top_product");
            boolean liveUpdated = json.optBoolean("live_updated", false);
            int liveReferences = json.optInt("live_references_added", 0);

            if (products != null && products.length() > 0) {
                StringBuilder status = new StringBuilder();
                status.append(liveUpdated ? "AO VIVO atualizado" : "Peça reconhecida");
                status.append(" • ").append(products.length()).append(" peça(s)");
                status.append("\n");
                StringBuilder copy = new StringBuilder();
                int max = Math.min(products.length(), 4);
                for (int i = 0; i < max; i++) {
                    JSONObject item = products.optJSONObject(i);
                    if (item == null) continue;
                    String code = item.optString("code", "");
                    String title = item.optString("title", "Peça");
                    String price = item.optString("price_label", "");
                    double score = item.optDouble("recognition_score", 0);
                    if (i == 0) {
                        status.append(code).append(" • ").append(title)
                                .append(" • score ").append(String.format("%.1f", score));
                    } else {
                        status.append("\n+ ").append(code).append(" • ").append(title)
                                .append(" • ").append(String.format("%.1f", score));
                    }
                    copy.append(title).append("\nCód: ").append(code);
                    if (price.length() > 0) copy.append("\nValor: ").append(price);
                    String link = item.optString("public_url", "");
                    if (link.length() > 0) copy.append("\n").append(link);
                    copy.append("\n\n");
                }
                if (liveReferences > 0) {
                    status.append("\nReferências extras salvas: ").append(liveReferences);
                }
                lastCopyText = copy.toString().trim();
                updateStatus(status.toString());
                return;
            }

            JSONArray low = json.optJSONArray("low_confidence");
            if (!responseLiveMode && low != null && low.length() > 0) {
                JSONObject item = low.optJSONObject(0);
                if (item != null) {
                    String code = item.optString("code", "");
                    String title = item.optString("title", "Peça parecida");
                    double score = item.optDouble("recognition_score", 0);
                    lastCopyText = "Possível peça: " + code + " • " + title;
                    updateStatus("Possível peça, mas baixa confiança: " + code + " • " + title + "\nScore " + String.format("%.1f", score) + ". Aproxime a peça e tente de novo.");
                    return;
                }
            }
            lastCopyText = "";
            String msg = json.optString("message", "Nenhuma peça reconhecida.");
            if (json.optInt("live_session_id", 0) > 0) {
                msg += "\nLive limpa: nenhuma peça atual no card da cliente.";
            }
            updateStatus(msg);
        } catch (Exception ex) {
            updateStatus("Resposta recebida, mas não consegui ler: " + ex.getMessage());
        }
    }


    private String getForegroundPackageName() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return null;
        try {
            UsageStatsManager usageStatsManager = (UsageStatsManager) getSystemService(Context.USAGE_STATS_SERVICE);
            if (usageStatsManager == null) return null;
            long now = System.currentTimeMillis();
            List<UsageStats> stats = usageStatsManager.queryUsageStats(
                    UsageStatsManager.INTERVAL_DAILY,
                    now - 60_000L,
                    now
            );
            if (stats == null || stats.isEmpty()) return null;
            UsageStats recent = null;
            for (UsageStats item : stats) {
                if (item == null || item.getPackageName() == null) continue;
                if (recent == null || item.getLastTimeUsed() > recent.getLastTimeUsed()) {
                    recent = item;
                }
            }
            return recent == null ? null : recent.getPackageName();
        } catch (Exception ignored) {
            return null;
        }
    }

    private void pauseAndCloseOverlayOutsideInstagram(String foregroundPackage) {
        String packageName = foregroundPackage == null ? "outro app" : foregroundPackage;
        lastCopyText = "";
        autoLiveMode = false;
        pendingAutoStartAfterPermission = false;
        foregroundGuardRunning = false;
        handler.removeCallbacks(autoRecognizeRunnable);
        handler.removeCallbacks(foregroundGuardRunnable);
        setAutoButtonText("Automático");
        updateStatus("Fora do Instagram. Assistente pausado para não reconhecer tela errada.");
        Toast.makeText(this, "BRECHORISEE: saí do Instagram (" + packageName + "), assistente fechado.", Toast.LENGTH_SHORT).show();
        handler.postDelayed(() -> stopSelf(), 650);
    }

    private void callAssistantStatus() {
        updateStatus("Consultando controle...");
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + "/api/instagram-assistant/status");
                HttpURLConnection con = (HttpURLConnection) url.openConnection();
                con.setConnectTimeout(8000);
                con.setReadTimeout(8000);
                con.setRequestMethod("GET");
                readAll(con.getInputStream());
                updateStatus("Controle online. Post/Reels/Live prontos para reconhecimento.");
            } catch (Exception ex) {
                updateStatus("Controle indisponível: " + ex.getMessage());
            }
        }).start();
    }

    private void copyLastMessage() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        ClipData clip = ClipData.newPlainText("BRECHORISEE", lastCopyText);
        clipboard.setPrimaryClip(clip);
        Toast.makeText(this, "Mensagem da peça copiada.", Toast.LENGTH_SHORT).show();
    }

    private void openPanel() {
        stopAutoLiveMode("Painel aberto. Assistente do Instagram pausado.");
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(baseUrl + "/admin-acesso"));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(i);
        handler.postDelayed(() -> stopSelf(), 700);
    }

    private void openInstagram() {
        try {
            Uri uri = Uri.parse(targetInstagramUri == null || targetInstagramUri.trim().isEmpty() ? "instagram://app" : targetInstagramUri.trim());
            Intent direct = new Intent(Intent.ACTION_VIEW, uri);
            direct.setPackage("com.instagram.android");
            direct.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            startActivity(direct);
            return;
        } catch (Exception ignored) {}

        try {
            Intent launch = getPackageManager().getLaunchIntentForPackage("com.instagram.android");
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                startActivity(launch);
                return;
            }
        } catch (Exception ignored) {}

        try {
            Intent market = new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.instagram.android"));
            market.setPackage("com.android.vending");
            market.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(market);
            return;
        } catch (Exception ignored) {}
        updateStatus("Instagram não encontrado no celular.");
    }

    private void startAssistantForeground(String text, boolean mediaProjectionMode) {
        Notification notification = buildNotification(text);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            int type = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC;
            if (mediaProjectionMode) {
                type = type | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION;
            }
            startForeground(9217, notification, type);
        } else {
            startForeground(9217, notification);
        }
    }

    private Notification buildNotification(String text) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        builder.setContentTitle("BRECHORISEE")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_menu_camera)
                .setOngoing(true);
        return builder.build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Assistente Instagram BRECHORISEE",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            nm.createNotificationChannel(channel);
        }
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        autoLiveMode = false;
        foregroundGuardRunning = false;
        handler.removeCallbacks(autoRecognizeRunnable);
        handler.removeCallbacks(foregroundGuardRunnable);
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        autoLiveMode = false;
        foregroundGuardRunning = false;
        handler.removeCallbacks(autoRecognizeRunnable);
        handler.removeCallbacks(foregroundGuardRunnable);
        if (windowManager != null && overlayView != null) {
            try { windowManager.removeView(overlayView); } catch (Exception ignored) {}
        }
        overlayView = null;
        synchronized (captureLock) {
            releaseCaptureSessionLocked(true);
        }
        clearCaptureAuthorization();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
