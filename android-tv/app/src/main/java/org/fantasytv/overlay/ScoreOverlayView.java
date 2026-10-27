package org.fantasytv.overlay;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import java.util.List;
import java.util.Locale;

/** Quiet sports layout on the same 1920×1080 logical canvas as the Samsung renderer. */
final class ScoreOverlayView extends View {
    interface Actions { void openMatchup(); void close(); void league(int direction); void scroll(int direction); }
    private final Actions actions;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Typeface body;
    private final Typeface semibold;
    private final Typeface totals;
    private final Shader corner;
    private FeedModels.Feed feed;
    private FeedModels.League league;
    private boolean sidebar, interactive;
    private int rowOffset;
    private static final int WHITE = Color.rgb(244,246,249), MUTED = Color.rgb(172,183,199), FAINT = Color.rgb(120,134,151),
        MINT = Color.rgb(139,221,181), RED = Color.rgb(201,120,123);
    ScoreOverlayView(Context context, Actions actions) {
        super(context); this.actions = actions;
        setFocusable(true); setFocusableInTouchMode(true); setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        // Load each face once for this View; drawing never opens a font file.
        body = loadFont(context,"fonts/QuietInter-Medium.ttf",Typeface.create("sans-serif-medium",Typeface.NORMAL));
        semibold = loadFont(context,"fonts/QuietInter-Semibold.ttf",Typeface.create("sans-serif",Typeface.BOLD));
        totals = loadFont(context,"fonts/BebasNeue-Regular.ttf",Typeface.create("sans-serif-condensed",Typeface.BOLD));
        int[] colors = new int[25]; float[] positions = new float[25];
        for (int i = 0; i < colors.length; i++) {
            float r = i * 1.5f / (colors.length - 1);
            int alpha = Math.round((float)(220 * Math.exp(-Math.pow(r, 8))));
            colors[i] = Color.argb(alpha, 8,13,18); positions[i] = i / (float)(colors.length - 1);
        }
        RadialGradient shader = new RadialGradient(0,0,1.5f,colors,positions,Shader.TileMode.CLAMP);
        Matrix matrix = new Matrix(); matrix.setScale(800,450); shader.setLocalMatrix(matrix); corner = shader;
    }
    private static Typeface loadFont(Context context, String asset, Typeface fallback) {
        try { return Typeface.createFromAsset(context.getAssets(),asset); }
        catch (RuntimeException e) { return fallback; }
    }
    void setContent(FeedModels.Feed feed, FeedModels.League league, boolean sidebar, int rowOffset, boolean interactive) {
        this.feed = feed; this.league = league; this.sidebar = sidebar; this.rowOffset = rowOffset; this.interactive = interactive;
        setContentDescription("Fantasy matchup " + league.mine.owner + " versus " + league.opponent.owner); invalidate();
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (league == null || feed == null) return;
        float scale = getResources().getDisplayMetrics().heightPixels / 1080f;
        canvas.save(); canvas.scale(scale, scale);
        if (sidebar) drawSidebar(canvas); else drawPopup(canvas);
        canvas.restore();
    }
    private void drawPopup(Canvas c) {
        paint.setShader(corner); c.drawRect(0,0,1000,650,paint); paint.setShader(null);
        text(c, league.name.toUpperCase(Locale.ROOT),24,15,14,MUTED,340,semibold);
        text(c, league.week > 0 ? "WEEK " + league.week : "MATCHUP",430,17,12,FAINT,90,semibold);
        rect(c,24,37,492,1,0x18DCE8EE); rect(c,270,49,1,105,0x12DCE8EE);
        text(c,league.mine.owner,24,54,23,WHITE,222,body);
        text(c,league.opponent.owner,294,54,23,MUTED,222,body);
        total(c,league.mine.score,22,85,68,230);
        total(c,league.opponent.score,292,85,68,230);
        text(c,"Estimated win chance",24,160,14,MUTED,492,body);
        probability(c,24,183,492,league.probability,false);
        if (interactive) button(c);
        else text(c,"FANTASY TV  ·  LIVE SCORE UPDATE",24,255,12,MUTED,492,semibold);
    }
    private void button(Canvas c) {
        paint.setColor(0x30000000); c.drawRoundRect(new RectF(24,247,268,295),10,10,paint);
        paint.setShader(new LinearGradient(0,244,0,292,0xFFF8F6ED,0xFFE5E9E4,Shader.TileMode.CLAMP));
        c.drawRoundRect(new RectF(24,244,268,292),10,10,paint); paint.setShader(null);
        paint.setColor(0xB3FFFFFF); paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(1);
        c.drawRoundRect(new RectF(24.5f,244.5f,267.5f,291.5f),9.5f,9.5f,paint); paint.setStyle(Paint.Style.FILL);
        text(c,"View matchup",42,255,18,0xFF18272D,158,semibold);
        rect(c,215,255,1,26,0x2918272D);
        text(c,"OK",230,260,12,0xFF4F6068,24,semibold);
    }
    private void drawSidebar(Canvas c) {
        rect(c,0,0,720,1080,0xB0101820);
        paint.setShader(new LinearGradient(720,0,900,0,0xB0101820,0x00101820,Shader.TileMode.CLAMP));
        c.drawRect(720,0,900,1080,paint); paint.setShader(null);
        text(c,league.name.toUpperCase(Locale.ROOT),28,25,14,WHITE,664,semibold);
        rect(c,28,60,306,2,0xFFB1DCCC); rect(c,28,62,664,1,0x12FFFFFF);
        text(c,(league.week > 0 ? "WEEK " + league.week : "WEEK —") + "  ·  MATCHUP",28,86,12,MUTED,664,body);
        header(c,league.mine,28); header(c,league.opponent,384);
        text(c,"vs",342,171,13,FAINT,30,body);
        text(c,"Estimated win chance",28,235,14,0xFFD2DADD,664,body);
        probability(c,28,257,664,league.probability,true);
        rect(c,28,309,664,1,0x14FFFFFF);
        text(c,"STARTING LINEUP",28,326,12,MUTED,664,semibold);
        for (int i = 0; i < 9; i++) {
            int top = 356 + i * 64;
            if (i % 2 == 0) rect(c,22,top - 6,676,59,0x03FFFFFF);
            player(c,league.mine.starters,rowOffset + i,0,top);
            player(c,league.opponent.starters,rowOffset + i,356,top);
        }
        int count = Math.max(league.mine.starters.size(),league.opponent.starters.size());
        String caption = !feed.watching.isEmpty() ? "WATCHING · " + feed.watching : "Starting lineup";
        if (count > 9) caption = "PLAYERS " + (rowOffset + 1) + "–" + Math.min(count,rowOffset + 9) + " OF " + count + "  ·  UP / DOWN Scroll";
        text(c,caption,28,950,11,MUTED,664,body);
        rect(c,28,1011,664,1,0x16FFFFFF);
        text(c,"BACK  Close",28,1035,14,WHITE,270,semibold);
        text(c,"LEFT / RIGHT  Switch league",358,1038,11,MUTED,338,body);
    }
    private void header(Canvas c, FeedModels.Team team, int x) {
        text(c,team.owner,x,116,23,WHITE,306,body); total(c,team.score,x - 2,150,60,306);
        text(c,"PROJ",x,215,10,FAINT,44,body);
        text(c,number(team.projection,2),x + 56,210,16,MUTED,250,semibold);
    }
    private void player(Canvas c, List<FeedModels.Player> players, int index, int offset, int top) {
        if (index >= players.size()) { text(c,"—",76 + offset,top + 14,20,FAINT,270,body); return; }
        FeedModels.Player player = players.get(index);
        if (player.live) {
            rect(c,22 + offset,top - 3,338,60,0x0F8BDDB5);
            paint.setColor(MINT); c.drawCircle(30 + offset,top + 43,2,paint);
            text(c,player.onTv ? "ON TV" : "LIVE",36 + offset,top + 36,10,MINT,43,semibold);
        }
        String slot = player.slot;
        if (slot.equals("SUPERFLEX") || slot.equals("SUPER_FLEX")) slot = "SF";
        if (slot.equals("FLEX")) slot = "FLX";
        text(c,slot,28 + offset,top + 10,11,FAINT,43,body);
        text(c,player.name,76 + offset,top + 5,20,WHITE,270,body);
        rightText(c,number(player.points,1),135 + offset,top + 31,22,WHITE,62,semibold);
        text(c,"PTS",142 + offset,top + 42,10,FAINT,36,body);
        text(c,"PROJ",214 + offset,top + 42,10,FAINT,38,body);
        rightText(c,number(player.projection,1),320 + offset,top + 35,16,MUTED,60,semibold);
    }
    private void probability(Canvas c, int x, int y, int width, Double probability, boolean large) {
        if (probability == null) text(c,"Unavailable",x,y,16,MUTED,width,body);
        else {
            text(c,percent(probability),x,y,20,MINT,width / 2,semibold);
            if (large) text(c,percent(1 - probability),384,y,20,0xFFFFD0D3,306,semibold);
            else rightText(c,percent(1 - probability),x + width,y,20,0xFFF2B7BA,width / 2,semibold);
        }
        float top = y + 31, height = large ? 8 : 6;
        RectF track = new RectF(x,top,x + width,top + height);
        paint.setColor(0x4076808A); c.drawRoundRect(track,4,4,paint);
        if (probability == null) return;
        c.save(); c.clipRect(x,top,x + width * probability.floatValue(),top + height);
        paint.setColor(MINT); c.drawRoundRect(track,4,4,paint); c.restore();
        c.save(); c.clipRect(x + width * probability.floatValue(),top,x + width,top + height);
        paint.setColor(RED); c.drawRoundRect(track,4,4,paint); c.restore();
    }
    private static String percent(double value) {
        if (value > 0 && value <= .0005) return "<0.1%";
        if (value >= .9995 && value < 1) return ">99.9%";
        return String.format(Locale.US,"%.1f%%",value * 100);
    }
    private static String number(Double value, int digits) {
        return value == null || !Double.isFinite(value) || Math.abs(value) > 9999 ? "—" : String.format(Locale.US,"%." + digits + "f",value);
    }
    private void total(Canvas c, double value, float x, float y, float size, float width) {
        String label = number(value,2); paint.setTypeface(totals); paint.setTextSize(size);
        while (paint.measureText(label) > width && size > 24) paint.setTextSize(--size);
        text(c,label,x,y,size,WHITE,width,totals);
    }
    private void text(Canvas c, String value, float x, float y, float size, int color, float width, Typeface face) {
        paint.setColor(color); paint.setTypeface(face); paint.setTextSize(size);
        String label = value == null ? "—" : value;
        if (paint.measureText(label) > width) {
            while (label.length() > 1 && paint.measureText(label + "…") > width) label = label.substring(0,label.offsetByCodePoints(label.length(),-1));
            label = label + "…";
        }
        c.drawText(label,x,y - paint.getFontMetrics().top,paint);
    }
    private void rightText(Canvas c, String value, float right, float y, float size, int color, float width, Typeface face) {
        paint.setTypeface(face); paint.setTextSize(size);
        text(c,value,right - Math.min(width,paint.measureText(value)),y,size,color,width,face);
    }
    private void rect(Canvas c, float x, float y, float w, float h, int color) {
        paint.setColor(color); c.drawRect(x,y,x + w,y + h,paint);
    }
    @Override public boolean onKeyDown(int code, KeyEvent event) {
        if (event.getRepeatCount() > 0 && (code == KeyEvent.KEYCODE_DPAD_CENTER || code == KeyEvent.KEYCODE_ENTER)) return true;
        if (code == KeyEvent.KEYCODE_BACK || code == KeyEvent.KEYCODE_ESCAPE) { actions.close(); return true; }
        if (!sidebar && (code == KeyEvent.KEYCODE_DPAD_CENTER || code == KeyEvent.KEYCODE_ENTER)) { actions.openMatchup(); return true; }
        if (sidebar && code == KeyEvent.KEYCODE_DPAD_LEFT) { actions.league(-1); return true; }
        if (sidebar && code == KeyEvent.KEYCODE_DPAD_RIGHT) { actions.league(1); return true; }
        if (sidebar && code == KeyEvent.KEYCODE_DPAD_UP) { actions.scroll(-1); return true; }
        if (sidebar && code == KeyEvent.KEYCODE_DPAD_DOWN) { actions.scroll(1); return true; }
        return super.onKeyDown(code,event);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        if (interactive && !sidebar && event.getAction() == MotionEvent.ACTION_UP) {
            float scale = getResources().getDisplayMetrics().heightPixels / 1080f;
            float x = event.getX() / scale, y = event.getY() / scale;
            if (x >= 24 && x <= 268 && y >= 244 && y <= 292) { performClick(); actions.openMatchup(); return true; }
        }
        return false;
    }
    @Override public boolean performClick() { super.performClick(); return true; }
}
