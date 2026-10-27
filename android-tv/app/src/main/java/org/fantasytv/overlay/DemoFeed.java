package org.fantasytv.overlay;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/** Fictional demo only; does not contact a server or imitate live provider data. */
final class DemoFeed {
    private DemoFeed() {}
    static FeedModels.Feed create(long step) {
        List<FeedModels.Player> mine = new ArrayList<>(), theirs = new ArrayList<>();
        String[] slots = {"QB","RB","RB","WR","WR","TE","FLEX","D/ST","K"};
        for (int i = 0; i < slots.length; i++) {
            mine.add(new FeedModels.Player(slots[i], new String[]{"Avery Rivers","Jordan Wells","Taylor Brooks","Cameron Reed","Morgan Blake","Riley Stone","Casey Lane","Coastal Defense","Drew Parker"}[i], 10.2 + i, 12.0 + i, "demo", i < 3, false));
            theirs.add(new FeedModels.Player(slots[i], new String[]{"Hayden Cole","Jamie North","Alex Quinn","Dakota Ellis","Skyler James","Rowan Cruz","Finley Hayes","Mountain Defense","Reese Walker"}[i], 8.3 + i, 11.4 + i, "demo", i == 2 || i == 4, false));
        }
        FeedModels.League first = new FeedModels.League("demo-a", "DEMO · Sunday league", 7,
            new FeedModels.Team("demo-own", "Alex", 112.46 + step * .1, 138.2, mine),
            new FeedModels.Team("demo-sam", "Sam", 104.82, 131.5, theirs), .643);
        FeedModels.League second = new FeedModels.League("demo-b", "DEMO · Friends league", 7,
            new FeedModels.Team("demo-own", "Alex", 98.74, 120.2, mine),
            new FeedModels.Team("demo-casey", "Casey", 102.12 + step * .1, 127.7, theirs), .412);
        return new FeedModels.Feed(System.currentTimeMillis() / 1000.0, "", Arrays.asList(first, second));
    }
}
