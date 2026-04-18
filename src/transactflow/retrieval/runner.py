from datetime import datetime
from enum import Enum
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.common.exceptions import ElementNotInteractableException, NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support.expected_conditions import element_to_be_clickable, presence_of_element_located
from selenium.common.exceptions import TimeoutException
from webdriver_manager.firefox import GeckoDriverManager
from typing import TYPE_CHECKING, Awaitable, TypeVar, Callable, Union
import asyncio
import random
import subprocess
import time
import pickle
import csv
import nodriver as uc

from . import amex, prestia, suica, smbcCard
from .config import (
    AmexRetrievalConfig,
    Browser,
    PrestiaRetrievalConfig,
    RetrievalConfig,
    SmbcCardRetrievalConfig,
    SuicaRetrievalConfig,
)

AMEX_DOWNLOAD_FILE_NAME = "Activity.xlsx"
PRESTIA_COOKIE_KEY = "Prestia"
SMBC_CREDIT_COOKIE_KEY = "SMBC-Credit"
AMEX_JP_COOKIE_KEY = "AMEX-JP"
SUICA_COOKIE_KEY = "Suica"

# TODO: Replace with a more secure storage e.g. OS keychain.
def readCredential(dir: Path, fileName: str):
    path = dir / fileName
    completedProcess = subprocess.run(["cat", str(path)], capture_output=True)
    return completedProcess.stdout.decode("utf-8")

def findElementDeuggable(
    browser: Union[RemoteWebDriver, WebElement], by: str, value: str,
    timeout: float = 5.0,
) -> WebElement:
    valueToTry = value
    while True:
        try:
            return WebDriverWait(browser, timeout=timeout).until(
                presence_of_element_located((by, valueToTry)))
        except TimeoutException:
            print(f"Element not found within {timeout}s for {by}={valueToTry!r}.")
            breakpoint()
            valueToTry = input("Try a different locator value: ")

def getAbsoluteXpath(element: WebElement) -> str:
    """Return a fully-indexed absolute XPath of `element` (e.g. `/html[1]/body[1]/div[2]/a[1]`)."""
    script = """
    const el = arguments[0];
    if (!el || el.nodeType !== 1) return '';
    const parts = [];
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentNode) {
        let i = 1;
        for (let sib = cur.previousSibling; sib; sib = sib.previousSibling) {
            if (sib.nodeType === 1 && sib.nodeName === cur.nodeName) i++;
        }
        parts.unshift(cur.nodeName.toLowerCase() + '[' + i + ']');
    }
    return '/' + parts.join('/');
    """
    return element.parent.execute_script(script, element)

def clickDeuggable(element: WebElement, timeout: float = 5.0):
    print(f"Clicking: {getAbsoluteXpath(element)}")
    try:
        WebDriverWait(element.parent, timeout=timeout).until(
            element_to_be_clickable(element))
    except TimeoutException:
        print(f"Element did not become clickable within {timeout}s. "
              "Resolve the page state in the browser, then continue (c) to retry.")
        breakpoint()
    try:
        element.click()
    except ElementNotInteractableException:
        print("Got ElementNotInteractableException on click. "
              "Resolve the page state in the browser, then continue (c) to retry.")
        breakpoint()
        element.click()

def find_element_by_any_xpath(browser: RemoteWebDriver, paths):
    lastException = NoSuchElementException()
    for path in paths:
        try:
            elem = browser.find_element(By.XPATH, path)
            return elem
        except NoSuchElementException as e:
            lastException = e
    raise lastException

def first_matching_for_xpath(browser: RemoteWebDriver, path, matchingFn):
    elems = browser.find_elements(By.XPATH, path)
    for elem in elems:
        if matchingFn(elem): return elem
    raise NoSuchElementException()

T = TypeVar("T")
def retryUntilNotNoneAndSatisfying(
    attemptFunc: Callable[[], T], condition, maxRetry, interval) -> T:
    def shouldRetry(elem):
        if elem is None: return True
        return not condition(elem)
    for _ in range(maxRetry):
        result = attemptFunc()
        if shouldRetry(result):
            time.sleep(interval)
            continue
        else: return result
    breakpoint()
    raise Exception()

def findElementOrNone(browser: Union[RemoteWebDriver, WebElement], by=By.ID, value=None):
    try:
        element = browser.find_element(by, value)
        return element
    except NoSuchElementException:
        return None

