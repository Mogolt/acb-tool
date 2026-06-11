using AcbStudio.Core;

namespace AcbStudio.ViewModels;

/// <summary>Row in a cue list (Browse tab).</summary>
public sealed class CueItem(Cue cue, int cueIndex) : ObservableObject
{
    private bool _isSelected;

    public Cue Cue { get; } = cue;
    public int CueIndex { get; } = cueIndex;

    public bool IsSelected { get => _isSelected; set => Set(ref _isSelected, value); }

    public string Name => Cue.Name;
    public string CueIdText => Cue.CueId.ToString();
    public string LengthText => Formatting.Duration(Cue.LengthSeconds);
    public string WaveCountText => Cue.WaveformTableIndices.Count.ToString();
}

/// <summary>Row in a waveform list (Browse / Extract / Inject tabs).</summary>
public sealed class WaveformItem(Waveform waveform, int tableIndex, string cueNames = "") : ObservableObject
{
    private bool _isSelected;
    private bool _isPending;

    public Waveform Waveform { get; } = waveform;

    /// <summary>Index into the ACB WaveformTable (== list position).</summary>
    public int TableIndex { get; } = tableIndex;

    public bool IsSelected { get => _isSelected; set => Set(ref _isSelected, value); }
    public bool IsPending { get => _isPending; set { if (Set(ref _isPending, value)) OnPropertyChanged(nameof(PendingText)); } }

    public string TableIndexText => TableIndex.ToString("000");
    public string AwbIdText => Waveform.Index.ToString("000");
    public string CueNames { get; } = cueNames;
    public string Codec => Waveform.Codec;
    public string ChannelsText => Waveform.Channels.ToString();
    public string RateText => Waveform.SampleRate.ToString("N0");
    public string DurationText => Formatting.Duration(Waveform.DurationSeconds);
    public string SamplesText => Waveform.SampleCount.ToString("N0");
    public string LoopText => Waveform.LoopFlag ? "loop" : "";
    public string PendingText => IsPending ? "● queued" : "";
}

/// <summary>Row in the pending-replacements panel (Inject tab).</summary>
public sealed class PendingItem(Replacement replacement, string cueNames) : ObservableObject
{
    private bool _isSelected;

    public Replacement Replacement { get; } = replacement;

    public bool IsSelected { get => _isSelected; set => Set(ref _isSelected, value); }

    public int TableIndex => Replacement.WaveformTableIndex;
    public string TableIndexText => TableIndex.ToString("000");
    public string CueNames { get; } = cueNames;
    public string FileName => System.IO.Path.GetFileName(Replacement.ReplacementWavPath);
    public string FormatText => $"{Replacement.NewChannels}ch {Replacement.NewSampleRate}Hz {Replacement.NewSampleCount:N0} samp";
}

/// <summary>Row in the Convert tab's file list.</summary>
public sealed class ConvertFileItem(string path) : ObservableObject
{
    private bool _isSelected;

    public string Path { get; } = path;
    public string Name => System.IO.Path.GetFileName(Path);
    public bool IsSelected { get => _isSelected; set => Set(ref _isSelected, value); }
}
