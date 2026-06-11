using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using AcbStudio.ViewModels;

namespace AcbStudio;

public partial class MainWindow : Window
{
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    private const int DwmwaUseImmersiveDarkMode = 20;

    private readonly MainViewModel _vm = new();
    private UserControl[] _views = [];
    private RadioButton[] _navs = [];
    private int _currentView;
    private bool _ready;

    public MainWindow()
    {
        InitializeComponent();
        DataContext = _vm;

        _views = [HomeTabView, BrowseTabView, ExtractTabView, InjectTabView, ConvertTabView];
        _navs = [NavHome, NavBrowse, NavExtract, NavInject, NavConvert];

        _vm.Home.NavigateRequested += NavigateTo;
        _vm.Home.OpenBankRequested += OpenAcb;

        SourceInitialized += (_, _) => EnableDarkTitleBar();
        ContentRendered += (_, _) => OnFirstRender();
    }

    private void EnableDarkTitleBar()
    {
        int on = 1;
        var hwnd = new WindowInteropHelper(this).Handle;
        _ = DwmSetWindowAttribute(hwnd, DwmwaUseImmersiveDarkMode, ref on, sizeof(int));
    }

    private void OnFirstRender()
    {
        if (_ready)
            return;
        _ready = true;
        BeginAnimation(OpacityProperty, new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(320)));
    }

    private void OnWindowClosing(object sender, CancelEventArgs e) => _vm.OnAppClosing();

    // ── Navigation ───────────────────────────────────────────────────────────

    private void NavigateTo(string key)
    {
        var target = key switch
        {
            "browse" => NavBrowse,
            "extract" => NavExtract,
            "inject" => NavInject,
            "convert" => NavConvert,
            _ => NavHome,
        };
        target.IsChecked = true;
    }

    private void OpenAcb(string path)
    {
        if (!File.Exists(path))
        {
            _vm.Status = $"File not found: {path}";
            return;
        }
        _vm.Browse.AcbPath = path;
        _vm.Browse.LoadProject(path);
        if (string.IsNullOrWhiteSpace(_vm.Browse.OutDir))
        {
            _vm.Browse.OutDir = Path.Combine(Path.GetDirectoryName(path)!,
                Path.GetFileNameWithoutExtension(path) + "_wav");
        }
        NavigateTo("browse");
    }

    private void NavChecked(object sender, RoutedEventArgs e)
    {
        if (_views.Length == 0)
            return;

        int index = Array.IndexOf(_navs, (RadioButton)sender);
        if (index < 0 || index == _currentView && _ready)
            return;

        _vm.OnTabSwitched();
        _currentView = index;

        for (int i = 0; i < _views.Length; i++)
            _views[i].Visibility = i == index ? Visibility.Visible : Visibility.Collapsed;

        if (!_ready)
            return;

        // Fade + slide the incoming view.
        var view = _views[index];
        view.Opacity = 0;
        var transform = (TranslateTransform)view.RenderTransform;
        transform.BeginAnimation(TranslateTransform.YProperty, null);
        transform.Y = 14;

        view.BeginAnimation(OpacityProperty,
            new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(200)));
        transform.BeginAnimation(TranslateTransform.YProperty,
            new DoubleAnimation(14, 0, TimeSpan.FromMilliseconds(300))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut },
            });
    }

    // ── Drop-anywhere routing ────────────────────────────────────────────────

    private void OnWindowDragOver(object sender, DragEventArgs e)
    {
        e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void OnWindowDrop(object sender, DragEventArgs e)
    {
        if (e.Data.GetData(DataFormats.FileDrop) is not string[] paths || paths.Length == 0)
            return;

        string? acb = paths.FirstOrDefault(p => p.EndsWith(".acb", StringComparison.OrdinalIgnoreCase));
        string? awb = paths.FirstOrDefault(p => p.EndsWith(".awb", StringComparison.OrdinalIgnoreCase));
        var audio = paths.Where(p => p.EndsWith(".wav", StringComparison.OrdinalIgnoreCase)
                                  || p.EndsWith(".hca", StringComparison.OrdinalIgnoreCase)).ToList();

        if (acb is not null)
        {
            OpenAcb(acb);
        }
        else if (awb is not null)
        {
            // Quick Extract is an advanced feature — reveal it for this.
            _vm.Options.IsAdvanced = true;
            _vm.Extract.AwbPath = awb;
            if (string.IsNullOrWhiteSpace(_vm.Extract.OutDir))
            {
                _vm.Extract.OutDir = Path.Combine(Path.GetDirectoryName(awb)!,
                    Path.GetFileNameWithoutExtension(awb) + "_wav");
            }
            _vm.Extract.LoadAwb(awb);
            NavigateTo("extract");
        }
        else if (audio.Count > 0)
        {
            _vm.Convert.AddPaths(audio);
            NavigateTo("convert");
        }
    }

    // ── About overlay ────────────────────────────────────────────────────────

    private void AboutClick(object sender, RoutedEventArgs e) => ShowAbout();

    private void AboutScrimClick(object sender, MouseButtonEventArgs e) => HideAbout();

    private void AboutCloseClick(object sender, RoutedEventArgs e) => HideAbout();

    private void ShowAbout()
    {
        AboutOverlay.Visibility = Visibility.Visible;
        AboutOverlay.BeginAnimation(OpacityProperty,
            new DoubleAnimation(1, TimeSpan.FromMilliseconds(180)));

        var transform = (TranslateTransform)AboutCard.RenderTransform;
        transform.BeginAnimation(TranslateTransform.YProperty,
            new DoubleAnimation(26, 0, TimeSpan.FromMilliseconds(280))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut },
            });
    }

    private void HideAbout()
    {
        var fade = new DoubleAnimation(0, TimeSpan.FromMilliseconds(160));
        fade.Completed += (_, _) => AboutOverlay.Visibility = Visibility.Collapsed;
        AboutOverlay.BeginAnimation(OpacityProperty, fade);
    }
}
