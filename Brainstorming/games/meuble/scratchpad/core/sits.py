import json,glob,math,os
for f in sorted(glob.glob('Assets/Resources/Levels/*.json')):
    if f.endswith('levels.json'): continue
    d=json.load(open(f,encoding='utf-8'))
    props={p['name']:p for p in d.get('props',[]) if 'name' in p}
    for h in d.get('inhabitants',[]):
        for i,s in enumerate(h.get('stations',[])):
            if s.get('sit'):
                if s['sit']=='player':
                    seat=s.get('seat',{}); sx,sz=seat.get('x',0),seat.get('z',0)
                else:
                    p=props.get(s['sit']); sx,sz=(p.get('x',0),p.get('z',0)) if p else (None,None)
                dist=math.hypot(s.get('x',0)-sx,s.get('z',0)-sz) if sx is not None else None
                print(os.path.basename(f), h.get('name'), i, s['sit'], 'station',(s.get('x',0),s.get('z',0),s.get('facing',0)),'seat',(sx,sz),'dist', None if dist is None else round(dist,3))
