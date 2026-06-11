using System.Collections.Specialized;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using AcbStudio.ViewModels;

namespace AcbStudio.Views;

public partial class BrowseView : UserControl
{
    private BrowseViewModel? _vm;

    public BrowseView()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged -= OnLogChanged;

        _vm = DataContext as BrowseViewModel;
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged += OnLogChanged;
    }

    private void OnLogChanged(object? sender, NotifyCollectionChangedEventArgs e)
        => LogScroll.ScrollToEnd();

    private void WaveformDoubleClick(object sender, MouseButtonEventArgs e)
        => _vm?.PreviewCommand.Execute(null);
}
