const DEFAULT_COLUMN_WIDTH = 15

const getColumnWidth = (columnWidth) => {
  if (typeof columnWidth === 'number') {
    return columnWidth
  }

  return columnWidth?.wch || columnWidth?.width || DEFAULT_COLUMN_WIDTH
}

const normalizeFileName = (fileName) => {
  const name = String(fileName || `export-${new Date().toISOString().slice(0, 10)}.xls`)

  if (/\.xlsx$/i.test(name)) {
    return name.replace(/\.xlsx$/i, '.xls')
  }

  if (/\.xls$/i.test(name)) {
    return name
  }

  return `${name}.xls`
}

const sanitizeXmlValue = (value) => String(value ?? '')
  .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')

const escapeXml = (value) => sanitizeXmlValue(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&apos;')

const normalizeSheetName = (sheetName) => {
  const name = sanitizeXmlValue(sheetName || 'Sheet1')
    .replace(/[\\/?*:\[\]]/g, ' ')
    .trim()

  return (name || 'Sheet1').slice(0, 31)
}

const xmlDataCell = (value, styleId) => (
  `<Cell ss:StyleID="${styleId}"><Data ss:Type="String">${escapeXml(value)}</Data></Cell>`
)

const buildWorkbookXml = ({ data, sheetName, columnWidths, headerBold }) => {
  const columns = data[0].map((_, index) => {
    const width = Math.max(8, getColumnWidth(columnWidths[index])) * 7
    return `<Column ss:Width="${width}"/>`
  }).join('')

  const rows = data.map((row, rowIndex) => {
    const styleId = rowIndex === 0 && headerBold ? 'Header' : 'Body'
    const cells = row.map((cell) => xmlDataCell(cell, styleId)).join('')
    return `<Row>${cells}</Row>`
  }).join('')

  return `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:x="urn:schemas-microsoft-com:office:excel"
  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Styles>
    <Style ss:ID="Header">
      <Font ss:Bold="1"/>
      <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
    </Style>
    <Style ss:ID="Body">
      <Alignment ss:Vertical="Top" ss:WrapText="1"/>
    </Style>
  </Styles>
  <Worksheet ss:Name="${escapeXml(normalizeSheetName(sheetName))}">
    <Table>${columns}${rows}</Table>
  </Worksheet>
</Workbook>`
}

export const exportAoaToExcel = async ({
  data,
  fileName,
  sheetName = 'Sheet1',
  columnWidths = [],
  headerBold = true
}) => {
  if (!Array.isArray(data) || data.length === 0) {
    throw new Error('No data to export')
  }

  const workbookXml = buildWorkbookXml({
    data,
    sheetName,
    columnWidths,
    headerBold
  })
  const blob = new Blob(
    ['\ufeff', workbookXml],
    { type: 'application/vnd.ms-excel;charset=utf-8' }
  )
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')

  link.href = url
  link.download = normalizeFileName(fileName)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