class CookieManager:
    def __init__(self, browser: RemoteWebDriver, cookiesPath: Path):
        self.browser = browser
        self.cookiesPath = cookiesPath
        self.cookies = None
    def loadCookies(self):
        if self.cookiesPath.exists():
            with open(self.cookiesPath, "rb") as f:
                self.cookies = pickle.load(f)
        else: self.cookies = {}
        for key, url in [
            (PRESTIA_COOKIE_KEY, "https://login.smbctb.co.jp"),
            (SMBC_CREDIT_COOKIE_KEY, "https://www.smbc-card.com/"),
            (SUICA_COOKIE_KEY, "https://www.mobilesuica.com"),
            (AMEX_JP_COOKIE_KEY, "https://www.americanexpress.com")
        ]:
            if key in self.cookies:
                self.browser.get(url)
                for cookie in self.cookies[key]:
                    try: self.browser.add_cookie(cookie)
                    except Exception as e: print(f"Error while adding cookie: {e}")

    def saveCookiesWithCurrentSession(self, sessionCookieKey: str):
        assert(self.cookies is not None)
        self.cookies[sessionCookieKey] = self.browser.get_cookies()
        with open(self.cookiesPath, "wb") as f:
            pickle.dump(self.cookies, f)

class SeleniumHandle:
    def __init__(self, makeBrowser, cookiesPath: Path):
        self.makeBrowser = makeBrowser
        self.cookiesPath = cookiesPath
        self.browser = None
    def __enter__(self):
        self.browser = self.makeBrowser()
        return self.browser, CookieManager(self.browser, self.cookiesPath)
    def __exit__(self, type, value, traceback):
        if self.browser: self.browser.quit()

def useNoDriver(
    userDataDir: Path,
    downloadDir: Path,
    useBrowser: Callable[["uc.Browser"], Awaitable[None]],
):
    userDataDir.mkdir(parents=True, exist_ok=True)

    async def inner():
        browser = await uc.start(
            user_data_dir=str(userDataDir),
            headless=False,
            lang="ja-JP",
        )
        try:
            await browser.main_tab.set_download_path(downloadDir)
            await useBrowser(browser)
        finally:
            browser.stop()
    asyncio.run(inner())

def busyWaitForAnyFile(paths: list[Path], verbose=True) -> Path:
    if verbose: print(f"Waiting for file(s) to exist: {paths}")
    try:
        firstExisting = next(p for p in paths if p.exists())
        return firstExisting
    except StopIteration:
        time.sleep(1.0)
        return busyWaitForAnyFile(paths, verbose=False)

def makeStockChromeBrowser(executable_path: str):
    return webdriver.Chrome(
        service=ChromeService(
            executable_path=executable_path
        )
    ) # type: ignore

def makeUCChromeBrowser(downloadDir: Path):
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": str(downloadDir)
    })
    options.add_argument("--lang=ja")
    options.__dict__["headless"] = False # type: ignore
    browser = uc.Chrome(options=options)
    return browser

def makeFirefoxBrowser(downloadDir: Path):
    options = FirefoxOptions()
    options.set_preference("intl.accept_languages", "ja-jp,ja")
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", str(downloadDir))
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "*/*, text/*");

    service = FirefoxService(executable_path=GeckoDriverManager().install())
    print(f"Service path: {service.path}")

    browser = webdriver.Firefox(service=service, options=options) # type: ignore
    return browser

