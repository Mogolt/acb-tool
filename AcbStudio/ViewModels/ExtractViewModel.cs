using System.Collections.ObjectModel;
using System.IO;
using Microsoft.Win32;
using AcbStudio.Core;
using AcbStudio.Services;

namespace AcbStudio.ViewModels;

/// <summary>Extract tab — Quick Mode: AWB only, numbered WAV output.</summary>
public sealed class ExtractViewModel : ObservableObject
{
    private readonly Action<string> _setStatus;
    private readonly PreviewPlayer _preview;

    private AwbQuickReader? _reader;
    private CancellationTokenSource? _cts;

    private string _awbPath = "";
    private string _outDir = "";
    private bool _isRunning;
    private double _progress;
    private double _progressMax = 1;
    private string _progressText = "";

    public ExtractViewModel(Action<string> setStatus, PreviewPlayer preview)
    {
        _setStatus = setStatus;
        _preview = preview;
        _preview.StateChanged += () => OnPropertyChanged(nameof(IsPreviewPlaying));

        BrowseAwbCommand = new RelayCommand(BrowseAwb);
        BrowseOutCommand = new RelayCommand(BrowseOut);
        ExtractAllCommand = new RelayCommand(ExtractAll);
        StopCommand = new RelayCommand(() => { _cts?.Cancel(); _setStatus("Stopping…"); });
        PreviewCommand = new RelayCommand(async () => await PreviewSelectedAsync());
        StopPreviewCommand = new RelayCommand(_preview.Stop);
    }

    public ObservableCollection<WaveformItem> Waveforms { get; } = [];
    public ObservableCollection<LogEntry> Log { get; } = [];

    public RelayCommand BrowseAwbCommand { get; }
    public RelayCommand BrowseOutCommand { get; }
    public RelayCommand ExtractAllCommand { get; }
    public RelayCommand StopCommand { get; }
    public RelayCommand PreviewCommand { get; }
    public RelayCommand StopPreviewCommand { get; }

    public string AwbPath { get => _awbPath; set => Set(ref _awbPath, value); }
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
    public bool CanExtract => _reader is not null && !_isRunning;

    public double Progress { get => _progress; private set => Set(ref _progress, value); }
    public double ProgressMax { get => _progressMax; private set => Set(ref _progressMax, value); }
    public string ProgressText { get => _progressText; private set => Set(ref _progressText, value); }

    private void BrowseAwb()
    {
        var dlg = new OpenFileDialog
        {
            Title = "Open AWB",
            Filter = "AWB files (*.awb)|*.awb|All files (*.*)|*.*",
        };
        if (dlg.ShowDialog() != true)
            return;

        AwbPath = dlg.FileName;
        if (string.IsNullOrWhiteSpace(OutDir))
            OutDir = Path.Combine(Path.GetDirectoryName(dlg.FileName)!,
                Path.GetFileNameWithoutExtension(dlg.FileName) + "_wav");
        LoadAwb(dlg.FileName);
    }

    private void BrowseOut()
    {
        var dlg = new OpenFolderDialog { Title = "Choose output folder" };
        if (dlg.ShowDialog() == true)
            OutDir = dlg.FolderName;
    }

    public void LoadAwb(string path)
    {
        Waveforms.Clear();
        _reader = null;
        OnPropertyChanged(nameof(CanExtract));

        try
        {
            _reader = new AwbQuickReader(path);
        }
        catch (Exception ex)
        {
            AddLog($"Open AWB failed: {ex.Message}", LogKind.Error);
            _setStatus($"Failed to open {Path.GetFileName(path)}");
            return;
        }

        for (int i = 0; i < _reader.Waveforms.Count; i++)
            Waveforms.Add(new WaveformItem(_reader.Waveforms[i], i));

        OnPropertyChanged(nameof(CanExtract));
        _setStatus($"{Path.GetFileName(path)} — {_reader.Archive.FileCount} waveforms");
        AddLog($"Opened {path} ({_reader.Archive.FileCount} waveforms)", LogKind.Info);
    }

    private async Task PreviewSelectedAsync()
    {
        if (_reader is null)
            return;
        var selected = Waveforms.FirstOrDefault(w => w.IsSelected);
        if (selected is null)
        {
            _setStatus("Select a waveform row to preview.");
            return;
        }

        try
        {
            _setStatus($"Preview: track {selected.Waveform.Index:0000}");
            await _preview.PlayHcaAsync(_reader.Archive.GetFileAt(selected.Waveform.Index));
        }
        catch (Exception ex)
        {
            AddLog($"Preview failed: {ex.Message}", LogKind.Error);
        }
    }

    private async void ExtractAll()
    {
        if (_reader is null || IsRunning)
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
        ProgressMax = _reader.Archive.FileCount;
        ProgressText = $"0 / {_reader.Archive.FileCount}";
        AddLog($"Extracting to {outDir}", LogKind.Info);

        var reader = _reader;
        var token = _cts.Token;

        try
        {
            var written = await Task.Run(() => reader.ExtractAll(
                outDir,
                progress: (done, total) => RunOnUi(() =>
                {
                    Progress = done;
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
