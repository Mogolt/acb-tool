using System.Collections.Specialized;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using AcbStudio.ViewModels;

namespace AcbStudio.Views;

public partial class ExtractView : UserControl
{
    private ExtractViewModel? _vm;

    public ExtractView()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged -= OnLogChanged;

        _vm = DataContext as ExtractViewModel;
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged += OnLogChanged;
    }

    private void OnLogChanged(object? sender, NotifyCollectionChangedEventArgs e)
        => LogScroll.ScrollToEnd();

    private void WaveformDoubleClick(object sender, MouseButtonEventArgs e)
        => _vm?.PreviewCommand.Execute(null);

    private void OnDragOver(object sender, DragEventArgs e)
    {
        e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void OnDrop(object sender, DragEventArgs e)
    {
        if (_vm is null || e.Data.GetData(DataFormats.FileDrop) is not string[] paths)
            return;
        var awb = paths.FirstOrDefault(p => p.EndsWith(".awb", StringComparison.OrdinalIgnoreCase));
        if (awb is null)
            return;
        _vm.AwbPath = awb;
        if (string.IsNullOrWhiteSpace(_vm.OutDir))
            _vm.OutDir = Path.Combine(Path.GetDirectoryName(awb)!, Path.GetFileNameWithoutExtension(awb) + "_wav");
        _vm.LoadAwb(awb);
    }
}
