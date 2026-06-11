namespace AcbStudio.Core;

/// <summary>A single HCA waveform entry — same shape for Quick (AWB-only) and Project (ACB+AWB) modes.</summary>
public sealed record Waveform(
    int Index,          // AWB offset-table index
    int Channels,
    int SampleRate,
    int SampleCount,
    string Codec = "HCA",
    bool LoopFlag = false)
{
    public double DurationSeconds => SampleRate > 0 ? (double)SampleCount / SampleRate : 0;
}

/// <summary>A named entry in the ACB cue table (Project mode only).</summary>
public sealed record Cue(
    int CueId,
    string Name,
    int LengthMs,
    IReadOnlyList<int> WaveformTableIndices)
{
    public double LengthSeconds => LengthMs / 1000.0;
}

public static class Formatting
{
    public static string Duration(double seconds)
    {
        if (seconds <= 0)
            return "?";
        int total = (int)Math.Round(seconds);
        int m = total / 60;
        int s = total % 60;
        return seconds < 1 ? $"{seconds:0.00}s" : $"{m}:{s:00}";
    }
}
