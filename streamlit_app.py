import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title='QF | QuoteFast', page_icon='⚡')
st.title('QF | QuoteFast')
st.caption('From RFQ to Quotation in Minutes — v0.2')
st.info('Demo: use fictional product and pricing data only.')


def extract_text(upload):
    name = upload.name.lower()
    if name.endswith('.pdf'):
        from pypdf import PdfReader
        reader = PdfReader(upload)
        return '\n'.join(page.extract_text() or '' for page in reader.pages)
    if name.endswith('.docx'):
        from docx import Document
        doc = Document(upload)
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(', '.join(cell.text for cell in row.cells))
        return '\n'.join(parts)
    if name.endswith(('.xlsx', '.xls')):
        frames = pd.read_excel(upload, sheet_name=None, header=None)
        return '\n'.join(', '.join('' if pd.isna(v) else str(v) for v in row)
                         for df in frames.values() for row in df.itertuples(index=False, name=None))
    if name.endswith('.csv'):
        return upload.getvalue().decode('utf-8-sig', errors='replace')
    return upload.getvalue().decode('utf-8-sig', errors='replace')


def parse_items(text):
    items = []
    for line in text.splitlines():
        # v0.2 accepts SKU, quantity; or SKU [tab/semicolon] quantity.
        match = re.fullmatch(r'\s*([A-Za-z0-9][A-Za-z0-9._/-]*)\s*[,;\t]\s*(\d+)\s*', line)
        if match:
            items.append((match.group(1).upper(), int(match.group(2))))
    return items

catalogue_file = st.file_uploader('Upload product catalogue (CSV)', type=['csv'])
rfq_file = st.file_uploader('Upload customer RFQ (PDF, Excel, Word, CSV, TXT)',
                            type=['pdf', 'xlsx', 'docx', 'csv', 'txt'])
rfq_text = st.text_area('Or paste RFQ items', placeholder='SKU001, 10\nSKU002, 5', height=120)
currency = st.selectbox('Currency', ['USD', 'EUR', 'GBP'])

if st.button('Generate Quotation', type='primary'):
    if catalogue_file is None:
        st.warning('Upload a catalogue first.')
    elif rfq_file is None and not rfq_text.strip():
        st.warning('Upload an RFQ or paste RFQ items.')
    else:
        try:
            catalogue = pd.read_csv(catalogue_file)
            catalogue.columns = catalogue.columns.str.strip().str.lower()
            required = {'sku', 'description', 'price'}
            if not required.issubset(catalogue.columns):
                st.error('Catalogue must contain columns: sku, description, price')
            else:
                catalogue['sku'] = catalogue['sku'].astype(str).str.strip().str.upper()
                catalogue['price'] = pd.to_numeric(catalogue['price'], errors='coerce')
                source = extract_text(rfq_file) if rfq_file is not None else rfq_text
                items = parse_items(source)
                if not items:
                    st.error('No items recognized. This demo expects one line per item: SKU001, 10. '
                             'Scanned PDFs and free-form RFQs will require the next AI upgrade.')
                    with st.expander('Show extracted RFQ text'):
                        st.text(source[:5000] or '(No extractable text)')
                else:
                    rows = []
                    for sku, qty in items:
                        found = catalogue[catalogue['sku'] == sku]
                        if len(found) == 1:
                            product = found.iloc[0]
                            price = product['price']
                            status = 'Matched' if pd.notna(price) else 'Price missing'
                            desc = product['description']
                        elif len(found) > 1:
                            price, desc, status = None, '', 'Duplicate SKU - review'
                        else:
                            price, desc, status = None, '', 'Not found - review'
                        rows.append({'SKU': sku, 'Description': desc, 'Quantity': qty,
                                     'Unit Price': price,
                                     'Total': round(qty * price, 2) if pd.notna(price) else None,
                                     'Status': status})
                    result = pd.DataFrame(rows)
                    st.subheader('Draft Quotation')
                    st.dataframe(result, use_container_width=True)
                    subtotal = result.loc[result['Status'] == 'Matched', 'Total'].sum()
                    st.metric('Matched items subtotal', f'{currency} {subtotal:,.2f}')
                    if (result['Status'] != 'Matched').any():
                        st.warning('Some items need review. They are excluded from the subtotal.')
                    st.download_button('Download Draft Quotation (CSV)',
                                       result.to_csv(index=False), 'quotefast_draft.csv', 'text/csv')
        except Exception as exc:
            st.error(f'Unable to process input: {exc}')

st.divider()
st.caption('Prototype v0.2: matches exact SKUs only. Verify all prices and quantities before use.')
