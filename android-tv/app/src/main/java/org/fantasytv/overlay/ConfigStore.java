package org.fantasytv.overlay;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Settings stay in private app storage; bearer tokens are encrypted with Android Keystore. */
final class ConfigStore {
    private static final String ALIAS = "fantasy-tv-feed-token";
    private final SharedPreferences prefs;
    ConfigStore(Context context) { prefs = context.getSharedPreferences("overlay_settings", Context.MODE_PRIVATE); }
    String url() { return prefs.getString("feed_url", ""); }
    boolean demo() { return prefs.getBoolean("demo", true); }
    boolean interactive() { return prefs.getBoolean("interactive", true); }
    String token() throws GeneralSecurityException {
        String saved = prefs.getString("feed_token", "");
        if (saved.isEmpty()) return "";
        try {
            String[] parts = saved.split(":", -1);
            if (parts.length != 2) throw new GeneralSecurityException("Invalid encrypted token");
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
            return EndpointPolicy.token(new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8));
        } catch (IllegalArgumentException e) { throw new GeneralSecurityException("Cannot read the private feed token"); }
    }
    void save(String url, String token, boolean demo, boolean interactive) throws GeneralSecurityException {
        if (!demo) EndpointPolicy.validate(url);
        token = EndpointPolicy.token(token);
        if (!demo && token.length() < 32) throw new IllegalArgumentException("Use your private feed token (at least 32 characters)");
        String encrypted = "";
        if (!token.isEmpty()) {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key());
            encrypted = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
                Base64.encodeToString(cipher.doFinal(token.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        }
        if (!prefs.edit().putString("feed_url", url.trim()).putString("feed_token", encrypted)
                .putBoolean("demo", demo).putBoolean("interactive", interactive).commit()) {
            throw new GeneralSecurityException("Could not save private settings");
        }
    }
    void clear() throws GeneralSecurityException {
        boolean erased = prefs.edit().clear().commit();
        try {
            KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
            if (store.containsAlias(ALIAS)) store.deleteEntry(ALIAS);
            if (!erased) throw new GeneralSecurityException("Could not erase private settings");
        } catch (Exception e) { throw new GeneralSecurityException("Could not erase private settings"); }
    }
    private static SecretKey key() throws GeneralSecurityException {
        try {
            KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
            if (store.containsAlias(ALIAS)) return (SecretKey)store.getKey(ALIAS, null);
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true).build());
            return generator.generateKey();
        } catch (Exception e) { throw new GeneralSecurityException("Android Keystore is unavailable"); }
    }
}
