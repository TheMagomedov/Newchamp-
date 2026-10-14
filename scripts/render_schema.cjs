// Exact FK diagrams from a dedicated training database; SQL is read-only metadata SELECTs.
// node scripts/render_schema.cjs ChampTraining_20261013
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const runtime = process.env.CODEX_NODE_MODULES || 'C:/Users/magom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const { instance } = require(path.join(runtime, '@viz-js/viz'));
const sharp = require(path.join(runtime, 'sharp'));
const database = process.argv[2];
if (!/^ChampTraining_[A-Za-z0-9_]+$/.test(database || '')) throw Error('Use a dedicated ChampTraining_ database.');
const output = path.resolve(__dirname, '../docs/diagrams');
fs.mkdirSync(output, { recursive: true });
function query(sql) {
  const result = execFileSync('sqlcmd', ['-S','localhost','-E','-C','-b','-d',database,'-y','0','-w','65535','-Q',`SET NOCOUNT ON; ${sql}`], { encoding:'utf8' });
  // ODBC sqlcmd rejects -h with -y 0. Remove its header and join FOR JSON output chunks.
  const start = result.indexOf('['), end = result.lastIndexOf(']');
  if (start < 0 || end < start) throw Error('sqlcmd did not return a JSON array.');
  return JSON.parse(result.slice(start,end+1).replace(/[\r\n]/g,''));
}
const tables = query(`SELECT t.name, (SELECT c.name, TYPE_NAME(c.user_type_id) AS type, c.is_nullable AS nullable,
  CAST(CASE WHEN EXISTS(SELECT 1 FROM sys.index_columns ic JOIN sys.indexes ix ON ix.object_id=ic.object_id AND ix.index_id=ic.index_id WHERE ic.object_id=c.object_id AND ic.column_id=c.column_id AND ix.is_primary_key=1) THEN 1 ELSE 0 END AS bit) AS pk,
  CAST(CASE WHEN EXISTS(SELECT 1 FROM sys.foreign_key_columns f WHERE f.parent_object_id=c.object_id AND f.parent_column_id=c.column_id) THEN 1 ELSE 0 END AS bit) AS fk
  FROM sys.columns c WHERE c.object_id=t.object_id ORDER BY c.column_id FOR JSON PATH) AS columns
  FROM sys.tables t WHERE t.is_ms_shipped=0 ORDER BY t.name FOR JSON PATH`);
const edges = query(`SELECT OBJECT_NAME(f.referenced_object_id) AS parent, OBJECT_NAME(f.parent_object_id) AS child,
  COL_NAME(f.parent_object_id,f.parent_column_id) AS columnName, c.is_nullable AS nullable,
  fk.delete_referential_action_desc AS deleteAction,
  CAST(CASE WHEN EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.indexes ix ON ix.object_id=ic.object_id AND ix.index_id=ic.index_id
    WHERE ic.object_id=c.object_id AND ic.column_id=c.column_id AND ix.is_unique=1 AND ic.key_ordinal=1
      AND (SELECT COUNT(*) FROM sys.index_columns x WHERE x.object_id=ic.object_id AND x.index_id=ic.index_id AND x.key_ordinal>0)=1) THEN 1 ELSE 0 END AS bit) AS uniqueChild
  FROM sys.foreign_key_columns f JOIN sys.columns c ON c.object_id=f.parent_object_id AND c.column_id=f.parent_column_id
  JOIN sys.foreign_keys fk ON fk.object_id=f.constraint_object_id ORDER BY parent,child,columnName FOR JSON PATH`);
