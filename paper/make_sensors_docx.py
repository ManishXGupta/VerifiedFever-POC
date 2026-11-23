"""Build the VerifiedFever article inside the IEEE Sensors Journal / Sensors Letters Word template.

The content (text, numbers, figures, tables, references) is taken from make_template_docx.py, so both
versions stay identical; only the layout helpers are swapped for the IEEE Sensors template styles
(Heading, Authors, Abstract box with graphical abstract, Index Terms, Heading1/Heading2 auto
numbering, Text, FigureCaption, TableTitle, References auto-numbered [n], first-page footnote).

The .doc template must first be converted to .docx (LibreOffice):
    soffice --headless --convert-to docx IEEE_SENSOR_TEMPLATE.doc
Usage:  python paper/make_sensors_docx.py TEMPLATE.docx OUTPUT.docx
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_template_docx as mt  # noqa: E402

FIG = mt.FIG
GA = mt.ROOT / "docs" / "figures" / "gagraphic_hires.png"
COL_TW = 5040                      # column width in twips (two columns, 0.2 in gap, letter page)
COL_PT = COL_TW / 20
FIGS: list[tuple[str, str]] = []
AUTHORS = "Manish Gupta, Senior Member, IEEE"
FOOTNOTE = ("Manuscript received Month DD, 2026. This work received no external funding. "
            "Manish Gupta is an independent researcher, USA (e-mail: manish.ingupta@gmail.com; ORCID 0009-0001-0847-7087).")
INDEX_TERMS = ("Agentic AI, AI guardrails, digital signatures, human-in-the-loop, Internet of Things, "
               "multi-agent systems, school health, syndromic surveillance")


def runs(text, size=None, bold=False, italic=False):
    return mt.runs(text, size=size, bold=bold, italic=italic).replace(mt.RF, "")


_first_body = [True]


def body(text):
    if _first_body[0]:
        _first_body[0] = False
        word, rest = text.split(" ", 1)
        cap = (f'<w:r><w:rPr><w:smallCaps/><w:position w:val="-3"/><w:sz w:val="55"/><w:szCs w:val="56"/></w:rPr>'
               f'<w:t>{escape(word[0])}</w:t></w:r><w:r><w:rPr><w:smallCaps/></w:rPr><w:t xml:space="preserve">{escape(word[1:].upper())} </w:t></w:r>')
        return f'<w:p><w:pPr><w:pStyle w:val="Text"/><w:spacing w:line="252" w:lineRule="auto"/><w:ind w:firstLine="0"/></w:pPr>{cap}{runs(rest)}</w:p>'
    return f'<w:p><w:pPr><w:pStyle w:val="Text"/></w:pPr>{runs(text)}</w:p>'


def center(text):
    return f'<w:p><w:pPr><w:pStyle w:val="Text"/><w:spacing w:before="60" w:after="60"/><w:ind w:firstLine="0"/><w:jc w:val="center"/></w:pPr>{runs(text)}</w:p>'


def h1(text):
    return f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{escape(text)}</w:t></w:r></w:p>'


def h2(text):
    text = re.sub(r"^[A-Z]\.\s+", "", text)
    return (f'<w:p><w:pPr><w:pStyle w:val="Heading2"/><w:keepNext/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="2"/></w:numPr>'
            f'</w:pPr><w:r><w:t>{escape(text)}</w:t></w:r></w:p>')


def caption_table(num, title):
    return (f'<w:p><w:pPr><w:pStyle w:val="TableTitle"/><w:keepNext/><w:spacing w:before="120" w:after="0"/></w:pPr>'
            f'<w:r><w:t>Table {num}</w:t></w:r></w:p>'
            f'<w:p><w:pPr><w:pStyle w:val="TableTitle"/><w:keepNext/><w:spacing w:after="60"/></w:pPr>'
            f'<w:r><w:t>{escape(title)}</w:t></w:r></w:p>')


def note(text):
    return f'<w:p><w:pPr><w:spacing w:before="40" w:after="120"/><w:jc w:val="both"/></w:pPr>{runs(text, size=14)}</w:p>'


def table(header, rows, widths_pt):
    scale = COL_PT / sum(widths_pt) if sum(widths_pt) > COL_PT else 1.0
    tw = [round(w * 20 * scale) for w in widths_pt]
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in tw)
    nrows = len(rows) + 1

    def cell(text, i, r):
        b = text.startswith("!")
        text = text[1:] if b else text
        top = r == 0
        bot = r in (0, nrows - 1)
        bd = (f'<w:top w:val="{"single" if top else "nil"}" w:sz="4" w:space="0" w:color="000000"/>'
              '<w:start w:val="nil"/>'
              f'<w:bottom w:val="{"single" if bot else "nil"}" w:sz="4" w:space="0" w:color="000000"/>'
              '<w:end w:val="nil"/>')
        return (f'<w:tc><w:tcPr><w:tcW w:w="{tw[i]}" w:type="dxa"/><w:tcBorders>{bd}</w:tcBorders><w:vAlign w:val="center"/></w:tcPr>'
                f'<w:p><w:pPr><w:keepNext/><w:jc w:val="{"start" if i == 0 else "center"}"/></w:pPr>'
                f'{runs(text, size=14, bold=(r == 0 or b))}</w:p></w:tc>')

    trs = "".join('<w:tr><w:trPr><w:cantSplit/><w:jc w:val="center"/></w:trPr>'
                  + "".join(cell(c, i, r) for i, c in enumerate(row)) + "</w:tr>"
                  for r, row in enumerate([header] + rows))
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(tw)}" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:start w:w="40" w:type="dxa"/><w:end w:w="40" w:type="dxa"/></w:tblCellMar></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{trs}</w:tbl>')


def drawing_inline(rid, cx, cy, n, descr):
    return (f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{200 + n}" name="Figure {n}" descr="{escape(descr)}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr>'
            f'<pic:cNvPr id="{200 + n}" name="fig{n}.png"/><pic:cNvPicPr><a:picLocks noChangeAspect="1"/></pic:cNvPicPr></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>')


def figure(file, caption, width_pt=None):
    from PIL import Image
    width_pt = min(width_pt or COL_PT, COL_PT)
    w, h = Image.open(FIG / file).size
    cx = int(width_pt * 12700); cy = int(cx * h / w)
    rid = f"rIdVF{len(FIGS) + 1}"
    FIGS.append((rid, file))
    n = len(FIGS)
    return (f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="120" w:after="60"/><w:jc w:val="center"/></w:pPr>'
            f'<w:r>{drawing_inline(rid, cx, cy, n, caption)}</w:r></w:p>'
            f'<w:p><w:pPr><w:pStyle w:val="FigureCaption"/><w:spacing w:after="120"/></w:pPr>'
            f'{runs(f"Fig. {n}. " + caption, size=16)}</w:p>')


def ref(i, text):
    return f'<w:p><w:pPr><w:pStyle w:val="References"/></w:pPr>{runs(text, size=16)}</w:p>'


def main(template: str, output: str):
    for name in ("body", "center", "h1", "h2", "caption_table", "note", "table", "figure", "ref"):
        setattr(mt, name, globals()[name])
    tmp = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(template) as z:
        z.extractall(tmp)
    W = tmp / "word"
    doc = (W / "document.xml").read_text(encoding="utf8")
    head, rest = doc.split("<w:body>", 1)

    # ---- front matter: title, authors, abstract box with graphical abstract, index terms
    tbl = re.search(r"<w:tbl>.*?</w:tbl>", rest, re.S).group(0)
    paras = re.findall(r"<w:p>(?:(?!<w:p>).)*?</w:p>|<w:p [^>]*>.*?</w:p>", tbl, re.S)
    abs_p = next(p for p in re.findall(r"<w:p>.*?</w:p>", tbl, re.S) if "Abstract" in p and "<w:drawing>" in p)
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", abs_p, re.S).group(0)
    draw = re.search(r"<w:r><w:drawing>.*?</w:drawing></w:r>", abs_p, re.S).group(0)
    cx = 2793365
    from PIL import Image
    gw, gh = Image.open(GA).size
    cy = int(cx * gh / gw)
    draw = re.sub(r'<wp:extent cx="\d+" cy="\d+"/>', f'<wp:extent cx="{cx}" cy="{cy}"/>', draw)
    draw = re.sub(r'<a:ext cx="\d+" cy="\d+"/>', f'<a:ext cx="{cx}" cy="{cy}"/>', draw)
    draw = re.sub(r'r:embed="[^"]+"', 'r:embed="rIdGA"', draw)
    draw = draw.replace('descr=""', 'descr="Graphical abstract"')
    new_abs = (f"<w:p>{ppr}{draw}<w:r><w:rPr><w:b/><w:bCs/><w:i/><w:iCs/></w:rPr><w:t>Abstract—</w:t></w:r>"
               f"{runs(mt.ABSTRACT)}</w:p>")
    tbl2 = tbl.replace(abs_p, new_abs)
    idx_p = next(p for p in re.findall(r"<w:p>.*?</w:p>", tbl2, re.S) if "IndexTerms" in p)
    ippr = re.search(r"<w:pPr>.*?</w:pPr>", idx_p, re.S).group(0)
    tbl2 = tbl2.replace(idx_p, f"<w:p>{ippr}<w:r><w:rPr><w:b/><w:bCs/><w:i/><w:iCs/></w:rPr><w:t>Index Terms—</w:t></w:r>{runs(INDEX_TERMS)}</w:p>")
    title = (f'<w:p><w:pPr><w:pStyle w:val="Heading"/><w:spacing w:before="0" w:after="160"/></w:pPr>'
             f'<w:r><w:rPr><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr><w:t>{escape(mt.TITLE)}</w:t></w:r></w:p>'
             f'<w:p><w:pPr><w:pStyle w:val="Authors"/></w:pPr><w:r><w:t xml:space="preserve">Manish Gupta, </w:t></w:r>'
             f'<w:r><w:rPr><w:i/><w:iCs/></w:rPr><w:t>Senior Member, IEEE</w:t></w:r></w:p>')
    HF = ('<w:headerReference w:type="default" r:id="rIdHdrN"/><w:headerReference w:type="first" r:id="rId5"/>'
          '<w:footerReference w:type="default" r:id="rId11"/><w:footerReference w:type="first" r:id="rId6"/>')
    sect1 = ('<w:p><w:pPr><w:sectPr>' + HF + '<w:footnotePr><w:numFmt w:val="decimal"/></w:footnotePr><w:type w:val="nextPage"/>'
             '<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:left="936" w:right="936" w:gutter="0" w:header="432" w:top="1008" w:footer="432" w:bottom="1008"/>'
             '<w:titlePg/><w:docGrid w:type="default" w:linePitch="360" w:charSpace="0"/></w:sectPr></w:pPr></w:p>')
    spacer = '<w:p><w:pPr><w:pStyle w:val="Text"/><w:ind w:firstLine="0"/></w:pPr></w:p>'

    # ---- body (two columns); first heading carries the unnumbered first-page footnote
    body_xml = mt.content()
    body_xml = re.sub(r'<w:p><w:pPr><w:keepNext/><w:spacing w:before="8pt"[^>]*/><w:jc w:val="center"/></w:pPr>'
                      r'<w:r><w:rPr>.*?</w:rPr><w:t>References</w:t></w:r></w:p>',
                      '<w:p><w:pPr><w:pStyle w:val="ReferenceHead"/><w:spacing w:before="280" w:after="80"/></w:pPr>'
                      '<w:r><w:t>References</w:t></w:r></w:p>', body_xml, flags=re.S)
    body_xml = body_xml.replace('<w:r><w:t>Introduction</w:t></w:r>',
                                '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:customMarkFollows="1" w:id="2"/>'
                                '<w:t xml:space="preserve"> </w:t></w:r><w:r><w:t>Introduction</w:t></w:r>', 1)
    for bad in ("pt\"",):
        assert not re.search(r'w:(?:w|line|before|after|firstLine|start|hanging|pos)="[0-9.]+pt"', body_xml), "strict units left"
    final = ('<w:sectPr>' + HF + '<w:footnotePr><w:numFmt w:val="decimal"/></w:footnotePr><w:type w:val="continuous"/>'
             '<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:left="936" w:right="936" w:gutter="0" w:header="432" w:top="1008" w:footer="432" w:bottom="1008"/>'
             '<w:cols w:num="2" w:space="288"/><w:titlePg/><w:docGrid w:type="default" w:linePitch="360" w:charSpace="0"/></w:sectPr>')
    (W / "document.xml").write_text(head + "<w:body>" + title + tbl2 + spacer + sect1 + body_xml + final + "</w:body></w:document>",
                                    encoding="utf8")

    # ---- footnote with affiliation
    fn = (W / "footnotes.xml").read_text(encoding="utf8")
    m = re.search(r'(<w:footnote [^>]*w:id="2"[^>]*>)(.*?)(</w:footnote>)', fn, re.S)
    fppr = re.search(r"<w:pPr>.*?</w:pPr>", m.group(2), re.S)
    fppr = fppr.group(0) if fppr else '<w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr>'
    fn = fn.replace(m.group(0), m.group(1) + f"<w:p>{fppr}{runs(FOOTNOTE, size=16)}</w:p>" + m.group(3))
    (W / "footnotes.xml").write_text(fn, encoding="utf8")

    # ---- running header for pages 2+ with a PAGE field
    h2x = (W / "header2.xml").read_text(encoding="utf8")
    h2x = re.sub(r"(<w:t[^>]*>)\s*2\s*(</w:t>)", r"\1\2", h2x, count=1)
    h2x = h2x.replace("<w:t></w:t>", '</w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
                      '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>2</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r><w:r><w:t></w:t>', 1)
    (W / "headerN.xml").write_text(h2x, encoding="utf8")
    shutil.copy(W / "_rels" / "header2.xml.rels", W / "_rels" / "headerN.xml.rels") if (W / "_rels" / "header2.xml.rels").exists() else None

    # ---- media and relationships
    rels = (W / "_rels" / "document.xml.rels").read_text(encoding="utf8")
    add = '<Relationship Id="rIdGA" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/ga.png"/>'
    add += '<Relationship Id="rIdHdrN" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="headerN.xml"/>'
    shutil.copy(GA, W / "media" / "ga.png")
    for rid, f in FIGS:
        shutil.copy(FIG / f, W / "media" / f)
        add += f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{f}"/>'
    (W / "_rels" / "document.xml.rels").write_text(rels.replace("</Relationships>", add + "</Relationships>"), encoding="utf8")
    ct = (tmp / "[Content_Types].xml").read_text(encoding="utf8")
    if 'Extension="wmf"' not in ct:
        ct = ct.replace("<Default ", '<Default Extension="wmf" ContentType="image/x-wmf"/><Default ', 1)
    if 'Extension="png"' not in ct:
        ct = ct.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
    ct = ct.replace("</Types>", '<Override PartName="/word/headerN.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/></Types>')
    (tmp / "[Content_Types].xml").write_text(ct, encoding="utf8")

    out = Path(output)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp / "[Content_Types].xml", "[Content_Types].xml")
        for f in sorted(tmp.rglob("*")):
            if f.is_file() and f.name != "[Content_Types].xml":
                z.write(f, f.relative_to(tmp).as_posix())
    print("wrote", out, "with", len(FIGS), "figures")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
