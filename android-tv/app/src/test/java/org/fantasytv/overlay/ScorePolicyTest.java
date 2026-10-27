package org.fantasytv.overlay;

import org.junit.Test;
import java.util.Arrays;
import java.util.Collections;
import static org.junit.Assert.*;

public class ScorePolicyTest {
    private FeedModels.League league(String id, double a, double b, double projection) {
        return new FeedModels.League(id, "Demo", 7,
            new FeedModels.Team("Alex", a, projection, Collections.emptyList()),
            new FeedModels.Team("Sam", b, projection, Collections.emptyList()), .5);
    }
    private FeedModels.Feed feed(FeedModels.League... leagues) { return new FeedModels.Feed(1000, "", Arrays.asList(leagues)); }
    @Test public void firstSnapshotIsQuiet() {
        assertTrue(new ScorePolicy().accept(feed(league("a",10,20,30))).isEmpty());
    }
    @Test public void eitherTotalChangeAndCorrectionAlert() {
        ScorePolicy p = new ScorePolicy(); p.accept(feed(league("a",10,20,30)));
        assertEquals(Arrays.asList("a"),p.accept(feed(league("a",10.1,20,30))));
        assertEquals(Arrays.asList("a"),p.accept(feed(league("a",10.1,19.9,30))));
        assertTrue(p.accept(feed(league("a",10.1,19.9,30))).isEmpty());
    }
    @Test public void projectionChangesNeverAlert() {
        ScorePolicy p = new ScorePolicy(); p.accept(feed(league("a",10,20,30)));
        assertTrue(p.accept(feed(league("a",10,20,99))).isEmpty());
    }
    @Test public void simultaneousLeaguesAreReportedSeparately() {
        ScorePolicy p = new ScorePolicy(); p.accept(feed(league("a",10,20,30),league("b",11,21,31)));
        assertEquals(Arrays.asList("a","b"),p.accept(feed(league("a",10.2,20,30),league("b",11,21.4,31))));
    }
    @Test public void newLeagueAndReturnedLeagueEstablishQuietBaseline() {
        ScorePolicy p = new ScorePolicy(); p.accept(feed(league("a",10,20,30)));
        assertTrue(p.accept(feed(league("b",11,21,31))).isEmpty());
        assertTrue(p.accept(feed(league("a",12,22,32),league("b",11,21,31))).isEmpty());
    }
    @Test public void newWeekAndOpponentMakeQuietBaseline() {
        ScorePolicy p = new ScorePolicy(); p.accept(feed(league("a",10,20,30)));
        FeedModels.League week = new FeedModels.League("a", "Demo", 8, new FeedModels.Team("own", "Alex",0,30.0,Collections.emptyList()), new FeedModels.Team("opp-2", "Sam",0,30.0,Collections.emptyList()), .5);
        assertTrue(p.accept(feed(week)).isEmpty());
        FeedModels.League opponent = new FeedModels.League("a", "Demo", 8, new FeedModels.Team("own", "Alex",0,30.0,Collections.emptyList()), new FeedModels.Team("opp-3", "Casey",40,30.0,Collections.emptyList()), .5);
        assertTrue(p.accept(feed(opponent)).isEmpty());
    }
    @Test public void newSeasonMakesQuietBaseline() {
        ScorePolicy p = new ScorePolicy();
        FeedModels.League old = league("a",10,20,30);
        p.accept(feed(new FeedModels.League(old.id,old.name,old.week,old.mine,old.opponent,.5,2026)));
        FeedModels.League fresh = league("a",0,0,30);
        assertTrue(p.accept(feed(new FeedModels.League(fresh.id,fresh.name,fresh.week,fresh.mine,fresh.opponent,.5,2027))).isEmpty());
    }
    @Test public void unavailableResetMakesRecoveryQuiet() {
        ScorePolicy p = new ScorePolicy(); p.accept(feed(league("a",10,20,30))); p.reset();
        assertTrue(p.accept(feed(league("a",12,22,30))).isEmpty());
    }
}
