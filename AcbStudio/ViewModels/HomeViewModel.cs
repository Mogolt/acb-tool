using AcbStudio.Services;

namespace AcbStudio.ViewModels;

/// <summary>Home screen: task cards, recent banks, drop-anywhere hint.</summary>
public sealed class HomeViewModel(UiOptions options) : ObservableObject
{
    public UiOptions Options { get; } = options;

    /// <summary>Raised with a section key: "browse" | "extract" | "inject" | "convert".</summary>
    public event Action<string>? NavigateRequested;

    /// <summary>Raised with an .acb path the user picked from the recent list.</summary>
    public event Action<string>? OpenBankRequested;

    public RelayCommand GoBrowseCommand => new(() => NavigateRequested?.Invoke("browse"));
    public RelayCommand GoInjectCommand => new(() => NavigateRequested?.Invoke("inject"));
    public RelayCommand GoConvertCommand => new(() => NavigateRequested?.Invoke("convert"));
    public RelayCommand GoExtractCommand => new(() => NavigateRequested?.Invoke("extract"));

    public void OpenRecent(string path) => OpenBankRequested?.Invoke(path);
}
