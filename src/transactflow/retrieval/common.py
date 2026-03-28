import os
from collections import namedtuple
from datetime import datetime
from typing import Any, Callable, Optional, TextIO
from tzlocal import get_localzone

def writeLocalTimeString(filePath: str, time: Optional[datetime] = None):
    with open(filePath, "w") as f:
        if time is None: time = datetime.now(get_localzone())
        f.write(time.isoformat())

def shiftCombinedForNewMerge(baseDir, ext):
    """
    Shift existing "combined.{ext}" files by one to make space
    for new combined file. Assume the 1st, 2nd and 3nd latest
    files named "combined.{ext}", "combined_prev.{ext}" and
    "combined_prev_prev.{ext}".
    
    Return path to "combined_prev.csv" which is the lastest
    before this retrieval, or None if nothing exists.
    """
    combinedPrevPrev = os.path.join(baseDir, f"combined_prev_prev.{ext}")
    if os.path.exists(combinedPrevPrev):
        os.remove(combinedPrevPrev)
    combinedPrev = os.path.join(baseDir, f"combined_prev.{ext}")
    if os.path.exists(combinedPrev):
        os.rename(combinedPrev, combinedPrevPrev)
    combined = os.path.join(baseDir, f"combined.{ext}")
    if os.path.exists(combined):
        os.rename(combined, combinedPrev)
        return combinedPrev
    return None

LineWithContext = namedtuple("LineWithContext", ["line", "lineBefore", "lineAfter"])

def readFileWithContext(file):
    lines = [None, None, None] # prev, this, next
    def rotate():
        lines[0] = lines[1]
        lines[1] = lines[2]
        lines[2] = None
    for line in file:
        rotate()
        lines[2] = line
        prev, this, succ = lines
        if this is not None:
            yield LineWithContext(line=this, lineBefore=prev, lineAfter=succ)
    rotate()
    prev, this, succ = lines
    if this is not None:
        yield LineWithContext(line=this, lineBefore=prev, lineAfter=succ)

def consumeUntil(pred, iterator):
    consumed = []
    consumedAll = True
    for elem in iterator:
        consumed.append(elem)
        if pred(elem):
            consumedAll = False
            break
    return consumed, consumedAll

class CannotFindAlignmentError(BaseException): pass
class InconsistentLinesError(BaseException): pass

def prependWithAlignment(
        fromFilePath: str,
        toFilePath: str,
        canUseAsAlignment: Callable[[LineWithContext], bool],
        outFilePath: Optional[str] = None,
        encoding: str = "shift_jis"
):
    """
    Aligns the lines of both files by `canUseAsAlignment`, then prepend all extra
    lines from `fromFilePath` to `toFilePath`, result is saved to `outFilePath`
    which defaults to `toFilePath`.

    `canUseAsAlignment` returns true for the line where both files should align
    at, the first match in `toFilePath` will be used for the alignment, lines in
    `fromFilePath` is then checked with `canUseAsAlignment` condition in addition
    to equality with the line content chosen in `toFilePath`.

    The intended use is that the line where this condition holds should be
    unique for both files, so that it is impossible to have more than one way
    to prepend.

    Also verifies consistency between files for lines before alignment.
    """
    with open(toFilePath, "r", encoding=encoding) as toFile:
        toFileIterator = readFileWithContext(toFile)
        res = consumeUntil(canUseAsAlignment, toFileIterator)
    toUntilAlignment, toNotFound = res
    if toNotFound: raise CannotFindAlignmentError()
    alignmentLine = toUntilAlignment[-1].line
    def isAlignment(lc):
        return canUseAsAlignment(lc) and lc.line == alignmentLine
    with open(fromFilePath, "r", encoding=encoding) as fromFile:
        fromFileIterator = readFileWithContext(fromFile)
        toFileIterator = readFileWithContext(toFile)
        res = consumeUntil(isAlignment, fromFileIterator)
        fromUntilAlignment, fromNotFound = res
        if fromNotFound or toNotFound:
            raise CannotFindAlignmentError()
    toPrepend = [e.line for e in fromUntilAlignment]
    notToPrepend = [e.line for e in toUntilAlignment]
    while len(notToPrepend) > 0:
        elem = notToPrepend.pop()
        if toPrepend.pop() != elem:
            raise InconsistentLinesError()
    # toPrepend should now hold only the lines to prepend
    with open(toFilePath, "r", encoding=encoding) as toFile:
        originalLines = toFile.readlines()
    if outFilePath is None: outFilePath = toFilePath
    with open(outFilePath, "w", encoding=encoding) as outFile:
        outFile.writelines(toPrepend)
        outFile.writelines(originalLines)

def forEachFileToReadFrom(
    dir: str,
    isCompleteSection: Callable[[str], bool],
    isIncompleteSection: Callable[[str], bool],
    sortingKeyFn,
    id: Callable[[str], str],
    runFn: Callable[[str, bool], None]
):
    files = { os.path.splitext(path)[0]: path for path in os.listdir(dir) }
    incompleteRecords = {
        name: path for name, path in files.items()
        if isIncompleteSection(name)
    }
    completeRecords = {
        name: path for name, path in files.items()
        if isCompleteSection(name)
    }
    completeIdSet = { id(k) for k in completeRecords.keys() }
    allRecords = { k: v for k, v in completeRecords.items() }
    for k, v in incompleteRecords.items():
        if id(k) in completeIdSet: continue
        allRecords[k] = v
    sortedNames = sorted(allRecords.keys(), key=sortingKeyFn)
    for name in sortedNames:
        readFrom = None
        incomplete = False
        if name in completeRecords:
            readFrom = completeRecords[name]
        elif name in incompleteRecords:
            readFrom = incompleteRecords[name]
            incomplete = True
        assert(readFrom is not None)
        runFn(readFrom, incomplete)
