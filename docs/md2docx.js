// 轻量 Markdown -> DOCX 转换器（支持标题/表格/代码块/有序无序列表/加粗）
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, LevelFormat, BorderStyle, WidthType,
  ShadingType, PageBreak
} = require('docx');

const CJK = "Microsoft YaHei";
const CONTENT_W = 9026; // A4 1英寸边距内容宽度

function parseInline(text, baseOpts = {}) {
  const runs = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) runs.push(new TextRun({ text: text.slice(last, m.index), ...baseOpts }));
    runs.push(new TextRun({ text: m[1], bold: true, ...baseOpts }));
    last = m.index + m[0].length;
  }
  if (last < text.length) runs.push(new TextRun({ text: text.slice(last), ...baseOpts }));
  if (runs.length === 0) runs.push(new TextRun({ text, ...baseOpts }));
  return runs;
}

function splitRow(line) {
  return line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(s => s.trim());
}

function isTableSep(line) {
  return /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes('-');
}

function buildDoc(md) {
  const lines = md.split('\n');
  const children = [];
  let i = 0;

  const bulletCfg = { reference: 'bullets', levels: [
    { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
    { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
  ]};
  const numCfg = { reference: 'numbers', levels: [
    { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
  ]};

  while (i < lines.length) {
    let line = lines[i];

    if (line.trim().startsWith('```')) {
      i++;
      const code = [];
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        code.push(lines[i]); i++;
      }
      i++;
      code.forEach(c => children.push(new Paragraph({
        spacing: { before: 0, after: 0 },
        children: [new TextRun({ text: c || ' ', font: 'Consolas', size: 18 })]
      })));
      continue;
    }

    if (line.includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(splitRow(lines[i])); i++;
      }
      const ncol = header.length;
      const colW = Math.floor(CONTENT_W / ncol);
      const border = { style: BorderStyle.SINGLE, size: 1, color: 'BFBFBF' };
      const borders = { top: border, bottom: border, left: border, right: border };
      const toRow = (cells, head) => new TableRow({ children: cells.map(c => new TableCell({
        borders, width: { size: colW, type: WidthType.DXA },
        shading: head ? { fill: 'D5E8F0', type: ShadingType.CLEAR } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ children: parseInline(c, { size: 20 }) })]
      })) });
      const table = new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnWidths: Array(ncol).fill(colW),
        rows: [toRow(header, true), ...rows.map(r => toRow(r, false))]
      });
      children.push(table);
      children.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun('')] }));
      continue;
    }

    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const lvl = h[1].length;
      const map = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2,
                    3: HeadingLevel.HEADING_3, 4: HeadingLevel.HEADING_4 };
      children.push(new Paragraph({ heading: map[lvl], children: parseInline(h[2]) }));
      i++; continue;
    }

    if (line.trim().startsWith('>')) {
      const txt = line.replace(/^\s*>\s?/, '');
      children.push(new Paragraph({ indent: { left: 360 }, spacing: { after: 80 },
        children: parseInline(txt, { italics: true, color: '595959' }) }));
      i++; continue;
    }

    const bul = /^(\s*)-\s+(.*)$/.exec(line);
    if (bul) {
      const lvl = bul[1].length >= 2 ? 1 : 0;
      children.push(new Paragraph({ numbering: { reference: 'bullets', level: lvl },
        children: parseInline(bul[2]) }));
      i++; continue;
    }

    const num = /^(\s*)(\d+)\.\s+(.*)$/.exec(line);
    if (num) {
      children.push(new Paragraph({ numbering: { reference: 'numbers', level: 0 },
        children: parseInline(num[3]) }));
      i++; continue;
    }

    if (line.trim() === '') { i++; continue; }

    children.push(new Paragraph({ spacing: { after: 120 }, children: parseInline(line) }));
    i++;
  }

  const doc = new Document({
    styles: {
      default: { document: { run: { font: CJK, size: 22 } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal',
          run: { size: 32, bold: true, font: CJK, color: '1F4E79' },
          paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal',
          run: { size: 26, bold: true, font: CJK, color: '2E75B6' },
          paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1 } },
        { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal',
          run: { size: 23, bold: true, font: CJK, color: '2E75B6' },
          paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
        { id: 'Heading4', name: 'Heading 4', basedOn: 'Normal', next: 'Normal',
          run: { size: 22, bold: true, font: CJK },
          paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 3 } },
      ]
    },
    numbering: { config: [bulletCfg, numCfg] },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      children
    }]
  });
  return doc;
}

(async () => {
  const input = process.argv[2];
  const output = process.argv[3] || input.replace(/\.md$/i, '.docx');
  const md = fs.readFileSync(input, 'utf-8');
  const doc = buildDoc(md);
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(output, buf);
  console.log('Generated:', output);
})();
