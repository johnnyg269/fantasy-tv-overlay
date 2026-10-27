package org.fantasytv.overlay;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** User-started specialUse foreground service, not a time-limited dataSync service. */
public final class OverlayService extends Service {
    static final String ACTION_START = "org.fantasytv.overlay.START";
    static final String ACTION_PREVIEW = "org.fantasytv.overlay.PREVIEW";
    static final String ACTION_STOP = "org.fantasytv.overlay.STOP";
    private static final String CHANNEL = "fantasy_tv_active";
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ScorePolicy policy = new ScorePolicy();
    private ScheduledExecutorService worker;
    private OverlayWindow window;
    private FeedModels.Feed current;
    private boolean previewPending, destroyed;
    private long generation, demoStart;
    private String activeEndpoint, activeToken;
    private boolean activeDemo, activeInteractive;
    @Override public void onCreate() {
        super.onCreate();
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Fantasy score overlay", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, OverlayService.class).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(this, CHANNEL).setSmallIcon(R.drawable.ic_fantasy)
            .setContentTitle("Fantasy TV is running").setContentText("Score alerts enabled. Open to configure or stop.")
            .setContentIntent(open).addAction(new Notification.Action.Builder(null, "Stop", stop).build())
            .setOngoing(true).setVisibility(Notification.VISIBILITY_SECRET).setCategory(Notification.CATEGORY_SERVICE).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(1, notification);
        window = new OverlayWindow(this, main);
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || ACTION_STOP.equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if (!ACTION_START.equals(intent.getAction()) && !ACTION_PREVIEW.equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if (!Settings.canDrawOverlays(this)) { stopSelf(); return START_NOT_STICKY; }
        final ConfigStore config = new ConfigStore(this);
        final boolean demo = config.demo(), interactive = config.interactive();
        final String endpoint = config.url(), token;
        try { token = config.token(); if (!demo) { EndpointPolicy.validate(endpoint); if (token.length() < 32) throw new IllegalArgumentException("Invalid private feed token"); } }
        catch (Exception e) { stopSelf(); return START_NOT_STICKY; }
        if (worker != null && endpoint.equals(activeEndpoint) && token.equals(activeToken) && demo == activeDemo && interactive == activeInteractive) {
            if (ACTION_PREVIEW.equals(intent.getAction())) {
                if (current != null && current.fresh(System.currentTimeMillis() / 1000.0)) window.enqueue(current.leagues.get(0).id);
                else previewPending = true;
            }
            return START_NOT_STICKY;
        }
        activeEndpoint = endpoint; activeToken = token; activeDemo = demo; activeInteractive = interactive;
        if (worker != null) worker.shutdownNow();
        generation++; final long session = generation;
        current = null; policy.reset(); window.clear(); window.setInteractive(interactive);
        previewPending = ACTION_PREVIEW.equals(intent.getAction()); demoStart = android.os.SystemClock.elapsedRealtime();
        worker = Executors.newSingleThreadScheduledExecutor();
        worker.scheduleWithFixedDelay(() -> {
            try {
                FeedModels.Feed feed = demo ? DemoFeed.create((android.os.SystemClock.elapsedRealtime() - demoStart) / 30_000) :
                    FeedParser.parse(new FeedClient().fetch(endpoint, token), System.currentTimeMillis() / 1000.0);
                main.post(() -> {
                    if (destroyed || session != generation) return;
                    if (!Settings.canDrawOverlays(this)) { stopSelf(); return; }
                    if (!feed.fresh(System.currentTimeMillis() / 1000.0)) { unavailable(); return; }
                    current = feed;
                    List<String> changes = policy.accept(feed);
                    window.update(feed);
                    if (previewPending) { previewPending = false; window.enqueue(feed.leagues.get(0).id); }
                    for (String id : changes) window.enqueue(id);
                });
            } catch (Exception e) {
                // Deliberately no exception details: URLs, response bodies and secrets never enter logs.
                main.post(() -> { if (!destroyed && session == generation) unavailable(); });
            }
        }, 0, 5, TimeUnit.SECONDS);
        return START_NOT_STICKY;
    }
    private void unavailable() { current = null; policy.reset(); window.clear(); }
    @Override public void onDestroy() {
        destroyed = true; generation++;
        if (worker != null) worker.shutdownNow();
        main.removeCallbacksAndMessages(null);
        if (window != null) window.clear();
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
