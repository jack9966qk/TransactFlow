from datetime import datetime

# from importers.equity import EquityItem
import patchright.sync_api
from patchright.sync_api import sync_playwright
from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support.expected_conditions import element_to_be_clickable
from selenium.common.exceptions import TimeoutException
from webdriver_manager.firefox import GeckoDriverManager
from typing import TypeVar, Callable, Union
import os
import subprocess
import time
import pickle
import csv

from . import prestia, amexJp, suica, smbcCard

AMEX_DOWNLOAD_FILE_NAME = "Activity.xlsx"
PRESTIA_COOKIE_KEY = "Prestia"
SMBC_CREDIT_COOKIE_KEY = "SMBC-Credit"
AMEX_JP_COOKIE_KEY = "AMEX-JP"
SUICA_COOKIE_KEY = "Suica"
COOKIES_PATH = "cookies.pkl"

# TODO: Replace with a more secure storage e.g. OS keychain.
def readCredential(dir: str, fileName: str):
    path = os.path.join(dir, fileName)
    completedProcess = subprocess.run(["cat", path], capture_output=True)
    return completedProcess.stdout.decode("utf-8")

def findElementDeuggable(browser: Union[RemoteWebDriver, WebElement], by=By.ID, value=None) -> WebElement:
    valueToTry = value
    while True:
        try:
            element = browser.find_element(by, valueToTry)
            return element
        except NoSuchElementException:
            breakpoint()
            valueToTry = input("Try a different locator value: ")

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
    def __init__(self, browser: RemoteWebDriver):
        self.browser = browser
        self.cookies = None
    def loadCookies(self):
        if os.path.exists(COOKIES_PATH):
            with open(COOKIES_PATH, "rb") as f:
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
        with open(COOKIES_PATH, "wb") as f:
            pickle.dump(self.cookies, f)

class SeleniumHandle:
    def __init__(self, makeBrowser):
        self.makeBrowser = makeBrowser
        self.browser = None
    def __enter__(self):
        self.browser = self.makeBrowser()
        return self.browser, CookieManager(self.browser)
    def __exit__(self, type, value, traceback):
        if self.browser: self.browser.quit()

def usePlaywright(usePage: Callable[[patchright.sync_api.Page], None]):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            usePage(page)
        except patchright.sync_api.TimeoutError as e:
            print(e)
            breakpoint()

def busyWaitForAnyFile(paths, verbose=True):
    if verbose: print(f"Waiting for file(s) to exist: {paths}")
    try:
        firstExisting = next(p for p in paths if os.path.exists(p))
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

def makeUCChromeBrowser(downloadDirAbsolute: str):
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": downloadDirAbsolute
    })
    options.add_argument("--lang=ja")
    options.__dict__["headless"] = False # type: ignore
    # options.add_argument(f"--download.default_directory={DOWNLOAD_DIR_FULL}")
    browser = uc.Chrome(options=options)
    return browser

