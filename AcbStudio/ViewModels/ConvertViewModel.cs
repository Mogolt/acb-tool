using System.Collections.ObjectModel;
using System.IO;
using Microsoft.Win32;
using AcbStudio.Core;
using AcbStudio.Services;

namespace AcbStudio.ViewModels;

/// <summary>Convert tab — standalone WAV ↔ HCA, batch-capable.</summary>
public sealed class ConvertViewModel : ObservableObject
{
    public static readonly string[] DirectionChoices =
    [
        "Auto-detect by extension",
        "WAV → HCA (encode)",
        "HCA → WAV (decode)",
    ];

    public static readonly string[] QualityChoices =
    [
        "Highest (default — required for PSNR ≥ 40 dB)",
        "High",
        "Middle",
        "Low",
        "Lowest",
    ];

    private readonly Action<string> _setStatus;
    private readonly PreviewPlayer _preview;
    private CancellationTokenSource? _cts;

    private string _outDir = "";
    private int _directionIndex;
    private int _qualityIndex;
    private bool _isRunning;
    private double _progress;
    private double _progressMax = 1;
    private string _progressText = "";

    public ConvertViewModel(Action<string> setStatus, PreviewPlayer preview)
    {
        _setStatus = setStatus;
        _preview = preview;
        _preview.StateChanged += () => OnPropertyChanged(nameof(IsPreviewPlaying));

        BrowseOutCommand = new RelayCommand(BrowseOut);
        AddFilesCommand = new RelayCommand(AddFiles);
        RemoveSelectedCommand = new RelayCommand(RemoveSelected);
        ClearCommand = new RelayCommand(() => Files.Clear());
        PreviewCommand = new RelayCommand(PreviewSelected);
        StopPreviewCommand = new RelayCommand(_preview.Stop);
        ConvertCommand = new RelayCommand(Convert);
        StopCommand = new RelayCommand(() => { _cts?.Cancel(); _setStatus("Stopping…"); });

        Files.CollectionChanged += (_, _) => OnPropertyChanged(nameof(FileCountText));
    }

    public ObservableCollection<ConvertFileItem> Files { get; } = [];
    public ObservableCollection<LogEntry> Log { get; } = [];

    public RelayCommand BrowseOutCommand { get; }
    public RelayCommand AddFilesCommand { get; }
    public RelayCommand RemoveSelectedCommand { get; }
    public RelayCommand ClearCommand { get; }
    public RelayCommand PreviewCommand { get; }
    public RelayCommand StopPreviewCommand { get; }
    public RelayCommand ConvertCommand { get; }
    public RelayCommand StopCommand { get; }

    public string OutDir { get => _outDir; set => Set(ref _outDir, value); }
    public int DirectionIndex { get => _directionIndex; set => Set(ref _directionIndex, value); }
    public int QualityIndex { get => _qualityIndex; set => Set(ref _qualityIndex, value); }
    public bool IsPreviewPlaying => _preview.IsPlaying;

    public bool IsRunning
    {
        get => _isRunning;
        private set
        {
            if (Set(ref _isRunning, value))
                OnPropertyChanged(nameof(IsIdle));
        }
    }

    public bool IsIdle => !_isRunning;

    public double Progress { get => _progress; private set => Set(ref _progress, value); }
    public double ProgressMax { get => _progressMax; private set => Set(ref _progressMax, value); }
    public string ProgressText { get => _progressText; private set => Set(ref _progressText, value); }

    public string FileCountText => Files.Count switch
    {
        0 => "No files yet — add WAVs/HCAs or drop them here",
        1 => "1 file",
        var n => $"{n} files",
    };

    private HcaQuality SelectedQuality => QualityIndex switch
    {
        1 => HcaQuality.High,
        2 => HcaQuality.Middle,
        3 => HcaQuality.Low,
        4 => HcaQuality.Lowest,
        _ => HcaQuality.Highest,
    };

    private void BrowseOut()
    {
        var dlg = new OpenFolderDialog { Title = "Choose output folder" };
        if (dlg.ShowDialog() == true)
            OutDir = dlg.FolderName;
    }

    public void AddPaths(IEnumerable<string> paths)
    {
        foreach (var path in paths)
        {
            if (Directory.Exists(path))
            {
                foreach (var f in Directory.EnumerateFiles(path)
                             .Where(f => f.EndsWith(".wav", StringComparison.OrdinalIgnoreCase)
                                      || f.EndsWith(".hca", StringComparison.OrdinalIgnoreCase))
                             .OrderBy(f => f, StringComparer.OrdinalIgnoreCase))
                    AddOne(f);
            }
            else
            {
                AddOne(path);
            }
        }
    }

