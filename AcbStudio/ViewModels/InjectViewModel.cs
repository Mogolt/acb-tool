using System.Collections.ObjectModel;
using System.IO;
using System.Windows;
using Microsoft.Win32;
using AcbStudio.Core;
using AcbStudio.Services;

namespace AcbStudio.ViewModels;

/// <summary>Inject tab — queue waveform replacements, save the modified ACB+AWB pair.</summary>
public sealed class InjectViewModel : ObservableObject
{
    private readonly Action<string> _setStatus;
    private readonly PreviewPlayer _preview;

    private AcbProject? _project;
    private InjectPlan? _plan;
    private Dictionary<int, string> _cueLabels = [];

    private string _acbPath = "";
    private string _outDir = "";
    private bool _isSaving;
    private WaveformItem? _selectedWaveform;
    private PendingItem? _selectedPending;

    public InjectViewModel(Action<string> setStatus, PreviewPlayer preview)
    {
        _setStatus = setStatus;
        _preview = preview;
        _preview.StateChanged += () => OnPropertyChanged(nameof(IsPreviewPlaying));

        BrowseAcbCommand = new RelayCommand(BrowseAcb);
        BrowseOutCommand = new RelayCommand(BrowseOut);
        ReplaceCommand = new RelayCommand(ReplaceSelected);
        RemovePendingCommand = new RelayCommand(RemovePendingSelected);
        PreviewSourceCommand = new RelayCommand(async () => await PreviewSourceAsync());
        PreviewReplacementCommand = new RelayCommand(PreviewReplacement);
        StopPreviewCommand = new RelayCommand(_preview.Stop);
        SaveCommand = new RelayCommand(Save);
    }

    /// <summary>Raised with the ACB path after a bank opens successfully.</summary>
    public event Action<string>? ProjectOpened;

    public ObservableCollection<WaveformItem> Waveforms { get; } = [];
    public ObservableCollection<PendingItem> Pending { get; } = [];
    public ObservableCollection<LogEntry> Log { get; } = [];

    public RelayCommand BrowseAcbCommand { get; }
    public RelayCommand BrowseOutCommand { get; }
    public RelayCommand ReplaceCommand { get; }
    public RelayCommand RemovePendingCommand { get; }
    public RelayCommand PreviewSourceCommand { get; }
    public RelayCommand PreviewReplacementCommand { get; }
    public RelayCommand StopPreviewCommand { get; }
    public RelayCommand SaveCommand { get; }

    public string AcbPath { get => _acbPath; set => Set(ref _acbPath, value); }
    public string OutDir { get => _outDir; set => Set(ref _outDir, value); }
    public bool IsPreviewPlaying => _preview.IsPlaying;

    public bool IsSaving
    {
        get => _isSaving;
        private set
        {
            if (Set(ref _isSaving, value))
            {
                OnPropertyChanged(nameof(CanSave));
                OnPropertyChanged(nameof(CanReplace));
            }
        }
    }

    public bool CanReplace => _project is not null && _selectedWaveform is not null && !_isSaving;
    public bool CanRemovePending => _selectedPending is not null;
    public bool CanSave => _plan is not null && Pending.Count > 0 && !_isSaving;

    public WaveformItem? SelectedWaveform
    {
        get => _selectedWaveform;
        set
        {
            if (Set(ref _selectedWaveform, value))
                OnPropertyChanged(nameof(CanReplace));
        }
    }

    public PendingItem? SelectedPending
    {
        get => _selectedPending;
        set
        {
            if (Set(ref _selectedPending, value))
                OnPropertyChanged(nameof(CanRemovePending));
        }
    }

    // ── loading ──────────────────────────────────────────────────────────────

    private void BrowseAcb()
    {
        var dlg = new OpenFileDialog
        {
            Title = "Open ACB",
            Filter = "ACB files (*.acb)|*.acb|All files (*.*)|*.*",
        };
        if (dlg.ShowDialog() != true)
            return;

        AcbPath = dlg.FileName;
        if (string.IsNullOrWhiteSpace(OutDir))
        {
            string parent = Path.GetDirectoryName(dlg.FileName)!;
            OutDir = Path.Combine(parent, new DirectoryInfo(parent).Name + "_modified");
        }
        LoadProject(dlg.FileName);
    }

