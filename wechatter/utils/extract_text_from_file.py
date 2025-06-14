import base64
from PyPDF2 import PdfReader
import docx
import pandas as pd

def extract_text_from_pdf(pdf_path):
    """
    从PDF文件中提取文本
    :param pdf_path: PDF文件路径
    :return: 提取的文本内容
    """
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def extract_text_from_docx(docx_path):
    """
    从Word文档中提取文本
    :param docx_path: Word文档路径
    :return: 提取的文本内容
    """
    doc = docx.Document(docx_path)
    return "\n".join([para.text for para in doc.paragraphs])

def extract_text_from_excel(excel_path):
    """
    从Excel文件中提取文本
    :param excel_path: Excel文件路径
    :return: 提取的文本内容
    """
    df = pd.read_excel(excel_path)
    return df.to_string()

def extract_text_from_file(file_path):
    """
    根据文件类型自动选择合适的方法提取文本
    :param file_path: 文件路径
    :return: 提取的文本内容
    """
    file_type = file_path.split(".")[-1].lower()

    if file_type == "pdf":
        return extract_text_from_pdf(file_path)
    elif file_type == "docx":
        return extract_text_from_docx(file_path)
    elif file_type in ["xlsx", "xls"]:
        return extract_text_from_excel(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {file_type}")
