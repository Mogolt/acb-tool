using System.IO;
using System.Text.RegularExpressions;

namespace AcbStudio.Core;

public sealed class ProjectLoadException(string message) : Exception(message);

/// <summary>
/// Quick Mode: an AWB opened directly, waveform metadata read from each
/// blob's HCA header (no decode).
/// </summary>
public sealed class AwbQuickReader
{
    public string FilePath { get; }
    public Afs2Archive Archive { get; }
    public IReadOnlyList<Waveform> Waveforms { get; }

    public AwbQuickReader(string path)
    {
        FilePath = path;
        Archive = Afs2Archive.Open(path);

        var waveforms = new List<Waveform>(Archive.FileCount);
        for (int i = 0; i < Archive.FileCount; i++)
        {
            var blob = Archive.GetFileAt(i);
            if (HcaMeta.LooksLikeHca(blob))
            {
                var meta = HcaMeta.Parse(blob);
                waveforms.Add(new Waveform(i, meta.Channels, meta.SampleRate, meta.SampleCount,
                    LoopFlag: meta.HasLoop));
            }
            else
            {
                waveforms.Add(new Waveform(i, 0, 0, 0, Codec: "???"));
            }
        }
        Waveforms = waveforms;
    }

    /// <summary>Extracts every waveform as `{stem}_track_NNNN.wav`. Returns written paths.</summary>
    public List<string> ExtractAll(
        string outDir,
        Action<int, int>? progress = null,
        Action<string, string>? log = null,
        CancellationToken ct = default)
    {
        Directory.CreateDirectory(outDir);
        string stem = Path.GetFileNameWithoutExtension(FilePath);
        var written = new List<string>();
        int total = Archive.FileCount;

        for (int i = 0; i < total; i++)
        {
            if (ct.IsCancellationRequested)
                break;
            string outPath = Path.Combine(outDir, $"{stem}_track_{i:0000}.wav");
            try
            {
                HcaCodec.DecodeToWavFile(Archive.GetFileAt(i), outPath);
                written.Add(outPath);
                log?.Invoke($"  extracted {Path.GetFileName(outPath)}", "ok");
            }
            catch (Exception ex)
            {
                log?.Invoke($"  failed track {i:0000}: {ex.Message}", "error");
            }
            progress?.Invoke(i + 1, total);
        }

        return written;
    }
}

/// <summary>
/// Full Project Mode: ACB + companion AWB paired by filename stem.
/// Cue-level browsing and cue-named extraction.
/// </summary>
public sealed class AcbProject
{
    public AcbDocument Acb { get; }
    public Afs2Archive Awb { get; }
    public string AwbPath { get; }

    private static readonly Regex SanitizeRe = new("[\\\\/:*?\"<>|\\x00-\\x1f]+", RegexOptions.Compiled);

    private AcbProject(AcbDocument acb, Afs2Archive awb, string awbPath)
    {
        Acb = acb;
        Awb = awb;
        AwbPath = awbPath;
    }

    public static AcbProject Open(string acbPath)
    {
        var acb = AcbDocument.Open(acbPath);
        string awbPath = acb.ExpectedAwbPath();
        if (!File.Exists(awbPath))
        {
            throw new ProjectLoadException(
                $"No companion AWB at {awbPath}. " +
                $"ACB Studio expects {Path.GetFileName(acbPath)} and {Path.GetFileName(awbPath)} in the same folder.");
        }
        return new AcbProject(acb, Afs2Archive.Open(awbPath), awbPath);
    }

    public string Name => Acb.Name;
    public IReadOnlyList<Cue> Cues() => Acb.Cues();
    public IReadOnlyList<Waveform> Waveforms() => Acb.Waveforms();

    private static string SanitizeFileName(string name)
    {
        string cleaned = SanitizeRe.Replace(name, "_").Trim(' ', '.');
        return cleaned.Length > 0 ? cleaned : "cue";
    }

    /// <summary>
    /// Extracts every cue to WAV named after the cue. Multi-waveform cues get
    /// a `_NN` suffix; duplicate names get `__NN`; orphan cues are skipped.
    /// </summary>
    public List<string> ExtractAllNamed(
        string outDir,
        Action<int, int>? progress = null,
        Action<string, string>? log = null,
        CancellationToken ct = default)
    {
        Directory.CreateDirectory(outDir);

        var cues = Cues();
        var waveforms = Waveforms();

        // Pre-compute tasks so progress is accurate.
        var tasks = new List<(string Stem, int AwbIndex)>();
        var seenNames = new Dictionary<string, int>();
        foreach (var cue in cues)
        {
            if (cue.WaveformTableIndices.Count == 0)
                continue;
            string baseName = SanitizeFileName(cue.Name);
            bool multi = cue.WaveformTableIndices.Count > 1;
            for (int k = 0; k < cue.WaveformTableIndices.Count; k++)
            {
                int tableIdx = cue.WaveformTableIndices[k];
                if (tableIdx < 0 || tableIdx >= waveforms.Count)
                    continue;
                string stem = multi ? $"{baseName}_{k:00}" : baseName;
                if (seenNames.TryGetValue(stem, out int count))
                {
                    seenNames[stem] = count + 1;
                    stem = $"{stem}__{count + 1:00}";
                }
                else
                {
                    seenNames[stem] = 0;
                }
                tasks.Add((stem, waveforms[tableIdx].Index));
            }
        }

        var written = new List<string>();
        int total = tasks.Count;
        for (int i = 0; i < total; i++)
        {
            if (ct.IsCancellationRequested)
                break;
            var (stem, awbIdx) = tasks[i];
            string outPath = Path.Combine(outDir, stem + ".wav");
            try
            {
                HcaCodec.DecodeToWavFile(Awb.GetFileAt(awbIdx), outPath);
                written.Add(outPath);
                log?.Invoke($"  extracted {Path.GetFileName(outPath)}", "ok");
            }
            catch (Exception ex)
            {
                log?.Invoke($"  failed {stem}: {ex.Message}", "error");
            }
            progress?.Invoke(i + 1, total);
        }

        return written;
    }
}
