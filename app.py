import json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
load_dotenv()
app=Flask(__name__); app.config['SECRET_KEY']=os.getenv('SECRET_KEY','local-demo-key')
DB=Path(os.getenv('DATABASE_PATH',Path(__file__).parent/'instance'/'app.db'))
FIELDS=["title", "people", "timezones", "start", "end", "notes"]; LABEL="Meeting window"; TITLE="Timefold"
def conn():
 DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, data TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL)"); return c
@app.get('/')
def home(): return render_template('index.html',title=TITLE,domain="Scheduling & collaboration",description="Compare working hours across cities, save candidate windows, and plan the agenda.",label=LABEL,fields=FIELDS)
@app.get('/api/items')
def list_items():
 q=request.args.get('q','').strip().lower(); c=conn(); rows=c.execute('SELECT * FROM items ORDER BY updated DESC').fetchall(); c.close(); out=[]
 for r in rows:
  x=json.loads(r['data']); x.update(id=r['id'],created=r['created'],updated=r['updated'])
  if not q or q in json.dumps(x).lower(): out.append(x)
 return jsonify(out)
@app.post('/api/items')
def create_item():
 data=request.get_json(silent=True) or {}; clean={k:str(data.get(k,'')).strip()[:12000] for k in FIELDS}
 if not any(clean.values()): return jsonify(error='Add at least one field before saving.'),400
 now=datetime.now(timezone.utc).isoformat(); c=conn(); cur=c.execute('INSERT INTO items(data,created,updated) VALUES(?,?,?)',(json.dumps(clean),now,now)); c.commit(); result={'id':cur.lastrowid,**clean,'created':now,'updated':now}; c.close(); return jsonify(result),201
@app.put('/api/items/<int:item_id>')
def update_item(item_id):
 data=request.get_json(silent=True) or {}; clean={k:str(data.get(k,'')).strip()[:12000] for k in FIELDS}; now=datetime.now(timezone.utc).isoformat(); c=conn(); cur=c.execute('UPDATE items SET data=?,updated=? WHERE id=?',(json.dumps(clean),now,item_id)); c.commit(); c.close()
 if not cur.rowcount:return jsonify(error='Not found'),404
 return jsonify(id=item_id,**clean,updated=now)
@app.delete('/api/items/<int:item_id>')
def delete_item(item_id):
 c=conn(); cur=c.execute('DELETE FROM items WHERE id=?',(item_id,)); c.commit(); c.close(); return ('',204) if cur.rowcount else (jsonify(error='Not found'),404)
@app.get('/api/summary')
def summary():
 c=conn(); count=c.execute('SELECT count(*) FROM items').fetchone()[0]; rows=c.execute('SELECT data FROM items ORDER BY updated DESC LIMIT 10').fetchall(); c.close(); return jsonify(count=count,recent=[json.loads(r[0]) for r in rows])
@app.post('/api/overlap')
def overlap():
 from datetime import datetime
 from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
 data=request.get_json(silent=True) or {}
 try:
  start=datetime.fromisoformat(data['start']); end=datetime.fromisoformat(data['end']); zones=data['timezones']
  if start.tzinfo or end.tzinfo or end<=start or not isinstance(zones,list) or not zones: raise ValueError()
  intervals=[]
  for name in zones:
   zone=ZoneInfo(name); intervals.append((start.replace(tzinfo=zone).astimezone(ZoneInfo('UTC')),end.replace(tzinfo=zone).astimezone(ZoneInfo('UTC'))))
  lo=max(x[0] for x in intervals); hi=min(x[1] for x in intervals)
 except (ValueError,KeyError,TypeError,ZoneInfoNotFoundError): return jsonify(error='Provide local ISO start/end, an end after start, and valid IANA timezones.'),400
 return jsonify(has_overlap=lo<hi,start_utc=lo.isoformat() if lo<hi else None,end_utc=hi.isoformat() if lo<hi else None,participants=zones)
@app.post('/api/coach')
def coach():
 prompt=(request.get_json(silent=True) or {}).get('prompt','').strip()[:3000]
 if not prompt:return jsonify(error='Enter a question first.'),400
 key=os.getenv('OPENAI_API_KEY')
 if key:
  try:
   from urllib.request import Request,urlopen
   req=Request('https://api.openai.com/v1/responses',data=json.dumps({'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'input':f'You are a practical Scheduling & collaboration assistant inside Timefold. Give specific, concise, safe advice. User: {prompt}'}).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
   with urlopen(req,timeout=35) as r: payload=json.loads(r.read())
   text=' '.join(part.get('text','') for item in payload.get('output',[]) for part in item.get('content',[]) if part.get('type')=='output_text')
   if text:return jsonify(answer=text,mode='ai')
  except Exception as e: return jsonify(error='AI request failed: '+str(e)),502
 return jsonify(answer=f'Demo coach: For “{prompt}”, start with one small, measurable next action. Save your work here, review it after a week, and adjust based on what actually helped.',mode='demo')
if __name__=='__main__': app.run(host='127.0.0.1',port=int(os.getenv('PORT',5000)),debug=os.getenv('FLASK_DEBUG')=='1')
