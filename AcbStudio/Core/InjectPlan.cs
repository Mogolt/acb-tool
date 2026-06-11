using System.IO;

namespace AcbStudio.Core;

/// <summary>One queued waveform swap, with WAV metadata for the pending panel.</summary>
public sealed record Replacement(
    int WaveformTableIndex,
    string ReplacementWavPath,
    HcaQuality Quality,
    int NewChannels,
    int NewSampleRate,
    int NewSampleCount)
{
    /// <summary>Reads WAV metadata only — the (slow) HCA encode is deferred to
    /// <see cref="InjectPlan.Apply"/> so queueing is instant.</summary>
    public static Replacement FromWav(int waveformTableIndex, string wavPath, HcaQuality quality = HcaCodec.DefaultQuality)
    {
        var fmt = WavUtil.ReadFormat(File.ReadAllBytes(wavPath));
        return new Replacement(waveformTableIndex, wavPath, quality, fmt.Channels, fmt.SampleRate, fmt.SampleFrames);
    }
}

public sealed record ApplyResult(byte[] ModifiedAcbBytes, byte[] ModifiedAwbBytes, int ReplacementsApplied);

/// <summary>
/// Collects waveform replacements and applies them in one atomic rebuild:
/// auto-resample → HCA encode (loop-preserving) → AWB rebuild → ACB
/// mirror-field + cue-length patch.
/// </summary>
public sealed class InjectPlan(AcbProject project)
{
    private readonly Dictionary<int, Replacement> _replacements = [];

    public AcbProject Project { get; } = project;

    public void Add(Replacement r)
    {
        var waveforms = Project.Waveforms();
        if (r.WaveformTableIndex < 0 || r.WaveformTableIndex >= waveforms.Count)
        {
            throw new ArgumentOutOfRangeException(nameof(r),
                $"waveform_table_index {r.WaveformTableIndex} out of range (bank has {waveforms.Count} waveforms)");
        }
        if (!File.Exists(r.ReplacementWavPath))
            throw new FileNotFoundException(r.ReplacementWavPath);
        _replacements[r.WaveformTableIndex] = r;
    }

    public void Remove(int waveformTableIndex) => _replacements.Remove(waveformTableIndex);

    public void Clear() => _replacements.Clear();

    public IReadOnlyList<Replacement> Pending()
        => _replacements.Keys.OrderBy(k => k).Select(k => _replacements[k]).ToList();

    /// <summary>Produces modified ACB + AWB bytes. Does not write to disk.</summary>
    public ApplyResult Apply()
    {
        if (_replacements.Count == 0)
            throw new InvalidOperationException("no replacements queued");

        var waveforms = Project.Waveforms();
        var cues = Project.Cues();
        var awb = Project.Awb;

        var replacementBlobs = new Dictionary<int, byte[]>();              // awb index -> new HCA
        var replacementMeta = new Dictionary<int, (int Ch, int Rate, int Samples)>(); // table index -> mirror fields

        foreach (var r in Pending())
        {
            var wf = waveforms[r.WaveformTableIndex];

            // Auto-resample to the source bank's rate — Switch RE4 silently
            // drops audio when the on-disk rate doesn't match what the engine
            // preallocated for.
            var wavBytes = File.ReadAllBytes(r.ReplacementWavPath);
            if (wf.SampleRate > 0 && wf.SampleRate != r.NewSampleRate)
                wavBytes = WavUtil.Resample(wavBytes, wf.SampleRate);

            // If the original waveform loops, emit a whole-file loop chunk in
            // the HCA. Without it, replacing BGM/long ambient cues plays once
            // then goes silent — exactly what hardware testing hit.
            bool preserveLooping = wf.LoopFlag;
            var hcaBytes = HcaCodec.EncodeWavToHca(wavBytes, r.Quality, loopWholeFile: preserveLooping);
            var meta = HcaMeta.Parse(hcaBytes);

            replacementBlobs[wf.Index] = hcaBytes;
            replacementMeta[r.WaveformTableIndex] = (meta.Channels, meta.SampleRate, meta.SampleCount);
        }

        // Rebuild the AWB: replacements where queued, original blobs elsewhere
        // (with their trailing alignment padding stripped — the rebuild re-pads).
        var newBlobs = new List<byte[]>(awb.FileCount);
        for (int i = 0; i < awb.FileCount; i++)
        {
            newBlobs.Add(replacementBlobs.TryGetValue(i, out var blob)
                ? blob
                : StripTrailingZeros(awb.GetFileAt(i)));
        }
        var newAwbBytes = awb.Rebuild(newBlobs);

        // Patch ACB WaveformTable mirror fields.
        foreach (var (tableIdx, meta) in replacementMeta)
            Project.Acb.PatchWaveform(tableIdx, meta.Ch, meta.Rate, meta.Samples);

        // Patch CueTable.Length for every cue referencing a replaced waveform,
        // so cues aren't truncated at their original length.
        for (int cueIdx = 0; cueIdx < cues.Count; cueIdx++)
        {
            foreach (var (tableIdx, meta) in replacementMeta)
            {
                if (cues[cueIdx].WaveformTableIndices.Contains(tableIdx))
                {
                    int newLenMs = (int)Math.Round(meta.Samples * 1000.0 / meta.Rate);
                    Project.Acb.PatchCueLength(cueIdx, newLenMs);
                    break;
                }
            }
        }

        return new ApplyResult(Project.Acb.Serialize(), newAwbBytes, _replacements.Count);
    }

    private static byte[] StripTrailingZeros(byte[] data)
    {
        int end = data.Length;
        while (end > 0 && data[end - 1] == 0)
            end--;
        return end == 0 ? data : data.AsSpan(0, end).ToArray();
    }
}
