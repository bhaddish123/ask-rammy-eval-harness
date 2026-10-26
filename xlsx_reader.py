"""
Minimal XLSX reader (no external dependencies).
Correctly resolves shared strings so cell values are readable text.
"""

import zipfile
import xml.etree.ElementTree as ET
import re

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def col_letter_to_index(cell_ref):
    """Convert 'C5' -> column index 2 (0-based)."""
    match = re.match(r'([A-Z]+)(\d+)', cell_ref)
    if not match:
        return 0
    col_letters = match.group(1)
    idx = 0
    for char in col_letters:
        idx = idx * 26 + (ord(char) - ord('A') + 1)
    return idx - 1

def read_xlsx_rows(xlsx_path, sheet="sheet1"):
    """
    Read an XLSX file and return a list of rows, each row a list of cell
    text values, correctly resolved through the shared string table.
    Empty/missing cells are "" and rows are padded to the widest row seen so far
    is NOT guaranteed — each row only contains cells up to its last populated column.
    """
    with zipfile.ZipFile(xlsx_path, 'r') as z:
        shared_strings = []
        try:
            strings_xml = z.read('xl/sharedStrings.xml')
            strings_root = ET.fromstring(strings_xml)
            for si in strings_root.findall('s:si', NS):
                # Text may be split across multiple <r><t> runs; concatenate all <t>
                texts = si.findall('.//s:t', NS)
                combined = "".join(t.text or "" for t in texts)
                shared_strings.append(combined)
        except KeyError:
            pass

        xml_data = z.read(f'xl/worksheets/{sheet}.xml')
        root = ET.fromstring(xml_data)

        rows = []
        for row in root.findall('.//s:row', NS):
            row_cells = {}
            max_col = -1
            for cell in row.findall('s:c', NS):
                cell_ref = cell.get('r', '')
                col_idx = col_letter_to_index(cell_ref)
                max_col = max(max_col, col_idx)

                value_elem = cell.find('s:v', NS)
                cell_type = cell.get('t', '')

                if value_elem is None:
                    row_cells[col_idx] = ""
                    continue

                value = value_elem.text or ""
                if cell_type == 's' and value.isdigit():
                    idx = int(value)
                    value = shared_strings[idx] if idx < len(shared_strings) else ""

                row_cells[col_idx] = value

            row_list = [row_cells.get(i, "") for i in range(max_col + 1)]
            rows.append(row_list)

        return rows