def downloadPrestiaLast180Days(
    browser: RemoteWebDriver,
    cookieManager: CookieManager,
    credentialsDir: Path,
    downloadDir: Path,
    prestiaConfig: PrestiaRetrievalConfig,
    merge=False
):
    userId = prestiaConfig.userId
    browser.get("https://login.smbctb.co.jp/ib/portal/POSNIN1prestiatop.prst?LOCALE=ja_JP")
    transTabXpath = '//*[@id="header-nav-label-0"]'
    if findElementOrNone(browser, By.XPATH, transTabXpath) is None:
        # Sign in page.
        heading = findElementDeuggable(browser, By.XPATH, "//div[@class='layout-table']/section/div[@class='heading']")
        assert("サインオン" in heading.text)

        idField = findElementDeuggable(browser, By.XPATH, '//*[@id="dispuserId"]')
        idField.send_keys(userId)
        pwField = findElementDeuggable(browser, By.XPATH, '//*[@id="disppassword"]')
        pwField.send_keys(readCredential(credentialsDir, "prestia"))
        submitButton = findElementDeuggable(browser, By.XPATH, "//div[@class='layout-table']/section//div[@class='btn-area']/a")
        assert("サインオン" in submitButton.text)
        submitButton.click()

    cookieManager.saveCookiesWithCurrentSession(PRESTIA_COOKIE_KEY)

    # Account landing page.
    transTab = findElementDeuggable(browser, By.XPATH, transTabXpath)
    assert("取引明細" in transTab.text)
    transTab.click()

    transDownloadPageLink = findElementDeuggable(browser, By.XPATH, "//*[@id='header-nav-menu-0']/li/a[contains(., '取引履歴ダウンロード')]")
    hrefText = transDownloadPageLink.get_attribute("href")
    assert(hrefText is not None and "accountinfotorihikidownload" in hrefText)
    clickDeuggable(transDownloadPageLink)

    # Transaction history download page.
    last180DaysRadioButton = findElementDeuggable(browser, By.XPATH, "/html/body/form[2]/main/div/section/div[2]/div[1]/table[1]/tbody/tr/td/fieldset[1]/label[3]/span")
    assert("直近180日間" in last180DaysRadioButton.text)
    last180DaysRadioButton.click()

    rows = browser.find_elements(By.XPATH, "//main//section[@class='account']//table[1]/tbody/tr")
    yenSavingsRow = None
    for row in rows:
        accountName = findElementDeuggable(row, By.XPATH, "./td[1]")
        if "プレスティア マルチマネー口座円普通預金" in accountName.text:
            continue
        if "円普通預金" in accountName.text:
            yenSavingsRow = row
            break
    assert(yenSavingsRow is not None)
    downloadButton = findElementDeuggable(yenSavingsRow, By.XPATH, "./td[5]")
    assert("ダウンロードする" in downloadButton.text)
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", downloadButton)
    time.sleep(3)
    downloadButton.click()

    downloadedFilePath = downloadDir / prestiaConfig.expectDownloadedFilename
    busyWaitForAnyFile([downloadedFilePath])
    if merge: prestia.updateFilesWithNewOriginalFile(downloadedFilePath, prestiaConfig)

