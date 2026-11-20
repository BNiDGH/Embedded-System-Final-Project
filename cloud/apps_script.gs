/**
 * WearWise cloud: Google Sheets ผ่าน Apps Script Web App
 *
 * วิธีใช้
 *  1. เปิดสเปรดชีต > Extensions > Apps Script แล้ววางโค้ดนี้ทับไฟล์เดิม
 *  2. Deploy > New deployment > type: Web app
 *     - Execute as: Me
 *     - Who has access: Anyone   (ถ้าเลือก "Anyone with Google account" จะเรียกจาก Python ไม่ได้)
 *  3. คัดลอก URL ที่ลงท้ายด้วย /exec ไปใส่ .env เป็น GOOGLE_SCRIPT_URL
 *  4. แก้โค้ดแล้วต้อง Deploy เวอร์ชันใหม่ (Manage deployments > Edit > New version)
 *
 * สัญญาที่ cloud/store.py ใช้
 *  POST {"table":"raw"|"events","row":{...}}  -> {"ok":true}
 *  GET  ?table=raw&limit=50                   -> {"ok":true,"rows":[{...}]}
 */

var COLS = {
  raw: ['ts', 'iso', 'node_id', 'seq', 'temp', 'hum', 'gas', 'lux',
        'dist_cm', 'person', 'fan', 'servo', 'estop', 'hop_ms', 'note'],
  events: ['ts', 'iso', 'node_id', 'kind', 'text', 'notify'],
};

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function sheetFor_(name) {
  if (!COLS[name]) throw new Error('ไม่รู้จักตาราง: ' + name);
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var cols = COLS[name];
  var sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  var header = sh.getRange(1, 1, 1, cols.length).getValues()[0].join('|');
  if (header !== cols.join('|')) {
    sh.getRange(1, 1, 1, cols.length).setValues([cols]);
    sh.setFrozenRows(1);
  }
  return { sheet: sh, cols: cols };
}

function doPost(e) {
  try {
    if (!e.postData || !e.postData.contents) throw new Error('ไม่มี body');
    var body = JSON.parse(e.postData.contents);
    var name = body.table || 'raw';
    var t = sheetFor_(name);
    var row = body.row || body;
    var values = t.cols.map(function (c) {
      return row[c] === undefined || row[c] === null ? '' : row[c];
    });
    t.sheet.appendRow(values);
    return json_({ ok: true, table: name });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function doGet(e) {
  try {
    var name = (e.parameter.table || 'raw');
    var limit = Number(e.parameter.limit || 50);
    var t = sheetFor_(name);
    var values = t.sheet.getDataRange().getValues();
    var rows = [];
    for (var i = 1; i < values.length; i++) {
      var obj = {};
      for (var j = 0; j < t.cols.length; j++) obj[t.cols[j]] = values[i][j];
      rows.push(obj);
    }
    return json_({ ok: true, rows: rows.slice(-limit) });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/**
 * ลบแถวที่ซ้ำทั้งแถว (ใช้เมื่อเคยส่งซ้ำ) — เลือกฟังก์ชันนี้แล้วกด Run ครั้งเดียว
 */
function removeDuplicateRows() {
  ['raw', 'events'].forEach(function (name) {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
    if (!sh || sh.getLastRow() < 3) return;
    sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).removeDuplicates();
  });
}
