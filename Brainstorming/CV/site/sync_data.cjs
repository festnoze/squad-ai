const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const files=['name','contact','summary','skills','experience','education','languages','sidebar_skills'].map(n=>path.join(root,'data',n+'.js'));
files.push(path.join(root,'cv_full','data','experience_full.js'));
const code=files.map(f=>fs.readFileSync(f,'utf8')).join('\n')+'\n;JSON.stringify({name:NAME,contact:CONTACT,summary:SUMMARY,skills:SKILLS,experience:EXPERIENCE,education:EDUCATION,languages:LANGUAGES,tools:TOOLS,missions:EXPERIENCE_FULL})';
const data=JSON.parse(vm.runInNewContext(code,{}, {timeout:2000}));
fs.writeFileSync(path.join(__dirname,'data','resume.json'),JSON.stringify(data,null,2)+'\n');
console.log(JSON.stringify({roles:data.experience.reduce((n,g)=>n+g.positions.length,0),missions:data.missions.length,skills:data.skills.filter(s=>s.title).length}));
// Keep the printable snapshot and portrait synchronized with the source CV.
fs.mkdirSync(path.join(__dirname,'assets','cv','data'),{recursive:true});
for(const file of files.slice(0,-1))fs.copyFileSync(file,path.join(__dirname,'assets','cv','data',path.basename(file)));
for(const name of ['cv.css','photo.jpg'])fs.copyFileSync(path.join(root,name),path.join(__dirname,'assets','cv',name));
let sourceHtml=fs.readFileSync(path.join(root,'index.html'),'utf8');
sourceHtml=sourceHtml.replace(/<link\s+rel="stylesheet"\s+href="https:\/\/cdnjs\.cloudflare\.com\/ajax\/libs\/font-awesome\/[^>]+>/g,'');
fs.writeFileSync(path.join(__dirname,'assets','cv','index.html'),sourceHtml);
fs.copyFileSync(path.join(root,'photo identité etienne.png'),path.join(__dirname,'assets','portrait.png'));
