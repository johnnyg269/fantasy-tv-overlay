using System;
using System.IO;
using System.Text.Json;

// Pure policy: native UI calls stay in FantasyOverlay's Ecore thread.
internal sealed class AlertPopupPolicy
{
    internal sealed class Spec
    {
        internal string Id;
        internal int DurationSeconds = 5;
    }

    private readonly long ticksPerSecond;
    private bool alertMode;
    private string activeId;
    private long deadline;

    internal AlertPopupPolicy(long frequency)
    {
        if (frequency <= 0 || frequency > long.MaxValue / 30)
            throw new ArgumentOutOfRangeException(nameof(frequency));
        ticksPerSecond = frequency;
    }

    internal static Spec Parse(JsonElement root)
    {
        Spec result = new Spec();
        if (!root.TryGetProperty("alertId", out JsonElement id)) return result;
        if (id.ValueKind != JsonValueKind.String)
            throw new InvalidDataException("alertId must be a nonempty string");
        result.Id = id.GetString();
        if (string.IsNullOrWhiteSpace(result.Id) || result.Id.Length > 256)
            throw new InvalidDataException("alertId must contain 1..256 nonblank characters");
        if (root.TryGetProperty("durationSeconds", out JsonElement duration))
        {
            if (duration.ValueKind != JsonValueKind.Number
                || !duration.TryGetInt32(out result.DurationSeconds)
                || result.DurationSeconds < 1 || result.DurationSeconds > 30)
                throw new InvalidDataException("durationSeconds must be an integer from 1 through 30");
        }
        return result;
    }

    // Return true only when a new alert is armed. Same-ID heartbeats never rearm.
    internal bool Apply(Spec spec, long now)
    {
        if (spec.Id == null)
        {
            alertMode = false;
            activeId = null;
            return false;
        }
        bool isNew = !alertMode || !string.Equals(activeId, spec.Id, StringComparison.Ordinal);
        if (isNew)
        {
            activeId = spec.Id;
            deadline = checked(now + (spec.DurationSeconds * ticksPerSecond));
        }
        alertMode = true;
        return isNew;
    }

    internal bool ShouldShow(bool requested, long now)
    {
        return requested && (!alertMode || now < deadline);
    }
}
