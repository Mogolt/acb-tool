using System.Collections.Specialized;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using AcbStudio.ViewModels;

namespace AcbStudio.Views;

public partial class InjectView : UserControl
{
    private InjectViewModel? _vm;

    public InjectView()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged -= OnLogChanged;

        _vm = DataContext as InjectViewModel;
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged += OnLogChanged;
    }

    private void OnLogChanged(object? sender, NotifyCollectionChangedEventArgs e)
        => LogScroll.ScrollToEnd();

    private void WaveformDoubleClick(object sender, MouseButtonEventArgs e)
        => _vm?.PreviewSourceCommand.Execute(null);

    private void PendingDoubleClick(object sender, MouseButtonEventArgs e)
        => _vm?.PreviewReplacementCommand.Execute(null);
}
