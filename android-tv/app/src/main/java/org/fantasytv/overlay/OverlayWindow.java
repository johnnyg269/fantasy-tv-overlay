package org.fantasytv.overlay;

import android.content.Context;
import android.graphics.PixelFormat;
import android.os.Handler;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.WindowManager;
import java.util.LinkedHashSet;

/** Only the visible overlay takes focus; removing it releases all keys immediately. */
final class OverlayWindow implements ScoreOverlayView.Actions {
    private final Context context;
    private final Handler main;
    private final WindowManager manager;
    private final LinkedHashSet<String> pending = new LinkedHashSet<>();
    private FeedModels.Feed feed;
    private ScoreOverlayView view;
    private String selected;
    private boolean sidebar, interactive = true;
    private int rowOffset;
    private long lastArrival, expiresAt;
    private final Runnable timer = new Runnable() {
        @Override public void run() {
            if (view == null) return;
            if (!fresh()) { clear(); return; }
            if (!sidebar && SystemClock.elapsedRealtime() >= expiresAt) { hide(); next(); return; }
            main.postDelayed(this, 200);
        }
    };
    OverlayWindow(Context context, Handler main) {
        this.context = context; this.main = main;
        this.manager = context.getSystemService(WindowManager.class);
    }
    void setInteractive(boolean interactive) { this.interactive = interactive; }
    void update(FeedModels.Feed feed) {
        this.feed = feed; lastArrival = SystemClock.elapsedRealtime();
        if (view != null) {
            if (feed.find(selected) == null) { hide(); next(); }
            else render();
        }
    }
    void enqueue(String id) {
        if (!fresh() || feed.find(id) == null) return;
        if (view != null && id.equals(selected)) {
            if (!sidebar) expiresAt = SystemClock.elapsedRealtime() + 5000;
            return;
        }
        if (pending.size() < 16) pending.add(id);
        if (view == null) next();
    }
    private boolean fresh() {
        return feed != null && feed.fresh(System.currentTimeMillis() / 1000.0) && SystemClock.elapsedRealtime() - lastArrival <= 30_000;
    }
    private void next() {
        if (!fresh()) { clear(); return; }
        while (!pending.isEmpty()) {
            String id = pending.iterator().next(); pending.remove(id);
            if (feed.find(id) != null) { selected = id; sidebar = false; rowOffset = 0; show(); return; }
        }
    }
    private void show() {
        if (!fresh()) return;
        try {
            if (view == null) {
                view = new ScoreOverlayView(context, this);
                manager.addView(view, layout());
            } else manager.updateViewLayout(view, layout());
            expiresAt = SystemClock.elapsedRealtime() + 5000;
            render();
            if (interactive || sidebar) view.requestFocus();
            main.removeCallbacks(timer); main.post(timer);
        } catch (RuntimeException e) { clear(); }
    }
    private WindowManager.LayoutParams layout() {
        float scale = context.getResources().getDisplayMetrics().heightPixels / 1080f;
        int width = Math.round((sidebar ? 900 : 1000) * scale);
        int height = sidebar ? WindowManager.LayoutParams.MATCH_PARENT : Math.round(650 * scale);
        int flags = WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
            | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED;
        if (!interactive && !sidebar) flags |= WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE;
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(width, height,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY, flags, PixelFormat.TRANSLUCENT);
        if (!interactive && !sidebar) params.alpha = 0.8f;
        params.gravity = Gravity.TOP | Gravity.LEFT; params.x = 0; params.y = 0;
        params.setTitle("Fantasy TV overlay");
        return params;
    }
    private void render() {
        if (view != null && feed != null) {
            FeedModels.League league = feed.find(selected);
            if (league != null) view.setContent(feed, league, sidebar, rowOffset, interactive);
        }
    }
    private void hide() {
        main.removeCallbacks(timer);
        if (view != null) {
            try { manager.removeViewImmediate(view); } catch (RuntimeException ignored) { }
            view = null;
        }
    }
    void clear() { hide(); pending.clear(); selected = null; feed = null; sidebar = false; }
    @Override public void openMatchup() {
        if (!fresh() || sidebar || !interactive) return;
        sidebar = true; rowOffset = 0; show();
    }
    @Override public void close() {
        pending.clear(); hide(); sidebar = false; selected = null;
    }
    @Override public void league(int direction) {
        if (!sidebar || !fresh()) return;
        int index = 0;
        for (int i = 0; i < feed.leagues.size(); i++) if (feed.leagues.get(i).id.equals(selected)) index = i;
        selected = feed.leagues.get((index + direction + feed.leagues.size()) % feed.leagues.size()).id;
        rowOffset = 0; render();
    }
    @Override public void scroll(int direction) {
        if (!sidebar || !fresh()) return;
        FeedModels.League league = feed.find(selected);
        int count = Math.max(league.mine.starters.size(), league.opponent.starters.size());
        rowOffset = Math.max(0, Math.min(Math.max(0, count - 9), rowOffset + direction)); render();
    }
}
