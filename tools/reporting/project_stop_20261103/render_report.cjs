"use strict";
// Status-report renderer. It never invokes the formal acceptance generators.
const fs = require('node:fs');
const path = require('node:path');
const {
  AlignmentType, BorderStyle, Document, Footer, Header, HeadingLevel,
  ImageRun, PageBreak, PageNumber, Packer, Paragraph, ShadingType,
  Table, TableCell, TableLayoutType, TableRow, TextRun, VerticalAlign, WidthType,
} = require('docx');

const root = path.resolve(__dirname, '../../..');
const out = path.join(root, 'docs/project-overview-20261103');
const pack = JSON.parse(fs.readFileSync(path.join(out, 'report_data.json'), 'utf8'));
if (pack.kind !== 'PROJECT_STOP_TIME_OVERVIEW_NOT_FINAL_ACCEPTANCE'
    || pack.formal_progress.completed !== 0 || pack.formal_progress.planned !== 280) {
  throw new Error('Unexpected report scope');
}
const FONT = 'Microsoft YaHei';
const WIDTH = 9746;
const run = (text, opts = {}) => new TextRun({text, font: FONT, size:21, ...opts});
const para = (text, opts = {}) => new Paragraph({
  children:[run(text)], spacing:{after:120,line:280}, ...opts,
});
const h = (text, level = 1, pageBreakBefore = false) => new Paragraph({
  text, heading:level === 1 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
  pageBreakBefore, keepNext:true, spacing:{before:140,after:240},
});
function normalizedWidths(block) {
  const ws = block.widths || block.headers.map(() => 1);
  const sum = ws.reduce((a,b)=>a+b,0);
  const widths=ws.map(w=>Math.round(w*WIDTH/sum));
  widths[widths.length-1] += WIDTH-widths.reduce((a,b)=>a+b,0);
  return widths;
}
function table(block) {
  const widths = normalizedWidths(block);
  const cell = (text,i,header,row) => new TableCell({
    width:{size:widths[i],type:WidthType.DXA},
    margins:{top:65,bottom:65,left:100,right:100},
    verticalAlign:VerticalAlign.CENTER,
    shading:{type:ShadingType.CLEAR, fill:header?'E8F0F4':row%2===0?'FFFFFF':'F6F9FB'},
    children:[new Paragraph({
      children:[run(String(text), {size:17.5,bold:header,color:header?'183B50':'243B4B'})],
      spacing:{before:0,after:0,line:230},
    })],
  });
  return new Table({
    width:{size:WIDTH,type:WidthType.DXA}, columnWidths:widths,
    layout:TableLayoutType.FIXED,
    borders:Object.fromEntries(['top','bottom','left','right','insideHorizontal','insideVertical']
      .map(k=>[k,{style:BorderStyle.SINGLE,size:4,color:'D8E3EB'}])),
    rows:[new TableRow({tableHeader:true,children:block.headers.map((t,i)=>cell(t,i,true,0))}),
      ...block.rows.map((row,n)=>new TableRow({cantSplit:true,children:row.map((t,i)=>cell(t,i,false,n))}))],
  });
}
function pngSize(raw) { return {width:raw.readUInt32BE(16),height:raw.readUInt32BE(20)}; }
const children=[];
children.push(para('项目整体报告', {spacing:{before:1300,after:260},children:[run('项目整体报告',{size:28,bold:true,color:'26766C'})]}));
children.push(new Paragraph({children:[run(pack.title,{size:46,bold:true,color:'183B50'})],spacing:{after:260,line:620}}));
children.push(para(pack.subtitle,{children:[run(pack.subtitle,{size:27,color:'526B7B'})],spacing:{after:480}}));
children.push(para(pack.date,{children:[run(pack.date,{size:24,color:'526B7B'})],spacing:{after:600}}));
children.push(para(pack.status,{children:[run(pack.status,{size:23,bold:true,color:'956222'})],
  shading:{type:ShadingType.CLEAR,fill:'FFF6E8'},spacing:{before:100,after:400,line:360}}));
