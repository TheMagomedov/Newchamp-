namespace Toir.Desktop;

// Учебный модуль: построение таблиц, подписи столбцов и цветовые подсказки.
public partial class MainWindow
{
    private static readonly Dictionary<string, string> ExtraLabels = new()
    {
        ["equipmentid"] = "Оборудование ID", ["equipment_id"] = "Оборудование ID", ["IsOverdue"] = "Просрочено", ["workshop_id"] = "Цех ID", ["MaintenanceTypeName"] = "Вид ТО", ["PlannedAt"] = "Плановая дата ТО", ["InventoryNumber"] = "Инвентарный номер", ["CommissionedOn"] = "Ввод в эксплуатацию", ["StartedOn"] = "Ввод в работу", ["ActualStart"] = "Фактическое начало", ["ActualEnd"] = "Фактическое окончание", ["PlannedStart"] = "Плановое начало", ["PlannedEnd"] = "Плановое окончание", ["LastName"] = "Фамилия", ["FirstName"] = "Имя", ["Patronymic"] = "Отчество", ["Phone"] = "Телефон", ["Email"] = "Email", ["IsActive"] = "Активен", ["FailureReason"] = "Причина отказа", ["CompletionReport"] = "Отчёт о работах", ["Priority"] = "Приоритет", ["Type"] = "Тип", ["ChangedBy"] = "Изменил ID", ["Reason"] = "Причина", ["WorkOrderId"] = "Заявка ID", ["MaterialId"] = "Материал ID", ["WorkshopId"] = "Цех ID", ["TeamId"] = "Бригада ID", ["MasterId"] = "Мастер ID", ["DisplayNumber"] = "Номер"
    };
    private TableView MakeTable(IEnumerable<JsonNode> source, IEnumerable<JsonNode>? fields = null)
    {
        var rows = source.ToList(); var fieldList = fields?.ToList() ?? [];
        var definitions = fieldList.Concat(meta["resources"].Rows().SelectMany(r => r["fields"].Rows())).GroupBy(f => f.Text("name")).ToDictionary(g => g.Key, g => g.First());
        var names = fieldList.Select(f => f.Text("name")).Concat(rows.SelectMany(r => r is JsonObject o ? o.Select(kv => kv.Key) : [])).Distinct().Where(n => n is not ("PasswordHash" or "Password" or "Version" or "SequenceNumber" or "CreatedBy" or "UpdatedBy" or "IsDeleted" or "DisplayNumber") && n.Length > 0).ToList();
        names.RemoveAll(n => n.EndsWith("Name") && fieldList.Any(f => f.Text("name") == n[..^4] + "Id" && f.Text("lookup").Length > 0));
        var preferred = new[] { "Id", "Number", "InventoryNumber", "Name", "EquipmentName", "EquipmentId", "Status", "Priority", "WorkshopId", "TeamId", "PlannedAt", "Stock", "Unit", "UnitPrice" };
        names = names.OrderBy(n => Array.IndexOf(preferred, n) is var i && i >= 0 ? i : 100).ToList();
        var data = new DataTable(); var grid = new DataGrid(); var map = new Dictionary<DataRow, JsonNode>();
        foreach (var name in names)
        {
            data.Columns.Add(name, typeof(string));
            var field = definitions.GetValueOrDefault(name);
            var elementStyle = new Style(typeof(TextBlock)); elementStyle.Setters.Add(new Setter(MarginProperty, new Thickness(9, 0, 9, 0))); elementStyle.Setters.Add(new Setter(VerticalAlignmentProperty, VerticalAlignment.Center)); elementStyle.Setters.Add(new Setter(TextBlock.TextTrimmingProperty, TextTrimming.CharacterEllipsis)); elementStyle.Setters.Add(new Setter(ToolTipProperty, new Binding($"[{name}]")));
            grid.Columns.Add(new DataGridTextColumn { Header = field.Text("label", CommonLabel(name)), Binding = new Binding($"[{name}]"), SortMemberPath = name, ElementStyle = elementStyle, MinWidth = name == "Id" ? 55 : 100, Width = DataGridLength.Auto, MaxWidth = name is "Name" or "EquipmentName" or "EquipmentId" ? 260 : 300 });
        }
        foreach (var node in rows)
        {
            var row = data.NewRow(); foreach (var name in names)
            {
                var value = name == "Number" ? node.Text("DisplayNumber", node.Text(name)) : node.Text(name); var lookup = definitions.GetValueOrDefault(name).Text("lookup");
                if (lookup.Length > 0) value = lookups[lookup].Rows().FirstOrDefault(x => x.Text("id") == value).Text("label", value);
                else if (value == "True" || value == "true") value = "Да"; else if (value == "False" || value == "false") value = "Нет";
                row[name] = value;
            }
            data.Rows.Add(row); map[row] = node;
        }
        grid.ItemsSource = data.DefaultView; DecorateTable(grid, map); return new(grid, map);
    }
    private static string CommonLabel(string name) => ExtraLabels.TryGetValue(name, out var label) ? label : name switch { "Id" => "№", "Name" => "Название", "Status" => "Статус", "Description" => "Описание", "EquipmentName" => "Оборудование", "WorkshopName" => "Цех", "TeamName" => "Бригада", "MaterialName" => "Материал", "Quantity" => "Количество", "UnitPrice" => "Цена", "CreatedAt" => "Создано (UTC)", "ChangedAt" => "Изменено (UTC)", "OldStatus" => "Было", "NewStatus" => "Стало", "Comment" => "Комментарий", "Number" => "Номер", "PlannedDate" => "Плановая дата", "StockQuantity" => "Остаток", "MinStock" => "Минимум", _ => name };
    private record TableView(DataGrid Grid, Dictionary<DataRow, JsonNode> Rows)
    {
        public JsonNode? Selected() => Grid.SelectedItem is DataRowView view && Rows.TryGetValue(view.Row, out var node) ? node : null;
    }
    private void DecorateTable(DataGrid grid, Dictionary<DataRow, JsonNode> rows)
    {
        grid.FontSize = FontSize; grid.RowHeight = FontSize + 26;
        grid.LoadingRow += (_, e) =>
        {
            if (e.Row.Item is not DataRowView view || !rows.TryGetValue(view.Row, out var record)) return;
            e.Row.Background = RowColor(record);
            e.Row.ToolTip = record.Text("Priority") is "критический" or "высокий" ? "Высокий приоритет" : record.Text("Status");
        };
        var saved = Preferences["columns"]?[section] as JsonObject;
        foreach (var column in grid.Columns)
        {
            var key = column.SortMemberPath;
            if (saved?[key] is JsonObject settings)
            {
                if (double.TryParse(settings.Text("width"), NumberStyles.Any, CultureInfo.InvariantCulture, out var width)) column.Width = Math.Clamp(width, 55, 600);
                column.Visibility = settings.Bool("hidden") ? Visibility.Collapsed : Visibility.Visible;
                column.DisplayIndex = Math.Clamp(settings.Int("index", column.DisplayIndex), 0, grid.Columns.Count - 1);
            }
        }
        grid.PreviewMouseLeftButtonUp += (_, _) =>
        {
            var prefs = Preferences; var columns = prefs["columns"] as JsonObject ?? new JsonObject();
            prefs["columns"] = null; var current = new JsonObject();
            foreach (var column in grid.Columns) current[column.SortMemberPath] = new JsonObject { ["width"] = column.ActualWidth, ["hidden"] = column.Visibility == Visibility.Collapsed, ["index"] = column.DisplayIndex };
            columns[section] = current; prefs["columns"] = columns; SavePreferences(prefs);
        };
    }
    private static Brush RowColor(JsonNode record)
    {
        var closed = record.Text("Status") is "выполнено" or "отменено" or "выполнена" or "закрыта" or "отменена";
        if (!closed && DateTime.TryParse(record.Text("PlannedAt"), out var date))
        {
            if (date < DateTime.UtcNow) return new SolidColorBrush(Color.FromRgb(255, 224, 224));
            if (date <= DateTime.UtcNow.AddDays(3)) return new SolidColorBrush(Color.FromRgb(255, 243, 195));
        }
        if (record.Text("Priority") == "критический") return new SolidColorBrush(Color.FromRgb(255, 224, 224));
        if (record.Text("Priority") == "высокий") return new SolidColorBrush(Color.FromRgb(255, 243, 195));
        if (closed) return new SolidColorBrush(Color.FromRgb(229, 243, 237));
        if (record.Text("Status") is "в работе" or "выполняется") return new SolidColorBrush(Color.FromRgb(234, 247, 247));
        if (record.Text("Status") is "назначена" or "назначено") return new SolidColorBrush(Color.FromRgb(234, 240, 255));
        if (record.Text("Status") is "ожидает материалов" or "в простое" or "в ремонте") return new SolidColorBrush(Color.FromRgb(255, 246, 215));
        return Brushes.White;
    }
}
