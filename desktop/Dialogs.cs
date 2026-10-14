namespace Toir.Desktop;

public static class Ui
{
    public static void Fit(Window window)
    {
        window.MaxHeight = SystemParameters.WorkArea.Height;
        window.MaxWidth = SystemParameters.WorkArea.Width;
        window.Height = Math.Min(window.Height, window.MaxHeight);
        window.Width = Math.Min(window.Width, window.MaxWidth);
    }
    public static TextBlock Text(string text, double size = 14, bool bold = false) => new() { Text = text, FontSize = size, FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 8) };
    public static Button Button(string text, RoutedEventHandler click, bool secondary = false)
    {
        var b = new Button { Content = text };
        if (secondary) { b.Background = new SolidColorBrush(Color.FromRgb(221, 233, 237)); b.Foreground = new SolidColorBrush(Color.FromRgb(36, 78, 96)); }
        b.Click += click; return b;
    }
    public static Border Card(UIElement child) => new() { Background = Brushes.White, CornerRadius = new CornerRadius(9), Padding = new Thickness(20), Child = child, Margin = new Thickness(0, 0, 12, 12) };
}

public sealed class LoginDialog : Window
{
    public LoginDialog(ApiClient api, bool unlock)
    {
        Style = (Style)Application.Current.FindResource(typeof(Window));
        Title = unlock ? "Разблокировка сеанса" : "Вход в ТОиР-Проф";
        Width = 480; Height = unlock ? 510 : 690; ResizeMode = ResizeMode.NoResize; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Ui.Fit(this);
        var panel = new StackPanel { Margin = new Thickness(34) }; Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        panel.Children.Add(Ui.Text(unlock ? "Сеанс заблокирован" : "ТОиР-Проф", 27, true));
        panel.Children.Add(Ui.Text(unlock ? "15 секунд бездействия. Введите пароль — открытые формы и изменения сохранятся." : "Оборудование, обслуживание и материалы в одном рабочем месте."));
        var settings = LocalStore.Read("settings.json");
        var address = new TextBox { Text = unlock ? api.BaseUrl : settings.Text("url", "http://127.0.0.1:8000"), Margin = new Thickness(0, 0, 0, 14) };
        if (!unlock) { panel.Children.Add(Ui.Text("Адрес API (без /api)")); panel.Children.Add(address); }
        panel.Children.Add(Ui.Text("Электронная почта"));
        var email = new TextBox { Text = unlock ? api.Email : settings.Text("email", "admin@toir.local"), IsReadOnly = unlock, Margin = new Thickness(0, 0, 0, 14) }; panel.Children.Add(email);
        panel.Children.Add(Ui.Text("Пароль")); var password = new PasswordBox { Margin = new Thickness(0, 0, 0, 16) }; panel.Children.Add(password);
        var plain = new TextBox { Visibility = Visibility.Collapsed, Margin = new Thickness(0, 0, 0, 16) }; panel.Children.Add(plain);
        var show = new CheckBox { Content = "Показать пароль", Margin = new Thickness(0, 0, 0, 14) }; panel.Children.Add(show);
        show.Checked += (_, _) => { plain.Text = password.Password; plain.Visibility = Visibility.Visible; password.Visibility = Visibility.Collapsed; };
        show.Unchecked += (_, _) => { password.Password = plain.Text; plain.Visibility = Visibility.Collapsed; password.Visibility = Visibility.Visible; };
        var remember = new CheckBox { Content = "Запомнить меня на этом Windows-профиле", IsChecked = api.Remember, Margin = new Thickness(0, 0, 0, 14) };
        if (!unlock) panel.Children.Add(remember);
        var progress = new ProgressBar { IsIndeterminate = true, Height = 4, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 0, 0, 12) }; panel.Children.Add(progress);
        var error = Ui.Text(""); error.Foreground = Brushes.Firebrick; panel.Children.Add(error);
        var submit = new Button { Content = unlock ? "Продолжить работу" : "Войти", IsDefault = true }; panel.Children.Add(submit);
        submit.Click += async (_, _) =>
        {
            submit.IsEnabled = false; address.IsEnabled = email.IsEnabled = password.IsEnabled = plain.IsEnabled = show.IsEnabled = remember.IsEnabled = false; progress.Visibility = Visibility.Visible; error.Text = "Проверяем данные…";
            try
            {
                if (!System.Net.Mail.MailAddress.TryCreate(email.Text.Trim(), out var parsed) || parsed.Address != email.Text.Trim()) throw new ArgumentException("Введите корректный email.");
                await api.Login(address.Text, email.Text.Trim(), show.IsChecked == true ? plain.Text : password.Password, unlock ? api.User.Int("Id") : null);
                if (!unlock) api.RememberSession(remember.IsChecked == true); DialogResult = true;
            }
            catch (Exception e) { error.Text = e.Message; password.SelectAll(); password.Focus(); }
            finally { submit.IsEnabled = true; address.IsEnabled = email.IsEnabled = password.IsEnabled = plain.IsEnabled = show.IsEnabled = remember.IsEnabled = true; progress.Visibility = Visibility.Collapsed; }
        };
        if (unlock) Closing += (_, e) => { if (DialogResult != true) e.Cancel = true; };
        Loaded += (_, _) => password.Focus();
    }
}

