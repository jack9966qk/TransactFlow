// ---------------------------------------------------------------------------
// API types (mirror the shapes returned by analysisServer.py).
// ---------------------------------------------------------------------------

interface EnumOption {
    name: string;
    value: string;
}

interface CategoryMeta {
    label: string;
    parentLabel: string | null;
    depth: number;
    isPseudo: boolean;
    color: string;
}

interface MetaResponse {
    labels: string[];
    labelSetAliases: EnumOption[];
    categories: CategoryMeta[];
    accounts: string[];
    segmentedDisplayOptions: EnumOption[];
    categorizeOptions: EnumOption[];
    deductIncomeOptions: EnumOption[];
    categoryColors: Record<string, string>;
    anyCategoryLabel: string;
    rates: { JPYCNYRate: number; USDJPYRate: number };
}

interface OverviewGroup {
    label: string;
    text: string;
}

interface OverviewResponse {
    groupOverviews: OverviewGroup[];
    netTotalsReport: string;
}

type LabelOptionKind = "label" | "alias" | "range";

interface LabelOptionValue {
    kind: LabelOptionKind;
    value: string;
    fromLabel?: string;
    toLabel?: string;
}

interface FilterPayload {
    labelOption: LabelOptionValue;
    descriptionContains: string | null;
    amountQuantityFrom: number;
    amountQuantityUntil: number;
    filterByRawAmount: boolean;
    recordAccount: string | null;
    categoryFilter: string | null;
    exactMatchCategory: boolean;
    segmentedDisplayOption: string;
}

interface RequestBody {
    filter: FilterPayload;
    categorizeOption: string;
    deductIncomeOption: string;
    includeRemaining: boolean;
    averageByGroup: boolean;
    limit?: number;
}

interface MoneyAmount {
    currency: string;
    quantity: number;
}

interface TransactionItem {
    date: string;
    description: string;
    account: string;
    relatedTo: string | null;
    category: string;
    rawAmount: MoneyAmount;
    adjustedAmount: MoneyAmount;
    adjustedAmountJPY: number | null;
    isForecast: boolean;
    isUnrealized: boolean;
    comment: string | null;
    sourceLocation: { filename: string; line: number } | null;
    rowColorCode: string | null;
}

interface TransactionsResponse {
    transactions: TransactionItem[];
    totalCount: number;
    returnedCount: number;
    truncated: boolean;
    totalRawAmountJPY: number;
    totalAdjustedAmountJPY: number;
}

interface AnnotatedCategoryDict {
    label: string;
    categoryLabel: string;
    isForecast: boolean;
    color: string;
}

interface BarSeries {
    category: AnnotatedCategoryDict;
    values: number[];
}

interface BarChartResponse {
    labels: string[];
    incomeSeries: BarSeries[];
    expenseSeries: BarSeries[];
}

interface PieEntry extends AnnotatedCategoryDict {
    amount: number;
    fraction: number;
}

interface PieChartResponse {
    labels: string[];
    entries: PieEntry[];
    otherEntries: PieEntry[] | null;
    isGroupAverage: boolean;
    total: number;
    longDescription: string;
}

interface ShopItem {
    name: string;
    amount: number;
}

