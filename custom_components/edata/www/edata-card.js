import {
  LitElement,
  html,
} from "https://unpkg.com/lit-element@2.0.1/lit-element.js?module";
import "https://cdnjs.cloudflare.com/ajax/libs/apexcharts/3.45.1/apexcharts.min.js?module";

// Set program constants and definitions
const PROG_NAME = "edata-card";
const VALID_CHART_TEMPLATES = ["consumptions", "surplus", "maximeter", "costs"];
const DEF_CHART_TEMPLATE = "consumptions";
const VALID_AGGR_PERIODS = ["month", "day", "hour"];
const DEF_AGGR_PERIOD = "month";
const DEF_RECORDS_FOR_METHOD = {
  month: 12,
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
  },
};

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

Apex.colors = ["#FF5733", "#FFC300", "#09AF00"];

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
    };
  }

  static getStubConfig() {
    return {
      entity: "sensor.edata_XXXX",
      chart: "consumption",
      aggr: "monthly",
      records: 12,
      title: "Gráfico de ejemplo",
    };
  }

  set hass(hass) {
    this._hass = hass;
  }

  render() {
    return html`
      <ha-card header="${this._title}">
        <div id="header"></div>
        <div id="chart"></div>
        <div id="footer"></div>
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
    this._title = config.title || PROG_NAME;

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

  async getConsumptionChartOptions() {
    return {
      chart: {
        stacked: true,
        id: "chart",
        type: "bar",
      },
      yaxis: {
        title: {
          text: DEF_ENERGY_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["p1"],
          data: await this._hass.callWS({
            type: "edata/ws/consumptions",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p1",
            records: this._records,
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p2"],
          data: await this._hass.callWS({
            type: "edata/ws/consumptions",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p2",
            records: this._records,
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p3"],
          data: await this._hass.callWS({
            type: "edata/ws/consumptions",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p3",
            records: this._records,
          }),
        },
      ],
    };
  }

  async getSurplusChartOptions() {
    return {
      chart: {
        stacked: true,
        type: "bar",
      },
      yaxis: {
        title: {
          text: DEF_ENERGY_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["p1"],
          data: await this._hass.callWS({
            type: "edata/ws/surplus",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p1",
            records: this._records,
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p2"],
          data: await this._hass.callWS({
            type: "edata/ws/surplus",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p2",
            records: this._records,
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p3"],
          data: await this._hass.callWS({
            type: "edata/ws/surplus",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p3",
            records: this._records,
          }),
        },
      ],
    };
  }

  async getCostsChartOptions() {
    return {
      chart: {
        stacked: true,
        type: "bar",
      },
      yaxis: {
        title: {
          text: DEF_COST_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["p1"],
          data: await this._hass.callWS({
            type: "edata/ws/costs",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p1",
            records: this._records,
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p2"],
          data: await this._hass.callWS({
            type: "edata/ws/costs",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p2",
            records: this._records,
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p3"],
          data: await this._hass.callWS({
            type: "edata/ws/costs",
            scups: this._scups,
            aggr: this._aggr,
            tariff: "p3",
            records: this._records,
          }),
        },
      ],
    };
  }

  async getMaximeterChartOptions() {
    return {
      chart: {
        id: "chart",
        type: "scatter",
      },
      yaxis: {
        title: {
          text: DEF_POWER_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["p1"],
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p1",
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p2_3"],
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p2",
          }),
        },
      ],
    };
  }

  async renderChart() {
    await this.updateComplete;

    if (!this._loaded && !this._chart) {
      this._loaded = true;
      var chartOptions;

      switch (this._template) {
        case "consumptions":
          chartOptions = await this.getConsumptionChartOptions();
          break;
        case "surplus":
          chartOptions = await this.getSurplusChartOptions();
          break;
        case "costs":
          chartOptions = await this.getCostsChartOptions();
          break;
        case "maximeter":
          chartOptions = await this.getMaximeterChartOptions();
          break;
      }

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

class EdataCardEditor extends LitElement {
  setConfig(config) {
    this._config = config;
  }

  configChanged(newConfig) {
    const event = new Event("config-changed", {
      bubbles: true,
      composed: true,
    });
    event.detail = { config: newConfig };
    this.dispatchEvent(event);
  }
}

customElements.define("Edata-card-editor", EdataCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "edata-card",
  name: "Edata Card (beta)",
  preview: true,
  description: "Visualize edata's data!",
  documentationURL: "https://github.com/uvejota/homeassistant-edata",
});

customElements.define("edata-card", EdataCard);
