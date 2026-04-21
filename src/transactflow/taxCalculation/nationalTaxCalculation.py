import logging
import math
from dataclasses import dataclass, field

# During last check, NTA webpages say: "[令和4年4月1日現在法令等]"
SUPPORTED_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

@dataclass
class DependentsConfig:
    numGeneralDependents: int = 0
    numSpecificDependents: int = 0
    numElderlyDependentLivingTogether: int = 0
    numElderlyDependentOthers: int = 0

@dataclass
class NationalTaxCalculator:
    forYear: int
    totalCompensation: float
    withholding: float
    capitalGain: float = 0
    socialSecurity: float = 0
    medicalFee: float = 0
    lifeInsurance: float = 0
    earthquakeInsurace: float = 0
    dependentsConfig: DependentsConfig = field(default_factory=DependentsConfig)
    furusato: float = 0
    prepayment: float = 0

    def __post_init__(self):
        # NOTE: WHEN ADDING A NEW YEAR, CHECK THE REFERENCES FOR ANY POTENTIAL CHANGE
        if self.forYear in SUPPORTED_YEARS: return
        assert(False)

    @property
    def 所得税率(self) -> tuple[float, float]:
        """
        Tax rate in the format of (multipler, adjustment).
        For example: (0.10, -9_7500) means 課税される所得金額 * 10% - 97500.
        Reference: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm
                    > 所得税の税率 > (平成27年分以降)
        """
        assert(self.forYear > 2015)
        amount = self.課税される所得金額
        if amount <= 194_9000: return (0.05, 0)
        if amount <= 329_9000: return (0.10, -9_7500)
        if amount <= 694_9000: return (0.20, -42_7500)
        if amount <= 899_9000: return (0.23, -63_6000)
        if amount <= 1799_9000: return (0.33, -153_6000)
        if amount <= 3999_9000: return (0.40, -279_6000)
        return (0.45, -479_6000)

    def 給与所得の金額(self, 収入金額: float) -> float:
        """
        Amount of taxable employment income. Note that 所得控除 (not 給与所得控除) is not applied here.
        収入金額: total employment income pre-tax
        Reference: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1400.htm
        """
        # Apply (2) 給与所得控除 according to
        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm
        # (3) 給与所得者の特定支出控除 is skipped because it does not apply to me.
        if self.forYear == 2019:
            # 平成29年(2018)分～令和元年(2019)分
            # Using easy calculation of the section "2 給与所得の金額の計算", only for income > 660万円.
            assert(収入金額 > 660_0000)
            if 収入金額 < 100_0000: return 収入金額 * 0.90 - 120_0000
            return 収入金額 - 220_0000
        elif self.forYear >= 2020:
            if self.forYear > 2025:
                logging.warning(f"Unsure about 給与所得控除 for {self.forYear} income.")
            # 令和2年(2020)分以降
            # Using easy calculation of the section "2 給与所得の金額の計算", only for income > 660万円.
            assert(収入金額 > 660_0000)
            if 収入金額 < 850_0000: return 収入金額 * 0.90 - 110_0000
            return 収入金額 - 195_0000
        assert(False)

    def 所得控除(self, 対象となる所得: float) -> float:
        """
        Amount of deduction to be applied to the total of 給与所得の金額.
        Reference: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1100.htm
        """
        # Skip 雑損控除.

        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1120.htm > 医療費控除の対象となる金額
        # Skip "(1) 保険金などで補てんされる金額" for now, this seems different to health insurance applied
        # before payment,
        医療費控除 = max(0.0, self.medicalFee - 10_0000)
        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1130.htm > 社会保険料控除の金額

        社会保険料控除 = self.socialSecurity
        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1140.htm > 生命保険料控除額の金額

        # Skip 小規模企業共済等掛金控除.

        def 生命保険料控除():
            # (1) 新契約（平成24年1月1日以後に締結した保険契約等）に基づく場合の控除額
            # Skip (2) 旧契約（平成23年12月31日以前に締結した保険契約等）に基づく場合の控除額
            if self.lifeInsurance < 2_0000: return self.lifeInsurance
            elif self.lifeInsurance < 4_0000: return self.lifeInsurance / 2 + 1_0000
            elif self.lifeInsurance < 8_0000: return self.lifeInsurance / 4 + 2_0000
            else: return 4_0000

        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1145.htm > 地震保険料控除の金額
        def 地震保険料控除():
            # (1)地震保険料
            # Skip (2)旧長期損害保険料
            if self.earthquakeInsurace < 5_0000: return self.earthquakeInsurace
            else: return 50000

        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/yogo/senmon.htm#word1 > 総所得金額等
        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/yogo/senmon.htm#word2 > 合計所得金額
        # They are similar to each other, except for 繰越控除, which is not yet supported here.
        # Although not part of 対象となる所得, capital gain is included in both.
        総所得金額等 = 対象となる所得 + self.capitalGain
        合計所得金額 = 総所得金額等

        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1150.htm > 寄附金控除の金額
        寄附金控除 = max(min(self.furusato, 総所得金額等 * 0.40) - 2000, 0)

        # Skip 障害者控除、寡婦控除、ひとり親控除、勤労学生控除、配偶者控除、配偶者特別控除.

        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1180.htm
        扶養控除 = (
            38_0000 * self.dependentsConfig.numGeneralDependents +
            63_0000 * self.dependentsConfig.numSpecificDependents +
            58_0000 * self.dependentsConfig.numElderlyDependentLivingTogether +
            48_0000 * self.dependentsConfig.numElderlyDependentOthers
        )

        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1199.htm > 基礎控除
        def 基礎控除():
            # https://www.nta.go.jp/taxes/shiraberu/taxanswer/yogo/senmon.htm#word2 > 合計所得金額
            # Although not part of 対象となる所得, capital gain is included in 合計所得金額.
            if 合計所得金額 < 2400_0000: return 48_0000
            elif 合計所得金額 < 2450_0000: return 32_0000
            elif 合計所得金額 < 2500_0000: return 16_0000
            else: return 0

        return (
            社会保険料控除 + 医療費控除 + 生命保険料控除() + 地震保険料控除() +
            寄附金控除 + 扶養控除 + 基礎控除()
        )

    @property
    def 課税される所得金額(self) -> float:
        収入金額 = self.totalCompensation
        # Also called "対象となる所得".
        総合課税の合計額 = self.給与所得の金額(収入金額)
        所得控除 = self.所得控除(総合課税の合計額)
        logging.debug(f"国税-総合課税の合計額（対象となる所得）: {総合課税の合計額}")
        logging.debug(f"国税-所得控除: {所得控除}")
        # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm
        # > 課税される所得金額(千円未満の端数金額を切り捨てた後の金額です。)
        return math.floor((総合課税の合計額 - 所得控除) / 1000) * 1000.0

    @property
    def 課税される所得金額に対する税額(self):
        """
        Total amount of national tax before applying tax deductions (after, not before applying tax
        rate).
        Reference: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2220.htm
        """
        def for総合課税():
            logging.debug(f"国税-課税される所得金額: {self.課税される所得金額}")
            multiplier, adjustment = self.所得税率
            return self.課税される所得金額 * multiplier + adjustment
        def for分離課税():
            上場株式等の譲渡 = self.capitalGain
            # Have not yet found documentation, but it seems to drop the digits
            # below 1000, just like the other parts.
            上場株式等の譲渡_対応分 = math.floor(上場株式等の譲渡 / 1000) * 1000.0
            logging.debug(f"国税-上場株式等の譲渡_対応分: {上場株式等の譲渡_対応分}")
            # https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1463.htm
            # > 20％（所得税15％、住民税5％）
            return 上場株式等の譲渡_対応分 * 0.15
        return for総合課税() + for分離課税()

    @property
    def nationalTaxToPay(self) -> float:
        """
        Actual amount of payment to make after Kakutei Shinkoku, including income tax not yet paid
        through withholding, and special tax, to be paid for `forYear` in `forYear + 1`
        """
        # The following calculation is done according to 確定申告書.
        # TODO: Find proper reference.
        # Skipping some deductions.
        差引所得税額 = self.課税される所得金額に対する税額
        logging.debug(f"国税-差引所得税額: {差引所得税額}")
        再差引所得税額 = 差引所得税額
        logging.debug(f"国税-再差引所得税額: {再差引所得税額}")
        # https://www.nta.go.jp/taxes/tetsuzuki/shinsei/annai/gensen/fukko/pdf/02.pdf
        # > [Q5] 源泉徴収すべき復興特別所得税の額はどのように算出するのですか。
        # > 1円未満の端数があるときは、その端数金額を切り捨てます。
        復興特別所得税額 = math.floor(再差引所得税額 * 0.021) * 1.0
        logging.debug(f"国税-復興特別所得税額: {復興特別所得税額}")
        logging.debug(f"国税-所得税及び復興特別所得税の額: {再差引所得税額 + 復興特別所得税額}")
        源泉徴収税額 = self.withholding
        予定納税額 = self.prepayment
        # Unofficial: https://biz-owner.net/tax/kirisute > 納税確定額から100円未満切り捨て
        totalToPay = math.floor((再差引所得税額 + 復興特別所得税額 - 源泉徴収税額) / 100) * 100.0
        remainingToPay = totalToPay - 予定納税額
        assert(remainingToPay > 0)
        return remainingToPay

