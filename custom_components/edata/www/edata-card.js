import { LitElement, css, html } from "./vendor/lit-core-3.3.3.min.js";
import "https://cdnjs.cloudflare.com/ajax/libs/apexcharts/5.3.3/apexcharts.min.js?module";
// Set program constants and definitions
const PROG_NAME = "edata-card";
const VALID_CHART_TEMPLATES = [
  "consumptions",
  "surplus",
  "maximeter",
  "costs",
  "summary-last-day",
  "summary-last-month",
  "summary-month",
];
const DEF_CHART_TEMPLATE = "";
const VALID_AGGR_PERIODS = ["month", "day", "hour"];
const DEF_AGGR_PERIOD = "month";
const DEF_RECORDS_FOR_METHOD = {
  month: 13,
  day: 60,
  hour: 48,
};
const DEF_ROUND_DECIMALS = 1;
const DEF_ENERGY_UNIT = "kWh";
const DEF_POWER_UNIT = "kW";
const DEF_COST_UNIT = "€";
// charts drawn from aggregated records; summaries and the maximeter ignore
// `aggr` and `records`
const BAR_CHART_TEMPLATES = ["consumptions", "surplus", "costs"];
const DEF_COLORS = ["#e54304", "#ff9e22", "#9ccc65"];
const LABELS_BY_LOCALE = {
  es: {
    p1: "Punta",
    p2: "Llano",
    p3: "Valle",
    p2_3: "Llano y Valle",
    surplus: "Retorno",
    title: "Título",
    entity: "Suministro",
    chart: "Gráfica",
    aggr: "Agregación",
    records: "Registros",
    total: "Total",
    date: "Fecha",
    cost: "Coste",
    energy: "Energía",
    power: "Potencia",
    others: "Otros",
    records_helper: "Por defecto: {n}",
    colors: "Colores",
    colors_helper: "Código hexadecimal, p. ej. #e54304. Vacío para el color por defecto.",
    no_supplies: "No se ha encontrado ningún suministro de edata.",
    consumptions: "Consumo",
    surplus_chart: "Excedentes",
    maximeter: "Maxímetro",
    costs: "Costes",
    "summary-last-day": "Resumen del último día",
    "summary-month": "Resumen del mes en curso",
    "summary-last-month": "Resumen del mes pasado",
    month: "Mensual",
    day: "Diaria",
    hour: "Horaria",
  },
  ca: {
    p1: "Punta",
    p2: "Pla",
    p3: "Vall",
    p2_3: "Pla i Vall",
    surplus: "Retorn",
    title: "Títol",
    entity: "Subministrament",
    chart: "Gràfica",
    aggr: "Agrupació",
    records: "Registres",
    total: "Total",
    date: "Data",
    cost: "Cost",
    energy: "Energia",
    power: "Potència",
    others: "Altres",
    records_helper: "Per defecte: {n}",
    colors: "Colors",
    colors_helper: "Codi hexadecimal, p. ex. #e54304. Buit per al color per defecte.",
    no_supplies: "No s'ha trobat cap subministrament d'edata.",
    consumptions: "Consum",
    surplus_chart: "Excedents",
    maximeter: "Maxímetre",
    costs: "Costos",
    "summary-last-day": "Resum de l'últim dia",
    "summary-month": "Resum del mes en curs",
    "summary-last-month": "Resum del mes passat",
    month: "Mensual",
    day: "Diària",
    hour: "Horària",
  },
  gl: {
    p1: "Punta",
    p2: "Chan",
    p3: "Val",
    p2_3: "Chan e Val",
    surplus: "Retorno",
    title: "Título",
    entity: "Subministración",
    chart: "Gráfica",
    aggr: "Agrupación",
    records: "Rexistros",
    total: "Total",
    date: "Data",
    cost: "Custo",
    energy: "Enerxía",
    power: "Potencia",
    others: "Outros",
    records_helper: "Por defecto: {n}",
    colors: "Cores",
    colors_helper: "Código hexadecimal, p. ex. #e54304. Baleiro para a cor por defecto.",
    no_supplies: "Non se atopou ningunha subministración de edata.",
    consumptions: "Consumo",
    surplus_chart: "Excedentes",
    maximeter: "Maxímetro",
    costs: "Custos",
    "summary-last-day": "Resumo do último día",
    "summary-month": "Resumo do mes en curso",
    "summary-last-month": "Resumo do mes pasado",
    month: "Mensual",
    day: "Diaria",
    hour: "Horaria",
  },
  en: {
    p1: "Peak",
    p2: "Flat",
    p3: "Valley",
    p2_3: "Flat and Valley",
    surplus: "Return",
    title: "Title",
    entity: "Supply",
    chart: "Chart",
    aggr: "Aggregation",
    records: "Records",
    total: "Total",
    date: "Date",
    cost: "Cost",
    energy: "Energy",
    power: "Power",
    others: "Others",
    records_helper: "Default: {n}",
    colors: "Colors",
    colors_helper: "Hex code, e.g. #e54304. Leave empty for the default color.",
    no_supplies: "No edata supply was found.",
    consumptions: "Consumption",
    surplus_chart: "Surplus",
    maximeter: "Maximeter",
    costs: "Costs",
    "summary-last-day": "Last day summary",
    "summary-month": "Current month summary",
    "summary-last-month": "Last month summary",
    month: "Monthly",
    day: "Daily",
    hour: "Hourly",
  },
};