    private void BrowseOut()
    {
        var dlg = new OpenFolderDialog { Title = "Choose output folder" };
        if (dlg.ShowDialog() == true)
            OutDir = dlg.FolderName;
    }

    public void LoadProject(string path)
    {
        Waveforms.Clear();
        Pending.Clear();
        _project = null;
        _plan = null;
        SelectedWaveform = null;
        SelectedPending = null;
        OnPropertyChanged(nameof(CanSave));
        OnPropertyChanged(nameof(CanReplace));

        try
        {
            _project = AcbProject.Open(path);
        }
        catch (Exception ex)
        {
            AddLog($"Open ACB failed: {ex.Message}", LogKind.Error);
            _setStatus($"Failed to open {Path.GetFileName(path)}");
            return;
        }

        _plan = new InjectPlan(_project);

        // Cue labels per waveform table index (a waveform may serve several cues, or none).
        _cueLabels = [];
        foreach (var cue in _project.Cues())
        {
            foreach (int tableIdx in cue.WaveformTableIndices)
            {
                _cueLabels[tableIdx] = _cueLabels.TryGetValue(tableIdx, out var existing)
                    ? $"{existing}, {cue.Name}"
                    : cue.Name;
            }
        }

        var waveforms = _project.Waveforms();
        for (int i = 0; i < waveforms.Count; i++)
            Waveforms.Add(new WaveformItem(waveforms[i], i, _cueLabels.GetValueOrDefault(i, "(no cue)")));

        string summary = $"{Path.GetFileName(path)}  +  {Path.GetFileName(_project.AwbPath)}  " +
                         $"— {_project.Cues().Count} cues, {waveforms.Count} waveforms";
        _setStatus(summary);
        AddLog($"Opened {path}", LogKind.Info);
        AddLog($"Paired  {_project.AwbPath}", LogKind.Info);
        ProjectOpened?.Invoke(path);
    }

    // ── previews ─────────────────────────────────────────────────────────────

    private async Task PreviewSourceAsync()
    {
        if (_project is null)
            return;
        var item = SelectedWaveform;
        if (item is null)
        {
            _setStatus("Select a waveform row to preview.");
            return;
        }

        try
        {
            _setStatus($"Preview source: wf[{item.TableIndex}] AWB[{item.Waveform.Index}]");
            await _preview.PlayHcaAsync(_project.Awb.GetFileAt(item.Waveform.Index));
        }
        catch (Exception ex)
        {
            AddLog($"Preview failed: {ex.Message}", LogKind.Error);
        }
    }

    private void PreviewReplacement()
    {
        if (_plan is null)
            return;

        // Pending row selection wins; else a waveform row with a queued replacement.
        int? tableIdx = SelectedPending?.TableIndex;
        if (tableIdx is null && SelectedWaveform is { } wf
            && _plan.Pending().Any(r => r.WaveformTableIndex == wf.TableIndex))
        {
            tableIdx = wf.TableIndex;
        }

        var replacement = _plan.Pending().FirstOrDefault(r => r.WaveformTableIndex == tableIdx);
        if (replacement is null)
        {
            _setStatus("Select a pending replacement (or a waveform that has one queued) to preview.");
            return;
        }

        try
        {
            _setStatus($"Preview replacement: {Path.GetFileName(replacement.ReplacementWavPath)}");
            _preview.PlayFile(replacement.ReplacementWavPath);
        }
        catch (Exception ex)
        {
            AddLog($"Preview failed: {ex.Message}", LogKind.Error);
        }
    }

    // ── queueing ─────────────────────────────────────────────────────────────