def downloadSMBCCreditCSV(
    browser: RemoteWebDriver,
    cookieManager: CookieManager,
    downloadDir: Path,
    credentialsDir: Path,
    smbcCardConfig: SmbcCardRetrievalConfig,
):
    userId = smbcCardConfig.userId
    # Sign in page.
    print("Loading smbc-card page, please clear cookie if the puzzle section never loads")
    browser.get("https://www.smbc-card.com/mem/index.jsp")

    idField = findElementDeuggable(browser, By.XPATH, "//form[@method='post']/div[@id='input_id']/input")
    idField.send_keys(userId)
    pwField = findElementDeuggable(browser, By.XPATH, "//form[@method='post']/div[@id='input_password']/input")
    pwField.send_keys(readCredential(credentialsDir, "smbc-card"))
    try:
        browser.find_elements(By.XPATH, "//div[@id='QqCmsEKCcaptcha']")
        input("Please finish the puzzle and click on log in button, press enter when the next page loads...")
    except NoSuchElementException:
        submitButton = findElementDeuggable(browser, By.XPATH, "/html/body/div[2]/div/div[4]/div/div/section[1]/div[1]/form/div[2]/input")
        valueText = submitButton.get_attribute("value")
        assert(valueText is not None and "ログイン" in valueText)
        submitButton.click()

    cookieManager.saveCookiesWithCurrentSession(SMBC_CREDIT_COOKIE_KEY)

    # Account landing page.
    # Now jump to the transactions page
    transHistoryXpath = "//div[@class='head']//ul[@class='megaMenu']/li[1]/div[2]/div[2]/div[1]/div/ul/li[2]/a/div"
    _ = retryUntilNotNoneAndSatisfying(
        attemptFunc=lambda: findElementOrNone(browser, By.XPATH, transHistoryXpath),
        condition=lambda e: "お支払い金額照会" in e.get_attribute("innerHTML"),
        maxRetry=60, interval=1) # Cannot click on the link, error: could not be scrolled into view
    browser.get("https://www.smbc-card.com/memx/web_meisai/top/index.html")

    # Transactions history page.
    monthSelectionXpath = '//div[@id="contents"]//form//select'
    def isMonthSelectionElem(elem):
        monthSelection = Select(elem)
        if "お選びください" not in monthSelection.options[0].text: return False
        if len(monthSelection.options) < 4: return False
        return True
    monthSelectionElem = retryUntilNotNoneAndSatisfying(
        attemptFunc=lambda: findElementOrNone(browser, By.XPATH, monthSelectionXpath),
        condition=isMonthSelectionElem, maxRetry=10, interval=3)
    assert(monthSelectionElem is not None)
    monthSelection = Select(monthSelectionElem)
    options = monthSelection.options
    values = [m.get_attribute("value") for m in options[1:1+smbcCardConfig.forLastNMonths]]
    values = [v for v in values if v is not None]
    for value in values:
        # For some reason trying to select with monthSelection may cause an error,
        # I don't have any patience left dealing with crappy bank website, so let's
        # just retry until it works.
        itWorked = False
        while not itWorked:
            try:
                monthSelection = Select(browser.find_element(By.XPATH, monthSelectionXpath))
                monthSelection.select_by_value(value)
                itWorked = True
            except Exception as e:
                print(f"Getting this exception for some reason: {e}")
                print(f"Sleep 0.5s and try again...")
                time.sleep(0.5)

        displayButtonXpath = '//div[@id="contents"]//form//input[@value="照会"]'
        displayButton = findElementDeuggable(browser, By.XPATH, displayButtonXpath)
        valueText = displayButton.get_attribute("value")
        assert(valueText is not None and "照会" in valueText)
        displayButton.click()
        # Page loading seems to be unknown by the browser (because the world always
        # want more Javascript controlled logic to make things more confusing), the
        # lazy solution here is just to wait (and hope loading is complete after the
        # wait).
        time.sleep(2)

        monthSelection = Select(findElementDeuggable(browser, By.XPATH, monthSelectionXpath))

        try:
            print(f"Try to download for {value}")
            isCSVDownloadButton = lambda e: (("CSV形式で保存する" in e.text) or ("Save in CSV format" in e.text))
            downloadButton = first_matching_for_xpath(browser, "//div/a|//div/p/a", isCSVDownloadButton)
            try:
                WebDriverWait(browser, timeout=5).until(element_to_be_clickable(downloadButton))
            except TimeoutException as e:
                print(f"Timeout excpetion waiting for button to be clickable: {e}")
                breakpoint()
            assert(("CSV形式で保存する" in downloadButton.text) or ("Save in CSV format" in downloadButton.text))
            downloadButton.click()
            downloadFilePaths = [downloadDir / f"{value}.csv"]
            # Sometimes, even for incomplete month, the download file name is the same
            # as complete month, therefore need to check this as well.
            # Incomplete month has 7 digits in selection menu (e.g 2020031).
            isIncompleteMonth = len(value) == 7
            if isIncompleteMonth:
                altFilename = value[:-1]
                downloadFilePaths.append(downloadDir / f"{altFilename}.csv")
            downloadedPath = busyWaitForAnyFile(downloadFilePaths)
            smbcCard.moveFileForMonthIntoDataDir(downloadedPath, value, smbcCardConfig)
        except NoSuchElementException:
            print(f"Skipping {value} because download button cannot be found (no transactions?)")

