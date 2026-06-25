package com.brechorisee.cliente;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.webkit.CookieManager;

import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

import org.json.JSONObject;

public class LiveNotificationService extends Service {
    private static final String DEFAULT_ROOT = "https://brechorisee-online.onrender.com";
    private static final String PREFS = "brechorisee_prefs";
    private static final String KEY_URL = "server_url";
    private static final String KEY_LAST_LIVE_NOTIFICATION_ID = "last_live_notification_id";
    private static final String LIVE_CHANNEL = "brechorisee_live";
    private static final String MONITOR_CHANNEL = "brechorisee_live_monitor";
    private static final int MONITOR_NOTIFICATION_ID = 8810;

    private Handler handler = new Handler(Looper.getMainLooper());
    private boolean running = false;
    private int intervalMs = 12000;

    private final Runnable pollRunnable = new Runnable() {
        @Override
        public void run() {
            if (!running) return;
            checkLiveNotification();
            handler.postDelayed(this, intervalMs);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        createChannels();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && intent.getStringExtra("server_root") != null) {
            getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit()
                    .putString(KEY_URL, intent.getStringExtra("server_root") + "/cliente")
                    .apply();
        }
        startMonitorForeground();
        running = true;
        handler.removeCallbacks(pollRunnable);
        handler.post(pollRunnable);
        return START_NOT_STICKY;
    }

    private void createChannels() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager == null) return;
            NotificationChannel live = new NotificationChannel(
                    LIVE_CHANNEL,
                    "Lives BRECHORISEE",
                    NotificationManager.IMPORTANCE_HIGH
            );
            live.setDescription("Avisos quando uma live começa e quando há interação importante.");
            manager.createNotificationChannel(live);

            NotificationChannel monitor = new NotificationChannel(
                    MONITOR_CHANNEL,
                    "Monitor BRECHORISEE",
                    NotificationManager.IMPORTANCE_MIN
            );
            monitor.setDescription("Mantém o app atento a lives quando você deixou o monitor ligado.");
            manager.createNotificationChannel(monitor);
        }
    }

    private void startMonitorForeground() {
        try {
            Intent intent = new Intent(this, MainActivity.class);
            intent.setData(Uri.parse("brechorisee://live"));
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
            PendingIntent pendingIntent = PendingIntent.getActivity(this, 8811, intent, flags);

            NotificationCompat.Builder builder = new NotificationCompat.Builder(this, MONITOR_CHANNEL)
                    .setSmallIcon(android.R.drawable.ic_menu_camera)
                    .setContentTitle("BRECHORISEE")
                    .setContentText("Acompanhando avisos da live.")
                    .setPriority(NotificationCompat.PRIORITY_MIN)
                    .setOngoing(true)
                    .setContentIntent(pendingIntent);

            startForeground(MONITOR_NOTIFICATION_ID, builder.build());
        } catch (Exception ignored) {
        }
    }

    private String getServerRoot() {
        SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String url = prefs.getString(KEY_URL, DEFAULT_ROOT + "/cliente");
        int schemeEnd = url.indexOf("://");
        if (schemeEnd >= 0) {
            int slash = url.indexOf("/", schemeEnd + 3);
            if (slash > 0) return url.substring(0, slash);
        }
        return url.replaceAll("/+$", "");
    }

    private void checkLiveNotification() {
        new Thread(() -> {
            try {
                String root = getServerRoot();
                HttpURLConnection con = (HttpURLConnection) new URL(root + "/api/cliente/notificacoes/live-alert").openConnection();
                con.setRequestMethod("GET");
                con.setConnectTimeout(6000);
                con.setReadTimeout(6000);
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
                if (!data.optBoolean("ok")) return;
                JSONObject notification = data.optJSONObject("notification");
                if (notification == null) return;

                int id = notification.optInt("id", 0);
                SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
                int lastId = prefs.getInt(KEY_LAST_LIVE_NOTIFICATION_ID, 0);
                if (id <= 0 || id == lastId) return;
                prefs.edit().putInt(KEY_LAST_LIVE_NOTIFICATION_ID, id).apply();

                String title = notification.optString("title", "BRECHORISEE ao vivo agora ✨");
                String message = notification.optString("message", "Toque para entrar direto na live.");
                showLiveNotification(id, title, message);
            } catch (Exception ignored) {
            }
        }).start();
    }

    private void showLiveNotification(int notificationId, String title, String message) {
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
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

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, LIVE_CHANNEL)
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

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        running = false;
        handler.removeCallbacks(pollRunnable);
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        running = false;
        handler.removeCallbacks(pollRunnable);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