    private void ReplaceSelected()
    {
        if (_project is null || _plan is null || SelectedWaveform is null)
            return;
        int tableIdx = SelectedWaveform.TableIndex;

        var dlg = new OpenFileDialog
        {
            Title = "Pick replacement WAV",
            Filter = "WAV files (*.wav)|*.wav|All files (*.*)|*.*",
        };
        if (dlg.ShowDialog() != true)
            return;

        Replacement replacement;
        try
        {
            replacement = Replacement.FromWav(tableIdx, dlg.FileName);
        }
        catch (Exception ex)
        {
            AddLog($"  queue failed for wf[{tableIdx}]: {ex.Message}", LogKind.Error);
            return;
        }

        // Format notes — auto-resample is harmless, channel mismatch may not be.
        var src = _project.Waveforms()[tableIdx];
        if (src.SampleRate > 0 && src.SampleRate != replacement.NewSampleRate)
        {
            AddLog($"  auto-resample wf[{tableIdx}]: {replacement.NewSampleRate} Hz → {src.SampleRate} Hz on Save " +
                   "(matches source bank; required for Switch playback)", LogKind.Info);
        }
        if (src.Channels > 0 && src.Channels != replacement.NewChannels)
        {
            AddLog($"  ⚠ channel mismatch on wf[{tableIdx}]: {replacement.NewChannels} ch vs source {src.Channels} ch " +
                   "— may cause playback issues in-game", LogKind.Skip);
        }

        _plan.Add(replacement);
        RefreshPending();
        AddLog($"  queued wf[{tableIdx}] ← {Path.GetFileName(dlg.FileName)}  " +
               $"({replacement.NewChannels}ch {replacement.NewSampleRate}Hz {replacement.NewSampleCount:N0} samp)", LogKind.Ok);
    }

    private void RemovePendingSelected()
    {
        if (_plan is null || SelectedPending is null)
            return;
        _plan.Remove(SelectedPending.TableIndex);
        SelectedPending = null;
        RefreshPending();
    }

    private void RefreshPending()
    {
        Pending.Clear();
        if (_plan is null)
            return;
        var pendingSet = new HashSet<int>();
        foreach (var r in _plan.Pending())
        {
            Pending.Add(new PendingItem(r, _cueLabels.GetValueOrDefault(r.WaveformTableIndex, "(no cue)")));
            pendingSet.Add(r.WaveformTableIndex);
        }
        foreach (var wf in Waveforms)
            wf.IsPending = pendingSet.Contains(wf.TableIndex);
        OnPropertyChanged(nameof(CanSave));
    }

    // ── save ─────────────────────────────────────────────────────────────────

    private async void Save()
    {
        if (_project is null || _plan is null || IsSaving || _plan.Pending().Count == 0)
            return;
        string outDir = OutDir.Trim();
        if (outDir.Length == 0)
        {
            AddLog("Choose an output folder first.", LogKind.Skip);
            return;
        }

        string outAcb = Path.Combine(outDir, Path.GetFileName(_project.Acb.FilePath));
        string outAwb = Path.Combine(outDir, Path.GetFileName(_project.AwbPath));

        if (string.Equals(Path.GetFullPath(outAcb), Path.GetFullPath(_project.Acb.FilePath), StringComparison.OrdinalIgnoreCase))
        {
            var answer = MessageBox.Show(
                $"The output path is the same as the source bank. Overwrite {Path.GetFileName(outAcb)} and {Path.GetFileName(outAwb)}?",
                "Overwrite source bank?", MessageBoxButton.YesNo, MessageBoxImage.Warning);
            if (answer != MessageBoxResult.Yes)
                return;
        }

        IsSaving = true;
        AddLog($"Saving modified bank ({_plan.Pending().Count} replacement(s)) → {outDir}", LogKind.Info);

        var plan = _plan;
        try
        {
            var result = await Task.Run(() =>
            {
                Directory.CreateDirectory(outDir);
                var r = plan.Apply();
                File.WriteAllBytes(outAcb, r.ModifiedAcbBytes);
                File.WriteAllBytes(outAwb, r.ModifiedAwbBytes);
                return r;
            });

            AddLog($"Wrote {Path.GetFileName(outAcb)} ({result.ModifiedAcbBytes.Length:N0} B) + " +
                   $"{Path.GetFileName(outAwb)} ({result.ModifiedAwbBytes.Length:N0} B)  " +
                   $"— {result.ReplacementsApplied} replacement(s) applied.", LogKind.Ok);
            _setStatus($"Saved → {outDir}");

            // Replacements are on disk — clear the queue so the UI shows clean state.
            plan.Clear();
            RefreshPending();
        }
        catch (Exception ex)
        {
            AddLog($"Save failed: {ex.Message}", LogKind.Error);
            _setStatus("Save failed.");
        }
        finally
        {
            IsSaving = false;
        }
    }

    private void AddLog(string text, LogKind kind)
        => RunOnUi(() => Log.Add(new LogEntry(text, kind)));
}