const labels = { Roles:'Роли', Users:'Пользователи', Workshops:'Цеха', Teams:'Бригады', Equipment:'Оборудование', EquipmentTypes:'Типы оборудования', MaintenanceTypes:'Виды ТО', MaintenanceNorms:'Нормативы ТО', MaintenanceSchedule:'График ТО', WorkOrders:'Заявки', Materials:'Материалы', Suppliers:'Поставщики', WorkOrderMaterials:'Списание материалов', AuditLog:'Аудит', EquipmentStatusHistory:'История оборудования', WorkOrderStatusHistory:'История заявок', RefreshTokens:'Сессии / refresh-токены', ClientRequests:'Защита от повторных запросов' };
const coreNames = ['Equipment','MaintenanceTypes','MaintenanceSchedule','WorkOrders','Teams','Materials','WorkOrderMaterials'];
const html = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const str = s => JSON.stringify(s);
async function draw(viz, basename, selected, title) {
  const names = new Set(selected.map(t => t.name));
  const relations = edges.filter(e => names.has(e.parent) && names.has(e.child));
  const lines = ['digraph ER {',
    'graph [rankdir=LR, bgcolor="#f5f8fc", pad="0.45", nodesep="0.48", ranksep="1.15", splines=polyline, fontname="Arial", fontsize=24, labelloc=t, label='+str(title+'\nКлючи и основные поля · PK — первичный ключ · FK — внешний ключ · ? — NULL')+' ];',
    'node [shape=plain, fontname="Arial"];',
    'edge [fontname="Arial", fontsize=10, color="#758499", fontcolor="#405166", arrowsize=0.8];'];
  const mermaid = ['%% Generated from SQL Server sys.* metadata. Fields are a key-field subset; metadata JSON includes all columns.', 'erDiagram', '    direction LR'];
  for (const t of selected) {
    const chosen = t.columns.filter(c => c.pk || c.fk || ['Name','Status','Number','Quantity','UnitPrice','Stock','Code','PlannedAt','PlannedStart','PlannedEnd','IntervalDays'].includes(c.name));
    const shown = chosen.length ? chosen : t.columns.slice(0,5);
    const color = t.name === 'WorkOrders' ? '#2563eb' : t.name === 'WorkOrderMaterials' ? '#0f766e' : '#243b53';
    const rows = shown.map(c => `<TR><TD ALIGN="LEFT"><FONT COLOR="#546579">${c.pk?'PK ':''}${c.fk?'FK ':''}${!c.pk&&!c.fk?' ':''}</FONT></TD><TD ALIGN="LEFT">${html(c.name)}${c.nullable?' ?':''}</TD><TD ALIGN="LEFT"><FONT COLOR="#65758b">${html(c.type)}</FONT></TD></TR>`).join('');
    lines.push(`${str(t.name)} [label=<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="7" BGCOLOR="white"><TR><TD COLSPAN="3" BGCOLOR="${color}"><FONT COLOR="white"><B>${html(t.name)}</B><BR/>${html(labels[t.name]||t.name)}</FONT></TD></TR>${rows}</TABLE>>];`);
    mermaid.push(`    ${t.name} {`);
    for (const c of shown) mermaid.push(`        ${c.type} ${c.name}${c.pk&&c.fk?' PK, FK':c.pk?' PK':c.fk?' FK':''}`);
    mermaid.push('    }');
  }
  for (const e of relations) {
    const parentCount = e.nullable ? '0..1' : '1';
    const childCount = e.uniqueChild ? '0..1' : '0..N';
    const isIdentifying = selected.find(t => t.name === e.child).columns.some(c => c.name === e.columnName && c.pk);
    const label = e.columnName + (e.deleteAction === 'NO_ACTION' ? '' : '\nDELETE '+e.deleteAction.replaceAll('_',' '));
    lines.push(`${str(e.parent)} -> ${str(e.child)} [label=${str(label)}, taillabel=${str(parentCount)}, headlabel=${str(childCount)}, dir=both, arrowtail=${e.nullable?'odottee':'teetee'}, arrowhead=${e.uniqueChild?'teeodot':'crowodot'}, labeldistance=2.1];`);
    mermaid.push(`    ${e.parent} ${e.nullable?'|o':'||'}${isIdentifying?'--':'..'}${e.uniqueChild?'o|':'o{'} ${e.child} : "${e.columnName}${e.deleteAction==='NO_ACTION'?'':' / DELETE '+e.deleteAction}"`);
  }
  lines.push('}');
  const dot = lines.join('\n');
  fs.writeFileSync(path.join(output,basename+'.dot'),dot);
  const svg = viz.renderString(dot, { format:'svg', engine:'dot' });
  for (const [ext, content] of [['dot',dot], ['mmd',mermaid.join('\n')], ['svg',svg]]) fs.writeFileSync(path.join(output,basename+'.'+ext),content);
  await sharp(Buffer.from(svg)).resize({ width:basename==='schema_core'?2600:5200 }).png().toFile(path.join(output,basename+'.png'));
  return { file:basename, tables:selected.length, relationships:relations.length };
}
(async () => {
  const viz = await instance();
  fs.writeFileSync(path.join(output,'schema_metadata.json'),JSON.stringify({ database,tables,edges },null,2));
  console.log(await draw(viz,'schema_core',tables.filter(t => coreNames.includes(t.name)),'ТОиР-Проф · основные связи для заучивания'));
  console.log(await draw(viz,'schema_full',tables,'ТОиР-Проф · все внешние ключи учебной БД'));
})().catch(error => { console.error(error.message); process.exitCode = 1; });
