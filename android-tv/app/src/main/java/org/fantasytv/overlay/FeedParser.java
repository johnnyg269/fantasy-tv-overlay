package org.fantasytv.overlay;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Strict, bounded, literal-text parser for the common fantasy feed. */
public final class FeedParser {
    private FeedParser() {}
    private static final Set<String> STARTERS = new HashSet<>(Arrays.asList(
        "QB","TQB","RB","WR","TE","K","PK","P","HC","D/ST","DST","DEF","D","FLEX","SUPERFLEX",
        "SUPER_FLEX","SF","OP","UTIL","RB/WR","WR/TE","RB/TE","RB/WR/TE","QB/RB/WR/TE",
        "Q/W/R/T","W/R/T","W/R","W/T","IDP","DP","DL","DE","DT","LB","DB","CB","S",
        "SS","FS","EDGE","DFLEX","DL/LB","LB/DB","D-FLEX"));
    private static final Set<String> UNAVAILABLE = new HashSet<>(Arrays.asList(
        "out","injured-reserve","inactive","suspended","practice-squad"));

    public static FeedModels.Feed parse(String body, double now) throws JSONException {
        if (body == null || body.length() > 1_048_576) throw new JSONException("Invalid feed size");
        checkDepth(body);
        JSONObject root = new JSONObject(body);
        if (!Boolean.TRUE.equals(root.opt("ok"))) throw new JSONException("Unavailable feed");
        Double updated = number(root.opt("updated"));
        if (updated == null || updated < 0 || now - updated > 120 || updated - now > 60) {
            throw new JSONException("Stale or invalid source time");
        }
        JSONArray items = root.optJSONArray("leagues");
        if (items == null || items.length() < 1 || items.length() > 16) throw new JSONException("Invalid leagues");
        JSONObject context = root.optJSONObject("tvContext");
        String watching = "", onTvGame = "";
        if (context != null && Boolean.TRUE.equals(context.opt("available"))) {
            Double time = number(context.opt("updated"));
            String confidence = text(context.opt("confidence"), 40);
            if (time != null && now - time <= 30 && time - now <= 5 &&
                (confidence.equals("exact-title-pair") || confidence.equals("manual"))) {
                onTvGame = identifier(context.opt("matchedGameId"));
                watching = text(context.opt("title"), 100);
            }
        }
        List<FeedModels.League> leagues = new ArrayList<>();
        Set<String> ids = new HashSet<>();
        for (int i = 0; i < items.length(); i++) {
            JSONObject league = items.optJSONObject(i);
            if (league == null || Boolean.FALSE.equals(league.opt("ok"))) continue;
            String id = identifier(league.opt("leagueId"));
            if (id.isEmpty() || !ids.add(id)) throw new JSONException("Invalid league identity");
            JSONObject mine = league.optJSONObject("me"), theirs = league.optJSONObject("opp");
            if (mine == null || theirs == null || identifier(mine.opt("teamId")).isEmpty() || identifier(theirs.opt("teamId")).isEmpty()
                || score(mine.opt("score")) == null || score(theirs.opt("score")) == null) continue;
            String title = text(league.opt("short"), 48);
            if (title.isEmpty()) title = text(league.opt("leagueName"), 48);
            if (title.isEmpty()) title = "Fantasy matchup";
            Double week = number(league.opt("week"));
            if (week == null || week < 1 || week > 30 || week != Math.floor(week)) throw new JSONException("Invalid scoring week");
            Double season = number(league.opt("seasonId"));
            Double probability = number(league.opt("winProb"));
            if (probability != null && (probability < 0 || probability > 1)) probability = null;
            leagues.add(new FeedModels.League(id, title, week.intValue(),
                team(mine, onTvGame), team(theirs, onTvGame), probability, season != null && season >= 2019 && season <= 2100 && season == Math.floor(season) ? season.intValue() : 0));
        }
        if (leagues.isEmpty()) throw new JSONException("No valid matchups");
        return new FeedModels.Feed(updated, watching, leagues);
    }
    private static FeedModels.Team team(JSONObject item, String onTvGame) throws JSONException {
        String owner = text(item.opt("ownerName"), 60);
        if (owner.isEmpty()) owner = text(item.opt("displayLabel"), 60);
        if (owner.isEmpty()) owner = "Owner unavailable";
        List<FeedModels.Player> players = new ArrayList<>();
        JSONArray roster = item.optJSONArray("players");
        if (roster != null && roster.length() > 80) throw new JSONException("Roster exceeds supported limits");
        if (roster != null) for (int i = 0; i < roster.length(); i++) {
            JSONObject player = roster.optJSONObject(i);
            if (player == null) continue;
            String slot = text(player.opt("slot"), 20).toUpperCase(Locale.ROOT).replaceAll("\\s+", "");
            boolean reserve = false;
            for (String flag : new String[]{"bench","isBench","reserve","isReserve","injuredReserve"}) {
                Object value = player.opt(flag);
                if (Boolean.TRUE.equals(value) || Integer.valueOf(1).equals(value) || "true".equalsIgnoreCase(String.valueOf(value))) reserve = true;
            }
            if (reserve || !STARTERS.contains(slot)) continue;
            if (players.size() >= 40) throw new JSONException("Starting lineup exceeds supported limits");
            String availability = text(player.opt("nflAvailability"), 30).toLowerCase(Locale.ROOT).replace('_','-').replace(' ','-');
            boolean live = Boolean.TRUE.equals(player.opt("nflHighlightLive")) &&
                "live".equals(text(player.opt("nflGameState"), 20).toLowerCase(Locale.ROOT)) && !UNAVAILABLE.contains(availability);
            String game = identifier(player.opt("gameId"));
            players.add(new FeedModels.Player(slot, text(player.opt("name"), 60), score(player.opt("pts")),
                score(player.opt("proj")), game, live, live && !onTvGame.isEmpty() && onTvGame.equals(game)));
        }
        return new FeedModels.Team(identifier(item.opt("teamId")), owner, score(item.opt("score")), score(item.opt("proj")), players);
    }
    private static void checkDepth(String body) throws JSONException {
        int depth = 0; boolean string = false, escaped = false;
        for (int i = 0; i < body.length(); i++) {
            char c = body.charAt(i);
            if (string) {
                if (escaped) escaped = false;
                else if (c == 92) escaped = true; // JSON string escape (backslash).
                else if (c == '"') string = false;
            } else if (c == '"') string = true;
            else if (c == '{' || c == '[') { if (++depth > 32) throw new JSONException("Feed nesting is too deep"); }
            else if (c == '}' || c == ']') { if (--depth < 0) throw new JSONException("Invalid feed nesting"); }
        }
        if (depth != 0 || string) throw new JSONException("Incomplete feed");
    }
    static Double score(Object value) {
        Double result = number(value);
        return result != null && Math.abs(result) <= 9999 ? result : null;
    }
    static Double number(Object value) {
        if (!(value instanceof Number)) return null;
        double number = ((Number)value).doubleValue();
        return Double.isFinite(number) && Math.abs(number) <= 10_000_000_000d ? number : null;
    }
    static String identifier(Object value) {
        if (!(value instanceof String) && !(value instanceof Number)) return "";
        String id = String.valueOf(value);
        return id.matches("[A-Za-z0-9_:-]{1,80}") ? id : "";
    }
    static String text(Object value, int maximum) {
        if (!(value instanceof String)) return "";
        String source = (String)value;
        StringBuilder result = new StringBuilder();
        for (int offset = 0; offset < source.length() && result.length() < maximum; ) {
            int cp = source.codePointAt(offset); offset += Character.charCount(cp);
            if (Character.isISOControl(cp) || Character.getType(cp) == Character.FORMAT) result.append(' ');
            else result.appendCodePoint(cp);
        }
        return result.toString().replaceAll("\\s+", " ").trim();
    }
}
