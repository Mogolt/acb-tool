using System.Collections.Specialized;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using AcbStudio.ViewModels;

namespace AcbStudio.Views;

public partial class ConvertView : UserControl
{
    private ConvertViewModel? _vm;

    public ConvertView()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged -= OnLogChanged;

        _vm = DataContext as ConvertViewModel;
        if (_vm is not null)
            ((INotifyCollectionChanged)_vm.Log).CollectionChanged += OnLogChanged;
    }

    private void OnLogChanged(object? sender, NotifyCollectionChangedEventArgs e)
        => LogScroll.ScrollToEnd();

    private void FileDoubleClick(object sender, MouseButtonEventArgs e)
        => _vm?.PreviewCommand.Execute(null);

    private void OnDragOver(object sender, DragEventArgs e)
    {
        e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void OnDrop(object sender, DragEventArgs e)
    {
        if (_vm is not null && e.Data.GetData(DataFormats.FileDrop) is string[] paths)
            _vm.AddPaths(paths);
    }
}
