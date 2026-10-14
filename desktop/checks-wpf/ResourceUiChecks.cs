using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Toir.Desktop;

internal static class ResourceUiChecks
{
    public static void Run(MainWindow window)
    {
        var root = (Grid)window.FindName("ContentHost");
        var buttons = Walk(root).OfType<Button>().ToList();
        var grid = Walk(root).OfType<DataGrid>().Single();
        Check(buttons.Any(b => Equals(b.Content, "Сбросить")), "reset filters visible");
        var actions = buttons.Where(b => b.Content is string s && new[] { "Изменить", "Удалить", "История", "Подробнее" }.Contains(s)).ToList();
        Check(actions.Count == 4, "shared row actions present for admin");
        Check(actions.All(b => !b.IsEnabled), "no selection disables row actions");
        grid.SelectedIndex = 0;
        Check(actions.All(b => b.IsEnabled), "selection enables row actions");
        grid.UnselectAll();
        Check(actions.All(b => !b.IsEnabled), "clearing selection disables row actions");
        var button = new Button { BorderThickness = new Thickness(2), BorderBrush = Brushes.Teal };
        button.Style = (Style)Application.Current.FindResource(typeof(Button));
        button.ApplyTemplate();
        var frame = (Border)button.Template.FindName("Frame", button);
        Check(frame.BorderThickness == new Thickness(2), "calendar selection border rendered");
        Console.WriteLine("6 resource UI checks passed; no writes or shown windows.");
    }
    private static IEnumerable<DependencyObject> Walk(DependencyObject parent)
    {
        yield return parent;
        foreach (var child in LogicalTreeHelper.GetChildren(parent).OfType<DependencyObject>())
            foreach (var nested in Walk(child)) yield return nested;
    }
    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException("FAIL " + message);
        Console.WriteLine("PASS " + message);
    }
}
