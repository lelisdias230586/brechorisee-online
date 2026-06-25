package com.brechorisee.admin;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.net.Uri;
import android.widget.Toast;

/**
 * Solicita consentimento explícito para captura de tela.
 * A captura real/analise fica no serviço; esta tela só pede autorização do Android.
 */
public class ScreenCapturePermissionActivity extends Activity {
    private static final int REQUEST_CAPTURE = 7712;
    private String baseUrl = "https://brechorisee-online.onrender.com";
    private boolean openInstagramAfter = false;
    private String targetInstagramUri = "instagram://app";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        String extra = getIntent().getStringExtra("base_url");
        if (extra != null && extra.trim().length() > 0) baseUrl = extra.trim();
        openInstagramAfter = getIntent().getBooleanExtra("open_instagram_after", false);
        String targetExtra = getIntent().getStringExtra("target_instagram_uri");
        if (targetExtra != null && targetExtra.trim().length() > 0) targetInstagramUri = targetExtra.trim();
        try {
            MediaProjectionManager manager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
            startActivityForResult(manager.createScreenCaptureIntent(), REQUEST_CAPTURE);
        } catch (Exception ex) {
            Toast.makeText(this, "Captura de tela indisponível: " + ex.getMessage(), Toast.LENGTH_LONG).show();
            finish();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQUEST_CAPTURE) {
            Intent service = new Intent(this, InstagramAssistantOverlayService.class);
            service.setAction(InstagramAssistantOverlayService.ACTION_CAPTURE_READY);
            service.putExtra("base_url", baseUrl);
            service.putExtra("result_code", resultCode);
            service.putExtra("result_data", data);
            service.putExtra("target_instagram_uri", targetInstagramUri);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(service);
            } else {
                startService(service);
            }
            Toast.makeText(this, resultCode == RESULT_OK ? "Captura autorizada. Abrindo Instagram com Assistente." : "Captura não autorizada.", Toast.LENGTH_SHORT).show();
            if (resultCode == RESULT_OK && openInstagramAfter) {
                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    openInstagramNative(targetInstagramUri);
                    finish();
                }, 550);
                super.onActivityResult(requestCode, resultCode, data);
                return;
            }
        }
        finish();
        super.onActivityResult(requestCode, resultCode, data);
    }

    private void openInstagramNative(String target) {
        Uri uri;
        try {
            uri = Uri.parse(target == null || target.trim().isEmpty() ? "instagram://app" : target.trim());
        } catch (Exception ex) {
            uri = Uri.parse("instagram://app");
        }
        try {
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
        } catch (Exception ignored) {
            Toast.makeText(this, "Instagram não encontrado no celular.", Toast.LENGTH_LONG).show();
        }
    }
}