let locale = navigator.languages
  ? navigator.languages[0]
  : navigator.language || navigator.userLanguage;

// the user's language in Home Assistant, which may come with a region (es-ES)
function setLocale(hass) {
  if (hass?.locale?.language) locale = hass.locale.language;
}

function getLabel(key) {
  const lang = locale?.split("-")[0];
  if (lang in LABELS_BY_LOCALE) return LABELS_BY_LOCALE[lang][key];
  else return LABELS_BY_LOCALE["en"][key];
}

// The supply (scups) an edata entity belongs to: the name its device was
// created with. Entity IDs used to be sensor.edata_<scups>, but newer Home
// Assistant versions prefix them with the device name (sensor.<scups>_edata_
// <scups>) and users can rename them, so the ID is only a fallback.
function getScups(hass, entityId) {
  const entry = hass?.entities?.[entityId];
  const device = entry?.platform === "edata" && hass.devices?.[entry.device_id];
  if (device?.name) return device.name.toLowerCase();
  return entityId?.match(/^sensor\.edata_([^_]+)/)?.[1];
}

// One entity per edata supply to choose from in the editor, labeled with the
// supply's device name: its main sensor (the one without a translated name)
// if it is there, any other sensor of the supply otherwise.
function getSupplyOptions(hass) {
  const options = new Map();
  for (const entry of Object.values(hass?.entities ?? {})) {
    if (
      entry.platform !== "edata" ||
      !entry.entity_id.startsWith("sensor.") ||
      !(entry.entity_id in hass.states)
    )
      continue;
    const scups = getScups(hass, entry.entity_id);
    if (!scups || (options.has(scups) && entry.translation_key)) continue;
    const device = hass.devices?.[entry.device_id];
    options.set(scups, {
      value: entry.entity_id,
      label: device?.name_by_user || device?.name || scups.toUpperCase(),
    });
  }
  // without the entity registry (it should always be there), any sensor
  // still named the old way
  if (!options.size) {
    for (const entityId of Object.keys(hass?.states ?? {})) {
      const scups = entityId.match(/^sensor\.edata_([^_]+)$/)?.[1];
      if (scups) options.set(scups, { value: entityId, label: scups.toUpperCase() });
    }
  }
  return [...options.values()];
}

// Set apexcharts defaults:
Apex.xaxis = {
  type: "datetime",
  labels: {
    datetimeUTC: false,
  },
};