children.push(table({headers:['核心开发','独立安全','扩展开发','正式研究'],rows:[['12/12 PASS','4/4 PASS','11 PASS / 4 FAIL / 1缺证','0/280']],widths:[2100,2100,3400,2100]}));
children.push(para('本报告覆盖系统设计、三阶段实现、历史与最新实验、失败分析、身份覆盖、算法结论、停止原因和未完成清单。所有数据取自已有结果；生成报告没有启动新实验。',{spacing:{before:400,after:220,line:340}}));
children.push(para('用途：毕业设计整理、当前成果验收与研究交接。',{children:[run('用途：毕业设计整理、当前成果验收与研究交接。',{size:20,color:'526B7B'})]}));
children.push(para('边界：状态报告，不是全部工程验收通过证书。',{children:[run('边界：状态报告，不是全部工程验收通过证书。',{size:20,color:'526B7B'})]}));
children.push(h('阅读目录',1,true));
for (let i=0;i<pack.sections.length;i++) {
  children.push(para(pack.sections[i].title,{spacing:{after:200,line:320},children:[run(pack.sections[i].title,{size:23,color:'21475A'})]}));
}
children.push(para('阅读建议：先看“一、整体结论”，再看“五、核心结果”“六、扩展失败”和“八、身份覆盖”；完整来源与未完成清单在末尾。',{spacing:{before:260,after:140,line:320}}));

for (const section of pack.sections) {
  children.push(h(section.title,1,true));
  for (const b of section.blocks) {
    if (b.type === 'paragraph') children.push(para(b.text));
    if (b.type === 'table') {
      children.push(table(b));
      children.push(new Paragraph({spacing:{after:100,before:0},children:[]}));
    }
    if (b.type === 'figure') {
      const raw=fs.readFileSync(path.join(out,b.path));const dim=pngSize(raw);
      const w=590, height=Math.round(w*dim.height/dim.width);
      children.push(new Paragraph({alignment:AlignmentType.CENTER,keepNext:true,
        spacing:{before:160,after:80},children:[new ImageRun({data:raw,type:'png',transformation:{width:w,height}})]}));
      children.push(para(b.caption,{alignment:AlignmentType.CENTER,
        children:[run(b.caption,{size:17,color:'596F7D'})],spacing:{after:200,line:250}}));
    }
  }
}
const doc=new Document({
  title:pack.title+'—'+pack.subtitle, subject:'实验停止时点的三阶段仿真项目整体报告',
  creator:'项目协作记录', description:'正式研究0/280；保留所有失败和未知。',
  styles:{default:{document:{run:{font:FONT,size:21,color:'243B4B'},paragraph:{spacing:{line:300}}}},
    paragraphStyles:[
      {id:'Heading1',name:'heading 1',basedOn:'Normal',next:'Normal',quickFormat:true,
       run:{font:FONT,size:32,bold:true,color:'183B50'},paragraph:{keepNext:true,outlineLevel:0}},
      {id:'Heading2',name:'heading 2',basedOn:'Normal',next:'Normal',quickFormat:true,
       run:{font:FONT,size:26,bold:true,color:'26766C'},paragraph:{keepNext:true,outlineLevel:1}},
    ]},
  sections:[{
    properties:{page:{size:{width:11906,height:16838},margin:{top:1000,bottom:1000,left:1080,right:1080,header:430,footer:430}}},
    headers:{default:new Header({children:[new Paragraph({
      children:[run('RGB-D无人机跟踪与自主跟随 · 项目整体报告',{size:16,color:'687D8A'})],
      border:{bottom:{style:BorderStyle.SINGLE,size:4,color:'D8E3EB'}},spacing:{after:90},
    })]})},
    footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,
      children:[run('实验停止时点｜2026-11-03　·　第 ',{size:16,color:'687D8A'}),
        new TextRun({children:[PageNumber.CURRENT],font:FONT,size:16,color:'687D8A'}),
        run(' / ',{size:16,color:'687D8A'}),
        new TextRun({children:[PageNumber.TOTAL_PAGES],font:FONT,size:16,color:'687D8A'}),run(' 页',{size:16,color:'687D8A'})],
    })]})}, children,
  }],
});
Packer.toBuffer(doc).then(buffer=>{
  const target=path.join(out,'项目整体报告_20261103.docx');fs.writeFileSync(target,buffer);
  process.stdout.write(JSON.stringify({path:target,bytes:buffer.length,sections:pack.sections.length})+'\n');
});
