// Send only fields belonging to the action currently confirmed in the UI.
// Hidden/prepopulated values from an old card must not overwrite concurrent edits.
export function transitionPayload(form, current) {
  const body = { status: form.status };
  if (form.status === 'назначена' && form.team_id !== '' && form.team_id != null) {
    body.team_id = Number(form.team_id);
  }
  if (form.status === 'в работе' && !current?.ActualStart && form.actual_start) {
    body.actual_start = form.actual_start;
  }
  if (form.status === 'выполнена') {
    body.actual_end = form.actual_end;
    body.completion_report = form.completion_report;
  }
  return body;
}
