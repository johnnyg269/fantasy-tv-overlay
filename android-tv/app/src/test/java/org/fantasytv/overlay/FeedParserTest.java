package org.fantasytv.overlay;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class FeedParserTest {
    private JSONObject player(String slot) throws Exception {
        return new JSONObject().put("slot",slot).put("name","Fictional Player").put("pts",12.3).put("proj",15.2)
            .put("nflHighlightLive",true).put("nflGameState","live").put("nflAvailability","active").put("gameId","game-a");
    }
    private JSONObject body() throws Exception {
        JSONObject mine = new JSONObject().put("teamId",1).put("ownerName","Alex").put("score",123.4).put("proj",150)
            .put("players",new JSONArray().put(player("QB")).put(player("BE")).put(player("IR")).put(player("WR").put("isBench",true)).put(player("FLEX")));
        JSONObject opponent = new JSONObject().put("teamId",2).put("ownerName","Sam").put("score",100).put("players",new JSONArray());
        JSONObject league = new JSONObject().put("leagueId","demo-a").put("leagueName","Demo league").put("week",7).put("winProb",.643)
            .put("me",mine).put("opp",opponent);
        return new JSONObject().put("ok",true).put("updated",1000).put("leagues",new JSONArray().put(league));
    }
    private JSONObject mine(JSONObject body) throws Exception { return body.getJSONArray("leagues").getJSONObject(0).getJSONObject("me"); }
    private void rejects(JSONObject body, double now) throws Exception {
        try { FeedParser.parse(body.toString(),now); fail("Accepted invalid feed"); } catch (JSONException expected) { }
    }
    @Test public void sharedBackendSyntheticFixtureParses() throws Exception {
        try (java.io.InputStream input = getClass().getResourceAsStream("/shared-demo-feed.json")) {
            assertNotNull(input);
            String body = new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
            FeedModels.Feed feed = FeedParser.parse(body,1000);
            assertEquals(2,feed.leagues.size());
            assertEquals("espn:1",feed.leagues.get(0).id);
            assertEquals("Alex",feed.leagues.get(0).mine.owner);
            assertEquals(9,feed.leagues.get(0).mine.starters.size());
        }
    }
    @Test public void providerNamespacedLeagueIdsAccepted() throws Exception {
        JSONObject b = body(); b.getJSONArray("leagues").getJSONObject(0).put("leagueId","espn:123");
        assertEquals("espn:123",FeedParser.parse(b.toString(),1000).leagues.get(0).id);
    }
    @Test public void startersOnlyAndOwnerPersonNames() throws Exception {
        FeedModels.League league = FeedParser.parse(body().toString(),1000).leagues.get(0);
        assertEquals("Alex",league.mine.owner); assertEquals(2,league.mine.starters.size());
        assertEquals("QB",league.mine.starters.get(0).slot); assertEquals("FLEX",league.mine.starters.get(1).slot);
        assertTrue(league.mine.starters.get(0).live); assertFalse(league.mine.starters.get(0).onTv);
    }
    @Test public void invalidScoringWeekRejects() throws Exception {
        JSONObject b = body(); b.getJSONArray("leagues").getJSONObject(0).put("week",7.5); rejects(b,1000);
    }
    @Test public void staleFutureAndMissingSourceTimeReject() throws Exception {
        rejects(body(),1121); rejects(body(),939); rejects(body().put("updated",JSONObject.NULL),1000);
        rejects(body().put("updated","1000"),1000); rejects(body().put("ok",false),1000);
    }
    @Test public void unknownSlotsAndTruthyBenchFlagsNeverAppear() throws Exception {
        JSONObject b = body(); mine(b).put("players",new JSONArray().put(player("UNKNOWN")).put(player("BN"))
            .put(player("WR").put("reserve",1)).put(player("RB").put("bench","true")).put(player("SUPER_FLEX")));
        assertEquals(1,FeedParser.parse(b.toString(),1000).leagues.get(0).mine.starters.size());
    }
    @Test public void oversizedStartingLineupRejectsInsteadOfTruncating() throws Exception {
        JSONObject b = body(); JSONArray players = new JSONArray();
        for (int i = 0; i < 41; i++) players.put(player("IDP"));
        mine(b).put("players",players); rejects(b,1000);
    }
    @Test public void unavailableAthleteIsNeverLive() throws Exception {
        JSONObject b = body(); mine(b).put("players",new JSONArray().put(player("WR").put("nflAvailability","out")));
        assertFalse(FeedParser.parse(b.toString(),1000).leagues.get(0).mine.starters.get(0).live);
    }
    @Test public void onTvRequiresFreshExactContext() throws Exception {
        JSONObject b = body(); JSONObject context = new JSONObject().put("available",true).put("updated",1000)
            .put("confidence","exact-title-pair").put("matchedGameId","game-a").put("title","Fictional Game");
        b.put("tvContext",context);
        assertTrue(FeedParser.parse(b.toString(),1000).leagues.get(0).mine.starters.get(0).onTv);
        context.put("updated",969);
        assertFalse(FeedParser.parse(b.toString(),1000).leagues.get(0).mine.starters.get(0).onTv);
        context.put("updated",1000).put("confidence","guess");
        assertFalse(FeedParser.parse(b.toString(),1000).leagues.get(0).mine.starters.get(0).onTv);
    }
    @Test public void probabilitiesAreNotInventedOrClamped() throws Exception {
        JSONObject b = body(); b.getJSONArray("leagues").getJSONObject(0).put("winProb",1.5);
        assertNull(FeedParser.parse(b.toString(),1000).leagues.get(0).probability);
    }
    @Test public void missingOwnerNeverFallsBackToTeamName() throws Exception {
        JSONObject b = body(); mine(b).remove("ownerName"); mine(b).put("name","Team name should not appear");
        assertEquals("Owner unavailable",FeedParser.parse(b.toString(),1000).leagues.get(0).mine.owner);
    }
    @Test public void controlsAreRemovedAndTextBounded() throws Exception {
        JSONObject b = body(); mine(b).put("ownerName","Alex\n\u202E Smith");
        assertEquals("Alex Smith",FeedParser.parse(b.toString(),1000).leagues.get(0).mine.owner);
    }
    @Test public void duplicateIdsAndHugeTotalsReject() throws Exception {
        JSONObject b = body(); b.getJSONArray("leagues").put(b.getJSONArray("leagues").getJSONObject(0)); rejects(b,1000);
        b = body(); mine(b).put("score",10000); rejects(b,1000);
    }
    @Test public void deepNestingRejectedBeforeJsonRecursion() throws Exception {
        String deeplyNested = "{\"ok\":true,\"x\":" + String.join("",java.util.Collections.nCopies(40,"[")) + "0" +
            String.join("",java.util.Collections.nCopies(40,"]")) + "}";
        try { FeedParser.parse(deeplyNested,1000); fail("Accepted deep nesting"); } catch (JSONException expected) { }
    }
    @Test public void bracketCharactersInsideStringsDoNotCountAsNesting() throws Exception {
        JSONObject b = body(); mine(b).put("ownerName","Alex [\\\"{{{{[[[[");
        assertEquals(1,FeedParser.parse(b.toString(),1000).leagues.size());
    }
}