Apex.chart = {
  toolbar: {
    show: false,
  },
  zoom: {
    enabled: false,
  },
  animations: {
    enabled: false,
  },
  background: "transparent",
};

Apex.yaxis = {
  labels: {
    formatter: (value) => {
      return value.toFixed(DEF_ROUND_DECIMALS);
    },
  },
};

Apex.dataLabels = {
  enabled: false,
};

Apex.tooltip = {
  enabled: true,
  intersect: false,
  shared: true,
  onDataHover: {
    highlightDataSeries: false,
  },
};

Apex.colors = DEF_COLORS;

// what each color is used for in a chart, in `colors` order
function getSeriesLabels(chart) {
  if (chart == "costs") return ["energy", "power", "others"].map(getLabel);
  if (chart == "maximeter") return ["p1", "p2_3"].map(getLabel);
  return ["p1", "p2", "p3"].map(getLabel);
}

// WCAG relative luminance (0..1) of any CSS color; unparseable colors count as
// black. The canvas normalizes the color to #rrggbb or rgba().
function getLuminance(color) {
  const ctx = document.createElement("canvas").getContext("2d");
  ctx.fillStyle = "#000";
  ctx.fillStyle = color.trim();
  const value = ctx.fillStyle;
  const rgb = value.startsWith("#")
    ? [1, 3, 5].map((i) => parseInt(value.slice(i, i + 2), 16))
    : value.match(/[\d.]+/g).slice(0, 3).map(Number);
  const [r, g, b] = rgb.map((c) => {
    c /= 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Any CSS color as #rrggbb, as a color input needs it; `fallback` for colors
// the canvas cannot make opaque (unparseable or transparent).
function toHexColor(color, fallback) {
  const ctx = document.createElement("canvas").getContext("2d");
  ctx.fillStyle = fallback;
  ctx.fillStyle = (color ?? "").trim();
  return ctx.fillStyle.startsWith("#") ? ctx.fillStyle : fallback;
}

// EdataCard class
class EdataCard extends LitElement {
  constructor() {
    super();
    this._loaded = false;
  }

  static get properties() {
    return {
      hass: {},
      config: {},
      _top_left_title: "",
      _top_left_value: "",
      _top_left_unit: "",
      _bottom_left_title: "",
      _bottom_left_value: "",
      _bottom_left_unit: "",
      _top_right_title: "",
      _top_right_value: "",
      _top_right_unit: "",
      _bottom_right_title: "",
      _bottom_right_value: "",
      _bottom_right_unit: "",
    };
  }

  static getConfigElement() {
    // Create and return an editor element
    return document.createElement("edata-card-editor");
  }

  static getStubConfig(hass) {
    return {
      entity: getSupplyOptions(hass)[0]?.value,
      chart: "summary-last-month",
      title: "",
    };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // the chart waits for hass when the config came first
    if (first) this.requestUpdate();

    // Override defaults based on dark mode
    let backgroundColor = window.getComputedStyle(document.documentElement).getPropertyValue('--card-background-color');
    const isLightTheme = getLuminance(backgroundColor) > 0.5

    if (hass.themes.darkMode || !isLightTheme) {
      Apex.theme = {
        mode: "dark",
      };
    }

    // Override locale
    setLocale(hass);
  }

  render() {
    return html`
      <ha-card>
        <div
          style="color: var(--secondary-text-color); font-size: 16px; font-weight: 500; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; padding-left: 15px; padding-top: 15px; "
        >
          ${this._title}
        </div>

        <div
          style="position: relative; width: 100%; height: 100%; margin: 0 auto;"
        >
          <div
            id="left"
            style="position: absolute; width: 40%; height: 90%; top: 0; left: 10px; display: flex; align-items: top; justify-content: left; padding-top: 10px"
          >
            <div
              id="top-left-box"
              style="padding-left: 10px; padding-top: 10px"
            >
              <span style="font-size: 20px; font-weight: bold;"
                >${this._top_left_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._top_left_unit}</span
              >
              <br /><span
                style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._top_left_title}</span
              >
            </div>
            <div
              id="bottom-left-box"
              style="position:absolute; padding-left: 10px; bottom: 10px;"
            >
              <span style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._bottom_left_title}</span
              >
              <br /><span style="font-size: 20px; font-weight: bold;"
                >${this._bottom_left_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._bottom_left_unit}</span
              >
            </div>
          </div>

          <div
            id="right"
            style="position: absolute; width: 40%; height: 90%; top: 0; right: 10px; display: flex; align-items: top; justify-content: right; padding-top: 10px"
          >
            <div
              id="top-right-box"
              style="padding-right: 10px; padding-top: 10px; text-align: right"
            >
              <span style="font-size: 20px; font-weight: bold;"
                >${this._top_right_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._top_right_unit}</span
              >
              <br /><span
                style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._top_right_title}</span
              >
            </div>
            <div
              id="bottom-right-box"
              style="position:absolute; padding-right: 10px; bottom: 10px; text-align: right;"
            >
              <span style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._bottom_right_title}</span
              >
              <br /><span style="font-size: 20px; font-weight: bold;"
                >${this._bottom_right_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._bottom_right_unit}</span
              >
            </div>
          </div>

          <div
            style="position: relative; width: 100%; height: 100%; margin: 0 auto"
          >
            <div
              id="chart"
              style="display: flex; justify-content: center; align-items: center;"
            ></div>
          </div>
        </div>
      </ha-card>
    `;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an edata entity (sensor.edata_XXXX)");
    }

    // config validation
    this._entity = config.entity;
    this._template = VALID_CHART_TEMPLATES.includes(config.chart)
      ? config.chart
      : DEF_CHART_TEMPLATE;
    this._aggr = VALID_AGGR_PERIODS.includes(config.aggr)
      ? config.aggr
      : DEF_AGGR_PERIOD;
    this._records = Number.isInteger(config.records)
      ? config.records
      : DEF_RECORDS_FOR_METHOD[this._aggr];
    this._title = config.title;

    this._colors = config.colors || Apex.colors;

    // the card editor sets every change on the same card: fetch the data
    // again only when it depends on the change
    const sameData = ["entity", "chart", "aggr", "records"].every(
      (key) => this._config?.[key] === config[key]
    );

    // store original config
    this._config = config;

    if (!sameData) {
      this._query = {};
      this.resetChart();
    } else if (this._chart) {
      this._chart.updateOptions({ colors: this._colors });
    }
  }

  resetChart() {
    this._chart?.destroy();
    this._chart = undefined;
    this._loaded = false;
    this._top_left_title = this._top_left_value = this._top_left_unit = "";
    this._bottom_left_title = this._bottom_left_value = this._bottom_left_unit = "";
    this._top_right_title = this._top_right_value = this._top_right_unit = "";
    this._bottom_right_title = this._bottom_right_value = this._bottom_right_unit = "";
    this.requestUpdate();
  }

  connectedCallback() {
    super.connectedCallback();
    if (!this._loaded) {
      this.renderChart();
    }
  }

  updated(changedProps) {
    super.updated(changedProps);
    if (!this._loaded) {
      this.renderChart();
    }
  }

  // splits: values of the `splitBy` websocket parameter (tariffs 1-3, or bill
  // terms), drawn as stacked series that add up to the total; all of them come
  // in one call through its plural form (`tariffs`, `terms`)
  async getBarChartOptions(endpoint, unit, splits, splitBy = "tariff") {
    let results;
    if (splits?.length > 0) {
      results = await this._hass.callWS({
        type: endpoint,
        scups: this._scups,
        aggr: this._aggr,
        [splitBy + "s"]: splits,
        records: this._records,
      });
    } else {
      results = [
        await this._hass.callWS({
          type: endpoint,
          scups: this._scups,
          aggr: this._aggr,
          records: this._records,
        }),
      ];
    }

    const series = splits?.length
      ? splits.map((split, index) => ({
        name: getLabel(splitBy == "tariff" ? "p" + split : split),
        data: this.normalizeX(...results)[index],
      }))
      : [
        {
          name: getLabel("total"),
          data: results[0],
        },
      ];

    var config = {
      chart: {
        stacked: true,
        id: "chart",
        type: "bar",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: unit,
        },
      },
      series: series,
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          },
        },
      };
    }

    return config;
  }

  async getMaximeterChartOptions() {
    const [p1, p2_3] = await Promise.all(
      [1, 2].map((tariff) =>
        this._hass.callWS({
          type: "edata/ws/maximeter",
          scups: this._scups,
          tariff: tariff,
        })
      )
    );
    return {
      chart: {
        id: "chart",
        type: "scatter",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: DEF_POWER_UNIT,
        },
      },
      series: [
        {
          name: getLabel("p1"),
          data: p1,
        },
        {
          name: getLabel("p2_3"),
          data: p2_3,
        },
      ],
    };
  }

  async getSummaryOptions(preset) {
    const query = this._query;
    const summary = await this._hass.callWS({
      type: "edata/ws/summary",
      scups: this._scups,
    });
    // the values below would land on the card of a newer config
    if (query !== this._query) return;

    var p1 = undefined;
    var p2 = undefined;
    var p3 = undefined;
    var surplus = undefined;
    var cost = undefined;
    var date = new Date(summary["last_datetime"]);

    switch (preset) {
      case "last-day":
        p1 = summary["last_day_consumption_by_tariff"][0];
        p2 = summary["last_day_consumption_by_tariff"][1];
        p3 = summary["last_day_consumption_by_tariff"][2];
        surplus = summary["last_day_surplus_kwh"];
        this._bottom_right_value =
          date.getDate() +
          "/" +
          (date.getMonth() + 1) +
          "/" +
          date.getFullYear();
        break;
      case "last-month":
        p1 = summary["last_month_consumption_by_tariff"][0];
        p2 = summary["last_month_consumption_by_tariff"][1];
        p3 = summary["last_month_consumption_by_tariff"][2];
        surplus = summary["last_month_surplus_kwh"];
        cost = summary["last_month_bill_value_eur"];
        date.setDate(0);
        this._bottom_right_value =
          date.getMonth() + 1 + "/" + date.getFullYear();
        break;
      case "month":
        p1 = summary["month_consumption_by_tariff"][0];
        p2 = summary["month_consumption_by_tariff"][1];
        p3 = summary["month_consumption_by_tariff"][2];
        surplus = summary["month_surplus_kwh"];
        cost = summary["month_bill_value_eur"];
        this._bottom_right_value =
          date.getMonth() + 1 + "/" + date.getFullYear();
        break;
    }

    this._top_left_value = Math.round((p1 + p2 + p3) * 100) / 100;
    this._top_left_unit = DEF_ENERGY_UNIT;
    this._top_left_title = getLabel("total");
    this._bottom_right_unit = "";
    this._bottom_right_title = getLabel("date");

    if (surplus) {
      this._bottom_left_title = getLabel("surplus");
      this._bottom_left_value = Math.round(surplus * 100) / 100;
      this._bottom_left_unit = DEF_ENERGY_UNIT;
    }

    if (cost) {
      this._top_right_title = getLabel("cost");
      this._top_right_value = Math.round(cost * 100) / 100;
      this._top_right_unit = DEF_COST_UNIT;
    }

    var config = {
      chart: {
        id: "chart",
        type: "pie",
        width: 300,
      },
      colors: this._colors,
      series: [p1, p2, p3],
      labels: [getLabel("p1"), getLabel("p2"), getLabel("p3")],
      legend: {
        position: "bottom",
      },
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          },
        },
      };
    }

    return config;
  }

  normalizeX(list1, list2, list3) {
    const allX = new Set();

    list1.forEach(([x, _]) => allX.add(x));
    list2.forEach(([x, _]) => allX.add(x));
    list3.forEach(([x, _]) => allX.add(x));

    const sortedX = Array.from(allX).sort((a, b) => a - b);

    const mergeList = (list) => {
      const map = new Map(list);
      return sortedX.map((x) => [x, map.get(x) || 0]);
    };

    const newList1 = mergeList(list1);
    const newList2 = mergeList(list2);
    const newList3 = mergeList(list3);

    return [newList1, newList2, newList3];
  }

  async renderChart() {
    await this.updateComplete;

    if (!this._loaded && !this._chart && this._hass && this._config) {
      this._loaded = true;
      this._scups = getScups(this._hass, this._entity);
      // a config asking for other data (from the card editor) may replace
      // this one meanwhile
      const query = this._query;
      var chartOptions;

      switch (this._template) {
        case "consumptions":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/consumptions",
            DEF_ENERGY_UNIT,
            [1, 2, 3]
          );
          break;
        case "surplus":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/surplus",
            DEF_ENERGY_UNIT,
            [1, 2, 3]
          );
          break;
        case "costs":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/costs",
            DEF_COST_UNIT,
            ["energy", "power", "others"],
            "term"
          );
          break;
        case "maximeter":
          chartOptions = await this.getMaximeterChartOptions();
          break;
        case "summary-last-day":
          chartOptions = await this.getSummaryOptions("last-day");
          break;
        case "summary-month":
          chartOptions = await this.getSummaryOptions("month");
          break;
        case "summary-last-month":
          chartOptions = await this.getSummaryOptions("last-month");
          break;
      }

      if (query !== this._query) return;
      this.render();
      this._chart = new ApexCharts(
        this.shadowRoot.querySelector("#chart"),
        chartOptions
      );
      this._chart.render();
    }
  }

  getCardSize() {
    return 3;
  }
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "edata-card",
  name: "edata",
  preview: true,
  description: "Visualize edata's data!",
  documentationURL: "https://github.com/uvejota/homeassistant-edata",
});