def downloadMobileSuicaAsTSV(
    browser: RemoteWebDriver,
    cookieManager: CookieManager,
    downloadDir: Path,
    credentialsDir: Path,
    suicaConfig: SuicaRetrievalConfig,
    merge=False
):
    email = suicaConfig.email

    browser.get("https://www.mobilesuica.com/")
    historyXpath = '//div[@id="btn_sfHistory"]'
    historyLink = findElementOrNone(browser, By.XPATH, historyXpath)
    # Check if sign in process is skipped.
    if historyLink is None:
        # Sign in page.
        idField = findElementDeuggable(browser, By.XPATH, '//input[@name="MailAddress"]')

        idField.send_keys(email)
        pwField = findElementDeuggable(browser, By.XPATH, '//input[@name="Password"]')
        pwField.send_keys(readCredential(credentialsDir, "suica"))
        captchaResult = input("Please enter CAPTCHA result: ")
        captchaField = findElementDeuggable(browser, By.XPATH, '//input[@id="WebCaptcha1__editor"]')
        altText = captchaField.get_attribute("alt")
        assert(altText is not None and "表示されている文字の入力" in altText)
        captchaField.send_keys(captchaResult)
        loginButton = findElementDeuggable(browser, By.XPATH, '//button[@name="LOGIN"]')
        loginButton.click()

        # Account landing page.
        historyLink = findElementDeuggable(browser, By.XPATH, historyXpath)

    cookieManager.saveCookiesWithCurrentSession(SUICA_COOKIE_KEY)

    # Account landing page.
    historyLink.click()

    # Transaction history page.
    tableXpath = '/html/body/form/table[4]/tbody/tr/td/table/tbody/tr[2]/td[2]/table[5]/tbody/tr[2]/td/table/tbody'
    table = findElementDeuggable(browser, By.XPATH, tableXpath)
    rows = table.find_elements(By.XPATH, "./tr")[1:]
    def parseRow(row):
        cols = row.find_elements(By.XPATH, "./td")
        return [c.text for c in cols]
    parsedTable = [parseRow(r) for r in rows]
    newSectionPath = downloadDir / "suica_new.tsv"
    with open(newSectionPath, "w") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerows(parsedTable)
    if merge: suica.updateFilesWithNewOriginalFile(newSectionPath, suicaConfig)

async def randomSleep(minSeconds: float, maxSeconds: float):
    await asyncio.sleep(random.uniform(minSeconds, maxSeconds))


class AMEXRegion(Enum):
    JP = "JP"
    US = "US"


async def downloadAMEX2026XLS(
    browser: "uc.Browser",
    downloadDir: Path,
    credentialsDir: Path,
    amexConfig: AmexRetrievalConfig,
    region: AMEXRegion,
):
    userId = amexConfig.userId
    year2026 = datetime.now().year
    if year2026 != 2026:
        # Need to support multi year, or do it manually by downloading the 2026 full record into
        # the data directory, and update the code to read and save 2027 data.
        assert(False)

    def loginURL():
        match region:
            case AMEXRegion.JP:
                return "https://www.americanexpress.com/ja-jp/account/login"
            case AMEXRegion.US:
                return "https://www.americanexpress.com/en-us/account/login"

    # Sign in page. nodriver's `send_keys` dispatches real CDP key events one at a time,
    # which avoids the one-shot DOM value assignment that bot detectors flag.
    tab = await browser.get(loginURL())
    await randomSleep(1.5, 3.0)

    userField = await tab.select("#eliloUserID")
    await userField.send_keys(userId)
    await randomSleep(0.4, 1.0)

    passField = await tab.select("#eliloPassword")
    match region:
        case AMEXRegion.JP:
            await passField.send_keys(readCredential(credentialsDir, "amex-jp"))
        case AMEXRegion.US:
            await passField.send_keys(readCredential(credentialsDir, "amex-us"))
    await randomSleep(0.6, 1.4)

    submitButton = await tab.select("#loginSubmit")
    await submitButton.click()

    # Verification page
    verificationHeading = None
    match region:
        case AMEXRegion.JP:
            verificationHeading = await tab.xpath(
                '//h2[normalize-space()="カード情報の認証:認証コード"]', timeout=10)
        case AMEXRegion.US:
            verificationHeading = await tab.xpath(
                '//h1[normalize-space()="Verify your identity"]', timeout=10)
    if verificationHeading:
        input("Please finish verification and proceed, press enter when the dashboard page loads...")

    # Dashboard page
    await randomSleep(1.0, 2.0)
    popupCloseButtons = await tab.xpath(
        '//div[contains(@aria-label, "ポップアップ")]//button[@aria-label="閉じる"]')
    if popupCloseButtons and popupCloseButtons[0] is not None:
        await popupCloseButtons[0].click()
        await randomSleep(0.4, 0.9)

    match region:
        case AMEXRegion.JP:
            usageButton = await tab.select('button[title="ご利用状況"]')
            await usageButton.click()
            await randomSleep(0.8, 1.6)
            historyLink = await tab.select('a[title="ご利用履歴"]')
            await historyLink.click()
        case AMEXRegion.US:
            historyLink = await tab.select('a[title="Statements & Activity"]')
            await historyLink.click()


    # History page
    match region:
        case AMEXRegion.JP:
            await randomSleep(3.0, 5.0)
            viewByYearsButton = await tab.select(
                '[data-module-name="axp-activity-navigation/Navigation"] button[title="年ごとに見る"]')
            await viewByYearsButton.click()
            await randomSleep(0.8, 1.5)
            thisYearOption = await tab.select(
                f'[data-module-name="axp-activity-navigation/Navigation"] a[title="{year2026}"]')
            await thisYearOption.click()

            await randomSleep(0.6, 1.2)
            downloadIcon = await tab.select("#action-icon-dls-icon-download-")
            await downloadIcon.click()

            await randomSleep(0.4, 0.9)
            excelOption = await tab.select(
                'label[for="axp-activity-download-body-selection-options-type_excel"]')
            await excelOption.click()

            await randomSleep(0.4, 0.9)
            downloadButton = await tab.select('button[title="ダウンロード"]')
            await downloadButton.click()
        case AMEXRegion.US:
            await randomSleep(3.0, 5.0)
            last30DaysSpans = await tab.xpath(
                '//span[normalize-space()="Last 30 Days"]', timeout=10)
            last30DaysSpan = last30DaysSpans[0]
            assert last30DaysSpan is not None
            await last30DaysSpan.click()
            await randomSleep(0.8, 1.5)

            yearToDateOptions = await tab.xpath(
                f'//div[normalize-space()="{year2026} Year To Date"]', timeout=10)
            yearToDateOption = yearToDateOptions[0]
            assert yearToDateOption is not None
            await yearToDateOption.click()
            await randomSleep(0.6, 1.2)

            downloadButton = await tab.select('button[title="Download"]')
            assert downloadButton is not None
            await downloadButton.click()
            await randomSleep(0.4, 0.9)

            excelLabels = await tab.xpath(
                '//label[contains(normalize-space(), "Excel")]', timeout=10)
            excelLabel = excelLabels[0]
            assert excelLabel is not None
            await excelLabel.click()
            await randomSleep(0.4, 0.9)

            excelDownloadButton = await tab.select(
                'button[title="Download"][element="excel"]')
            assert excelDownloadButton is not None
            await excelDownloadButton.click()

    downloadedFilePath = downloadDir / AMEX_DOWNLOAD_FILE_NAME
    busyWaitForAnyFile([downloadedFilePath])
    amex.updateFilesWithDownloadedXLSX(downloadedFilePath, f"{year2026}", amexConfig)


