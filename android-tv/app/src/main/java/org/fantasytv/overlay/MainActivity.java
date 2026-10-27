package org.fantasytv.overlay;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Remote-friendly setup. Incoming intent extras never execute overlay commands. */
public final class MainActivity extends Activity {
    private EditText endpoint, token;
    private CheckBox demo, interactive;
    private TextView status;
    private ConfigStore store;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        store = new ConfigStore(this);
        ScrollView scroll = new ScrollView(this);
        LinearLayout column = new LinearLayout(this); column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(42), dp(28), dp(42), dp(28)); scroll.addView(column);
        label(column, "Fantasy TV", 32, Color.rgb(244,246,249));
        label(column, "Live matchup scores, without leaving your show.", 18, Color.rgb(172,183,199));
        label(column, "Experimental Android TV / Google TV build. First verify overlays in every TV app you use. Another HDMI device's picture cannot be overlaid by an external streaming stick.", 15, Color.rgb(172,183,199));
        status = label(column, "", 15, Color.rgb(139,221,181));
        demo = new CheckBox(this); demo.setText("Use fictional demo data (no network)"); demo.setChecked(store.demo()); column.addView(demo);
        label(column, "Your private HTTPS scores endpoint", 16, Color.WHITE);
        endpoint = new EditText(this); endpoint.setSingleLine(true); endpoint.setTextSize(17);
        endpoint.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        endpoint.setHint("https://your-service.example/api/scores"); endpoint.setText(store.url()); column.addView(endpoint);
        label(column, "Feed token (leave blank to keep the saved token)", 16, Color.WHITE);
        token = new EditText(this); token.setSingleLine(true); token.setTextSize(17);
        token.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        token.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        token.setSaveEnabled(false); column.addView(token);
        interactive = new CheckBox(this); interactive.setText("Allow remote OK to open the matchup during popups");
        interactive.setChecked(store.interactive()); column.addView(interactive);
        label(column, "Interactive popups hold remote focus for five seconds. If a video app pauses when focus changes, switch this off for passive alerts. Passive mode does not intercept remote keys.", 14, Color.rgb(172,183,199));
        button(column, "1  Allow display over other apps", v -> allowOverlay());
        Button preview = button(column, "2  Save and preview", v -> launch(true));
        button(column, "3  Start score alerts", v -> launch(false));
        button(column, "Stop overlay", v -> {
            stopService(new Intent(this, OverlayService.class)); status.setText("Overlay stopped.");
        });
        button(column, "Erase private settings", v -> {
            stopService(new Intent(this, OverlayService.class));
            try { store.clear(); endpoint.setText(""); token.setText(""); demo.setChecked(true); interactive.setChecked(true); status.setText("Private settings erased."); }
            catch (Exception e) { status.setText("Settings could not be erased. Use Android Settings → Apps → Fantasy TV → Clear data."); }
        });
        label(column, "Your token is encrypted with Android Keystore. Backups, screenshots of this setup page, analytics and cleartext network traffic are disabled. No accessibility or screen-capture permission is requested. Restart alerts from this screen after a TV reboot.", 14, Color.rgb(172,183,199));
        setContentView(scroll); preview.requestFocus();
        updatePermissionStatus();
    }
    @Override protected void onResume() { super.onResume(); if (status != null) updatePermissionStatus(); }
    private void updatePermissionStatus() {
        status.setText(Settings.canDrawOverlays(this) ? "Overlay permission enabled. Ready to preview." : "Overlay permission is needed before a preview.");
    }
    private void allowOverlay() {
        try { startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()))); }
        catch (ActivityNotFoundException e) { status.setText("Open TV Settings → Apps → Special app access → Display over other apps → Fantasy TV. Some TVs do not offer this permission."); }
    }
    private void launch(boolean preview) {
        if (!Settings.canDrawOverlays(this)) { status.setText("First enable display over other apps. If your TV blocks it, this overlay path is unsupported."); return; }
        try {
            String entered = token.getText().toString();
            if (entered.isEmpty()) entered = store.token();
            store.save(endpoint.getText().toString(), entered, demo.isChecked(), interactive.isChecked());
            token.setText("");
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
            }
            Intent intent = new Intent(this, OverlayService.class).setAction(preview ? OverlayService.ACTION_PREVIEW : OverlayService.ACTION_START);
            startForegroundService(intent);
            status.setText(preview ? "Preview requested. Only fresh feed data will be shown." : "Alerts started. Return to your streaming app; score changes appear for five seconds.");
            moveTaskToBack(true);
        } catch (IllegalArgumentException e) { status.setText(e.getMessage()); }
        catch (Exception e) { status.setText("Cannot start. Check private settings and the TV's service permissions. No credentials were logged."); }
    }
    private TextView label(LinearLayout parent, String text, int size, int color) {
        TextView view = new TextView(this); view.setText(text); view.setTextSize(size); view.setTextColor(color);
        view.setPadding(0, dp(6), 0, dp(8)); parent.addView(view); return view;
    }
    private Button button(LinearLayout parent, String text, View.OnClickListener listener) {
        Button button = new Button(this); button.setText(text); button.setTextSize(16); button.setAllCaps(false);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(52));
        params.setMargins(0, dp(6), 0, dp(2)); parent.addView(button, params); button.setOnClickListener(listener); return button;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
