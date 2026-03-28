from dataclasses import dataclass, field
import logging
from tabnanny import check
from typing import Tuple
from taxCalculation.nationalTaxCalculation import NationalTaxCalculator
from taxCalculation.nationalTaxCalculation import DependentsConfig
import math

# During last check, the document says:
# 令和4年1月1日現在、渋谷区内に住所がある人に対して、
# 令和3年の1月から12月までの1年間の所得を基礎に税額を算出します。
SUPPORTED_YEARS = [2019, 2020, 2021]
UNSURE_YEARS = [2022, 2023, 2024, 2025]

@dataclass
class LocalTaxCalculator:
    forYear: int
    totalCompensation: float
    capitalGain: float = 0
    socialSecurity: float = 0
    medicalFee: float = 0
    lifeInsurance: float = 0
    earthquakeInsurace: float = 0
    dependentsConfig: DependentsConfig = field(default_factory=DependentsConfig)
    furusato: float = 0

    def __post_init__(self):
        # NOTE: WHEN ADDING A NEW YEAR, CHECK THE REFERENCES FOR ANY POTENTIAL CHANGE
        if self.forYear in SUPPORTED_YEARS: return
        if self.forYear in UNSURE_YEARS:
            logging.warning(f"Local Tax calculation for year {self.forYear} may be inaccurate")
            return
        assert(False)

    def 所得控除額(self, taxableIncome: float) -> float:
        # Can only see the PDF for 2021 now, but there doesn't seem to be change in 2021 and 2020.
        # Skip 雑損控除
        医療費控除 = min(max(self.medicalFee - min(10_0000, taxableIncome * 0.05), 0), 200_0000)
        # Skip セルフメディケーション税制
        社会保険料控除 = self.socialSecurity
        # Skip【旧制度適用契約】1一般生命保険料 2個人年金保険料
        def 生命保険料控除():
            if self.lifeInsurance < 1_2000: return self.lifeInsurance
            elif self.lifeInsurance <= 3_2000: return self.lifeInsurance / 2 + 6000
            elif self.lifeInsurance <= 5_6000: return self.lifeInsurance / 4 + 1_4000
            else: return 2_8000
        def 地震保険控除():
            # Skip 【旧長期損害保険料】
            if self.earthquakeInsurace <= 5000: return self.earthquakeInsurace
            elif self.earthquakeInsurace <= 1_5000: return self.earthquakeInsurace / 2 + 2500
            else: return 1_0000
        # Skip 配偶者控除
        # Skip 配偶者特別控除
        扶養控除 = (
            33_0000 * self.dependentsConfig.numGeneralDependents +
            45_0000 * self.dependentsConfig.numSpecificDependents +
            45_0000 * self.dependentsConfig.numElderlyDependentLivingTogether +
            38_0000 * self.dependentsConfig.numElderlyDependentOthers
        )
        # Skip 障害者控除
        # Skip 同居特別障害者控除
        # Skip 寡婦控除
        # Skip ひとり親控除
        # Skip 勤労学生控除
        def 基礎控除():
            if taxableIncome <= 2400_0000: return 43_0000
            elif taxableIncome <= 2450_0000: return 29_0000
            elif taxableIncome <= 2500_0000: return 15_0000
            else: return 0
        return 医療費控除 + 社会保険料控除 + 生命保険料控除() + 地震保険控除() + 扶養控除 + 基礎控除()

    def 税額控除額(self, 総所得金額等: float):
        """
        Amount to be deducted from Shibuya Local Tax
        """
        def 調整控除():
            def 人的控除額の差の合計額():
                def 基礎控除():
                    if 総所得金額等 <= 2400_0000: return 5_0000
                    elif 総所得金額等 <= 2450_0000: return 3_0000
                    else: return 1_0000
                # Skip 配偶者控除, 配偶者特別控除, 扶養控除 (TODO: Add this)
                # Skip ひとり親, 障害者・寡婦・勤労学生, 特別障害者, 同居特障害者(特別障害者に加算)
                return 基礎控除()
            if 総所得金額等 < 200_0000:
                return min(総所得金額等, 人的控除額の差の合計額()) * 0.05
            else:
                return max((人的控除額の差の合計額() - (総所得金額等 - 200_0000)) * 0.05, 2500)
        # Skip 配当控除
        def 寄附金税額控除():
            # Skip anything other than 都道府県・市区町村(指定団体)
            基本分 = max(min(self.furusato, 総所得金額等 * 0.3) - 2000, 0) * 0.10
            # The multiplier for local tax seems to be following the same logic
            # as national tax. 所得税の税率 is not clearly defined, but on certain
            # sites, it is linked to the national tax page, for example:
            # https://www.city.meguro.tokyo.jp/kurashi/zeikin/kojin/kifu/furusatonouzei.html
            # NOTE: maybe an edge case is missing, as mentioned in the Shibuya PDF file:
            # "所得税で適用されている所得税率と異なる場合があります"
            multiplier, _ = NationalTaxCalculator(
                forYear=self.forYear,
                totalCompensation=self.totalCompensation,
                capitalGain=self.capitalGain,
                withholding=0,
                socialSecurity=self.socialSecurity,
                medicalFee=self.medicalFee,
                lifeInsurance=self.lifeInsurance,
                earthquakeInsurace=self.earthquakeInsurace,
                dependentsConfig=self.dependentsConfig,
                furusato=self.furusato).所得税率
            特例分 = min(max(self.furusato - 2000, 0) * (0.9 - multiplier * 1.021),
                        総所得金額等 * 0.2)
            return 基本分 + 特例分
        # Skip 住宅借入金等特別税額控除 (TODO: Add this)
        # Skip 配当割額または株式等譲渡所得割額の控除 (TODO: Add this)
        return 調整控除() + 寄附金税額控除()

    @property
    def shibuyaLocalTax(self) -> float:
        """
        Local tax for Shibuya. The result should be similar/same to other regions.
        Reference: PDF File linked from
        https://www.city.shibuya.tokyo.jp/kurashi/zeikin/juminzei/juminzei_fuka.html
        Note: the reference page only has PDF for the current year. PDF for the previous years is
        no longer accessible.
        """
        def for総合課税ish():
            # (1) 収入金額
            収入金額 = self.totalCompensation
            # Skip (2) 必要経費
            # Skip (3) 専従者控除
            # (4) 給与所得控除
            logging.debug(f"住民税-収入金額: {収入金額}")
            def 給与所得控除後の金額():
                def 計算収入額(): return math.floor(収入金額 / 4000) * 4000.0
                # TODO remove self.forYear == 2021, information for 2021 isn't available yet.
                if self.forYear >= 2020:
                    if self.forYear in UNSURE_YEARS:
                        logging.warning(f"Unsure about 計算収入額 for {UNSURE_YEARS} income.")

                    if 収入金額 <= 55_0999: return 0
                    if 収入金額 <= 161_8999: return 収入金額 - 55_0000
                    if 収入金額 <= 161_9999: return 106_9000
                    if 収入金額 <= 162_1999: return 107_0000
                    if 収入金額 <= 162_3999: return 107_2000
                    if 収入金額 <= 162_7999: return 107_4000
                    if 収入金額 <= 179_9999: return 計算収入額() * 0.6 + 10_0000
                    if 収入金額 <= 359_9999: return 計算収入額() * 0.7 - 8_0000
                    if 収入金額 <= 659_9999: return 計算収入額() * 0.8 - 44_0000
                    if 収入金額 <= 849_9999: return 収入金額 * 0.9 - 110_0000
                    else: return 収入金額 - 195_0000
                elif self.forYear == 2019:
                    # Derived from 2020 PDF and the changes made in 2021:
                    # (changes made in 2021 => applied to tax for 2020 income,
                    #  before the changes => applied to tax for 2019 income)
                    # https://www.city.shibuya.tokyo.jp/kurashi/zeikin/juminzei/zeisei_kaisei03.html
                    if 収入金額 <= 65_0999: return 0
                    if 収入金額 <= 161_8999: return 収入金額 - 65_0000
                    if 収入金額 <= 161_9999: return 96_9000
                    if 収入金額 <= 162_1999: return 97_0000
                    if 収入金額 <= 162_3999: return 97_2000
                    if 収入金額 <= 162_7999: return 97_4000
                    if 収入金額 <= 179_9999: return 計算収入額() * 0.6
                    if 収入金額 <= 359_9999: return 計算収入額() * 0.7 - 18_0000
                    if 収入金額 <= 659_9999: return 計算収入額() * 0.8 - 54_0000
                    if 収入金額 <= 1000_0000: return 収入金額 * 0.9 - 120_0000
                    else: return 収入金額 - 220_0000
                assert(False)
            総所得金額 = 給与所得控除後の金額()
            logging.debug(f"住民税-総所得金額: {総所得金額}")
            # Skip 所得金額調整控除
            # Skip (5) 公的年金等所得金額
            # (6) 所得控除額
            所得控除合計 = self.所得控除額(総所得金額)
            logging.debug(f"住民税-所得控除合計: {所得控除合計}")
            課税標準額 = math.floor((総所得金額 - 所得控除合計) / 1000) * 1000.0
            logging.debug(f"住民税-課税標準額（所得）: {課税標準額}")
            # (7) 所得割税率
            区民税所得割 = 課税標準額 * 0.06
            都民税所得割 = 課税標準額 * 0.04
            logging.debug(f"住民税-区民税所得割: {区民税所得割}")
            logging.debug(f"住民税-都民税所得割: {都民税所得割}")
            # Skip 分離課税の税率 (calculated as `for分離課税ish`)
            # (8) 税額控除
            税額控除 = self.税額控除額(総所得金額等=総所得金額 + self.capitalGain)
            logging.debug(f"住民税-税額控除: {税額控除}")
            # (9) 均等割額
            均等割額 = 3500 + 1500
            return math.floor(
                (max(区民税所得割 + 都民税所得割 - 税額控除, 0) + 均等割額) / 100
            ) * 100.0
        def for分離課税ish():
            # This part is copied from national tax calculator.
            上場株式等の譲渡 = self.capitalGain
            # Have not yet found documentation, but it seems to drop the digits
            # below 1000, just like the other parts.
            上場株式等の譲渡_対応分 = math.floor(上場株式等の譲渡 / 1000) * 1000.0
            logging.debug(f"住民税-上場株式等の譲渡_対応分: {上場株式等の譲渡_対応分}")
            # > (7) 所得割税率 -> 分離課税の税率
            return 上場株式等の譲渡_対応分 * 0.05
        finalAmount = for総合課税ish() + for分離課税ish()
        assert(finalAmount >= 0)
        return finalAmount

    @property
    def shinagawaLocalTax(self) -> float:
        """
        Local tax for Shinagawa. For now, this gives the same result as Shibuya.
        Reference: https://www.city.shinagawa.tokyo.jp/PC/procedure/procedure-zeikin/procedure-zeikin-zeigaku/kuminzeiR3-/index.html
        """
        # TODO: check whether calculation for Shibuya is applicable for Shinagawa.
        return self.shibuyaLocalTax