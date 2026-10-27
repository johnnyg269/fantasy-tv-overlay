package org.fantasytv.overlay;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Immutable normalized feed data. Never contains credentials or a URL to launch. */
public final class FeedModels {
    private FeedModels() {}
    public static final class Player {
        public final String slot, name, gameId;
        public final Double points, projection;
        public final boolean live, onTv;
        public Player(String slot, String name, Double points, Double projection,
                      String gameId, boolean live, boolean onTv) {
            this.slot = slot; this.name = name; this.points = points; this.projection = projection;
            this.gameId = gameId; this.live = live; this.onTv = onTv;
        }
    }
    public static final class Team {
        public final String id, owner;
        public final double score;
        public final Double projection;
        public final List<Player> starters;
        public Team(String owner, double score, Double projection, List<Player> starters) {
            this("", owner, score, projection, starters);
        }
        public Team(String id, String owner, double score, Double projection, List<Player> starters) {
            this.id = id; this.owner = owner; this.score = score; this.projection = projection;
            this.starters = Collections.unmodifiableList(new ArrayList<>(starters));
        }
    }
    public static final class League {
        public final String id, name;
        public final int week, season;
        public final Team mine, opponent;
        public final Double probability;
        public League(String id, String name, int week, Team mine, Team opponent, Double probability) {
            this(id,name,week,mine,opponent,probability,0);
        }
        public League(String id, String name, int week, Team mine, Team opponent, Double probability, int season) {
            this.season = season; this.id = id; this.name = name; this.week = week; this.mine = mine;
            this.opponent = opponent; this.probability = probability;
        }
    }
    public static final class Feed {
        public final double updated;
        public final String watching;
        public final List<League> leagues;
        public Feed(double updated, String watching, List<League> leagues) {
            this.updated = updated; this.watching = watching;
            this.leagues = Collections.unmodifiableList(new ArrayList<>(leagues));
        }
        public League find(String id) {
            for (League league : leagues) if (league.id.equals(id)) return league;
            return null;
        }
        public boolean fresh(double now) { return now - updated <= 120 && updated - now <= 60; }
    }
}