def makeBrowserFactory(config: RetrievalConfig) -> Callable[[], RemoteWebDriver]:
    match config.browser:
        case Browser.UC_CHROME:
            return lambda: makeUCChromeBrowser(config.downloadDir)
        case Browser.FIREFOX:
            return lambda: makeFirefoxBrowser(config.downloadDir)
        case Browser.STOCK_CHROME:
            assert(config.chromeDriverPath is not None)
            executablePath = str(config.chromeDriverPath)
            return lambda: makeStockChromeBrowser(executablePath)


def run(config: RetrievalConfig):
    downloadDir = config.downloadDir
    credentialsDir = config.credentialsDir

    assert(downloadDir.exists())
    for child in downloadDir.iterdir():
        child.unlink()

    if (amexJpConfig := config.amexJp) is not None:
        useNoDriver(
            amexJpConfig.userDataDir,
            downloadDir,
            lambda browser: downloadAMEX2026XLS(
                browser, downloadDir, credentialsDir, amexJpConfig, AMEXRegion.JP),
        )

    if (amexUsConfig := config.amexUs) is not None:
        useNoDriver(
            amexUsConfig.userDataDir,
            downloadDir,
            lambda browser: downloadAMEX2026XLS(
                browser, downloadDir, credentialsDir, amexUsConfig, AMEXRegion.US),
        )

    with SeleniumHandle(
        makeBrowserFactory(config),
        config.cookiesPath,
    ) as (browser, cookieManager):
        cookieManager.loadCookies()
        # if config.suica is not None:
        #     downloadMobileSuicaAsTSV(
        #         browser, cookieManager, downloadDir, credentialsDir,
        #         config.suica, merge=True)
        # if config.smbcCard is not None:
        #     downloadSMBCCreditCSV(
        #         browser, cookieManager, downloadDir, credentialsDir,
        #         config.smbcCard)
        if (prestiaConfig := config.prestia) is not None:
            downloadPrestiaLast180Days(
                browser,
                cookieManager,
                credentialsDir,
                downloadDir,
                prestiaConfig,
                merge=True,
            )
        input("Finished. Press enter to close browser.")