    private void AddOne(string path)
    {
        if (!Files.Any(f => string.Equals(f.Path, path, StringComparison.OrdinalIgnoreCase)))
            Files.Add(new ConvertFileItem(path));
    }

    private void AddFiles()
    {
        var dlg = new OpenFileDialog
        {
            Title = "Add WAV or HCA files",
            Filter = "Audio (*.wav;*.hca)|*.wav;*.hca|WAV (*.wav)|*.wav|HCA (*.hca)|*.hca|All files (*.*)|*.*",
            Multiselect = true,
        };
        if (dlg.ShowDialog() == true)
            AddPaths(dlg.FileNames);
    }

    private void RemoveSelected()
    {
        foreach (var item in Files.Where(f => f.IsSelected).ToList())
            Files.Remove(item);
    }

    private void PreviewSelected()
    {
        var item = Files.FirstOrDefault(f => f.IsSelected);
        if (item is null)
        {
            _setStatus("Select a file in the list to preview.");
            return;
        }

        _setStatus($"Preview: {item.Name}");
        try
        {
            if (item.Path.EndsWith(".hca", StringComparison.OrdinalIgnoreCase))
                _ = _preview.PlayHcaAsync(File.ReadAllBytes(item.Path));
            else
                _preview.PlayFile(item.Path);
        }
        catch (Exception ex)
        {
            AddLog($"Preview failed: {ex.Message}", LogKind.Error);
        }
    }

    private static bool? IsEncode(string path, int directionIndex) => directionIndex switch
    {
        1 => true,
        2 => false,
        _ => Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".wav" => true,
            ".hca" => false,
            _ => null,
        },
    };

    private async void Convert()
    {
        if (IsRunning)
            return;
        if (Files.Count == 0)
        {
            AddLog("Add WAV or HCA files to the list first.", LogKind.Skip);
            return;
        }
        string outDir = OutDir.Trim();
        if (outDir.Length == 0)
        {
            AddLog("Choose an output folder first.", LogKind.Skip);
            return;
        }

        var files = Files.Select(f => f.Path).ToList();
        var quality = SelectedQuality;
        int directionIndex = DirectionIndex;

        IsRunning = true;
        _cts = new CancellationTokenSource();
        Progress = 0;
        ProgressMax = files.Count;
        ProgressText = $"0 / {files.Count}";
        AddLog($"Converting {files.Count} file(s) → {outDir}", LogKind.Info);

        var token = _cts.Token;
        int succeeded = 0;

        await Task.Run(() =>
        {
            Directory.CreateDirectory(outDir);
            for (int i = 0; i < files.Count; i++)
            {
                if (token.IsCancellationRequested)
                    break;

                string src = files[i];
                bool? encode = IsEncode(src, directionIndex);
                if (encode is null)
                {
                    AddLog($"  skip (unrecognized): {Path.GetFileName(src)}", LogKind.Error);
                }
                else
                {
                    string outPath = Path.Combine(outDir,
                        Path.GetFileNameWithoutExtension(src) + (encode.Value ? ".hca" : ".wav"));
                    try
                    {
                        if (encode.Value)
                            HcaCodec.EncodeWavFileToHcaFile(src, outPath, quality);
                        else
                            HcaCodec.DecodeToWavFile(File.ReadAllBytes(src), outPath);
                        AddLog($"  ok   {Path.GetFileName(outPath)}", LogKind.Ok);
                        succeeded++;
                    }
                    catch (Exception ex)
                    {
                        AddLog($"  fail {Path.GetFileName(src)}: {ex.Message}", LogKind.Error);
                    }
                }

                int done = i + 1;
                RunOnUi(() =>
                {
                    Progress = done;
                    ProgressText = $"{done} / {files.Count}";
                });
            }
        });

        string msg = $"Done — {succeeded}/{files.Count} files converted.";
        AddLog(msg, succeeded == files.Count ? LogKind.Ok : LogKind.Info);
        _setStatus(msg);
        IsRunning = false;
    }

    private void AddLog(string text, LogKind kind)
        => RunOnUi(() => Log.Add(new LogEntry(text, kind)));
}