customElements.define("edata-card", EdataCard);

class EdataCardEditor extends LitElement {
  static get properties() {
    return {
      hass: {},
      _config: {},
    };
  }

  static get styles() {
    return css`
      .colors {
        margin-top: 16px;
      }
      .colors summary {
        cursor: pointer;
        padding: 8px 0;
        font-weight: 500;
      }
      .color-row {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .color-row ha-form {
        flex: 1;
      }
      .color-row input[type="color"] {
        width: 40px;
        height: 40px;
        padding: 0;
        border: none;
        background: none;
        cursor: pointer;
      }
      .helper,
      .warning {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin-top: 4px;
      }
      .warning {
        color: var(--warning-color);
        margin: 0 0 8px;
      }
    `;
  }

  setConfig(config) {
    this._config = config;
  }

  // the values the form shows: aggregation shows its default when unset
  get _formData() {
    return {
      title: this._config.title,
      entity: this._config.entity,
      chart: this._config.chart,
      aggr: this._config.aggr ?? DEF_AGGR_PERIOD,
      records: this._config.records,
    };
  }

  _schema(supplies) {
    const isBarChart = BAR_CHART_TEMPLATES.includes(this._config.chart);
    const options = (values) =>
      values.map((value) => ({
        value,
        label: getLabel(value == "surplus" ? "surplus_chart" : value),
      }));
    return [
      { name: "title", selector: { text: {} } },
      {
        name: "entity",
        required: true,
        selector: { select: { options: supplies, mode: "dropdown" } },
      },
      {
        name: "chart",
        required: true,
        selector: {
          select: { options: options(VALID_CHART_TEMPLATES), mode: "dropdown" },
        },
      },
      // summaries and the maximeter do not use them
      ...(isBarChart
        ? [
          {
            name: "aggr",
            required: true,
            selector: {
              select: { options: options(VALID_AGGR_PERIODS), mode: "dropdown" },
            },
          },
          {
            name: "records",
            selector: { number: { min: 1, max: 365, mode: "box" } },
          },
        ]
        : []),
    ];
  }

