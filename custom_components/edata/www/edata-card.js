import {
  LitElement,
  html,
} from "https://cdn.jsdelivr.net/npm/lit-element@4.1.1/+esm";
import "https://cdnjs.cloudflare.com/ajax/libs/apexcharts/5.3.3/apexcharts.min.js?module";
import tinycolor from "https://esm.sh/tinycolor2";
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
const VALID_AGGR_PERIODS = ["year", "month", "week", "day", "hour"];
const DEF_AGGR_PERIOD = "month";
const DEF_RECORDS_FOR_METHOD = {
  year: 3,
  month: 13,
  week: 4,
  day: 60,
  hour: 48,
};
const DEF_ROUND_DECIMALS = 1;
const DEF_ENERGY_UNIT = "kWh";
const DEF_POWER_UNIT = "kW";
const DEF_COST_UNIT = "€";
const LABELS_BY_LOCALE = {
  es: {
    p1: "Punta",
    p2: "Llano",
    p3: "Valle",
    p2_3: "Llano y Valle",
    surplus: "Retorno",
    title: "Título",
    entity: "Entidad",
    chart: "Gráfica",
    aggr: "Agregación (no aplica en resúmenes)",
    records: "Registros (no aplica en resúmenes)",
    total: "Total",
    date: "Fecha",
    cost: "Coste",
  },
  ca: {
    p1: "Punta",
    p2: "Pla",
    p3: "Vall",
    p2_3: "Pla i Vall",
    surplus: "Retorn",
    title: "Títol",
    entity: "Entitat",
    chart: "Gràfica",
    aggr: "Agrupació (no aplica en resums)",
    records: "Registres (no aplica en resums)",
    total: "Total",
    date: "Data",
    cost: "Cost",
  },
  gl: {
    p1: "Punta",
    p2: "Chan",
    p3: "Val",
    p2_3: "Chan e Val",
    surplus: "Retorno",
    title: "Título",
    entity: "Entidade",
    chart: "Gráfica",
    aggr: "Agrupación (non aplica en resumos)",
    records: "Rexistros (non aplica en resumos)",
    total: "Total",
    date: "Data",
    cost: "Custo",
  },
  en: {
    p1: "Peak",
    p2: "Flat",
    p3: "Valley",
    p2_3: "Flat and Valley",
    surplus: "Return",
    title: "Title",
    entity: "Entity",
    chart: "Chart",
    aggr: "Aggregation (not applicable in summaries)",
    records: "Records (not applicable in summaries)",
    total: "Total",
    date: "Date",
    cost: "Cost",
  },
};

let locale = navigator.languages
  ? navigator.languages[0]
  : navigator.language || navigator.userLanguage;