interface ShopDistributionResponse {
    shops: ShopItem[];
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

interface AppState {
    meta: MetaResponse | null;
    barData: BarChartResponse | null;
    selectedBarLabel: string | null;
}

const state: AppState = {
    meta: null,
    barData: null,
    selectedBarLabel: null,
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function byId<T extends HTMLElement = HTMLElement>(id: string): T {
    const node = document.getElementById(id);
    if (node === null) throw new Error(`Missing element #${id}`);
    return node as T;
}

type ElChild = Node | string | null | undefined;

function el(
    tag: string,
    attrs: Record<string, unknown> | null,
    children: ElChild[] | null,
): HTMLElement {
    const node = document.createElement(tag);
    if (attrs !== null) {
        for (const [k, v] of Object.entries(attrs)) {
            if (k === "class") node.className = v as string;
            else if (k === "style") node.setAttribute("style", v as string);
            else if (k.startsWith("on") && typeof v === "function") {
                node.addEventListener(
                    k.slice(2).toLowerCase(),
                    v as EventListener,
                );
            } else if (v !== undefined && v !== null && v !== false) {
                node.setAttribute(k, String(v));
            }
        }
    }
    for (const c of children ?? []) {
        if (c == null) continue;
        node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
}

function populateSelect<T>(
    select: HTMLSelectElement,
    options: T[],
    valueForOption: (o: T) => string,
    labelForOption: (o: T) => string,
): void {
    select.innerHTML = "";
    for (const o of options) {
        const opt = document.createElement("option");
        opt.value = valueForOption(o);
        opt.textContent = labelForOption(o);
        select.appendChild(opt);
    }
}

function setStatus(text: string): void {
    byId("statusBar").textContent = text;
}

function requireMeta(): MetaResponse {
    if (state.meta === null) throw new Error("Meta not loaded");
    return state.meta;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

async function apiGet<T>(path: string): Promise<T> {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`${path}: ${res.status}`);
    return (await res.json()) as T;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${path}: ${res.status}`);
    return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Filter and options
// ---------------------------------------------------------------------------

function readLabelOptionValue(): LabelOptionValue {
    const sel = byId<HTMLSelectElement>("labelOption");
    const opt = sel.options[sel.selectedIndex];
    const kind = (opt.dataset.kind ?? "label") as LabelOptionKind;
    return { kind, value: opt.value };
}

function readCurrentFilter(): FilterPayload {
    const meta = requireMeta();
    const categoryLabel = byId<HTMLSelectElement>("categoryFilter").value;
    const recordAccount = byId<HTMLSelectElement>("recordAccount").value;
    return {
        labelOption: readLabelOptionValue(),
        descriptionContains:
            byId<HTMLInputElement>("descriptionContains").value || null,
        amountQuantityFrom: parseFloat(byId<HTMLInputElement>("amountFrom").value),
        amountQuantityUntil: parseFloat(
            byId<HTMLInputElement>("amountUntil").value,
        ),
        filterByRawAmount: byId<HTMLInputElement>("filterByRawAmount").checked,
        recordAccount: recordAccount === "__any__" ? null : recordAccount,
        categoryFilter:
            categoryLabel === meta.anyCategoryLabel ? null : categoryLabel,
        exactMatchCategory: byId<HTMLInputElement>("exactMatchCategory").checked,
        segmentedDisplayOption: byId<HTMLSelectElement>("segmentedDisplay").value,
    };
}

function readRequestBody(): RequestBody {
    return {
        filter: readCurrentFilter(),
        categorizeOption: byId<HTMLSelectElement>("categorizeOption").value,
        deductIncomeOption: byId<HTMLSelectElement>("deductIncomeOption").value,
        includeRemaining: byId<HTMLInputElement>("includeRemaining").checked,
        averageByGroup: byId<HTMLInputElement>("averageByGroup").checked,
    };
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

function formatAmount(amount: number): string {
    const abs = Math.abs(amount);
    if (abs < 10000) return amount.toFixed(0);
    return `${(amount / 10000).toFixed(2)}万`;
}

function formatAmountInCNY(amount: number): string {
    const rate = state.meta?.rates.JPYCNYRate;
    if (rate === undefined) return "";
    return `CNY ${formatAmount(rate * Math.abs(amount))}`;
}

// ---------------------------------------------------------------------------
// Meta loading
// ---------------------------------------------------------------------------

async function loadMeta(): Promise<void> {
    const meta = await apiGet<MetaResponse>("/api/meta");
    state.meta = meta;

    const labelSel = byId<HTMLSelectElement>("labelOption");
    labelSel.innerHTML = "";
    for (const label of meta.labels) {
        const opt = document.createElement("option");
        opt.value = label;
        opt.textContent = label;
        opt.dataset.kind = "label";
        labelSel.appendChild(opt);
    }
    for (const alias of meta.labelSetAliases) {
        const opt = document.createElement("option");
        opt.value = alias.name;
        opt.textContent = alias.value;
        opt.dataset.kind = "alias";
        labelSel.appendChild(opt);
    }
    for (let i = 0; i < labelSel.options.length; i++) {
        const opt = labelSel.options[i];
        if (opt.dataset.kind === "alias" && opt.value === "MONTHS_2024") {
            opt.selected = true;
            break;
        }
    }

    populateSelect(
        byId<HTMLSelectElement>("categoryFilter"),
        meta.categories,
        (c) => c.label,
        (c) => " ".repeat(c.depth) + c.label,
    );
    byId<HTMLSelectElement>("categoryFilter").value = meta.anyCategoryLabel;

    const accountOptions = ["__any__", ...meta.accounts];
    populateSelect(
        byId<HTMLSelectElement>("recordAccount"),
        accountOptions,
        (a) => a,
        (a) => (a === "__any__" ? "Any account" : a),
    );

    populateSelect(
        byId<HTMLSelectElement>("segmentedDisplay"),
        meta.segmentedDisplayOptions,
        (e) => e.value,
        (e) => e.value,
    );
    populateSelect(
        byId<HTMLSelectElement>("categorizeOption"),
        meta.categorizeOptions,
        (e) => e.value,
        (e) => e.value,
    );
    populateSelect(
        byId<HTMLSelectElement>("deductIncomeOption"),
        meta.deductIncomeOptions,
        (e) => e.value,
        (e) => e.value,
    );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

async function loadOverview(): Promise<void> {
    const data = await apiGet<OverviewResponse>("/api/overview");
    const root = byId("overviewContent");
    root.innerHTML = "";
    for (const item of data.groupOverviews) {
        root.appendChild(el("div", { class: "overview-group" }, [item.text + "\n"]));
    }
    root.appendChild(
        el("div", { class: "overview-group" }, ["\n" + data.netTotalsReport]),
    );
}

// ---------------------------------------------------------------------------
// Transactions table
// ---------------------------------------------------------------------------

function renderTransactionsTable(
    transactions: TransactionItem[],
    colorOn: boolean,
): void {
    const header = el("tr", null, [
        el("th", null, ["Category"]),
        el("th", null, ["Date"]),
        el("th", null, ["Account"]),
        el("th", null, ["Amount"]),
        el("th", null, ["Raw amount"]),
        el("th", null, ["Related to"]),
        el("th", null, ["Description"]),
    ]);
    const rows = transactions.map((t) => {
        const amountStyle =
            colorOn && t.rowColorCode !== null
                ? `background-color: ${t.rowColorCode}`
                : "";
        return el("tr", null, [
            el("td", null, [t.category]),
            el("td", null, [t.date]),
            el("td", null, [t.account]),
            el("td", { class: "amount", style: amountStyle }, [
                t.adjustedAmount.quantity.toFixed(2),
            ]),
            el("td", { class: "amount" }, [t.rawAmount.quantity.toFixed(2)]),
            el("td", null, [t.relatedTo ?? ""]),
            el("td", { class: "desc" }, [t.description]),
        ]);
    });
    const table = el("table", { class: "trans" }, [header, ...rows]);
    const wrap = byId("transactionsTableWrap");
    wrap.innerHTML = "";
    wrap.appendChild(table);
}

async function loadTransactions(): Promise<void> {
    const body: RequestBody = readRequestBody();
    body.limit = 600;
    const data = await apiPost<TransactionsResponse>("/api/transactions", body);
    const stats = byId("transactionStats");
    if (data.totalCount === 0) {
        stats.textContent = "No transactions to display.";
        byId("transactionsTableWrap").innerHTML = "";
        return;
    }
    const parts: string[] = [];
    if (data.truncated) {
        parts.push(
            `${data.totalCount} transactions in total, showing first ${data.returnedCount}`,
        );
    } else {
        parts.push(`${data.totalCount} transactions`);
    }
    parts.push(
        `totalRawAmountJPY=${data.totalRawAmountJPY.toFixed(0)}, ` +
            `totalAdjustedAmountJPY=${data.totalAdjustedAmountJPY.toFixed(0)}`,
    );
    stats.textContent = parts.join("\n");
    renderTransactionsTable(
        data.transactions,
        byId<HTMLInputElement>("colorOn").checked,
    );
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------

interface StackedBarOpts {
    width: number;
    baseOpacity: number;
    forecastOpacity: number;
    stroke: string;
}

// Plotly is loaded from a CDN (<script> tag in index.html). Its global is
// exposed by @types/plotly.js via `export as namespace Plotly`.
//
// The click event payload type isn't exported cleanly from the types package,
// so type what we read out of it locally.
interface PlotlyClickEvent {
    points?: Array<{ x: string | number }>;
}

type PlotlyChartDiv = HTMLElement & {
    on?: (event: string, handler: (evt: PlotlyClickEvent) => void) => void;
    removeAllListeners?: (event: string) => void;
};

function stackedBarTraces(
    series: BarSeries[],
    labels: string[],
    opts: StackedBarOpts,
): Plotly.Data[] {
    const bases: number[] = labels.map(() => 0);
    const traces: Plotly.Data[] = [];
    for (const s of series) {
        const base = bases.slice();
        for (let i = 0; i < labels.length; i++) bases[i] += s.values[i];
        traces.push({
            type: "bar",
            name: s.category.label,
            x: labels,
            y: s.values,
            base,
            width: opts.width,
            marker: {
                color: s.category.color,
                opacity: s.category.isForecast
                    ? opts.forecastOpacity
                    : opts.baseOpacity,
                line: { color: opts.stroke, width: 0.5 },
            },
            hovertemplate:
                `<b>%{fullData.name}</b><br>` +
                `%{x}: %{y:,.0f} JPY<extra></extra>`,
        } as Plotly.Data);
    }
    return traces;
}

async function loadBarChart(): Promise<void> {
    const body = readRequestBody();
    const data = await apiPost<BarChartResponse>("/api/barChartData", body);
    state.barData = data;

    const incomeTraces = stackedBarTraces(data.incomeSeries, data.labels, {
        width: 0.8,
        baseOpacity: 0.5,
        forecastOpacity: 0.1,
        stroke: "gray",
    });
    const expenseTraces = stackedBarTraces(data.expenseSeries, data.labels, {
        width: 0.4,
        baseOpacity: 1.0,
        forecastOpacity: 0.25,
        stroke: "black",
    });
    const traces: Plotly.Data[] = [...incomeTraces, ...expenseTraces];

    const layout: Partial<Plotly.Layout> = {
        barmode: "overlay",
        title: `Bar chart for ${body.filter.labelOption.value} — click a bar to filter the pie`,
        margin: { t: 40, r: 20, b: 80, l: 60 },
        xaxis: { type: "category", tickangle: -30 },
        yaxis: { tickformat: ".2s", title: "JPY" },
        hovermode: "closest",
        legend: { orientation: "h", y: -0.3, font: { size: 10 } },
    };

    const chart = byId<PlotlyChartDiv>("barChart");
    await Plotly.react(chart, traces, layout, {
        displaylogo: false,
        responsive: true,
    });
    chart.removeAllListeners?.("plotly_click");
    chart.on?.("plotly_click", (evt: PlotlyClickEvent) => {
        const point = evt.points?.[0];
        if (point === undefined) return;
        state.selectedBarLabel = String(point.x);
        void loadPieChart();
    });
}

function blendWithWhite(hex: string, alpha: number): string {
    const h = hex.replace("#", "");
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    const br = Math.round(r * alpha + 255 * (1 - alpha));
    const bg = Math.round(g * alpha + 255 * (1 - alpha));
    const bb = Math.round(b * alpha + 255 * (1 - alpha));
    return `rgb(${br}, ${bg}, ${bb})`;
}

async function loadPieChart(): Promise<void> {
    const chart = byId("pieChart");
    const desc = byId("pieDescription");

    const body = readRequestBody();
    if (state.selectedBarLabel !== null) {
        body.filter = {
            ...body.filter,
            labelOption: { kind: "label", value: state.selectedBarLabel },
        };
    }
    const data = await apiPost<PieChartResponse | null>(
        "/api/pieChartData",
        body,
    );

    Plotly.purge(chart);
    if (data === null) {
        chart.innerHTML = "<p style='padding:16px'>No data to plot.</p>";
        desc.textContent = "";
        return;
    }

    chart.innerHTML = "";
    const sliceLabels = data.entries.map((e) => {
        const amt = Math.abs(e.amount);
        return `${e.label} — ${formatAmount(amt)} (${formatAmountInCNY(amt)})`;
    });
    const values = data.entries.map((e) => Math.abs(e.amount));
    // `hoverinfo: "label+percent+value"` and `uniformtext` are valid Plotly
    // options but the bundled types are stricter than the runtime schema, so
    // assemble via `unknown` to pass without losing the rest of the typing.
    const trace = {
        type: "pie",
        labels: sliceLabels,
        values,
        sort: false,
        textinfo: "label+percent",
        textposition: "outside",
        hoverinfo: "label+percent+value",
        marker: {
            colors: data.entries.map((e) =>
                e.isForecast ? blendWithWhite(e.color, 0.5) : e.color,
            ),
            line: { color: "#fff", width: 1 },
        },
    } as unknown as Plotly.Data;
    const total = data.total;
    const titlePrefix = data.isGroupAverage ? "Avg. expenses" : "Expenses";
    const scope =
        state.selectedBarLabel ?? body.filter.labelOption.value ?? "selection";
    const layout = {
        title: `${titlePrefix} for ${scope} (total: ${formatAmount(total)})`,
        margin: { t: 50, r: 180, b: 40, l: 180 },
        showlegend: false,
        uniformtext: { minsize: 9, mode: "hide" },
    } as unknown as Partial<Plotly.Layout>;
    await Plotly.newPlot(chart, [trace], layout, {
        displaylogo: false,
        responsive: true,
    });
    desc.textContent = data.longDescription;
}

// ---------------------------------------------------------------------------
// Shop distribution
// ---------------------------------------------------------------------------

async function loadShopDistribution(): Promise<void> {
    const body = readRequestBody();
    const data = await apiPost<ShopDistributionResponse>(
        "/api/shopDistribution",
        body,
    );
    const root = byId("shopList");
    root.innerHTML = "";
    for (const s of data.shops) {
        root.appendChild(
            el("div", { class: "shop-row" }, [
                el("span", null, [s.name]),
                el("span", { class: "amt" }, [
                    `${formatAmount(s.amount)} (${formatAmountInCNY(s.amount)})`,
                ]),
            ]),
        );
    }
    if (data.shops.length === 0) {
        root.textContent = "No shop data for current filter.";
    }
}

// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------

function activeTabName(): string {
    const active = document.querySelector<HTMLElement>(".tab.active");
    return active?.dataset.tab ?? "overview";
}

async function refreshActiveTab(): Promise<void> {
    const name = activeTabName();
    try {
        setStatus("Loading…");
        if (name === "overview") await loadOverview();
        else if (name === "charts") {
            state.selectedBarLabel = null;
            await loadBarChart();
            await loadPieChart();
        } else if (name === "transactions") await loadTransactions();
        else if (name === "shops") await loadShopDistribution();
        setStatus("Ready");
    } catch (err) {
        console.error(err);
        const msg = err instanceof Error ? err.message : String(err);
        setStatus(`Error: ${msg}`);
    }
}

function setupTabs(): void {
    const tabs = document.querySelectorAll<HTMLElement>(".tab");
    const panels = document.querySelectorAll<HTMLElement>(".tab-panel");
    tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            tabs.forEach((t) => t.classList.remove("active"));
            panels.forEach((p) => p.classList.remove("active"));
            tab.classList.add("active");
            const tabName = tab.dataset.tab;
            if (tabName !== undefined) byId(`tab-${tabName}`).classList.add("active");
            void refreshActiveTab();
        });
    });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function debounce<Args extends unknown[]>(
    fn: (...args: Args) => void,
    wait: number,
): (...args: Args) => void {
    let timer: ReturnType<typeof setTimeout> | null = null;
    return (...args: Args) => {
        if (timer !== null) clearTimeout(timer);
        timer = setTimeout(() => {
            timer = null;
            fn(...args);
        }, wait);
    };
}

function setupAutoApply(): void {
    const debouncedRefresh = debounce(() => void refreshActiveTab(), 300);
    const filterIds = [
        "labelOption", "descriptionContains", "amountFrom", "amountUntil",
        "filterByRawAmount", "recordAccount", "categoryFilter",
        "exactMatchCategory", "segmentedDisplay", "categorizeOption",
        "deductIncomeOption", "includeRemaining", "averageByGroup",
    ];
    for (const id of filterIds) {
        const node = document.getElementById(id);
        if (node === null) continue;
        const tag = node.tagName;
        const type = (node as HTMLInputElement).type;
        if (tag === "SELECT" || type === "checkbox") {
            node.addEventListener("change", () => void refreshActiveTab());
        } else {
            node.addEventListener("input", debouncedRefresh);
        }
    }
}

async function init(): Promise<void> {
    try {
        setStatus("Loading metadata…");
        await loadMeta();
        setupTabs();
        setupAutoApply();
        byId("colorOn").addEventListener("change", () => {
            if (activeTabName() === "transactions") void loadTransactions();
        });
        await refreshActiveTab();
    } catch (err) {
        console.error(err);
        const msg = err instanceof Error ? err.message : String(err);
        setStatus(`Error during init: ${msg}`);
    }
}

document.addEventListener("DOMContentLoaded", () => void init());