def makeFirefoxBrowser(downloadDirAbsolute: str):
    # Disabled as browser.helperApps.neverAsk.SaveToDisk does not seem to work.
    # Set profile to set file save location and skip the save dialog from Firefox.
    # profile = webdriver.FirefoxProfile()
    # downloadFileTypes = ["text/csv", "text/plain", "application/force-download"]
    # # downloadFileTypes = ["*/*"]
    # profile.set_preference("browser.helperApps.neverAsk.SaveToDisk", ", ".join(downloadFileTypes))
    # profile.set_preference("browser.download.manager.showWhenStarting", False)
    # USER_DEFINED_LOCATION = 2
    # profile.set_preference("browser.download.folderList", USER_DEFINED_LOCATION)
    # currentDir = os.getcwd()
    # profile.set_preference("browser.download.dir", currentDir)

    # Use existing profile:
    # profile = webdriver.FirefoxProfile("/Users/[username]/Library/Application Support/Firefox/Profiles/[profile].Test")
    # profile.set_preference('intl.accept_languages', 'ja')

    options = FirefoxOptions()
    options.set_preference("intl.accept_languages", "ja-jp,ja")
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", downloadDirAbsolute)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "*/*, text/*");

    service = FirefoxService(executable_path=GeckoDriverManager().install())
    print(f"Service path: {service.path}")

    browser = webdriver.Firefox(service=service, options=options) # type: ignore
    # browser = webdriver.Firefox(firefox_profile=profile)
    # # Or not to specify it:
    # browser = webdriver.Firefox()
    return browser

def downloadPrestiaLast180Days(
    browser: RemoteWebDriver,
    cookieManager: CookieManager,
    credentialsDirAbsolute: str,
    downloadDirAbsolute: str,
    expectDownloadedFilename: str,
    merge=False
):
    userId = os.getenv("PRESTIA_USER_ID")
    assert(userId is not None)
    browser.get("https://login.smbctb.co.jp/ib/portal/POSNIN1prestiatop.prst?LOCALE=ja_JP")
    transTabXpath = '//*[@id="header-nav-label-0"]'
    if findElementOrNone(browser, By.XPATH, transTabXpath) is None:
        # Sign in page.
        heading = findElementDeuggable(browser, By.XPATH, "//div[@class='layout-table']/section/div[@class='heading']")
        assert("サインオン" in heading.text)

        idField = findElementDeuggable(browser, By.XPATH, '//*[@id="dispuserId"]')
        idField.send_keys(userId)
        pwField = findElementDeuggable(browser, By.XPATH, '//*[@id="disppassword"]')
        pwField.send_keys(readCredential(credentialsDirAbsolute, "prestia"))
        submitButton = findElementDeuggable(browser, By.XPATH, "//div[@class='layout-table']/section//div[@class='btn-area']/a")
        assert("サインオン" in submitButton.text)
        submitButton.click()

    cookieManager.saveCookiesWithCurrentSession(PRESTIA_COOKIE_KEY)

    # Account landing page.
    transTab = findElementDeuggable(browser, By.XPATH, transTabXpath)
    assert("取引明細" in transTab.text)
    transTab.click()
    transDownloadPageLink = findElementDeuggable(browser, By.XPATH, "/html/body/form[1]/nav/div/ul/li[2]/ul/li[4]/a")
    hrefText = transDownloadPageLink.get_attribute("href")
    assert(hrefText is not None and "accountinfotorihikidownload" in hrefText)
    transDownloadPageLink.click()

    # Transaction history download page.
    last180DaysRadioButton = findElementDeuggable(browser, By.XPATH, "/html/body/form[2]/main/div/section/div[2]/div[1]/table[1]/tbody/tr/td/fieldset[1]/label[3]/span")
    assert("直近180日間" in last180DaysRadioButton.text)
    last180DaysRadioButton.click()
    firstRow = findElementDeuggable(browser, By.XPATH, "/html/body/form[2]/main/div/section/div[2]/section/table/tbody/tr[1]")
    accountName = findElementDeuggable(firstRow, By.XPATH, "./td[1]")
    assert("円普通預金" in accountName.text)
    downloadButton = findElementDeuggable(firstRow, By.XPATH, "./td[5]")
    assert("ダウンロードする" in downloadButton.text)
    downloadButton.click()

    downloadedFilePath = os.path.join(downloadDirAbsolute, expectDownloadedFilename)
    busyWaitForAnyFile([downloadedFilePath])
    if merge: prestia.updateFilesWithNewOriginalFile(downloadedFilePath)

def downloadSMBCCreditCSV(
    browser: RemoteWebDriver,
    cookieManager: CookieManager,
    downloadDirAbsolute: str,
    credentialsDirAbsolute: str,
    forLastNMonths=3
):
    userId = os.getenv("SMBC_CARD_USER_ID")
    assert(userId is not None)
    # Sign in page.
    print("Loading smbc-card page, please clear cookie if the puzzle section never loads")
    browser.get("https://www.smbc-card.com/mem/index.jsp")

    idField = findElementDeuggable(browser, By.XPATH, "//form[@method='post']/div[@id='input_id']/input")
    idField.send_keys(userId)
    pwField = findElementDeuggable(browser, By.XPATH, "//form[@method='post']/div[@id='input_password']/input")
    pwField.send_keys(readCredential(credentialsDirAbsolute, "smbc-card"))
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
    values = [m.get_attribute("value") for m in options[1:1+forLastNMonths]]
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
            # if not downloadButton.is_displayed():
            #     raise NoSuchElementException()
            assert(("CSV形式で保存する" in downloadButton.text) or ("Save in CSV format" in downloadButton.text))
            downloadButton.click()
            downloadFilePaths = [os.path.join(downloadDirAbsolute, f"{value}.csv")]
            # Sometimes, even for incomplete month, the download file name is the same
            # as complete month, therefore need to check this as well.
            # Incomplete month has 7 digits in selection menu (e.g 2020031).
            isIncompleteMonth = len(value) == 7
            if isIncompleteMonth:
                altFilename = value[:-1]
                downloadFilePaths.append(os.path.join(downloadDirAbsolute, f"{altFilename}.csv"))
            downloadedPath = busyWaitForAnyFile(downloadFilePaths)
            smbcCard.moveFileForMonthIntoDataDir(downloadedPath, value)
        except NoSuchElementException:
            print(f"Skipping {value} because download button cannot be found (no transactions?)")

def downloadMobileSuicaAsTSV(
    browser: RemoteWebDriver,
    cookieManager: CookieManager,
    downloadDirAbsolute: str,
    credentialsDirAbsolute: str,
    merge=False
):
    email = os.getenv("MOBILE_SUICA_EMAIL")
    assert(email is not None)

    browser.get("https://www.mobilesuica.com/")
    historyXpath = '//div[@id="btn_sfHistory"]'
    historyLink = findElementOrNone(browser, By.XPATH, historyXpath)
    # Check if sign in process is skipped.
    if historyLink is None:
        # Sign in page.
        idField = findElementDeuggable(browser, By.XPATH, '//input[@name="MailAddress"]')
        
        idField.send_keys(email)
        pwField = findElementDeuggable(browser, By.XPATH, '//input[@name="Password"]')
        pwField.send_keys(readCredential(credentialsDirAbsolute, "suica"))
        # Uncomment below to get the captcha image and present it to the user.
        # captchaImage = browser.find_element(By.XPATH, '//img[@class="igc_TrendyCaptchaImage"]')
        # imageData = captchaImage.screenshot_as_png
        # with open("suica_captcha.png", "wb") as f:
        #     f.write(imageData)
        # subprocess.run("open suica_captcha.png".split())
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
    newSectionPath = os.path.join(downloadDirAbsolute, "suica_new.tsv")
    with open(newSectionPath, "w") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerows(parsedTable)
    if merge: suica.updateFilesWithNewOriginalFile(newSectionPath)

def downloadAMEXJP2026XLS(
    page: patchright.sync_api.Page,
    downloadDirAbsolute: str,
    credentialsDirAbsolute: str,
):
    userId = os.getenv("AMEX_JP_USER_ID")
    assert(userId is not None)
    year2026 = datetime.now().year
    if year2026 != 2026:
        # Need to support multi year, or do it manually by downloading the 2026 full record into
        # the data directory, and update the code to read and save 2027 data.
        assert(False)

    # Sign in page
    page.goto("https://www.americanexpress.com/ja-jp/account/login")
    page.fill("xpath=//input[@id='eliloUserID']", userId)
    page.fill("xpath=//input[@id='eliloPassword']", readCredential(credentialsDirAbsolute, "amex-jp"))
    page.click("xpath=//button[@id='loginSubmit']")

    verificationHeadingLocator = 'xpath=//h2[normalize-space()="カード情報の認証:認証コード"]'
    usageButtonLocator = 'xpath=//button[@title="ご利用状況"]'
    historyLinkLocator = 'xpath=//a[@title="ご利用履歴"]'

    # Verification page
    try:
        page.wait_for_selector(verificationHeadingLocator, timeout=30000)
        if page.is_visible(verificationHeadingLocator):
            input("Please finish verification and proceed, press enter when the dashboard page loads...")
    except patchright.sync_api.TimeoutError:
        pass

    # cookieManager.saveCookiesWithCurrentSession(AMEX_JP_COOKIE_KEY)

    # Dashboard page
    page.click(usageButtonLocator)
    page.click(historyLinkLocator)

    # History page
    viewByYearsButtonLocator = 'xpath=//div[@data-module-name="axp-activity-navigation/Navigation"]//button[@title="年ごとに見る"]'
    page.wait_for_selector(viewByYearsButtonLocator, timeout=10000)
    time.sleep(5)
    page.click(viewByYearsButtonLocator)
    time.sleep(1)
    thisYearOptionLocator = f'xpath=//div[@data-module-name="axp-activity-navigation/Navigation"]//a[@title="{year2026}"]'
    page.click(thisYearOptionLocator)

    downloadIconLocator = 'xpath=//*[@id="action-icon-dls-icon-download-"]'
    page.wait_for_selector(downloadIconLocator, timeout=10000)
    page.click(downloadIconLocator)

    excelOptionLocator = 'xpath=//label[@for="axp-activity-download-body-selection-options-type_excel"]'
    page.click(excelOptionLocator)

    with page.expect_download() as downloadInfo:
        downloadButtonLocator = 'xpath=//button[@title="ダウンロード"]'
        page.click(downloadButtonLocator)
    download = downloadInfo.value
    downloadedFilePath = os.path.join(downloadDirAbsolute, AMEX_DOWNLOAD_FILE_NAME)
    download.save_as(str(downloadedFilePath))

    busyWaitForAnyFile([downloadedFilePath])
    amexJp.updateFilesWithDownloadedXLSX(downloadedFilePath, f"{year2026}")


def run(
    downloadDirAbsolute: str,
    credentialsDirAbsolute: str,
    expectPrestiaDownloadedFilename: str,
):
    # updateEquityTSVWithProsperHTML()

    assert(os.path.exists(downloadDirAbsolute))
    for fileName in os.listdir(downloadDirAbsolute):
        os.remove(os.path.join(downloadDirAbsolute, fileName))

    # usePlaywright(downloadAMEXJP2026XLS)

    # with SeleniumHandle(makeSeleniumBaseBrowser) as (browser, cookieManager):
    # with SeleniumHandle(makeFirefoxBrowser) as (browser, cookieManager):
    with SeleniumHandle(makeUCChromeBrowser) as (browser, cookieManager):
    # with SeleniumHandle(makeStockChromeBrowser) as (browser, cookieManager):
        cookieManager.loadCookies()
        # downloadMobileSuicaAsTSV(browser, cookieManager, merge=True)
        # downloadSMBCCreditCSV(browser, cookieManager, forLastNMonths=10)
        downloadPrestiaLast180Days(
            browser,
            cookieManager,
            downloadDirAbsolute,
            credentialsDirAbsolute,
            expectPrestiaDownloadedFilename,
            merge=True,
        )
        input("Finished. Press enter to close browser.")