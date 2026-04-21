from dataclasses import dataclass
from typing import Optional, Tuple

from ..base import Date


@dataclass(frozen=True)
class PayslipAnnotationItem:
    sourceLocation: Optional[Tuple[str, int]]
    date: Date
    type: str
    gross: float
    healthInsurance: float
    welfare: float
    unemplIns: float
    pensionVoluntary: float
    nationalTax: float
    localTax: float
    yearEndAdj: float
    """e.g. meal allowance, non cash spot bonus deduction."""
    miscDeduction: float
    housingBenefitTaxable: float
    housingBenefitNonTaxable: float
    reimbursement: float
    payable: float

    def __post_init__(self):
        # Verify that each annotation line has "gross - deduction items = payable".
        # Not checking `self.reimbursement` since it is already part of "gross".
        calculatedPayable = (self.gross -
                             self.yearEndAdj -
                             self.healthInsurance -
                             self.welfare -
                             self.unemplIns -
                             self.pensionVoluntary -
                             self.nationalTax -
                             self.localTax -
                             self.miscDeduction -
                             self.housingBenefitTaxable)
        assert(calculatedPayable == self.payable)
