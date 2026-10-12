import json
import xml.etree.ElementTree as E
from pathlib import Path
base=Path(__file__).resolve().parent
model=json.loads((base/'architecture.json').read_text(encoding='utf-8'))
root=E.Element('div',id='architecture-api-explorer')
E.SubElement(root,'h2').text='Architecture modulaire'
controls=E.SubElement(root,'div',{'class':'viz-controls'})
options=[(v['id'],v['label']) for v in model['views']]
for attr,label,values in [('data-focus','Focus au scroll',options),('data-flow','Flux mis en évidence',[(f['id'],f['label']) for f in model['flows'] if f['id']!='connections'])]:
    field=E.SubElement(controls,'label',{'class':'form-label'})
    field.text=label
    select=E.SubElement(field,'select',{'class':'form-select',attr:'','aria-label':label})
    for value,name in values:E.SubElement(select,'option',dict(value=value,**({'selected':'selected'} if attr=='data-flow' and value=='agentic' else {}))).text=name
E.SubElement(root,'div',{'class':'viz-row text-small','data-legend':''})
E.SubElement(root,'div',{'data-diagram':''})
E.SubElement(root,'div',{'class':'text-small','data-detail':'','aria-live':'polite'})
E.SubElement(root,'style').text=(base/'diagram.css').read_text(encoding='utf-8-sig')
E.SubElement(root,'script',{'type':'application/json','data-model':''}).text=json.dumps(model,ensure_ascii=False)
E.SubElement(root,'script').text=(base/'diagram.js').read_text(encoding='utf-8-sig')
out=Path('C:/Users/e.millerioux/.codex/visualizations/2026/10/12/01a12f3b-42b1-7eb3-ab00-a81b927d4d5a/architecture-api.html')
out.parent.mkdir(parents=True,exist_ok=True)
E.indent(root,space='  ')
E.ElementTree(root).write(out,encoding='utf-8',method='html')
html=out.read_text(encoding='utf-8')
assert '<html' not in html and '<body' not in html
assert '(() =>' in html and 'model.views' in html
print(str(out),out.stat().st_size)
