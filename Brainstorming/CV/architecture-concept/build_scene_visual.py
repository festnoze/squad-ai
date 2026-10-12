import xml.etree.ElementTree as E
from pathlib import Path
base=Path(__file__).resolve().parent
root=E.Element('div',id='reactor-scene-proposal')
E.SubElement(root,'h2').text='Projection du réacteur'
field=E.SubElement(root,'label',{'class':'form-label','for':'reactor-explode'})
field.text='Décomposition · '
E.SubElement(field,'span',{'data-value':'','class':'tabular-nums'}).text='0 %'
E.SubElement(root,'input',{'id':'reactor-explode','type':'range','class':'form-range','data-explode':'','min':'0','max':'100','value':'0','aria-label':'Décomposition du réacteur'})
E.SubElement(root,'div',{'data-projection':''})
E.SubElement(root,'style').text='''#reactor-scene-proposal {color:var(--foreground)}
#reactor-scene-proposal .reactor-projection {display:block;width:100%}
#reactor-scene-proposal .reactor-projection text {fill:var(--foreground);font-size:12px;font-weight:400}
#reactor-scene-proposal [data-projection] {width:100%;margin-top:12px}'''
E.SubElement(root,'script').text=(base/'scene-proposal.js').read_text(encoding='utf-8-sig')
E.indent(root,space='  ')
out=Path('C:/Users/e.millerioux/.codex/visualizations/2026/10/12/01a12f3b-42b1-7eb3-ab00-a81b927d4d5a/reactor-proposal.html')
E.ElementTree(root).write(out,encoding='utf-8',method='html')
print(out,out.stat().st_size)
