package org.fantasytv.overlay;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Pure score-change policy: first data is quiet, projections never trigger alerts. */
public final class ScorePolicy {
    private Map<String, double[]> baseline = new HashMap<>();
    private Map<String, String> identities = new HashMap<>();
    public List<String> accept(FeedModels.Feed feed) {
        List<String> changes = new ArrayList<>();
        Map<String, double[]> next = new HashMap<>();
        Map<String, String> nextIdentities = new HashMap<>();
        for (FeedModels.League league : feed.leagues) {
            double[] totals = {league.mine.score, league.opponent.score};
            double[] old = baseline.get(league.id);
            String identity = league.season + "|" + league.week + "|" + league.mine.id + "|" + league.opponent.id;
            if (old != null && identity.equals(identities.get(league.id)) && (Double.compare(old[0], totals[0]) != 0 || Double.compare(old[1], totals[1]) != 0)) {
                changes.add(league.id);
            }
            next.put(league.id, totals);
            nextIdentities.put(league.id, identity);
        }
        baseline = next; identities = nextIdentities;
        return changes;
    }
    public void reset() { baseline.clear(); identities.clear(); }
}
