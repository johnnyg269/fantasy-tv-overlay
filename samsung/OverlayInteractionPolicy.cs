using System;
using System.Collections.Generic;

// Pure local UI state. It never reads input devices or sends commands to the TV.
internal sealed class OverlayInteractionPolicy
{
    private readonly List<string> leagueIds = new List<string>();
    private string lastAlertId;
    private string lastControlRevision;
    private bool haveControlRevision;
    internal bool IsExpanded { get; private set; }
    internal bool IsDismissed { get; private set; }
    internal string SelectedLeagueId { get; private set; }

    internal void AcceptState(string alertId, bool hostVisible, string requestedLeague, IEnumerable<string> available, string controlRevision = null)
    {
        bool controlChanged = controlRevision != null
            && (!haveControlRevision || !string.Equals(controlRevision, lastControlRevision, StringComparison.Ordinal));
        if (controlRevision != null)
        {
            haveControlRevision = true;
            lastControlRevision = controlRevision;
        }
        bool newAlert = alertId != null && !string.Equals(alertId, lastAlertId, StringComparison.Ordinal);
        if (newAlert || controlChanged) IsDismissed = false;
        if (controlChanged && !hostVisible) IsExpanded = false;
        leagueIds.Clear();
        leagueIds.AddRange(available);
        if (!IsExpanded || !leagueIds.Contains(SelectedLeagueId ?? string.Empty))
        {
            SelectedLeagueId = requestedLeague != null && leagueIds.Contains(requestedLeague)
                ? requestedLeague : (leagueIds.Count == 0 ? null : leagueIds[0]);
        }
        if (leagueIds.Count == 0) IsExpanded = false;
        lastAlertId = alertId;
    }

    internal bool Open()
    {
        if (IsDismissed || leagueIds.Count == 0) return false;
        IsExpanded = true;
        return true;
    }

    internal bool MoveLeague(int direction)
    {
        if (!IsExpanded || leagueIds.Count < 2 || direction == 0) return false;
        int current = leagueIds.IndexOf(SelectedLeagueId);
        if (current < 0) current = 0;
        int next = (current + Math.Sign(direction) + leagueIds.Count) % leagueIds.Count;
        SelectedLeagueId = leagueIds[next];
        return true;
    }

    internal void Close()
    {
        IsExpanded = false;
        IsDismissed = true;
    }

    internal bool ShouldShow(bool requested, bool popupAlive)
    {
        return IsExpanded || (!IsDismissed && requested && popupAlive);
    }
}
