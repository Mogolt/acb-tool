using System.Collections.ObjectModel;
using System.IO;
using Microsoft.Win32;
using AcbStudio.Core;
using AcbStudio.Services;

namespace AcbStudio.ViewModels;

/// <summary>Browse tab — Full Project Mode: cue explorer + cue-named extraction.</summary>
public sealed class BrowseViewModel : ObservableObject
{
    private readonly Action<string> _setStatus;
    private readonly PreviewPlayer _preview;

    private AcbProject? _project;
    private CancellationTokenSource? _cts;

    private string _acbPath = "";
    private string _outDir = "";
    private bool _isRunning;
    private double _progress;
    private double _progressMax = 1;
    private string _progressText = "";
    private CueItem? _selectedCue;

    public BrowseViewModel(Action<string> setStatus, PreviewPlayer preview)
    {
        _setStatus = setStatus;
        _preview = preview;
        _preview.StateChanged += () => OnPropertyChanged(nameof(IsPreviewPlaying));

        BrowseAcbCommand = new RelayCommand(BrowseAcb);
        BrowseOutCommand = new RelayCommand(BrowseOut);
        ExtractAllCommand = new RelayCommand(ExtractAll);
        StopCommand = new RelayCommand(() => { _cts?.Cancel(); _setStatus("Stopping…"); });
        PreviewCommand = new RelayCommand(async () => await PreviewSelectedAsync());
        StopPreviewCommand = new RelayCommand(_preview.Stop);
    }

    public ObservableCollection<CueItem> Cues { get; } = [];
    public ObservableCollection<WaveformItem> Waveforms { get; } = [];
    public ObservableCollection<LogEntry> Log { get; } = [];

    public RelayCommand BrowseAcbCommand { get; }
    public RelayCommand BrowseOutCommand { get; }
    public RelayCommand ExtractAllCommand { get; }
    public RelayCommand StopCommand { get; }
    public RelayCommand PreviewCommand { get; }
    public RelayCommand StopPreviewCommand { get; }

    public string AcbPath { get => _acbPath; set => Set(ref _acbPath, value); }
    public string OutDir { get => _outDir; set => Set(ref _outDir, value); }
    public bool IsPreviewPlaying => _preview.IsPlaying;

    public bool IsRunning
    {
        get => _isRunning;
        private set
        {
            if (Set(ref _isRunning, value))
            {
                OnPropertyChanged(nameof(CanExtract));
                OnPropertyChanged(nameof(IsIdle));
            }
        }
    }

    public bool IsIdle => !_isRunning;
    public bool HasProject => _project is not null;
    public bool CanExtract => _project is not null && !_isRunning;

    public double Progress { get => _progress; private set => Set(ref _progress, value); }
    public double ProgressMax { get => _progressMax; private set => Set(ref _progressMax, value); }
    public string ProgressText { get => _progressText; private set => Set(ref _progressText, value); }

    public CueItem? SelectedCue
    {
        get => _selectedCue;
        set
        {
            if (!Set(ref _selectedCue, value) || value is null)
                return;
            // Highlight the waveform rows belonging to the selected cue.
            var targets = value.Cue.WaveformTableIndices.ToHashSet();
            foreach (var wf in Waveforms)
                wf.IsSelected = targets.Contains(wf.TableIndex);
        }
    }

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
            OutDir = Path.Combine(Path.GetDirectoryName(dlg.FileName)!,
                Path.GetFileNameWithoutExtension(dlg.FileName) + "_wav");
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
        Cues.Clear();
        Waveforms.Clear();
        _project = null;
        OnPropertyChanged(nameof(HasProject));
        OnPropertyChanged(nameof(CanExtract));

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

        var cues = _project.Cues();
        var waveforms = _project.Waveforms();

        for (int i = 0; i < cues.Count; i++)
            Cues.Add(new CueItem(cues[i], i));
        for (int i = 0; i < waveforms.Count; i++)
            Waveforms.Add(new WaveformItem(waveforms[i], i));

        OnPropertyChanged(nameof(HasProject));
        OnPropertyChanged(nameof(CanExtract));

        string summary = $"{Path.GetFileName(path)}  +  {Path.GetFileName(_project.AwbPath)}  — {cues.Count} cues, {waveforms.Count} waveforms";
        _setStatus(summary);
        AddLog($"Opened {path}", LogKind.Info);
        AddLog($"Paired  {_project.AwbPath}", LogKind.Info);
    }

    private async Task PreviewSelectedAsync()
    {
        if (_project is null)
            return;
        var selected = Waveforms.FirstOrDefault(w => w.IsSelected);
        if (selected is null)
        {
            _setStatus("Select a waveform row to preview.");
            return;
        }

        try
        {
            _setStatus($"Preview: AWB[{selected.Waveform.Index}] ({selected.DurationText})");
            await _preview.PlayHcaAsync(_project.Awb.GetFileAt(selected.Waveform.Index));
        }
        catch (Exception ex)
        {
            AddLog($"Preview failed: {ex.Message}", LogKind.Error);
        }
    }

    private async void ExtractAll()
    {
        if (_project is null || IsRunning)
            return;
        string outDir = OutDir.Trim();
        if (outDir.Length == 0)
        {
            AddLog("Choose an output folder first.", LogKind.Skip);
            return;
        }

        IsRunning = true;
        _cts = new CancellationTokenSource();
        Progress = 0;
        ProgressMax = 1;
        ProgressText = "";
        AddLog($"Extracting to {outDir}", LogKind.Info);

        var project = _project;
        var token = _cts.Token;

        try
        {
            var written = await Task.Run(() => project.ExtractAllNamed(
                outDir,
                progress: (done, total) => RunOnUi(() =>
                {
                    Progress = done;
                    ProgressMax = Math.Max(total, 1);
                    ProgressText = $"{done} / {total}";
                }),
                log: (msg, tag) => AddLog(msg, tag == "ok" ? LogKind.Ok : tag == "error" ? LogKind.Error : LogKind.Info),
                ct: token));

            string msg = $"Done — {written.Count} files written to {outDir}";
            AddLog(msg, LogKind.Ok);
            _setStatus(msg);
        }
        catch (Exception ex)
        {
            AddLog($"Extraction error: {ex.Message}", LogKind.Error);
            _setStatus("Extraction failed.");
        }
        finally
        {
            IsRunning = false;
        }
    }

    private void AddLog(string text, LogKind kind)
        => RunOnUi(() => Log.Add(new LogEntry(text, kind)));
}
