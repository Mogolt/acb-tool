using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json;
using AcbStudio.ViewModels;

namespace AcbStudio.Services;

/// <summary>
/// App-wide UI preferences, persisted next to the executable:
/// the Advanced-mode switch and the recently opened banks list.
/// </summary>
public sealed class UiOptions : ObservableObject
{
    private const int MaxRecent = 6;
    private static string StorePath => Path.Combine(AppContext.BaseDirectory, "settings.json");

    private bool _isAdvanced;
    private bool _loaded;

    public UiOptions()
    {
        try
        {
            if (File.Exists(StorePath))
            {
                var doc = JsonSerializer.Deserialize<Persisted>(File.ReadAllText(StorePath));
                if (doc is not null)
                {
                    _isAdvanced = doc.Advanced;
                    foreach (var path in doc.Recent.Take(MaxRecent))
                        RecentBanks.Add(path);
                }
            }
        }
        catch
        {
            // Corrupt settings are not fatal — start fresh.
        }
        _loaded = true;
    }

    /// <summary>Advanced mode reveals Quick Extract, waveform internals and encoder options.</summary>
    public bool IsAdvanced
    {
        get => _isAdvanced;
        set
        {
            if (Set(ref _isAdvanced, value))
                Save();
        }
    }

    public ObservableCollection<string> RecentBanks { get; } = [];

    public void AddRecent(string path)
    {
        RunOnUi(() =>
        {
            var existing = RecentBanks.FirstOrDefault(p => string.Equals(p, path, StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
                RecentBanks.Remove(existing);
            RecentBanks.Insert(0, path);
            while (RecentBanks.Count > MaxRecent)
                RecentBanks.RemoveAt(RecentBanks.Count - 1);
            Save();
        });
    }

    private void Save()
    {
        if (!_loaded)
            return;
        try
        {
            File.WriteAllText(StorePath, JsonSerializer.Serialize(new Persisted
            {
                Advanced = _isAdvanced,
                Recent = RecentBanks.ToList(),
            }, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch
        {
            // Read-only install dir etc. — preferences just won't persist.
        }
    }

    private sealed class Persisted
    {
        public bool Advanced { get; set; }
        public List<string> Recent { get; set; } = [];
    }
}
