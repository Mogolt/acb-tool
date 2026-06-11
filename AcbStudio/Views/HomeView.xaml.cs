using System.Windows;
using System.Windows.Controls;
using AcbStudio.ViewModels;

namespace AcbStudio.Views;

public partial class HomeView : UserControl
{
    public HomeView()
    {
        InitializeComponent();
    }

    private void RecentClick(object sender, RoutedEventArgs e)
    {
        if (DataContext is HomeViewModel vm && sender is Button { DataContext: string path })
            vm.OpenRecent(path);
    }
}
