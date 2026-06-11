using System.Buffers.Binary;
using System.IO;

namespace AcbStudio.Core;

/// <summary>
/// Read + patch view over an ACB file (a root @UTF table with nested tables).
///
/// Resolves cues to waveform indices across both schema variants seen in RE4
/// banks (simple `Id`, extended `StreamAwbId`/`MemoryAwbId`) and both
/// reference types seen (0x01 direct, 0x03 sequence).
/// </summary>
public sealed class AcbDocument
{
    public string FilePath { get; }
    public UtfTable Root { get; }

    private List<Waveform>? _waveforms;
    private List<Cue>? _cues;

    private AcbDocument(string path, UtfTable root)
    {
        FilePath = path;
        Root = root;
    }

    public static AcbDocument Open(string path)
    {
        var root = UtfTable.Parse(File.ReadAllBytes(path));
        return new AcbDocument(path, root);
    }

    public string Name =>
        Root.Rows.Count > 0 && Root.Rows[0].TryGetValue("Name", out var v) && v.Value is string s ? s : "";

    public string ExpectedAwbPath() => Path.ChangeExtension(FilePath, ".awb");

    private UtfTable RequireTable(string column)
        => Root.NestedTable(column) ?? throw new InvalidDataException($"ACB has no {column}");

    public UtfTable WaveformTable => RequireTable("WaveformTable");
    public UtfTable CueTable => RequireTable("CueTable");
    public UtfTable? CueNameTable => Root.NestedTable("CueNameTable");
    public UtfTable? SequenceTable => Root.NestedTable("SequenceTable");

    // ── waveforms ────────────────────────────────────────────────────────────

    public IReadOnlyList<Waveform> Waveforms() => _waveforms ??= BuildWaveforms();

    private List<Waveform> BuildWaveforms()
    {
        var result = new List<Waveform>();
        var wt = WaveformTable;
        foreach (var row in wt.Rows)
        {
            long Get(string key, long fallback = 0)
                => row.TryGetValue(key, out var v) && v.Value is not null ? v.AsInt() : fallback;

            long streaming = Get("Streaming");
            long awbIdx;
            if (row.ContainsKey("StreamAwbId") && streaming == 1)
            {
                awbIdx = Get("StreamAwbId");
            }
            else if (row.ContainsKey("MemoryAwbId"))
            {
                long memId = Get("MemoryAwbId");
                awbIdx = memId == 0xFFFF && row.ContainsKey("StreamAwbId") ? Get("StreamAwbId") : memId;
            }
            else if (row.ContainsKey("Id"))
            {
                awbIdx = Get("Id");
            }
            else
            {
                throw new InvalidDataException(
                    $"unknown WaveformTable schema, columns: {string.Join(", ", wt.Columns)}");
            }

            long encodeType = Get("EncodeType", 2);
            string codecName = encodeType switch
            {
                0 => "ADX", 1 => "PCM", 2 => "HCA", 6 => "HCAMX",
                _ => $"codec_{encodeType}",
            };

            result.Add(new Waveform(
                Index: (int)awbIdx,
                Channels: (int)Get("NumChannels"),
                SampleRate: (int)Get("SamplingRate"),
                SampleCount: (int)Get("NumSamples"),
                Codec: codecName,
                LoopFlag: Get("LoopFlag") != 0));
        }
        return result;
    }

    // ── cues ─────────────────────────────────────────────────────────────────

    public IReadOnlyList<Cue> Cues() => _cues ??= BuildCues();

    private List<Cue> BuildCues()
    {
        var nameByCueIdx = new Dictionary<int, string>();
        if (CueNameTable is { } cnt)
        {
            foreach (var row in cnt.Rows)
            {
                if (row.TryGetValue("CueIndex", out var ci) && row.TryGetValue("CueName", out var cn)
                    && cn.Value is string name)
                {
                    nameByCueIdx[(int)ci.AsInt()] = name;
                }
            }
        }

        var cues = new List<Cue>();
        var ct = CueTable;
        for (int cueIdx = 0; cueIdx < ct.Rows.Count; cueIdx++)
        {
            var row = ct.Rows[cueIdx];
            int cueId = (int)row["CueId"].AsInt();
            string name = nameByCueIdx.TryGetValue(cueIdx, out var n1) ? n1
                : nameByCueIdx.TryGetValue(cueId, out var n2) ? n2
                : $"cue_{cueId:00000}";
            int refType = (int)row["ReferenceType"].AsInt();
            int refIdx = (int)row["ReferenceIndex"].AsInt();
            int lengthMs = (int)row["Length"].AsInt();

            cues.Add(new Cue(cueId, name, lengthMs, ResolveReference(refType, refIdx)));
        }
        return cues;
    }

    private List<int> ResolveReference(int refType, int refIdx)
    {
        // 0x01 direct, 0x03 sequence (track -> waveform indices); other types
        // (0x02 Synth / 0x08 BlockSequence) don't occur in RE4 — return empty
        // so the GUI still shows the cue with a no-waveform indicator.
        if (refType == 0x01)
            return [refIdx];

        if (refType == 0x03 && SequenceTable is { } st && refIdx >= 0 && refIdx < st.Rows.Count)
        {
            var seq = st.Rows[refIdx];
            int numTracks = (int)seq["NumTracks"].AsInt();
            if (seq["TrackIndex"].Value is byte[] blob)
            {
                var indices = new List<int>(numTracks);
                for (int i = 0; i < numTracks && i * 2 + 1 < blob.Length; i++)
                    indices.Add(BinaryPrimitives.ReadUInt16BigEndian(blob.AsSpan(i * 2, 2)));
                return indices;
            }
        }

        return [];
    }

    // ── patching (inject) ────────────────────────────────────────────────────

    /// <summary>Patch the ACB mirror fields for one waveform row, in lockstep
    /// with the AWB rebuild. Identity fields (Id/StreamAwbId/EncodeType/
    /// Streaming/LoopFlag) are deliberately untouched.</summary>
    public void PatchWaveform(int tableIndex, int channels, int sampleRate, int sampleCount)
    {
        var row = WaveformTable.Rows[tableIndex];
        SetIntCell(row, "NumChannels", channels);
        SetIntCell(row, "SamplingRate", sampleRate);
        SetIntCell(row, "NumSamples", sampleCount);
        _waveforms = null;
    }

    public void PatchCueLength(int cueIndex, int lengthMs)
    {
        SetIntCell(CueTable.Rows[cueIndex], "Length", lengthMs);
        _cues = null;
    }

    private static void SetIntCell(Dictionary<string, UtfValue> row, string key, long value)
    {
        if (!row.TryGetValue(key, out var cell))
            return;
        row[key].Value = cell.Type switch
        {
            UtfType.U8 => (byte)value,
            UtfType.S8 => (sbyte)value,
            UtfType.U16 => (ushort)value,
            UtfType.S16 => (short)value,
            UtfType.U32 => (uint)value,
            UtfType.S32 => (int)value,
            UtfType.U64 => (ulong)value,
            UtfType.S64 => value,
            _ => row[key].Value,
        };
    }

    public byte[] Serialize() => Root.Serialize();
}