  // Only the fields the user changed go into the config, and emptied ones
  // are removed from it, so untouched defaults are not written to the YAML.
  _valueChanged(ev) {
    if (!this._config || !this.hass) {
      return;
    }
    const before = this._formData;
    const _config = Object.assign({}, this._config);
    for (const [key, value] of Object.entries(ev.detail.value)) {
      if (value === before[key]) continue;
      if (value === undefined || value === null || value === "") delete _config[key];
      else _config[key] = value;
    }
    this._setConfig(_config);
  }

  // `colors` gets a color for every series, the default where none was given
  // (the chart would repeat the given ones otherwise); it is removed when only
  // defaults are left
  _colorChanged(index, value) {
    const colors = Array.isArray(this._config.colors) ? [...this._config.colors] : [];
    colors[index] = value?.trim();
    colors.length = Math.max(colors.length, DEF_COLORS.length);
    for (let i = 0; i < colors.length; i++) colors[i] ||= DEF_COLORS[i];
    if (colors.length == DEF_COLORS.length && colors.every((c, i) => c == DEF_COLORS[i])) {
      colors.length = 0;
    }

    const _config = Object.assign({}, this._config);
    if (colors.length) _config.colors = colors;
    else delete _config.colors;
    this._setConfig(_config);
  }

  _setConfig(config) {
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      })
    );
  }

  render() {
    if (!this.hass || !this._config) {
      return html``;
    }
    setLocale(this.hass);

    const supplies = getSupplyOptions(this.hass);
    // keep showing an entity this list does not have (written by hand)
    if (this._config.entity && !supplies.some((x) => x.value == this._config.entity)) {
      supplies.push({ value: this._config.entity, label: this._config.entity });
    }

    return html`
      ${supplies.length
        ? ""
        : html`<div class="warning">${getLabel("no_supplies")}</div>`}
      <ha-form
        .hass=${this.hass}
        .data=${this._formData}
        .schema=${this._schema(supplies)}
        .computeLabel=${(schema) => getLabel(schema.name)}
        .computeHelper=${(schema) =>
          schema.name == "records"
            ? getLabel("records_helper").replace(
              "{n}",
              DEF_RECORDS_FOR_METHOD[this._config.aggr ?? DEF_AGGR_PERIOD]
            )
            : undefined}
        @value-changed=${this._valueChanged}
      ></ha-form>
      ${this._renderColors()}
    `;
  }

  _renderColors() {
    const colors = Array.isArray(this._config.colors) ? this._config.colors : [];
    return html`
      <details class="colors" ?open=${colors.length > 0}>
        <summary>${getLabel("colors")}</summary>
        ${getSeriesLabels(this._config.chart).map(
          (label, i) => html`
            <div class="color-row">
              <input
                type="color"
                aria-label=${label}
                .value=${toHexColor(colors[i], DEF_COLORS[i])}
                @input=${(ev) => this._colorChanged(i, ev.target.value)}
              />
              <ha-form
                .hass=${this.hass}
                .data=${{ color: colors[i] ?? "" }}
                .schema=${[{ name: "color", selector: { text: {} } }]}
                .computeLabel=${() => label}
                @value-changed=${(ev) => {
                  ev.stopPropagation();
                  this._colorChanged(i, ev.detail.value.color);
                }}
              ></ha-form>
            </div>
          `
        )}
        <div class="helper">${getLabel("colors_helper")}</div>
      </details>
    `;
  }
}

customElements.define("edata-card-editor", EdataCardEditor);
