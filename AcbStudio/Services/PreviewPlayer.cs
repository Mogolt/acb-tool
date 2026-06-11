using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Threading;
using AcbStudio.Core;

namespace AcbStudio.Services;

/// <summary>
/// One app-wide audio preview: decodes HCA blobs to a temp WAV (or plays WAV
/// files directly) through winmm. Starting a new preview, switching tabs, or
/// closing the app stops the current one.
/// </summary>
public sealed class PreviewPlayer
{
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    private static extern bool PlaySound(string? pszSound, IntPtr hmod, uint fdwSound);

    private const uint SND_ASYNC = 0x0001;
    private const uint SND_NODEFAULT = 0x0002;
    private const uint SND_PURGE = 0x0040;
    private const uint SND_FILENAME = 0x00020000;

    private DispatcherTimer? _timer;
    private string? _tempFile;
    private int _generation;

    public bool IsPlaying { get; private set; }

    /// <summary>Raised on the UI thread whenever playback starts or stops.</summary>
    public event Action? StateChanged;

    /// <summary>Decode an HCA blob and play it. Replaces any current preview.</summary>
    public async Task PlayHcaAsync(byte[] hcaBlob)
    {
        int gen = ++_generation;
        Stop();

        string temp = Path.Combine(Path.GetTempPath(), $"acb_preview_{Guid.NewGuid():N}.wav");
        double duration = await Task.Run(() =>
        {
            var wav = HcaCodec.DecodeToWav(hcaBlob);
            File.WriteAllBytes(temp, wav);
            var fmt = WavUtil.ReadFormat(wav);
            return fmt.SampleRate > 0 ? (double)fmt.SampleFrames / fmt.SampleRate : 0;
        });

        if (gen != _generation)
        {
            try { File.Delete(temp); } catch { }
            return;
        }

        StartPlayback(temp, duration, deleteWhenDone: true);
    }

    /// <summary>Play a WAV (or other winmm-supported) file from disk.</summary>
    public void PlayFile(string path)
    {
        _generation++;
        Stop();

        double duration = 0;
        try
        {
            var fmt = WavUtil.ReadFormat(File.ReadAllBytes(path));
            duration = fmt.SampleRate > 0 ? (double)fmt.SampleFrames / fmt.SampleRate : 0;
        }
        catch
        {
            // Non-WAV input — let winmm try anyway; auto-stop falls back to 1s.
        }

        StartPlayback(path, duration, deleteWhenDone: false);
    }

    private void StartPlayback(string path, double durationSeconds, bool deleteWhenDone)
    {
        _tempFile = deleteWhenDone ? path : null;
        PlaySound(path, IntPtr.Zero, SND_FILENAME | SND_ASYNC | SND_NODEFAULT);
        IsPlaying = true;
        StateChanged?.Invoke();

        _timer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(durationSeconds * 1000 + 1000),
        };
        _timer.Tick += (_, _) => Stop();
        _timer.Start();
    }

    public void Stop()
    {
        _timer?.Stop();
        _timer = null;

        if (IsPlaying)
        {
            PlaySound(null, IntPtr.Zero, SND_PURGE);
            IsPlaying = false;
            StateChanged?.Invoke();
        }

        var temp = _tempFile;
        _tempFile = null;
        if (temp is not null)
        {
            // Give winmm a moment to release the file before deleting it.
            _ = Task.Delay(500).ContinueWith(_ =>
            {
                try { File.Delete(temp); } catch { /* best effort */ }
            });
        }
    }
}
