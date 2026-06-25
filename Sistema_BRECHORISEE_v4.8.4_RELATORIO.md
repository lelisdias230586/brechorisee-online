# Sistema BRECHORISEE v4.8.4

Correção aplicada:

- O instalador Windows não exige mais `gradlew.bat` dentro das pastas Android.
- Agora ele usa `PREPARAR_DEPENDENCIAS_ANDROID_WINDOWS.bat` para baixar/validar Android SDK e Gradle.
- Depois compila com `tools\gradle-8.10.2\bin\gradle.bat` ou com `gradle` do PATH.
- Primeiro tenta `assembleRelease`.
- Se release falhar, tenta `assembleDebug` para não travar a publicação.
- Compila Cliente e Admin.
- Publica somente o APK Cliente no servidor.
- Mantém Tailscale configurado em `http://100.121.45.12:8000`.
