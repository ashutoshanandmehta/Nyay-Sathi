package in.nyaysaathi.app;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import androidx.core.content.FileProvider;
import com.getcapacitor.BridgeActivity;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/**
 * Nyay Saathi Android MainActivity (Package 3 Native Bridges).
 * Provides:
 * 1. window.NyayNativeSecureStorage: Android Keystore AES-256-GCM encrypted SharedPreferences for Supabase Auth tokens.
 * 2. window.NyayNativeFiles: Native file export and FileProvider share sheet for PDF/DOCX/JSON case bundles.
 * 3. Hardware back-button interception (closing active UI drawers/menus before exiting).
 * 4. OAuth deep-link callback forwarding (in.nyaysaathi.app://oauth-callback).
 */
public class MainActivity extends BridgeActivity {
    private static final String KEYSTORE_PROVIDER = "AndroidKeyStore";
    private static final String KEY_ALIAS = "nyay_saathi_auth_master_key_v1";
    private static final String PREFS_NAME = "nyay_secure_auth_prefs";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int GCM_TAG_BITS = 128;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (getBridge() != null && getBridge().getWebView() != null) {
            WebView webView = getBridge().getWebView();
            webView.addJavascriptInterface(new NativeSecureStorageBridge(this), "NyayNativeSecureStorage");
            webView.addJavascriptInterface(new NativeFilesBridge(this), "NyayNativeFiles");
        }

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (getBridge() != null && getBridge().getWebView() != null) {
                    WebView webView = getBridge().getWebView();
                    webView.evaluateJavascript(
                        "(function(){ return Boolean(window.__nyayHandleBackPress && window.__nyayHandleBackPress()); })()",
                        result -> {
                            if (!"true".equals(result)) {
                                setEnabled(false);
                                getOnBackPressedDispatcher().onBackPressed();
                                setEnabled(true);
                            }
                        }
                    );
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                    setEnabled(true);
                }
            }
        });

        handleOAuthIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleOAuthIntent(intent);
    }

    private void handleOAuthIntent(Intent intent) {
        if (intent == null || intent.getData() == null) {
            return;
        }
        Uri data = intent.getData();
        if (!"in.nyaysaathi.app".equals(data.getScheme()) || !"oauth-callback".equals(data.getHost())) {
            return;
        }
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        try {
            JSONObject payload = new JSONObject();
            payload.put("url", data.toString());
            payload.put("provider", data.getQueryParameter("provider"));
            payload.put("code", data.getQueryParameter("code"));
            payload.put("state", data.getQueryParameter("state"));
            payload.put("error", data.getQueryParameter("error"));
            String payloadJson = payload.toString();
            String js = "window.__nyayPendingOAuthCallback = " + payloadJson + "; "
                + "window.dispatchEvent(new CustomEvent('nyay:oauth-callback', { detail: "
                + payloadJson + " }));";
            WebView webView = getBridge().getWebView();
            webView.post(() -> webView.evaluateJavascript(js, null));
        } catch (Exception ignored) {
            // Never crash on malformed external intent data.
        }
    }

    private static SecretKey getOrCreateMasterKey() throws Exception {
        KeyStore keyStore = KeyStore.getInstance(KEYSTORE_PROVIDER);
        keyStore.load(null);
        if (keyStore.containsAlias(KEY_ALIAS)) {
            KeyStore.SecretKeyEntry entry = (KeyStore.SecretKeyEntry) keyStore.getEntry(KEY_ALIAS, null);
            return entry.getSecretKey();
        }
        KeyGenerator keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE_PROVIDER);
        KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build();
        keyGenerator.init(spec);
        return keyGenerator.generateKey();
    }

    public static final class NativeSecureStorageBridge {
        private final SharedPreferences prefs;

        NativeSecureStorageBridge(Context context) {
            this.prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        }

        @JavascriptInterface
        public String getItem(String key) {
            if (key == null || key.isEmpty()) {
                return null;
            }
            String stored = prefs.getString(key, null);
            if (stored == null) {
                return null;
            }
            int sep = stored.indexOf('.');
            if (sep <= 0) {
                return null;
            }
            try {
                byte[] iv = Base64.decode(stored.substring(0, sep), Base64.NO_WRAP);
                byte[] ciphertext = Base64.decode(stored.substring(sep + 1), Base64.NO_WRAP);
                Cipher cipher = Cipher.getInstance(TRANSFORMATION);
                cipher.init(Cipher.DECRYPT_MODE, getOrCreateMasterKey(), new GCMParameterSpec(GCM_TAG_BITS, iv));
                cipher.updateAAD(key.getBytes(StandardCharsets.UTF_8));
                byte[] plain = cipher.doFinal(ciphertext);
                return new String(plain, StandardCharsets.UTF_8);
            } catch (Exception e) {
                return null;
            }
        }

        @JavascriptInterface
        public void setItem(String key, String value) {
            if (key == null || key.isEmpty() || value == null) {
                return;
            }
            try {
                Cipher cipher = Cipher.getInstance(TRANSFORMATION);
                cipher.init(Cipher.ENCRYPT_MODE, getOrCreateMasterKey());
                cipher.updateAAD(key.getBytes(StandardCharsets.UTF_8));
                byte[] iv = cipher.getIV();
                byte[] ciphertext = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
                String encoded = Base64.encodeToString(iv, Base64.NO_WRAP)
                    + "."
                    + Base64.encodeToString(ciphertext, Base64.NO_WRAP);
                prefs.edit().putString(key, encoded).apply();
            } catch (Exception ignored) {
                // Fail closed rather than writing unencrypted session credentials.
            }
        }

        @JavascriptInterface
        public void removeItem(String key) {
            if (key == null || key.isEmpty()) {
                return;
            }
            prefs.edit().remove(key).apply();
        }
    }

    public static final class NativeFilesBridge {
        private final Context context;

        NativeFilesBridge(Context context) {
            this.context = context;
        }

        @JavascriptInterface
        public boolean saveAndShareBase64File(String filename, String mimeType, String base64Data) {
            if (filename == null || base64Data == null || base64Data.isEmpty()) {
                return false;
            }
            try {
                String safeName = filename.replaceAll("[^a-zA-Z0-9._-]", "_");
                if (safeName.isEmpty()) {
                    safeName = "nyay-saathi-export.bin";
                }
                File exportDir = new File(context.getCacheDir(), "exports");
                if (!exportDir.exists() && !exportDir.mkdirs()) {
                    return false;
                }
                File outFile = new File(exportDir, safeName);
                byte[] rawBytes = Base64.decode(base64Data, Base64.DEFAULT);
                try (FileOutputStream fos = new FileOutputStream(outFile)) {
                    fos.write(rawBytes);
                    fos.flush();
                }

                Uri contentUri = FileProvider.getUriForFile(
                    context,
                    context.getPackageName() + ".fileprovider",
                    outFile
                );

                Intent shareIntent = new Intent(Intent.ACTION_SEND);
                shareIntent.setType(mimeType != null && !mimeType.isEmpty() ? mimeType : "application/octet-stream");
                shareIntent.putExtra(Intent.EXTRA_STREAM, contentUri);
                shareIntent.putExtra(Intent.EXTRA_TITLE, safeName);
                shareIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);

                Intent chooser = Intent.createChooser(shareIntent, safeName);
                chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(chooser);
                return true;
            } catch (Exception e) {
                return false;
            }
        }
    }
}
