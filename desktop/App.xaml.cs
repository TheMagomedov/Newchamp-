namespace Toir.Desktop;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += (_, args) =>
        {
            LocalStore.Log("UNHANDLED", args.Exception.ToString());
            MessageBox.Show("Не удалось выполнить действие. Подробности записаны в локальный журнал.", "ТОиР • ошибка", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };
        base.OnStartup(e);
    }
}
