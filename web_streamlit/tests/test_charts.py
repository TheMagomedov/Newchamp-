"""Схемы Vega selection и переход по выбранной строке, без браузера и API."""
from types import SimpleNamespace

import pytest

import charts


@pytest.mark.parametrize('point,expected', [
    ([{'_row': 0}], 0),
    ([{'_row': 2}], 2),
    ([{'_row': 1}, {'_row': 2}], 1),
    ({'_row': [0]}, 0),
    ({'_row': [1, 2], 'vlPoint': {'or': [{'_row': 1}]}}, 1),
    ({'_row': 2}, 2),
    ({'_row': [2.0]}, 2),
    ([], None), ({}, None), (None, None), ('0', None),
    ({'_row': []}, None), ({'_row': None}, None), ({'other': [0]}, None),
    ([{}], None), ([None, 'invalid'], None), ({'_row': ['0']}, None),
    ({'_row': [True, False]}, None), ({'_row': [0.5]}, None),
    ({'_row': [float('nan'), float('inf')]}, None),
    ({'_row': [-1]}, None), ([{'_row': 3}], None),
    ({'_row': [9999999999999999999999]}, None),
    ({'_row': [-1, 2]}, 2),
])
def test_selection_shapes_and_invalid_indices(point, expected):
    assert charts.selection_index(point, 3) == expected


@pytest.mark.parametrize('point', [[{'_row': 0}], {'_row': [0]}])
def test_selection_never_opens_empty_dataset(point):
    assert charts.selection_index(point, 0) is None


@pytest.mark.parametrize('point,expected', [
    ([{'_row': 1}], 'Вторая'), ({'_row': [1]}, 'Вторая'),
    ({'_row': []}, None), ({'_row': [-1]}, None), ({'_row': [99]}, None),
])
def test_chart_passes_correct_original_row_to_target(monkeypatch, point, expected):
    targets, buttons = [], []
    fake = SimpleNamespace(
        markdown=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        vega_lite_chart=lambda *args, **kwargs: {'selection': {'point': point}},
        button=lambda label, **kwargs: buttons.append(label) or True,
        download_button=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(charts, 'st', fake)
    rows = [{'label': 'Без данных', 'value': None}, {'label': 'Вторая', 'value': 4}]
    charts.chart('Тест', rows, 'test', target=targets.append)
    assert [row['label'] for row in targets] == ([] if expected is None else [expected])
    assert len(buttons) == (0 if expected is None else 1)
