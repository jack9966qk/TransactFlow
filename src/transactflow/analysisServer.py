from flask import Flask, Response, request
import json
from .serialization import ConvertObject, categoryForLabel, CategoryKeysToLabels
from .userConfig import UserConfig

app = Flask(__name__)

def initProvider(config: UserConfig):
    global provider
    from .processes.runAll import run
    trans = run(config)
    from .analysis import AnalysisProvider
    assert config.stock is not None
    provider = AnalysisProvider(trans, config)

from .analysis import AnalysisProviderOptions, DeductIncomeOption, SegmentedDisplayOption

def JSONResponse(obj):
    return Response(json.dumps(obj, default=ConvertObject),
                    mimetype="application/json")

def providerOptionsFromRequest(request):
    providerOptionsDict = request.get_json()["options"]
    if "categoryFilter" in providerOptionsDict:
        category = categoryForLabel(providerOptionsDict["categoryFilter"])
        providerOptionsDict["categoryFilter"] = category
    if "segmentedDisplayOption" in providerOptionsDict:
        option = SegmentedDisplayOption(providerOptionsDict["segmentedDisplayOption"])
        providerOptionsDict["segmentedDisplayOption"] = option
    options = AnalysisProviderOptions(**providerOptionsDict)
    return options


# def JSONItemsFromDict(d, key="key", value="value"):
#     return [{key: k, value: v} for k, v in d.items()]

@app.route("/allTransactions")
def allTransactions():
    return JSONResponse(provider.labelsToGroups["All"])

@app.route("/categories")
def categories():
    return JSONResponse(provider.categories)

@app.route("/labelOptions")
def labelOptions():
    return JSONResponse({
        "individualGroups": provider.labels,
        "all": provider.labelsWithExtra
    })

@app.route("/transactions", methods=["POST"])
def transactions():
    options = providerOptionsFromRequest(request)
    matched = provider.transactionsMatching(options)
    return JSONResponse(matched)

@app.route("/barChartData", methods=["POST"])
def barChartData():
    options = providerOptionsFromRequest(request)
    deductSalaryOption = DeductIncomeOption(request.get_json()["deductSalaryOption"])
    data = provider.barChartData(options, deductSalaryOption)
    dictData = data.__dict__
    dictData["incomeTotalsByCat"] = [ CategoryKeysToLabels(d) for d in data.incomeTotalsByCat ]
    dictData["expenseTotalsByCat"] = [ CategoryKeysToLabels(d) for d in data.expenseTotalsByCat ]
    return JSONResponse(dictData)

@app.route("/pieChartData", methods=["POST"])
def pieChartData():
    options = providerOptionsFromRequest(request)
    deductSalaryOption = DeductIncomeOption(request.get_json()["deductSalaryOption"])
    includeRemaining = request.get_json()["includeRemaining"]
    if includeRemaining is None: includeRemaining = False
    pieChartData = provider.pieChartData(options, deductSalaryOption, includeRemaining)
    catLabelToAmount = { c.label: am for c, am in pieChartData.categoryToAmount.items() }
    responseJSONData = {"categoryToAmount": catLabelToAmount}
    return JSONResponse(responseJSONData)