import csv
from datetime import datetime
from .common import writeLocalTimeString
import xlrd
import openpyxl
import openpyxl.worksheet.worksheet
import os
from typing import List, Tuple

AMEX_DATA_DIR = "./data/rawTransactions/amex-jp"
AMEX_DATA_YEARS_DIR = "./data/rawTransactions/amex-jp/years"
AMEX_DATA_CONVERTED_DIR = "./data/rawTransactions/amex-jp/converted_years"
AMEX_DATA_TIMESTAMP_PATH = "./data/rawTransactions/amex-jp/last_update_time"

def moveFileForYearIntoDataDir(filePath: str, name: str):
    moveToPath = os.path.join(AMEX_DATA_YEARS_DIR, f"{name}.xlsx")
    if os.path.exists(moveToPath): os.remove(moveToPath)
    os.rename(filePath, moveToPath)

def convertYearsXLSToCSV():
    # Remove existing converted files.
    for filename in os.listdir(AMEX_DATA_CONVERTED_DIR):
        os.remove(os.path.join(AMEX_DATA_CONVERTED_DIR, filename))

    for nameWithExt in os.listdir(AMEX_DATA_YEARS_DIR):
        name, ext = os.path.splitext(nameWithExt)
        filePath = os.path.join(AMEX_DATA_YEARS_DIR, nameWithExt)
        def applyLineBreakEscape(s: str) -> str: return s.replace("\n", "\\n")
        if ext == ".xls":
            workbook = xlrd.open_workbook(filePath)
            assert(workbook.sheet_names()[0] =="ご利用金額")
            sheet = workbook.sheet_by_index(0)
            cellValues = [
                [applyLineBreakEscape(s) for s in sheet.row_values(r)]
                for r in range(sheet.nrows)
            ]
        elif ext == ".xlsx":
            workbook = openpyxl.load_workbook(filename=filePath, read_only=True)
            assert(workbook.sheetnames[0] == "ご利用履歴")
            sheet = workbook.worksheets[0]
            cellValues = [
                [applyLineBreakEscape("" if item is None else str(item)) for item in row]
                for row in sheet.iter_rows(values_only=True)
            ]
        else:
            print(f"[FileMerge/AMEX JP] Skipping {nameWithExt} under sheets directory")
            continue
        # There seems to be no indication of completeness in the file itself.
        currentYear = 2026
        yearComplete = int(name) < currentYear
        # Remember to update `yearComplete` when the current year changes.
        assert(datetime.now().year == currentYear)
        outputName = f"{name}.csv" if yearComplete else f"{name}_incomplete.csv"
        with open(os.path.join(AMEX_DATA_CONVERTED_DIR, outputName), "w") as outFile:
            csvWriter = csv.writer(outFile)
            for row in cellValues: csvWriter.writerow(row)

def updateFilesWithDownloadedXLSX(filePath: str, name: str):
    moveFileForYearIntoDataDir(filePath, name)
    convertYearsXLSToCSV()
    writeLocalTimeString(AMEX_DATA_TIMESTAMP_PATH)