public sealed class EditorDialog : Window
{
    private readonly Dictionary<string, (JsonNode Meta, FrameworkElement Control)> controls = [];
    private readonly JsonNode? original;
    public JsonObject? Result { get; private set; }
    public Func<JsonObject, Task<bool>>? SaveAsync { get; set; }
    public EditorDialog(string title, IEnumerable<JsonNode> fields, JsonNode lookups, JsonNode? record = null)
    {
        Style = (Style)Application.Current.FindResource(typeof(Window));
        Title = title; Width = 570; Height = 650; MinHeight = 440; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Ui.Fit(this);
        original = record;
        var root = new DockPanel { Margin = new Thickness(25) }; Content = root;
        root.Children.Add(new Border { Child = Ui.Text(title, 23, true), Padding = new Thickness(0, 0, 0, 12) }); DockPanel.SetDock(root.Children[^1], Dock.Top);
        var bottom = new StackPanel { Margin = new Thickness(0, 16, 0, 0) }; DockPanel.SetDock(bottom, Dock.Bottom); root.Children.Add(bottom);
        var error = Ui.Text(""); error.Foreground = Brushes.Firebrick; bottom.Children.Add(error);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal };
        var save = new Button { Content = "Сохранить", IsDefault = true };
        save.Click += async (_, _) =>
        {
            save.IsEnabled = false;
            try { Result = Read(); if (SaveAsync is null || await SaveAsync(Result)) DialogResult = true; }
            catch (Exception e) { error.Text = e.Message; }
            finally { save.IsEnabled = true; }
        };
        buttons.Children.Add(save); buttons.Children.Add(Ui.Button("Отмена", (_, _) => Close(), true)); bottom.Children.Add(buttons);
        var body = new StackPanel(); root.Children.Add(new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        foreach (var field in fields.Where(f => !f.Bool("readOnly")))
        {
            var name = field.Text("name"); if (name is "Id" or "Version" or "PasswordHash") continue;
            body.Children.Add(Ui.Text(field.Text("label", name) + (field.Bool("required") ? " *" : "")));
            var type = field.Text("type", "text"); var value = record?[name]?.ToString() ?? ""; FrameworkElement control;
            var lookup = field.Text("lookup");
            if (name is "MasterId" or "master_id" && lookups["masters"] is JsonArray) lookup = "masters";
            if (lookup.Length > 0 || field["options"] is JsonArray)
            {
                var combo = new ComboBox { DisplayMemberPath = "Label", SelectedValuePath = "Value" };
                var options = new List<Choice>();
                if (!field.Bool("required")) options.Add(new("", "— не выбрано —"));
                options.AddRange(lookup.Length > 0 ? lookups[lookup].Rows().Select(v => new Choice(v.Text("id"), v.Text("label"))) : field["options"].Rows().Select(v => v is JsonObject ? new Choice(v.Text("value"), v.Text("label")) : new Choice(v.ToString(), v.ToString())));
                combo.ItemsSource = options; combo.SelectedValue = value; control = combo;
            }
            else if (type == "bool") control = new CheckBox { IsChecked = value.Equals("true", StringComparison.OrdinalIgnoreCase) || (record is null && name == "IsActive"), Content = "Да", Margin = new Thickness(0, 5, 0, 5) };
            else if (type == "date") control = new DatePicker { SelectedDate = DateTime.TryParse(value, out var date) ? date : null, MinHeight = 36 };
            else if (type == "password") control = new PasswordBox();
            else control = new TextBox { Text = value, AcceptsReturn = type == "textarea", TextWrapping = type == "textarea" ? TextWrapping.Wrap : TextWrapping.NoWrap, MinHeight = type == "textarea" ? 75 : 36 };
            control.Margin = new Thickness(0, 0, 0, 15); controls[name] = (field, control); body.Children.Add(control);
            if (type == "datetime") body.Children.Add(Ui.Text("Дата и время UTC: 2027-02-10T09:00:00", 11));
            if (type == "password" && record is not null) body.Children.Add(Ui.Text("Оставьте пустым, чтобы сохранить текущий пароль.", 11));
        }
    }
    private JsonObject Read()
    {
        var result = new JsonObject();
        foreach (var (name, (meta, control)) in controls)
        {
            var value = control switch { TextBox t => t.Text.Trim(), PasswordBox p => p.Password, ComboBox c => c.SelectedValue?.ToString() ?? "", DatePicker d => d.SelectedDate?.ToString("yyyy-MM-dd") ?? "", CheckBox b => b.IsChecked == true ? "true" : "false", _ => "" };
            var type = meta.Text("type");
            if (type == "password" && value.Length == 0 && original is not null) continue;
            if (value.Length == 0 && meta.Bool("required")) throw new InvalidOperationException($"Заполните «{meta.Text("label", name)}».");
            if (value.Length == 0) { if (original is not null) result[name] = null; continue; }
            if (type == "bool") result[name] = value == "true";
            else if (meta.Text("lookup").Length > 0) result[name] = int.Parse(value, CultureInfo.InvariantCulture);
            else if (type == "number")
            {
                if (!decimal.TryParse(value.Replace(',', '.'), NumberStyles.Number, CultureInfo.InvariantCulture, out var n)) throw new InvalidOperationException($"«{meta.Text("label", name)}»: введите число.");
                result[name] = n;
            }
            else if (type == "datetime")
            {
                if (!DateTime.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.AllowWhiteSpaces, out var date)) throw new InvalidOperationException($"«{meta.Text("label", name)}»: неверная дата/время.");
                result[name] = date.ToString("yyyy-MM-ddTHH:mm:ss");
            }
            else result[name] = value;
        }
        if (original?["Version"] is not null) result["_version"] = original["Version"]!.DeepClone();
        return result;
    }
    public record Choice(string Value, string Label);
}
