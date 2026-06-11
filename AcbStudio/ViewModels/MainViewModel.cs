using System.Windows;
using AcbStudio.Services;

namespace AcbStudio.ViewModels;

public sealed class MainViewModel : ObservableObject
{
    private readonly PreviewPlayer _preview = new();
    private string _status = "Ready.";

    public MainViewModel()
    {
        Action<string> setStatus = s =>
        {
            var dispatcher = Application.Current?.Dispatcher;
            if (dispatcher is null || dispatcher.CheckAccess())
                Status = s;
            else
                dispatcher.Invoke(() => Status = s);
        };

        Options = new UiOptions();
        Home = new HomeViewModel(Options);
        Browse = new BrowseViewModel(setStatus, _preview);
        Extract = new ExtractViewModel(setStatus, _preview);
        Inject = new InjectViewModel(setStatus, _preview);
        Convert = new ConvertViewModel(setStatus, _preview);

        // Successful bank loads land on the Home screen's recent list.
        Browse.ProjectOpened += Options.AddRecent;
        Inject.ProjectOpened += Options.AddRecent;
    }

    public UiOptions Options { get; }
    public HomeViewModel Home { get; }
    public BrowseViewModel Browse { get; }
    public ExtractViewModel Extract { get; }
    public InjectViewModel Inject { get; }
    public ConvertViewModel Convert { get; }

    public string Status { get => _status; set => Set(ref _status, value); }

    /// <summary>Stops any in-flight preview so audio doesn't keep playing across sections.</summary>
    public void OnTabSwitched() => _preview.Stop();

    public void OnAppClosing() => _preview.Stop();
}