function getLabel(key) {
  if (locale in LABELS_BY_LOCALE) return LABELS_BY_LOCALE[locale][key];
  else return LABELS_BY_LOCALE["en"][key];
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

Apex.colors = ["#e54304", "#ff9e22", "#9ccc65"];

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

  static getStubConfig() {
    return {
      entity: undefined,
      chart: "summary-last-month",
      title: "",
    };
  }

  set hass(hass) {
    this._hass = hass;

    // Override defaults based on dark mode
    let backgroundColor = window.getComputedStyle(document.documentElement).getPropertyValue('--card-background-color');
    const isLightTheme = tinycolor(backgroundColor).getLuminance() > 0.5

    if (hass.themes.darkMode || !isLightTheme) {
      Apex.theme = {
        mode: "dark",
      };
    }

    // Override locale
    locale = hass.locale["language"];
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
    if (!config.entity?.startsWith("sensor.edata")) {
      throw new Error("You need to define a valid entity (sensor.edata_XXXX)");
    }

    // extract scups
    this._scups = config.entity.split("_")[1];

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

    // store original config
    this._config = config;
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

  async getBarChartOptions(endpoint, unit, tariffs) {
    let results;
    if (tariffs?.length > 0) {
      results = await Promise.all(
        tariffs.map((tariff) =>
          this._hass.callWS({
            type: endpoint,
            scups: this._scups,
            aggr: this._aggr,
            tariff: tariff,
            records: this._records,
          })
        )
      );
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

    const series = tariffs?.length
      ? tariffs.map((tariff, index) => ({
          name: getLabel(tariff),
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
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p1",
          }),
        },
        {
          name: getLabel("p2_3"),
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p2",
          }),
        },
      ],
    };
  }

  async getSummaryOptions(preset) {
    const summary = await this._hass.callWS({
      type: "edata/ws/summary",
      scups: this._scups,
    });

    var p1 = undefined;
    var p2 = undefined;
    var p3 = undefined;
    var surplus = undefined;
    var cost = undefined;
    var date = new Date(summary["last_registered_date"]);

    switch (preset) {
      case "last-day":
        p1 = summary["last_registered_day_p1_kWh"];
        p2 = summary["last_registered_day_p2_kWh"];
        p3 = summary["last_registered_day_p3_kWh"];
        surplus = summary["last_registered_day_surplus_kWh"];
        this._bottom_right_value =
          date.getDate() +
          "/" +
          (date.getMonth() + 1) +
          "/" +
          date.getFullYear();
        break;
      case "last-month":
        p1 = summary["last_month_p1_kWh"];
        p2 = summary["last_month_p2_kWh"];
        p3 = summary["last_month_p3_kWh"];
        surplus = summary["last_month_surplus_kWh"];
        cost = summary["last_month_€"];
        date.setDate(0);
        this._bottom_right_value =
          date.getMonth() + 1 + "/" + date.getFullYear();
        break;
      case "month":
        p1 = summary["month_p1_kWh"];
        p2 = summary["month_p2_kWh"];
        p3 = summary["month_p3_kWh"];
        surplus = summary["month_surplus_kWh"];
        cost = summary["month_€"];
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
      this._bottom_left_value = surplus;
      this._bottom_left_unit = DEF_ENERGY_UNIT;
    }

    if (cost) {
      this._top_right_title = getLabel("cost");
      this._top_right_value = cost;
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

    console.log();

    if (!this._loaded && !this._chart) {
      this._loaded = true;
      var chartOptions;

      switch (this._template) {
        case "consumptions":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/consumptions",
            DEF_ENERGY_UNIT,
            ["p1", "p2", "p3"]
          );
          break;
        case "surplus":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/surplus",
            DEF_ENERGY_UNIT
          );
          break;
        case "costs":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/costs",
            DEF_COST_UNIT,
            ["p1", "p2", "p3"]
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

  _valueChanged(ev) {
    if (!this._config || !this.hass) {
      return;
    }
    const _config = Object.assign({}, this._config);
    _config.title = ev.detail.value.title;
    _config.entity = ev.detail.value.entity;
    _config.chart = ev.detail.value.chart;
    _config.aggr = ev.detail.value.aggr;
    _config.records = ev.detail.value.records;

    this._config = _config;

    const event = new CustomEvent("config-changed", {
      detail: { config: _config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  setConfig(config) {
    this._config = config;
  }

  render() {
    if (!this.hass || !this._config) {
      return html``;
    }

    return html`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[
        { name: "title", selector: { text: {} } },
        {
          name: "entity",
          selector: {
            select: {
              options: Object.keys(this.hass.states).filter((entity) =>
                entity.startsWith("sensor.edata_")
              ),
              mode: "dropdown",
            },
          },
        },
        {
          name: "chart",
          selector: {
            select: { options: VALID_CHART_TEMPLATES, mode: "dropdown" },
          },
        },
        {
          name: "aggr",
          selector: {
            select: { options: VALID_AGGR_PERIODS, mode: "dropdown" },
          },
        },
        { name: "records", selector: { number: { min: 1, max: 365 } } },
      ]}
      .computeLabel=${this._computeLabel}
      @value-changed=${this._valueChanged}
    ></ha-form> `;
  }

  _computeLabel(schema) {
    return getLabel(schema.name);
  }
}

customElements.define("edata-card-editor", EdataCardEditor);
