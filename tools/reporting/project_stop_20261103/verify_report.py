"""Validate the generated report against its saved sources and actual Word PDF."""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
import fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'docs/project-overview-20261103'
PREVIEW = ROOT/'results/project_stop_report_20261103/final_visual'
PREVIEW.mkdir(parents=True,exist_ok=True)
read = lambda p: json.loads(p.read_bytes())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
norm = lambda s: re.sub(r'\s+', '', unicodedata.normalize('NFKC', s))
pack=read(OUT/'report_data.json'); sources=read(OUT/'report.sources.json')
for row in sources['inputs']:
    p=ROOT/row['path']
    assert p.stat().st_size==row['bytes'] and digest(p)==row['sha256'], row['path']
assert pack['formal_progress']=={'completed':0,'planned':280}
assert pack['identity_totals']=={'scheduled_samples':3014,'correct':2551,'wrong':0,'unknown':463}
assert all(r['status']=='PASS' for r in pack['core_rows']) and len(pack['core_rows'])==12
assert {s:sum(r['status']==s for r in pack['extension_rows']) for s in ['PASS','FAIL','INCOMPLETE_EVIDENCE']} == {'PASS':11,'FAIL':4,'INCOMPLETE_EVIDENCE':1}
with zipfile.ZipFile(OUT/'项目整体报告_20261103.docx') as z:
    doc=ET.fromstring(z.read('word/document.xml'))
    doc_text=''.join(doc.itertext())
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    heading_count=sum(p.get('{'+ns['w']+'}val')=='Heading1' for p in doc.findall('.//w:pStyle',ns))
    assert heading_count==15
paragraphs=[]
for sec in pack['sections']:
    for b in sec['blocks']:
        if b['type']=='paragraph':
            assert b['text'] in doc_text
            paragraphs.append(b['text'])
render=read(OUT/'word_pdf_render.json')
assert digest(OUT/'项目整体报告_20261103.docx')==render['input']['sha256']
assert digest(OUT/'项目整体报告_20261103.pdf')==render['output']['sha256']
pdf=fitz.open(OUT/'项目整体报告_20261103.pdf')
assert len(pdf)==render['word_pages']
pdf_text=''.join(page.get_text() for page in pdf)
for sec in pack['sections']:
    assert norm(sec['title']) in norm(pdf_text), sec['title']
for r in pack['core_rows']:
    for key in ['base_link_distance_rmse_m','base_link_height_rmse_m']:
        assert f'{r["measured"][key]:.4f}' in pdf_text
assert all(s in pdf_text for s in ['0/280','2551','463','2.2219','3.0726','2.0369'])
page_info=[]; thumbs=[]
for i,page in enumerate(pdf):
    text=page.get_text()
    assert len(text)>250, f'Sparse or blank page {i+1}'
    overflow=[]
    for block in page.get_text('dict')['blocks']:
        x0,y0,x1,y1=block['bbox']
        if x0 < -1 or y0 < -1 or x1 > page.rect.width+1 or y1 > page.rect.height+1:
            overflow.append(block['bbox'])
    assert not overflow, (i+1,overflow)
    pix=page.get_pixmap(matrix=fitz.Matrix(1.3,1.3))
    target=PREVIEW/f'page_{i+1:02}.png'; pix.save(target)
    im=Image.open(target).convert('RGB');im.thumbnail((660,935));thumbs.append(im)
    page_info.append({'page':i+1,'text_chars':len(text),'out_of_page_blocks':0,'preview_sha256':digest(target)})
for a in range(0,len(thumbs),4):
    sheet=Image.new('RGB',(1360,1950),'#cbd4dc');draw=ImageDraw.Draw(sheet)
    for k,im in enumerate(thumbs[a:a+4]):
        x=15+(k%2)*680;y=25+(k//2)*975;sheet.paste(im,(x,y));draw.text((x,y-18),f'Page {a+k+1}',fill='black')
    sheet.save(PREVIEW/f'contact_{a//4+1:02}.png')
record={'kind':'REPORT_CONTENT_AND_RENDER_VALIDATION_NOT_EXPERIMENT',
        'created_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS_AUTOMATED_DOCUMENT_CHECKS',
        'source_fingerprints_matched':len(sources['inputs']),
        'narrative_paragraphs_matched_in_docx':len(paragraphs),
        'heading_count':heading_count,'pdf_pages':len(pdf),'per_page':page_info,
        'visual_review':'PENDING_HUMAN_MODEL_IMAGE_INSPECTION',
        'experiments_started':False,'formal_progress':'0/280'}
(OUT/'report_validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k!='per_page'},ensure_ascii=False))
